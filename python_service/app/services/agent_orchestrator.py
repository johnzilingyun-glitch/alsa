import os
import logging
import json
import asyncio
import time
from typing import Optional, Any
from datetime import datetime

from .llm_gateway import llm_gateway, current_token_usage
from .expert_tools import (
    parse_tool_calls,
    has_tool_calls,
    tool_executor,
    get_openai_tools,
    COMPUTATION_TOOL_NAMES,
)
from .token_guard import token_guard

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """AgentOrchestrator handles tool execution loop, reasoning accumulation,
    quality-gate checks, and recovery synthesis.
    
    This decouples agent orchestrator logic from LLMGateway client setup.
    """

    async def generate_with_tools(
        self,
        prompt: str,
        model: str = "gemini-3.1-pro-preview",
        role: str = None,
        temperature: float = 0.3,
        max_tool_rounds: int = 30,
        on_chunk: Optional[callable] = None,
        gemini_api_key: Optional[str] = None,
        deepseek_api_key: Optional[str] = None,
        cache_key: Optional[str] = None,
        prompt_version_id: Optional[str] = None,
        response_schema: Optional[Any] = None,
    ) -> str:
        """Generate content with tool-calling loop.
        
        For DeepSeek: uses native OpenAI-compatible function calling API.
        For other models: uses text-based <tool_call> parsing.
        """
        # For DeepSeek, use native OpenAI-compatible function calling
        if "deepseek" in model.lower():
            return await self.generate_with_native_tools(
                prompt,
                model,
                role=role,
                temperature=temperature,
                max_tool_rounds=max_tool_rounds,
                on_chunk=on_chunk,
                deepseek_api_key=deepseek_api_key,
                cache_key=cache_key,
                prompt_version_id=prompt_version_id,
                response_schema=response_schema,
            )

        current_prompt = prompt
        all_content_parts = []

        for round_num in range(max_tool_rounds + 1):
            # Guard against prompt size explosion
            prompt_chars = len(current_prompt)
            prompt_tokens_est = len(str(current_prompt).encode("utf-8")) // 3
            logger.info(f"  [ToolLoop] Prompt size: ~{prompt_tokens_est} tokens ({prompt_chars} chars)")
            if prompt_tokens_est > 60000:
                logger.warning(
                    "  [ToolLoop] WARNING: Prompt exceeds 60k tokens, truncating search enrichment..."
                )
                # Truncate the enrichment section if present
                enrichment_start = current_prompt.find("[SEARCH ENRICHMENT]")
                enrichment_end = current_prompt.find("[MANDATORY] GROUND TRUTH")
                if enrichment_start > 0 and enrichment_end > enrichment_start:
                    current_prompt = (
                        current_prompt[:enrichment_start]
                        + "[SEARCH ENRICHMENT - truncated due to prompt size]\n"
                        + current_prompt[enrichment_end:]
                    )

            # Generate
            result = await llm_gateway.generate_content(
                current_prompt,
                model=model,
                temperature=temperature,
                on_chunk=on_chunk,
                gemini_api_key=gemini_api_key,
                deepseek_api_key=deepseek_api_key,
                prompt_version_id=prompt_version_id,
            )

            if not result:
                break

            # Check for tool calls
            if not has_tool_calls(result):
                # No tool calls — final response
                all_content_parts.append(result)
                break

            # Parse tool calls
            tool_calls = parse_tool_calls(result)
            if not tool_calls:
                # Has <tool_call> tag but couldn't parse — treat as final
                all_content_parts.append(result)
                break

            logger.info(f"  [ToolLoop] Round {round_num + 1}: {len(tool_calls)} tool call(s)")

            # Reset TokenGuard round budget for this batch
            token_guard.reset_round()

            # Extract text before first tool call (the LLM's reasoning so far)
            first_call_pos = result.find("<tool_call>")
            if first_call_pos > 0:
                reasoning_before = result[:first_call_pos].strip()
                if reasoning_before:
                    all_content_parts.append(reasoning_before)

            if on_chunk:
                tool_names = [tc.get("tool", "unknown") for tc in tool_calls]
                on_chunk(0, message=f"{role or 'Agent'} (工具调用第 {round_num + 1} 轮: {', '.join(tool_names)})")

            # Execute tools
            observations = await tool_executor.execute_all(tool_calls)

            # Heartbeat: keep frontend idle timer alive after tool execution
            if on_chunk:
                on_chunk((round_num + 1) * (len(tool_calls) + 100), message=f"{role or 'Agent'} (第 {round_num + 1} 轮工具调用完成，正在思考...)")

            # Build continuation prompt (TokenGuard already enforces per-tool limits)
            tool_section = "\n\n--- TOOL RESULTS ---\n"
            for tc, obs in zip(tool_calls, observations):
                label = tc.get("symbol", tc.get("query", ""))
                tool_section += f"\n[Tool: {tc['tool']} | Query: {label}]\n"
                tool_section += obs + "\n"
            tool_section += "\n--- END TOOL RESULTS ---\n"
            tool_section += "\nContinue your analysis using the tool results above. Do NOT repeat previous analysis. Build on it with the new data.\n"

            current_prompt = (
                current_prompt
                + "\n\n--- ASSISTANT PARTIAL RESPONSE ---\n"
                + result
                + "\n"
                + tool_section
            )

            if round_num == max_tool_rounds:
                # Last round — force completion without tools
                current_prompt += "\nIMPORTANT: This is your final response round. Do NOT make any more tool calls. Complete your analysis now.\n"

        return (
            "\n".join(all_content_parts)
            if all_content_parts
            else result or ""
        )

    async def generate_with_native_tools(
        self,
        prompt: str,
        model: str,
        role: str = None,
        temperature: float = 0.3,
        max_tool_rounds: int = 30,
        on_chunk: Optional[callable] = None,
        deepseek_api_key: Optional[str] = None,
        cache_key: Optional[str] = None,
        prompt_version_id: Optional[str] = None,
        response_schema: Optional[Any] = None,
    ) -> str:

        start_time = time.perf_counter()

        # Get token usage diff
        usage_ctx = current_token_usage.get()
        created_ctx = False
        if usage_ctx is None:
            usage_ctx = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
            token = current_token_usage.set(usage_ctx)
            created_ctx = True

        start_prompt = usage_ctx.get("promptTokens", 0)
        start_cand = usage_ctx.get("candidatesTokens", 0)

        result_text = None
        try:
            result_text = await self._generate_with_native_tools_inner(
                prompt,
                model,
                role,
                temperature,
                max_tool_rounds,
                on_chunk,
                deepseek_api_key,
                cache_key,
                response_schema=response_schema,
            )
            return result_text
        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            if prompt_version_id:
                try:
                    # Determine provider
                    provider = "deepseek" if "deepseek" in model.lower() else "default"

                    prompt_tokens = usage_ctx.get("promptTokens", 0) - start_prompt
                    cand_tokens = usage_ctx.get("candidatesTokens", 0) - start_cand

                    if prompt_tokens == 0:
                        prompt_tokens = len(str(prompt).encode("utf-8")) // 3
                    if cand_tokens == 0 and result_text:
                        cand_tokens = len(str(result_text).encode("utf-8")) // 3

                    # Schema validation
                    schema_passed = True
                    if result_text and (
                        "json" in prompt.lower()
                        or (model and "json" in model.lower())
                    ):
                        try:
                            import re

                            json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
                            if json_match:
                                json.loads(json_match.group(0))
                            else:
                                schema_passed = False
                        except Exception:
                            logger.exception("Failed to validate JSON schema in agent response")
                            schema_passed = False
                    elif not result_text:
                        schema_passed = False

                    from ..prompting.runtime import prompt_runtime

                    prompt_runtime.record_run(
                        {
                            "prompt_version_id": prompt_version_id,
                            "model": model,
                            "provider": provider,
                            "input_tokens": prompt_tokens,
                            "output_tokens": cand_tokens,
                            "latency_ms": latency_ms,
                            "tool_calls": 0,
                            "schema_validation_passed": schema_passed,
                        }
                    )
                except Exception as ex:
                    logger.error(f"Error recording prompt run metrics: {ex}")
            if created_ctx:
                current_token_usage.reset(token)

    async def _generate_with_native_tools_inner(
        self,
        prompt: str,
        model: str,
        role: str = None,
        temperature: float = 0.3,
        max_tool_rounds: int = 30,
        on_chunk: Optional[callable] = None,
        deepseek_api_key: Optional[str] = None,
        cache_key: Optional[str] = None,
        response_schema: Optional[Any] = None,
    ) -> str:
        """Generate content using DeepSeek's native OpenAI-compatible function calling API."""
        if cache_key:
            today = datetime.now().strftime("%Y-%m-%d")
            safe_key = "".join(c if c.isalnum() else "_" for c in cache_key)
            cache_file = os.path.join(
                os.path.expanduser("~/.alsa_cache/llm"),
                f"{safe_key}_native_{today}.json",
            )
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r") as f:
                        cached_data = json.load(f)
                    logger.info(
                        f"✅ Native Cache HIT for {cache_key}! Skipping all tools."
                    )
                    if on_chunk:
                        on_chunk(len(cached_data["content"]))
                    return cached_data["content"]
                except Exception as e:
                    logger.info(f"Failed to read native cache {cache_file}: {e}")

        model_map = {
            "deepseek-chat": "deepseek-v4-pro",
            "deepseek-reasoner": "deepseek-v4-pro",
        }
        final_model = model_map.get(model, model)

        tools = get_openai_tools(role=role)
        messages = [
            {"role": "system", "content": "You are a professional financial analyst expert."},
            {"role": "user", "content": prompt},
        ]

        # Guard against prompt size explosion
        prompt_chars = len(prompt)
        prompt_tokens_est = len(str(prompt).encode("utf-8")) // 3
        if prompt_tokens_est > 60000:
            logger.warning(
                "  [ToolLoop] WARNING: Prompt exceeds 60k tokens, truncating search enrichment..."
            )
            enrichment_start = prompt.find("[SEARCH ENRICHMENT]")
            enrichment_end = prompt.find("[MANDATORY] GROUND TRUTH")
            if enrichment_start > 0 and enrichment_end > enrichment_start:
                prompt = (
                    prompt[:enrichment_start]
                    + "[SEARCH ENRICHMENT - truncated due to prompt size]\n"
                    + prompt[enrichment_end:]
                )
                messages[1]["content"] = prompt

        final_content = ""  # The actual analysis from the final (no-tools) round
        tool_round_text = []  # Thinking text from tool-call rounds (fallback only)
        had_tool_rounds = False  # Whether any tool calls were made
        content = None  # Current round content

        for round_num in range(max_tool_rounds + 1):
            # CHECK FOR USER STOP SIGNAL
            if os.path.exists(".stop"):
                logger.info("User stop signal detected (.stop file). Aborting tool loop...")
                raise Exception("Analysis stopped by user.")

            total_chars = sum(len(m.get("content") or "") for m in messages)
            total_tokens_est = len(str(total_chars).encode("utf-8")) // 3  # roughly
            logger.info(
                f"  [ToolLoop] Prompt size: ~{total_tokens_est} tokens ({total_chars} chars)"
            )

            # Last round: force completion without tools
            use_tools = round_num < max_tool_rounds

            # For the final round after tool calls, add explicit completion instruction
            if not use_tools and had_tool_rounds:
                # Manage context: truncate long tool observations to prevent context overflow
                total_tool_chars = sum(
                    len(m.get("content", ""))
                    for m in messages
                    if m.get("role") == "tool"
                )
                trunc_limit = 2000 if total_tool_chars > 30000 else 3000
                for i, msg in enumerate(messages):
                    if (
                        msg.get("role") == "tool"
                        and len(msg.get("content", "")) > trunc_limit
                    ):
                        messages[i]["content"] = (
                            msg["content"][:trunc_limit]
                            + "\n\n... [content truncated for context management]"
                        )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "IMPORTANT: All data gathering is COMPLETE. You MUST now write your full expert analysis.\n\n"
                            "REQUIREMENTS:\n"
                            "1. Synthesize ALL information gathered from your tool calls above\n"
                            "2. Do NOT make any more tool calls or repeat search queries\n"
                            "3. Write a COMPREHENSIVE analysis (400-800 words minimum) with specific data points, tables, and conclusions\n"
                            "4. If some search results were empty, analyze based on the data you DID obtain plus the API data provided in the original prompt\n"
                            "5. Start writing your analysis immediately - do not output search queries or planning text"
                        ),
                    }
                )

            def _stream_with_tools():
                """Blocking streaming call with native tool support."""
                # httpx 0.28+ HTTP/2 transport requires an event loop even for sync Client.
                # asyncio.to_thread runs in a bare thread — inject a loop to prevent
                # "no running event loop" RuntimeError.
                import asyncio as _asyncio
                _loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(_loop)
                try:
                    client = llm_gateway.deepseek_client(api_key=deepseek_api_key)
                    kwargs = {
                        "model": final_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": 16384,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    }
                    if use_tools:
                        kwargs["tools"] = tools
                    else:
                        # Only enable reasoning on final synthesis round (no tools)
                        kwargs["extra_body"] = {"reasoning": {"effort": "high"}}
                        if response_schema:
                            kwargs["response_format"] = {"type": "json_object"}

                    response = client.chat.completions.create(**kwargs)

                    content_parts = []
                    reasoning_parts = []  # capture reasoning_content for thinking mode
                    tool_calls_acc = []  # accumulated tool calls from streaming deltas
                    char_count = 0

                    for chunk in response:
                        if hasattr(chunk, "usage") and chunk.usage:
                            usage_dict = {
                                "promptTokens": getattr(chunk.usage, "prompt_tokens", 0),
                                "candidatesTokens": getattr(
                                    chunk.usage, "completion_tokens", 0
                                ),
                                "totalTokens": getattr(chunk.usage, "total_tokens", 0),
                            }
                            usage_ctx = current_token_usage.get()
                            if usage_ctx is not None:
                                usage_ctx["promptTokens"] += usage_dict["promptTokens"]
                                usage_ctx["candidatesTokens"] += usage_dict[
                                    "candidatesTokens"
                                ]
                                usage_ctx["totalTokens"] += usage_dict["totalTokens"]

                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta

                        # Accumulate reasoning_content (thinking mode)
                        reasoning_text = getattr(delta, "reasoning_content", None)
                        if reasoning_text:
                            reasoning_parts.append(reasoning_text)
                            char_count += len(reasoning_text)
                            if on_chunk:
                                on_chunk(char_count)

                        # Accumulate content
                        if delta.content:
                            content_parts.append(delta.content)
                            char_count += len(delta.content)
                            if on_chunk:
                                on_chunk(char_count)

                        # Accumulate tool calls from streaming deltas
                        if delta.tool_calls:
                            for tc_delta in delta.tool_calls:
                                idx = tc_delta.index
                                while len(tool_calls_acc) <= idx:
                                    tool_calls_acc.append(
                                        {
                                            "id": "",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    )
                                if tc_delta.id:
                                    tool_calls_acc[idx]["id"] = tc_delta.id
                                if tc_delta.function:
                                    if tc_delta.function.name:
                                        tool_calls_acc[idx]["function"][
                                            "name"
                                        ] += tc_delta.function.name
                                    if tc_delta.function.arguments:
                                        tool_calls_acc[idx]["function"][
                                            "arguments"
                                        ] += tc_delta.function.arguments

                    reasoning_content = (
                        "".join(reasoning_parts) if reasoning_parts else None
                    )
                    return "".join(content_parts), tool_calls_acc, reasoning_content
                finally:
                    _loop.close()

            # Wrap with async timeout to prevent infinite hangs from API server
            _round_timeout = 360  # 6 minutes max per round
            try:
                content, tool_calls_data, reasoning_content = (
                    await asyncio.wait_for(
                        asyncio.to_thread(_stream_with_tools),
                        timeout=_round_timeout,
                    )
                )
            except asyncio.TimeoutError:
                logger.info(
                    f"  [ToolLoop] ⚠️ Round {round_num} TIMED OUT after {_round_timeout}s!"
                )
                if on_chunk:
                    on_chunk(
                        0,
                        message=f"第 {round_num+1} 轮 API 请求超时({_round_timeout}s)，正在重试...",
                    )
                if use_tools:
                    logger.info(
                        f"  [ToolLoop] Tool round {round_num} timed out, continuing..."
                    )
                    continue
                # Final round timed out — try with truncated context
                logger.info(
                    "  [ToolLoop] Final round timed out. Retrying with truncated context..."
                )
                for i, msg in enumerate(messages):
                    if msg.get("role") == "tool" and len(msg.get("content", "")) > 1000:
                        messages[i]["content"] = msg["content"][:1000] + "\n[truncated]"
                try:
                    content, tool_calls_data, reasoning_content = (
                        await asyncio.wait_for(
                            asyncio.to_thread(_stream_with_tools),
                            timeout=_round_timeout,
                        )
                    )
                    if content:
                        final_content = content
                except Exception as e2:
                    logger.info(f"  [ToolLoop] Retry also failed: {e2}")
                break
            except Exception as e:
                error_msg = str(e)
                logger.error(f"DeepSeek Native Tool Error (round {round_num}): {error_msg}")
                
                # Fail fast for fatal API errors
                fatal_keywords = ["401", "402", "429", "authentication fails", "invalid api key", "insufficient balance"]
                if any(k in error_msg.lower() for k in fatal_keywords):
                    raise e
                
                if use_tools:
                    # Error in tool round — continue to next round (may reach final round)
                    logger.info(
                        f"  [ToolLoop] Tool round {round_num} failed, continuing..."
                    )
                    continue
                # Error in final (no-tools) round — try with aggressively truncated context
                logger.info(
                    "  [ToolLoop] Final round failed. Retrying with truncated context..."
                )
                for i, msg in enumerate(messages):
                    if msg.get("role") == "tool" and len(msg.get("content", "")) > 1000:
                        messages[i]["content"] = msg["content"][:1000] + "\n[truncated]"
                try:
                    content, tool_calls_data, reasoning_content = (
                        await asyncio.wait_for(
                            asyncio.to_thread(_stream_with_tools),
                            timeout=_round_timeout,
                        )
                    )
                    if content:
                        final_content = content
                except Exception as e2:
                    logger.info(f"  [ToolLoop] Retry also failed: {e2}")
                break

            # No tool calls — final response
            if not tool_calls_data:
                if content:
                    final_content = content
                else:
                    logger.warning(
                        "  [ToolLoop] WARNING: Final round produced empty content"
                    )
                break

            had_tool_rounds = True
            logger.info(
                f"  [ToolLoop] Round {round_num + 1}: {len(tool_calls_data)} native tool call(s)"
            )

            # Reset TokenGuard round budget for this batch of tool calls
            token_guard.reset_round()

            if content and "DSML" not in content:
                tool_round_text.append(content)

            # Build assistant message with tool_calls for conversation history
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in tool_calls_data
                ],
            }
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            messages.append(assistant_msg)

            if on_chunk:
                tool_names = [tc["function"]["name"] for tc in tool_calls_data]
                on_chunk(0, message=f"{role or 'Agent'} (工具调用第 {round_num + 1} 轮: {', '.join(tool_names)})")

            # Execute all tool calls in PARALLEL for speed
            async def _exec_one_tool(tc_data):
                func_name = tc_data["function"]["name"]
                try:
                    args = json.loads(tc_data["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # Convert to our ToolExecutor format
                tool_call = {"tool": func_name, "reason": "native function call"}
                if func_name == "deep_scrape":
                    tool_call["url"] = args.get("url", "")
                    tool_call["query"] = args.get("query", "")
                elif func_name == "financial_data":
                    tool_call["symbol"] = args.get("symbol", "")
                    tool_call["query"] = args.get("query", "")
                elif func_name in COMPUTATION_TOOL_NAMES:
                    tool_call["params_json"] = json.dumps(args)
                else:
                    tool_call["query"] = args.get("query", "")

                label = tool_call.get(
                    "url", tool_call.get("symbol", tool_call.get("query", ""))
                )[:60]
                logger.info(f"  [ToolExecutor] {func_name}: {label}...")

                obs = await tool_executor.execute(tool_call)
                obs_clean = (
                    obs.replace("<tool_observation>", "")
                    .replace("</tool_observation>", "")
                    .strip()
                )
                return tc_data["id"], obs_clean

            # Run all tool calls concurrently
            tool_results = await asyncio.gather(
                *[_exec_one_tool(tc) for tc in tool_calls_data],
                return_exceptions=True,
            )

            # Heartbeat: notify frontend of activity after tool execution
            if on_chunk:
                on_chunk((round_num + 1) * (len(messages) + 500), message=f"{role or 'Agent'} (第 {round_num + 1} 轮工具调用完成，正在思考...)")

            # Append results in order as role:tool messages
            for i, result_or_exc in enumerate(tool_results):
                if isinstance(result_or_exc, Exception):
                    tc_id = tool_calls_data[i]["id"]
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": f"Tool execution error: {result_or_exc}",
                        }
                    )
                else:
                    tc_id, obs_clean = result_or_exc
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": obs_clean,
                        }
                    )

        # Prefer final analysis content; fall back to tool-round thinking text if final round failed
        def _is_valid_analysis(text: str) -> bool:
            if not text or len(text.strip()) < 200:
                return False
            # Detect raw computation tool params: mostly numbers, JSON arrays, short lines
            lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
            if len(lines) < 5:
                import re

                non_prose = sum(
                    1
                    for l in lines
                    if re.match(r"^[\[\]{}\d\s.,\-\":\w_]+$", l) and len(l) < 80
                )
                if non_prose >= len(lines) * 0.7:
                    return False
            return True

        def _is_analysis_fragment(text: str) -> bool:
            if not text or len(text.strip()) < 300:
                return False
            has_structure = (
                "##" in text or "|" in text or "- **" in text or "1." in text
            )
            filler_indicators = sum(
                1
                for w in [
                    "让我搜索",
                    "我需要",
                    "let me search",
                    "I need to",
                    "I will now",
                    "接下来我",
                ]
                if w in text
            )
            return has_structure and filler_indicators < 2

        def _dedup_fragments(fragments: list, final: str) -> list:
            if not fragments or not final:
                return fragments

            if len(final) > 1000:
                return []

            import re

            final_paras = set()
            for para in re.split(r"\n{2,}", final):
                stripped = para.strip()
                if len(stripped) > 15:
                    final_paras.add(stripped[:20].lower())

            deduped = []
            for frag in fragments:
                frag_paras = re.split(r"\n{2,}", frag)
                kept_paras = []
                for para in frag_paras:
                    stripped = para.strip()
                    if len(stripped) <= 15:
                        kept_paras.append(para)
                        continue

                    if stripped[:20].lower() not in final_paras:
                        kept_paras.append(para)

                result_frag = "\n\n".join(kept_paras).strip()
                if len(result_frag) > 200:
                    deduped.append(result_frag)
            return deduped

        async def _recovery_synthesis() -> str:
            recovery_messages = [messages[0], messages[1]]
            tool_summaries = []
            for msg in messages:
                if msg.get("role") == "tool":
                    tool_summaries.append((msg.get("content", ""))[:500])
            if tool_summaries:
                recovery_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Here is a summary of data you gathered from your tool calls:\n\n"
                            + "\n---\n".join(tool_summaries[:8])
                            + "\n\nBased on the above data AND the API data in the original prompt, write your COMPLETE "
                            "expert analysis report NOW. 400+ words with specific data points, tables, and conclusions. "
                            "Do NOT output raw numbers, tool parameters, or planning text — write investor-facing prose."
                        ),
                    }
                )
            else:
                recovery_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Write your COMPLETE expert analysis report NOW based on the API data in the original prompt. "
                            "400+ words with specific data points and conclusions. Do NOT output raw numbers or tool parameters."
                        ),
                    }
                )

            def _recovery_call():
                # Same event-loop fix as _stream_with_tools above
                import asyncio as _asyncio
                _loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(_loop)
                try:
                    client = llm_gateway.deepseek_client(api_key=deepseek_api_key)
                    kwargs = {
                        "model": final_model,
                        "messages": recovery_messages,
                        "temperature": temperature,
                        "max_tokens": 16384,
                        "stream": True,
                    }
                    if response_schema:
                        kwargs["response_format"] = {"type": "json_object"}
                    resp = client.chat.completions.create(**kwargs)
                    parts = []
                    for chunk in resp:
                        if chunk.choices and chunk.choices[0].delta.content:
                            parts.append(chunk.choices[0].delta.content)
                    return "".join(parts)
                finally:
                    _loop.close()

            try:
                rc = await asyncio.to_thread(_recovery_call)
                if rc and _is_valid_analysis(rc):
                    logger.info(
                        f"  [ToolLoop] Recovery synthesis successful: {len(rc)} chars"
                    )
                    return rc
            except Exception as e:
                logger.error(f"  [ToolLoop] Recovery synthesis error: {e}")
            return ""

        if final_content and _is_valid_analysis(final_content):
            analysis_fragments = [
                t for t in tool_round_text if _is_analysis_fragment(t)
            ]
            if analysis_fragments:
                analysis_fragments = _dedup_fragments(
                    analysis_fragments, final_content
                )
            if analysis_fragments:
                combined = (
                    "\n\n".join(analysis_fragments) + "\n\n" + final_content
                )
                logger.info(
                    f"  [ToolLoop] Merged {len(analysis_fragments)} deduped fragment(s) ({sum(len(f) for f in analysis_fragments)} chars) with final content ({len(final_content)} chars)"
                )
                result = combined
            else:
                result = final_content
        elif final_content:
            logger.warning(
                f"  [ToolLoop] WARNING: Final round produced only {len(final_content)} chars or invalid content. Retrying with tools..."
            )
            messages.append({"role": "assistant", "content": final_content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your response appears to contain only raw tool parameters, not a proper analysis. "
                        "You MUST call the computation tools (e.g. drawdown_scenario, risk_reward, kelly_calculator, stop_loss_validator, position_sizer) "
                        "to get their results, then write a FULL, DETAILED expert analysis report (400+ words) with specific numbers, comparisons, and conclusions."
                    ),
                }
            )
            try:

                def _retry_with_tools():
                    # Same event-loop fix as _stream_with_tools above
                    import asyncio as _asyncio
                    _loop = _asyncio.new_event_loop()
                    _asyncio.set_event_loop(_loop)
                    try:
                        client = llm_gateway.deepseek_client(api_key=deepseek_api_key)
                        kwargs = {
                            "model": final_model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": 16384,
                            "stream": True,
                            "tools": tools,
                        }
                        response = client.chat.completions.create(**kwargs)
                        content_parts = []
                        tool_calls_acc = []
                        for chunk in response:
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
                            if delta.content:
                                content_parts.append(delta.content)
                        return "".join(content_parts), tool_calls_acc
                    finally:
                        _loop.close()

                retry_content, retry_tool_calls = await asyncio.to_thread(
                    _retry_with_tools
                )

                if retry_tool_calls:
                    logger.info(
                        f"  [ToolLoop] Retry: {len(retry_tool_calls)} computation tool call(s)"
                    )
                    assistant_msg = {
                        "role": "assistant",
                        "content": retry_content or None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": tc["function"]["arguments"],
                                },
                            }
                            for tc in retry_tool_calls
                        ],
                    }
                    messages.append(assistant_msg)
                    for tc_data in retry_tool_calls:
                        func_name = tc_data["function"]["name"]
                        try:
                            args = json.loads(tc_data["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        tool_call = {
                            "tool": func_name,
                            "reason": "native function call",
                        }
                        if func_name in COMPUTATION_TOOL_NAMES:
                            tool_call["params_json"] = json.dumps(args)
                        else:
                            tool_call["query"] = args.get("query", "")
                        logger.info(f"  [ToolExecutor] {func_name}: ...")
                        obs = await tool_executor.execute(tool_call)
                        obs_clean = (
                            obs.replace("<tool_observation>", "")
                            .replace("</tool_observation>", "")
                            .strip()
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_data["id"],
                                "content": obs_clean,
                            }
                        )
                    # Final generation with tool results
                    messages.append(
                        {
                            "role": "user",
                            "content": "Now write your COMPLETE expert analysis using the computation results above. 400+ words.",
                        }
                    )
                    retry_content, _, _ = await asyncio.to_thread(
                        _stream_with_tools
                    )

                if retry_content and _is_valid_analysis(retry_content):
                    result = retry_content
                    final_response = retry_content
                else:
                    recovered = await _recovery_synthesis()
                    final_response = recovered or (
                        retry_content
                        if _is_valid_analysis(retry_content or "")
                        else ""
                    )
            except Exception:
                final_response = await _recovery_synthesis()

            if cache_key and final_response:
                try:
                    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                    with open(cache_file, "w") as f:
                        json.dump({"content": final_response}, f)
                except Exception as e:
                    logger.info(f"Failed to write native cache {cache_file}: {e}")
            result = final_response or ""

        elif tool_round_text:
            logger.warning(
                "  [ToolLoop] WARNING: No final analysis produced. Attempting recovery..."
            )
            recovered = await _recovery_synthesis()
            if recovered:
                result = recovered
            else:
                fragments = [
                    t for t in tool_round_text if _is_analysis_fragment(t)
                ]
                result = "\n\n".join(fragments) if fragments else ""
        else:
            result = content or ""

        if not _is_valid_analysis(result):
            logger.warning(
                "  [ToolLoop] WARNING: Assembled result invalid. Last-resort synthesis..."
            )
            recovered = await _recovery_synthesis()
            if recovered:
                result = recovered
            elif not (result and len(result.strip()) >= 200):
                result = (
                    "**数据采集受限说明**\n\n"
                    "本轮分析所需的关键行情/财务数据在多次工具调用后仍未能完整获取，"
                    "为避免编造数据，本专家不输出推测性结论。请检查数据源（行情/财务接口）可用性后重试。"
                )

        if "DSML" in result:
            import re

            result = re.sub(r"<[｜|]*DSML[｜|]*[^>]*>", "", result)
            result = re.sub(r"</[｜|]*DSML[｜|]*[^>]*>", "", result)
            result = re.sub(r"\n{3,}", "\n\n", result).strip()
        return result


# Singleton
agent_orchestrator = AgentOrchestrator()
