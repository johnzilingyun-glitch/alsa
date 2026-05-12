import os
import json
import asyncio
from google import genai
from openai import OpenAI
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load .env
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

class LLMGateway:
    def __init__(self, gemini_api_key=None, deepseek_api_key=None):
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.deepseek_api_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
        self._gemini_client = None
        self._deepseek_client = None
        
        if not self.gemini_api_key:
            print("WARNING: GEMINI_API_KEY not found in LLMGateway.")
        if not self.deepseek_api_key:
            print("WARNING: DEEPSEEK_API_KEY not found in LLMGateway.")

    def gemini_client(self, api_key=None):
        target_key = api_key or self.gemini_api_key
        if self._gemini_client is None or (api_key and api_key != self.gemini_api_key):
            if target_key:
                try:
                    return genai.Client(api_key=target_key)
                except Exception as e:
                    print(f"Failed to initialize Gemini Client: {e}")
                    return None
            else:
                return None
        return self._gemini_client

    def deepseek_client(self, api_key=None):
        target_key = api_key or self.deepseek_api_key
        if self._deepseek_client is None or (api_key and api_key != self.deepseek_api_key):
            if target_key:
                return OpenAI(
                    api_key=target_key,
                    base_url="https://api.deepseek.com"
                )
            else:
                raise ValueError("DEEPSEEK_API_KEY is missing.")
        return self._deepseek_client

    async def generate_content(self, prompt: str, model: str = "gemini-3.1-pro-preview", temperature: float = 0.3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None) -> str:
        """
        Generate content with built-in quality-gate retry.
        Retries up to 2 extra times if response is truncated or garbage.
        """
        max_quality_retries = 2
        for quality_attempt in range(max_quality_retries + 1):
            if "deepseek" in model.lower():
                result = await self._generate_deepseek(prompt, model, temperature, on_chunk=on_chunk, api_key=deepseek_api_key)
            else:
                result = await self._generate_gemini(prompt, model, temperature, on_chunk=on_chunk, api_key=gemini_api_key)

            # Quality gate: detect truncated responses
            if result and len(result) < 150:
                if quality_attempt < max_quality_retries:
                    print(f"WARNING: Very short response ({len(result)} chars) — quality retry {quality_attempt+1}/{max_quality_retries}")
                    continue
                else:
                    print(f"WARNING: Very short response ({len(result)} chars) after {max_quality_retries} retries — using anyway")

            # Quality gate: detect off-topic garbage
            if result and any(keyword in result[:200].lower() for keyword in
                              ["h2020", "erasmus", "empowering women", "stem education"]):
                if quality_attempt < max_quality_retries:
                    print(f"WARNING: Off-topic response — quality retry {quality_attempt+1}/{max_quality_retries}")
                    continue
                else:
                    print(f"WARNING: Off-topic response persists after retries — using anyway")

            if result and len(result) < 200:
                print(f"WARNING: Short response ({len(result)} chars) — may be truncated")

            return result

        return result  # fallback

    async def _generate_gemini(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None) -> str:
        client = self.gemini_client(api_key=api_key)
        if not client:
            raise ValueError("Gemini client not initialized (missing API key?)")
            
        max_retries = 20
        retry_delay = 15 # Initial delay in seconds
        max_delay = 3600 # 1 hour
        
        # Strict mode: NO model degradation. Only use the user-selected model.
        # Rate limits are handled by exponential backoff with extended wait times.
        for attempt in range(max_retries):
            # CHECK FOR USER STOP SIGNAL
            if os.path.exists(".stop"):
                print("User stop signal detected (.stop file). Aborting analysis...")
                raise Exception("Analysis stopped by user.")

            try:
                # Assemble generation config
                config = {
                    "temperature": temperature,
                    "max_output_tokens": 8192,
                }
                if "gemini" in model.lower():
                    config["tools"] = [{"google_search": {}}]

                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=config
                )
                
                if response and hasattr(response, 'text'):
                    return response.text
                elif response and isinstance(response, str):
                    return response
                else:
                    raise ValueError(f"Unexpected response type from Gemini: {type(response)}")
            except Exception as e:
                error_msg = str(e)
                print(f"Gemini Error ({model}) on attempt {attempt + 1}/{max_retries}: {error_msg}")
                
                # Retry on 429 Quota Exceeded or 503 Service Unavailable — extend wait, never degrade
                if "429" in error_msg or "quota" in error_msg.lower() or "503" in error_msg:
                    if attempt < max_retries - 1:
                        print(f"Rate limit hit. Waiting {retry_delay}s before retry {attempt + 2}/{max_retries} (no model downgrade)...")
                        # Interruptible sleep
                        for _ in range(int(retry_delay)):
                            await asyncio.sleep(1)
                            if os.path.exists(".stop"):
                                print("User stop signal detected during wait. Aborting...")
                                raise Exception("Analysis stopped by user.")
                        
                        retry_delay = min(retry_delay * 2, max_delay)
                        continue
                
                # Non-retryable error: raise immediately, no fallback
                print(f"Non-retryable error with {model}. Strict mode: no model downgrade.")
                raise e
                
        raise Exception(f"Failed to generate content with {model} after {max_retries} attempts due to rate limits. No model downgrade allowed.")

    async def _generate_deepseek(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None) -> str:
        client = self.deepseek_client(api_key=api_key)
        max_retries = 10
        retry_delay = 15
        
        # Only V4 models are supported; pass model name directly
        final_model = model
        
        def _stream_generate():
            """Blocking streaming call — runs in thread for async compatibility."""
            response = self.deepseek_client(api_key=api_key).chat.completions.create(
                model=final_model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=16384,
                stream=True
            )
            content_parts = []
            char_count = 0
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    content_parts.append(text)
                    char_count += len(text)
                    if on_chunk:
                        on_chunk(char_count)
            print(flush=True)  # newline after streaming dots
            return "".join(content_parts)
        
        for attempt in range(max_retries):
            try:
                result = await asyncio.to_thread(_stream_generate)
                if not result:
                    raise ValueError("DeepSeek returned empty streaming response")
                return result
            except Exception as e:
                error_msg = str(e)
                print(f"DeepSeek Error ({final_model}) on attempt {attempt + 1}/{max_retries}: {error_msg}")
                
                # Retry on transient errors: 429 Quota, 503/524 Server, empty response, connection errors
                if "429" in error_msg or "quota" in error_msg.lower() or "503" in error_msg or "524" in error_msg or "500" in error_msg or "502" in error_msg or "empty response" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                    if attempt < max_retries - 1:
                        print(f"Rate limit hit. Waiting {retry_delay}s before retry {attempt + 2}/{max_retries} (no model downgrade)...")
                        # Interruptible sleep
                        for _ in range(int(retry_delay)):
                            await asyncio.sleep(1)
                            if os.path.exists(".stop"):
                                print("User stop signal detected during wait. Aborting...")
                                raise Exception("Analysis stopped by user.")
                        retry_delay = min(retry_delay * 2, 3600)
                        continue
                
                # Strict mode: Do not fallback or downgrade
                print(f"Strict model mode enforced. Failed to generate with {final_model}. Raising error without fallback.")
                raise e
                
        raise Exception(f"Failed to generate content with {final_model} after {max_retries} attempts due to rate limits.")

    async def generate_with_native_tools(self, prompt: str, model: str, temperature: float = 0.3, max_tool_rounds: int = 3, on_chunk: Optional[callable] = None, deepseek_api_key: Optional[str] = None) -> str:
        """
        Generate content using DeepSeek's native OpenAI-compatible function calling API.
        
        Instead of text-based <tool_call> parsing, uses the `tools` parameter
        for structured function calling with streaming progress output.
        """
        from .expert_tools import get_openai_tools, tool_executor
        
        model_map = {
            "deepseek-chat": "deepseek-v4-pro",
            "deepseek-reasoner": "deepseek-v4-pro"
        }
        final_model = model_map.get(model, model)
        
        tools = get_openai_tools()
        messages = [
            {"role": "system", "content": "You are a professional financial analyst expert."},
            {"role": "user", "content": prompt}
        ]
        
        # Guard against prompt size explosion
        prompt_chars = len(prompt)
        prompt_tokens_est = prompt_chars // 4
        if prompt_tokens_est > 60000:
            print(f"  [ToolLoop] WARNING: Prompt exceeds 60k tokens, truncating search enrichment...")
            enrichment_start = prompt.find("[SEARCH ENRICHMENT]")
            enrichment_end = prompt.find("[MANDATORY] GROUND TRUTH")
            if enrichment_start > 0 and enrichment_end > enrichment_start:
                prompt = prompt[:enrichment_start] + "[SEARCH ENRICHMENT - truncated due to prompt size]\n" + prompt[enrichment_end:]
                messages[1]["content"] = prompt
        
        final_content = ""        # The actual analysis from the final (no-tools) round
        tool_round_text = []     # Thinking text from tool-call rounds (fallback only)
        had_tool_rounds = False  # Whether any tool calls were made
        content = None           # Current round content (initialized to prevent UnboundLocalError)
        
        for round_num in range(max_tool_rounds + 1):
            # CHECK FOR USER STOP SIGNAL
            if os.path.exists(".stop"):
                print("User stop signal detected (.stop file). Aborting tool loop...")
                raise Exception("Analysis stopped by user.")
            
            total_chars = sum(len(m.get("content") or "") for m in messages)
            total_tokens_est = total_chars // 4
            print(f"  [ToolLoop] Prompt size: ~{total_tokens_est} tokens ({total_chars} chars)")
            
            # Last round: force completion without tools
            use_tools = round_num < max_tool_rounds
            
            # For the final round after tool calls, add explicit completion instruction
            if not use_tools and had_tool_rounds:
                # Manage context: truncate long tool observations to prevent context overflow
                total_tool_chars = sum(len(m.get("content", "")) for m in messages if m.get("role") == "tool")
                # If total tool content is very large, be more aggressive with truncation
                trunc_limit = 2000 if total_tool_chars > 30000 else 3000
                for i, msg in enumerate(messages):
                    if msg.get("role") == "tool" and len(msg.get("content", "")) > trunc_limit:
                        messages[i]["content"] = msg["content"][:trunc_limit] + "\n\n... [content truncated for context management]"
                messages.append({
                    "role": "user",
                    "content": (
                        "IMPORTANT: All data gathering is COMPLETE. You MUST now write your full expert analysis.\n\n"
                        "REQUIREMENTS:\n"
                        "1. Synthesize ALL information gathered from your tool calls above\n"
                        "2. Do NOT make any more tool calls or repeat search queries\n"  
                        "3. Write a COMPREHENSIVE analysis (400-800 words minimum) with specific data points, tables, and conclusions\n"
                        "4. If some search results were empty, analyze based on the data you DID obtain plus the API data provided in the original prompt\n"
                        "5. Start writing your analysis immediately - do not output search queries or planning text"
                    )
                })
            
            def _stream_with_tools():
                """Blocking streaming call with native tool support."""
                kwargs = {
                    "model": final_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 16384,
                    "stream": True,
                }
                if use_tools:
                    kwargs["tools"] = tools
                
                response = self.deepseek_client(api_key=deepseek_api_key).chat.completions.create(**kwargs)
                
                content_parts = []
                reasoning_parts = []  # capture reasoning_content for thinking mode
                tool_calls_acc = []  # accumulated tool calls from streaming deltas
                char_count = 0
                
                for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    
                    # Accumulate reasoning_content (thinking mode)
                    reasoning_text = getattr(delta, "reasoning_content", None)
                    if reasoning_text:
                        reasoning_parts.append(reasoning_text)
                    
                    # Accumulate content
                    if delta.content:
                        content_parts.append(delta.content)
                        char_count += len(delta.content)
                        if char_count % 200 < len(delta.content):
                            print(".", end="", flush=True)
                        if on_chunk:
                            on_chunk(char_count)
                    
                    # Accumulate tool calls from streaming deltas
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            while len(tool_calls_acc) <= idx:
                                tool_calls_acc.append({"id": "", "function": {"name": "", "arguments": ""}})
                            if tc_delta.id:
                                tool_calls_acc[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tool_calls_acc[idx]["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_acc[idx]["function"]["arguments"] += tc_delta.function.arguments
                
                print(flush=True)
                reasoning_content = "".join(reasoning_parts) if reasoning_parts else None
                return "".join(content_parts), tool_calls_acc, reasoning_content
            
            try:
                content, tool_calls_data, reasoning_content = await asyncio.to_thread(_stream_with_tools)
            except Exception as e:
                error_msg = str(e)
                print(f"DeepSeek Native Tool Error (round {round_num}): {error_msg}")
                if use_tools:
                    # Error in tool round — continue to next round (may reach final round)
                    print(f"  [ToolLoop] Tool round {round_num} failed, continuing...")
                    continue
                # Error in final (no-tools) round — try with aggressively truncated context
                print(f"  [ToolLoop] Final round failed. Retrying with truncated context...")
                for i, msg in enumerate(messages):
                    if msg.get("role") == "tool" and len(msg.get("content", "")) > 1000:
                        messages[i]["content"] = msg["content"][:1000] + "\n[truncated]"
                try:
                    content, tool_calls_data, reasoning_content = await asyncio.to_thread(_stream_with_tools)
                    if content:
                        final_content = content
                except Exception as e2:
                    print(f"  [ToolLoop] Retry also failed: {e2}")
                break
            
            # No tool calls — final response
            if not tool_calls_data:
                if content:
                    final_content = content
                else:
                    print(f"  [ToolLoop] WARNING: Final round produced empty content")
                break
            
            had_tool_rounds = True
            print(f"  [ToolLoop] Round {round_num + 1}: {len(tool_calls_data)} native tool call(s)")
            
            # During tool-call rounds, DON'T include thinking text in output.
            # It's just "let me search for X" filler, not actual analysis.
            # Save as fallback in case the final round fails to produce content.
            if content and 'DSML' not in content:
                tool_round_text.append(content)
            
            # Build assistant message with tool_calls for conversation history
            # Must include reasoning_content when model uses thinking mode
            assistant_msg = {"role": "assistant", "content": content or None, "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"]
                    }
                }
                for tc in tool_calls_data
            ]}
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            messages.append(assistant_msg)
            
            # Execute each tool and append result as role:tool message
            for tc_data in tool_calls_data:
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
                else:
                    tool_call["query"] = args.get("query", "")
                
                label = tool_call.get('url', tool_call.get('query', ''))[:60]
                print(f"  [ToolExecutor] {func_name}: {label}...")
                
                obs = await tool_executor.execute(tool_call)
                # Strip XML tags — native tool API uses plain content in messages
                obs_clean = obs.replace("<tool_observation>", "").replace("</tool_observation>", "").strip()
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_data["id"],
                    "content": obs_clean
                })
        
        # Prefer final analysis content; fall back to tool-round thinking text if final round failed
        if final_content and len(final_content.strip()) > 100:
            result = final_content
        elif final_content:
            # Final round produced very short content — likely incomplete
            print(f"  [ToolLoop] WARNING: Final round produced only {len(final_content)} chars. Retrying...")
            # Retry once with a stronger prompt
            messages.append({"role": "assistant", "content": final_content})
            messages.append({
                "role": "user",
                "content": "Your response was too short and incomplete. Please write a FULL, DETAILED expert analysis report (400+ words) with specific numbers, comparisons, and conclusions. Start now."
            })
            try:
                retry_content, _, _ = await asyncio.to_thread(_stream_with_tools)
                if retry_content and len(retry_content.strip()) > 100:
                    result = retry_content
                else:
                    result = final_content
            except Exception:
                result = final_content
        elif tool_round_text:
            # No final content at all — the final round failed or produced empty response
            # Try one more time with aggressively trimmed context
            print(f"  [ToolLoop] WARNING: No final analysis produced. Attempting recovery...")
            # Keep only system, original user prompt, and a summary of tool results
            recovery_messages = [messages[0], messages[1]]  # system + user
            tool_summaries = []
            for msg in messages:
                if msg.get("role") == "tool":
                    content_preview = (msg.get("content", ""))[:500]
                    tool_summaries.append(content_preview)
            if tool_summaries:
                recovery_messages.append({
                    "role": "user",
                    "content": "Here is a summary of search results you gathered:\n\n" + "\n---\n".join(tool_summaries[:6]) + 
                    "\n\nBased on the above data AND the API data in the original prompt, write your COMPLETE expert analysis report now. 400+ words with specific data points."
                })
            try:
                def _recovery_call():
                    resp = self.deepseek_client(api_key=deepseek_api_key).chat.completions.create(
                        model=final_model, messages=recovery_messages,
                        temperature=temperature, max_tokens=16384, stream=True
                    )
                    parts = []
                    for chunk in resp:
                        if chunk.choices and chunk.choices[0].delta.content:
                            parts.append(chunk.choices[0].delta.content)
                            if len(parts) % 50 == 0:
                                print(".", end="", flush=True)
                    print(flush=True)
                    return "".join(parts)
                
                recovery_content = await asyncio.to_thread(_recovery_call)
                if recovery_content and len(recovery_content.strip()) > 100:
                    result = recovery_content
                    print(f"  [ToolLoop] Recovery successful: {len(recovery_content)} chars")
                else:
                    print(f"  [ToolLoop] Recovery failed. Using {len(tool_round_text)} tool-round fragments as fallback.")
                    result = "\n".join(tool_round_text)
            except Exception as e:
                print(f"  [ToolLoop] Recovery error: {e}. Using tool-round fragments.")
                result = "\n".join(tool_round_text)
        else:
            result = content or ""
        # Safety net: strip any remaining DSML tokens that may have leaked
        if 'DSML' in result:
            import re
            result = re.sub(r'<[｜|]*DSML[｜|]*[^>]*>', '', result)
            result = re.sub(r'</[｜|]*DSML[｜|]*[^>]*>', '', result)
            # Clean up leftover whitespace from stripped tokens
            result = re.sub(r'\n{3,}', '\n\n', result).strip()
        return result

    async def generate_with_tools(self, prompt: str, model: str = "gemini-3.1-pro-preview", temperature: float = 0.3, max_tool_rounds: int = 3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None) -> str:
        """
        Generate content with tool-calling loop.
        
        For DeepSeek: uses native OpenAI-compatible function calling API.
        For other models: uses text-based <tool_call> parsing.
        """
        # For DeepSeek, use native OpenAI-compatible function calling
        if "deepseek" in model.lower():
            return await self.generate_with_native_tools(prompt, model, temperature, max_tool_rounds, on_chunk=on_chunk, deepseek_api_key=deepseek_api_key)
        
        from .expert_tools import parse_tool_calls, has_tool_calls, tool_executor
        
        current_prompt = prompt
        all_content_parts = []
        
        for round_num in range(max_tool_rounds + 1):
            # Guard against prompt size explosion
            prompt_chars = len(current_prompt)
            prompt_tokens_est = prompt_chars // 4
            print(f"  [ToolLoop] Prompt size: ~{prompt_tokens_est} tokens ({prompt_chars} chars)")
            if prompt_tokens_est > 60000:
                print(f"  [ToolLoop] WARNING: Prompt exceeds 60k tokens, truncating search enrichment...")
                # Truncate the enrichment section if present
                enrichment_start = current_prompt.find("[SEARCH ENRICHMENT]")
                enrichment_end = current_prompt.find("[MANDATORY] GROUND TRUTH")
                if enrichment_start > 0 and enrichment_end > enrichment_start:
                    current_prompt = current_prompt[:enrichment_start] + "[SEARCH ENRICHMENT - truncated due to prompt size]\n" + current_prompt[enrichment_end:]

            # Generate
            result = await self.generate_content(current_prompt, model=model, temperature=temperature, on_chunk=on_chunk, gemini_api_key=gemini_api_key, deepseek_api_key=deepseek_api_key)
            
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
            
            print(f"  [ToolLoop] Round {round_num + 1}: {len(tool_calls)} tool call(s)")
            
            # Extract text before first tool call (the LLM's reasoning so far)
            first_call_pos = result.find("<tool_call>")
            if first_call_pos > 0:
                reasoning_before = result[:first_call_pos].strip()
                if reasoning_before:
                    all_content_parts.append(reasoning_before)
            
            # Execute tools
            observations = await tool_executor.execute_all(tool_calls)
            
            # Build continuation prompt
            tool_section = "\n\n--- TOOL RESULTS ---\n"
            for tc, obs in zip(tool_calls, observations):
                tool_section += f"\n[Tool: {tc['tool']} | Query: {tc['query']}]\n"
                tool_section += obs + "\n"
            tool_section += "\n--- END TOOL RESULTS ---\n"
            tool_section += "\nContinue your analysis using the tool results above. Do NOT repeat previous analysis. Build on it with the new data.\n"
            
            current_prompt = current_prompt + "\n\n--- ASSISTANT PARTIAL RESPONSE ---\n" + result + "\n" + tool_section
            
            if round_num == max_tool_rounds:
                # Last round — force completion without tools
                current_prompt += "\nIMPORTANT: This is your final response round. Do NOT make any more tool calls. Complete your analysis now.\n"
        
        return "\n".join(all_content_parts) if all_content_parts else result or ""

llm_gateway = LLMGateway()
