import os
import logging
logger = logging.getLogger(__name__)
import json
import asyncio
import time
import threading
import queue
from datetime import datetime
from contextvars import ContextVar
from google import genai
from openai import OpenAI
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Global context variable to track token usage across the current async task
current_token_usage: ContextVar[Optional[Dict[str, int]]] = ContextVar("current_token_usage", default=None)

# Load .env
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
load_dotenv(os.path.join(root_dir, ".env"), override=True)
load_dotenv(os.path.join(root_dir, ".env.runtime"), override=True)


class RateLimiter:
    """Token-bucket style rate limiter for API requests.
    
    Ensures minimum interval between requests and limits concurrency
    to prevent 503 errors from the relay (中转站).
    
    Supports adaptive rate limiting based on context:
    - 'tool': Tool-calling round (faster, 1.0s)
    - 'final': Final synthesis round (moderate, 1.5s)
    - 'default': Conservative default (3.0s)
    """

    def __init__(
        self,
        min_interval: float = 3.0,
        max_concurrent: int = 2,
        tool_interval: float = None,
        final_interval: float = None,
    ):
        self._min_interval = min_interval
        self._default_min_interval = min_interval
        self._tool_interval = tool_interval or 1.0          # 工具轮速率
        self._final_interval = final_interval or 1.5        # 最终轮速率
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()
        self._pending_context: str = "default"  # context for next acquire via async with

    def with_context(self, context: str) -> "RateLimiter":
        """Set context for the next async with acquisition. Returns self for chaining.
        Usage: async with limiter.with_context('tool'): ...
        """
        self._pending_context = context
        return self

    async def acquire(self, context: str = "default"):
        """Wait until it's safe to make a request.
        
        Args:
            context: 'tool' (工具轮) | 'final' (最终轮) | 'default' (其他)
        """
        await self._semaphore.acquire()
        async with self._lock:
            # 根据上下文选择最小间隔
            if context == "tool":
                min_interval = self._tool_interval
            elif context == "final":
                min_interval = self._final_interval
            else:
                min_interval = self._min_interval
            
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                logger.debug(f"[RateLimiter] Waiting {wait_time:.2f}s (context={context})")
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()

    def release(self, success: bool = True):
        """Release the semaphore after request completes."""
        if success:
            self._min_interval = self._default_min_interval
        self._semaphore.release()

    async def __aenter__(self):
        ctx = self._pending_context
        self._pending_context = "default"  # reset for next use
        await self.acquire(ctx)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release(success=(exc_type is None))


class LLMGateway:
    def __init__(self, gemini_api_key=None, deepseek_api_key=None, openrouter_api_key=None):
        self._gemini_api_key_override = gemini_api_key
        self._deepseek_api_key_override = deepseek_api_key
        self._openrouter_api_key_override = openrouter_api_key
        self.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.default_api_key = os.getenv("DEFAULT_LLM_API_KEY")
        self.default_base_url = os.getenv("DEFAULT_LLM_BASE_URL", "http://xbrain-dify-service-test.xiaopeng.link/llm_api")
        self.default_model = os.getenv("DEFAULT_LLM_MODEL", "deepseek-v4-pro")
        self._gemini_client = None
        self._deepseek_client = None
        self._openrouter_client = None
        self._default_client = None
        self._last_gemini_key = None
        self._last_deepseek_key = None
        self._last_openrouter_key = None
        self.deepseek_api_key = self.get_deepseek_api_key()

        # Rate limiter for the default relay (中转站) to prevent 503 errors
        # 自适应速率: 工具轮(tool)用1.0s, 最终轮(final)用1.5s, 其他默认1.5s
        _min_interval = float(os.getenv("LLM_RATE_LIMIT_INTERVAL", "1.5"))
        _max_concurrent = int(os.getenv("LLM_RATE_LIMIT_CONCURRENCY", "3"))
        _tool_interval = float(os.getenv("LLM_TOOL_INTERVAL", "1.0"))
        _final_interval = float(os.getenv("LLM_FINAL_INTERVAL", "1.5"))
        
        self._default_rate_limiter = RateLimiter(
            min_interval=_min_interval,
            max_concurrent=_max_concurrent,
            tool_interval=_tool_interval,
            final_interval=_final_interval,
        )

        # Cache configuration
        self._cache_dir = os.path.join(os.path.expanduser("~/.alsa_cache/llm"))
        self._cache_ttl_hours = int(os.getenv("LLM_CACHE_TTL_HOURS", "12"))

    def _get_cache_path(self, cache_key: str) -> str:
        """Get cache file path for a given key."""
        import hashlib
        today = datetime.now().strftime('%Y-%m-%d')
        safe_key = hashlib.md5(f"{cache_key}_{today}".encode()).hexdigest()[:16]
        return os.path.join(self._cache_dir, f"{safe_key}.json")

    def _read_cache(self, cache_key: str) -> Optional[str]:
        """Read cached LLM response if valid (within TTL)."""
        try:
            cache_file = self._get_cache_path(cache_key)
            if not os.path.exists(cache_file):
                return None

            mtime = os.path.getmtime(cache_file)
            age_hours = (datetime.now().timestamp() - mtime) / 3600
            if age_hours > self._cache_ttl_hours:
                logger.info(f"[Cache] Expired ({age_hours:.1f}h old): {cache_key}")
                return None

            with open(cache_file, "r") as f:
                data = json.load(f)
            return data.get("content")
        except Exception as e:
            logger.debug(f"[Cache] Read failed: {e}")
            return None

    def _write_cache(self, cache_key: str, content: str):
        """Write LLM response to cache."""
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
            cache_file = self._get_cache_path(cache_key)
            with open(cache_file, "w") as f:
                json.dump({"content": content, "cached_at": datetime.now().isoformat()}, f)
        except Exception as e:
            logger.debug(f"[Cache] Write failed: {e}")

    async def validate_api_key(self, provider: str, api_key: str) -> bool:
        """Validate if the given API key is active and working."""
        try:
            if provider == "gemini":
                client = genai.Client(api_key=api_key)
                loop = asyncio.get_event_loop()
                def _test():
                    client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents="Say 'OK'",
                        config={"max_output_tokens": 5}
                    )
                await loop.run_in_executor(None, _test)
                return True
            elif provider == "deepseek":
                import httpx
                client = OpenAI(
                    api_key=api_key,
                    base_url=self.deepseek_base_url,
                    timeout=httpx.Timeout(10.0, connect=5.0),
                )
                loop = asyncio.get_event_loop()
                def _test():
                    client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": "Say 'OK'"}],
                        max_tokens=2
                    )
                await loop.run_in_executor(None, _test)
                return True
            elif provider == "openrouter":
                import httpx
                client = OpenAI(
                    api_key=api_key,
                    base_url=self.openrouter_base_url,
                    timeout=httpx.Timeout(10.0, connect=5.0),
                )
                loop = asyncio.get_event_loop()
                def _test():
                    client.chat.completions.create(
                        model="tencent/hy3",
                        messages=[{"role": "user", "content": "Say 'OK'"}],
                        max_tokens=2
                    )
                await loop.run_in_executor(None, _test)
                return True
            return False
        except Exception as e:
            err_msg = str(e).lower()
            if any(term in err_msg for term in ["invalid", "key not", "unauthorized", "authentication", "incorrect", "401"]):
                logger.error(f"API key validation failed for {provider}: {e}")
                return False
            # For other errors (like timeout/503), assume key is valid to prevent false negatives
            logger.warning(f"Key validation got transient error, assuming valid: {e}")
            return True

    def get_gemini_api_key(self, api_key=None):
        if api_key:
            return api_key
        if self._gemini_api_key_override:
            return self._gemini_api_key_override
        load_dotenv(os.path.join(root_dir, ".env"), override=True)
        load_dotenv(os.path.join(root_dir, ".env.runtime"), override=True)
        return os.getenv("GEMINI_API_KEY")

    def get_deepseek_api_key(self, api_key=None):
        if api_key:
            return api_key
        if self._deepseek_api_key_override:
            return self._deepseek_api_key_override
        current = os.getenv("DEEPSEEK_API_KEY")
        if current:
            return current
        load_dotenv(os.path.join(root_dir, ".env"), override=False)
        load_dotenv(os.path.join(root_dir, ".env.runtime"), override=False)
        return os.getenv("DEEPSEEK_API_KEY")

    def get_openrouter_api_key(self, api_key=None):
        if api_key:
            return api_key
        if self._openrouter_api_key_override:
            return self._openrouter_api_key_override
        current = os.getenv("OPENROUTER_API_KEY")
        if current:
            return current
        load_dotenv(os.path.join(root_dir, ".env"), override=False)
        load_dotenv(os.path.join(root_dir, ".env.runtime"), override=False)
        return os.getenv("OPENROUTER_API_KEY")

    def gemini_client(self, api_key=None):
        target_key = self.get_gemini_api_key(api_key)
        if self._gemini_client is None or (target_key and target_key != self._last_gemini_key):
            if target_key:
                try:
                    self._gemini_client = genai.Client(api_key=target_key)
                    self._last_gemini_key = target_key
                except Exception as e:
                    logger.info(f"Failed to initialize Gemini Client: {e}")
                    return None
            else:
                return None
        return self._gemini_client

    def deepseek_client(self, api_key=None):
        target_key = self.get_deepseek_api_key(api_key)
        if self._deepseek_client is None or (target_key and target_key != self._last_deepseek_key):
            if target_key:
                import httpx
                # DeepSeek API can intermittently hang. Use a shorter read timeout
                # (60s) so a stuck request fails fast, and rely on SDK auto-retry
                # (max_retries) to recover instead of waiting the full 120s.
                _read_timeout = float(os.getenv("DEEPSEEK_READ_TIMEOUT", "60.0"))
                _max_retries = int(os.getenv("DEEPSEEK_MAX_RETRIES", "3"))
                self._deepseek_client = OpenAI(
                    api_key=target_key,
                    base_url=self.deepseek_base_url,
                    timeout=httpx.Timeout(_read_timeout, connect=15.0),
                    max_retries=_max_retries,
                )
                self._last_deepseek_key = target_key
            else:
                raise ValueError("DEEPSEEK_API_KEY is missing.")
        return self._deepseek_client

    def openrouter_client(self, api_key=None):
        target_key = self.get_openrouter_api_key(api_key)
        if self._openrouter_client is None or (target_key and target_key != self._last_openrouter_key):
            if target_key:
                import httpx
                _read_timeout = float(os.getenv("OPENROUTER_READ_TIMEOUT", "60.0"))
                _max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "3"))
                self._openrouter_client = OpenAI(
                    api_key=target_key,
                    base_url=self.openrouter_base_url,
                    timeout=httpx.Timeout(_read_timeout, connect=15.0),
                    max_retries=_max_retries,
                )
                self._last_openrouter_key = target_key
            else:
                raise ValueError("OPENROUTER_API_KEY is missing.")
        return self._openrouter_client

    def default_client(self):
        if self._default_client is None:
            if self.default_api_key:
                import httpx
                self._default_client = OpenAI(
                    api_key=self.default_api_key,
                    base_url=self.default_base_url,
                    timeout=httpx.Timeout(120.0, connect=15.0),
                )
            else:
                raise ValueError("DEFAULT_LLM_API_KEY is missing.")
        return self._default_client

    def _llm_stream_timeout_seconds(self) -> float:
        return float(os.getenv("LLM_STREAM_TIMEOUT_SECONDS", "300"))

    async def _run_blocking_llm_call(self, provider: str, func) -> str:
        timeout_seconds = self._llm_stream_timeout_seconds()
        result_queue: queue.Queue = queue.Queue(maxsize=1)

        def _target():
            try:
                result_queue.put((True, func()), block=False)
            except Exception as exc:
                result_queue.put((False, exc), block=False)

        thread = threading.Thread(target=_target, name=f"llm-{provider}-stream", daemon=True)
        thread.start()
        deadline = time.monotonic() + timeout_seconds
        while thread.is_alive():
            if os.path.exists(".stop"):
                raise Exception("Analysis stopped by user.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{provider} streaming call timed out after {timeout_seconds:.0f}s")
            await asyncio.sleep(min(0.5, remaining))

        ok, value = result_queue.get_nowait()
        if ok:
            return value
        raise value

    async def generate_content(self, prompt: str, model: str = None, temperature: float = 0.3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None, openrouter_api_key: Optional[str] = None, cache_key: Optional[str] = None, prompt_version_id: Optional[str] = None, response_schema: Optional[Any] = None) -> str:
        try:
            loop = asyncio.get_running_loop()
            _original_on_chunk = on_chunk
            _last_call_time = [0.0]
            _accumulated_args = [0] # for accumulating char counts if args[0] is count
            def _safe_on_chunk(*args, **kwargs):
                if _original_on_chunk:
                    now = time.monotonic()
                    # If it's just a count update, accumulate it
                    if not kwargs and len(args) == 1 and isinstance(args[0], int):
                        _accumulated_args[0] += args[0]
                    
                    # Send if it has kwargs, or if 0.5s passed, or if it's not just a simple int update
                    if kwargs or (now - _last_call_time[0] > 0.5) or len(args) != 1 or not isinstance(args[0], int):
                        _last_call_time[0] = now
                        if not kwargs and len(args) == 1 and isinstance(args[0], int):
                            val = _accumulated_args[0]
                            _accumulated_args[0] = 0
                            loop.call_soon_threadsafe(_original_on_chunk, val)
                        elif kwargs:
                            # Pass accumulated value if first arg is int
                            if len(args) > 0 and isinstance(args[0], int):
                                val = _accumulated_args[0] + args[0]
                                _accumulated_args[0] = 0
                                new_args = (val,) + args[1:]
                                loop.call_soon_threadsafe(lambda: _original_on_chunk(*new_args, **kwargs))
                            else:
                                loop.call_soon_threadsafe(lambda: _original_on_chunk(*args, **kwargs))
                        else:
                            loop.call_soon_threadsafe(_original_on_chunk, *args)
            on_chunk = _safe_on_chunk
        except RuntimeError:
            pass

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
            result_text = await self._generate_content_inner(prompt, model, temperature, on_chunk, gemini_api_key, deepseek_api_key, openrouter_api_key, cache_key, response_schema)
            return result_text
        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            if prompt_version_id:
                try:
                    # Determine provider
                    provider = "unknown"
                    res_model = model or self.default_model
                    if res_model:
                        if res_model.lower().startswith("gemini"):
                            provider = "gemini"
                        elif "deepseek" in res_model.lower():
                            provider = "deepseek"
                        elif res_model.lower().startswith("tencent/") or "/" in res_model:
                            provider = "openrouter"
                        else:
                            provider = "default"
                            
                    prompt_tokens = usage_ctx.get("promptTokens", 0) - start_prompt
                    cand_tokens = usage_ctx.get("candidatesTokens", 0) - start_cand
                    
                    if prompt_tokens == 0:
                        prompt_tokens = len(str(prompt).encode('utf-8')) // 3
                    if cand_tokens == 0 and result_text:
                        cand_tokens = len(str(result_text).encode('utf-8')) // 3
                        
                    # Schema validation
                    schema_passed = True
                    if result_text and ("json" in prompt.lower() or (res_model and "json" in res_model.lower())):
                        try:
                            import json
                            import re
                            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                            if json_match:
                                json.loads(json_match.group(0))
                            else:
                                schema_passed = False
                        except Exception:
                            logger.exception("Failed to validate JSON schema in LLM response")
                            schema_passed = False
                    elif not result_text:
                        schema_passed = False
                        
                    from ..prompting.runtime import prompt_runtime
                    prompt_runtime.record_run({
                        "prompt_version_id": prompt_version_id,
                        "model": res_model,
                        "provider": provider,
                        "input_tokens": prompt_tokens,
                        "output_tokens": cand_tokens,
                        "latency_ms": latency_ms,
                        "tool_calls": 0,
                        "schema_validation_passed": schema_passed
                    })
                except Exception as ex:
                    logger.error(f"Error recording prompt run metrics: {ex}")
            if created_ctx:
                current_token_usage.reset(token)

    async def _generate_content_inner(self, prompt: str, model: str = None, temperature: float = 0.3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None, openrouter_api_key: Optional[str] = None, cache_key: Optional[str] = None, response_schema: Optional[Any] = None) -> str:
        """
        Generate content with built-in quality-gate retry.
        Retries up to 2 extra times if response is truncated or garbage.
        Routes through default provider unless model is explicitly gemini-*.
        """
        if cache_key:
            cache_result = self._read_cache(cache_key)
            if cache_result is not None:
                logger.info(f"[Cache] HIT for {cache_key}")
                if on_chunk:
                    on_chunk(len(cache_result))
                return cache_result

        # Resolve model: use default from env if not specified
        if not model:
            model = self.default_model
        
        max_quality_retries = 2
        for quality_attempt in range(max_quality_retries + 1):
            providers = []
            if model.lower().startswith("gemini"):
                providers = [
                    ("gemini", self._generate_gemini),
                    ("default", self._generate_default)
                ]
            else:
                providers = [
                    ("openrouter", self._generate_openrouter),
                    ("deepseek", self._generate_deepseek),
                    ("default", self._generate_default),
                    ("gemini", self._generate_gemini)
                ]
            
            result_text = None
            for provider_name, generate_func in providers:
                try:
                    kwargs = {"temperature": temperature, "on_chunk": on_chunk, "response_schema": response_schema}
                    if provider_name == "gemini":
                        kwargs["api_key"] = gemini_api_key
                        if not self.get_gemini_api_key(gemini_api_key):
                            continue
                    elif provider_name == "deepseek":
                        kwargs["api_key"] = deepseek_api_key
                        if not self.get_deepseek_api_key(deepseek_api_key):
                            continue
                    elif provider_name == "openrouter":
                        kwargs["api_key"] = openrouter_api_key
                        if not self.get_openrouter_api_key(openrouter_api_key):
                            continue
                    elif provider_name == "default":
                        if not self.default_api_key:
                            continue
                        
                    result_text = await generate_func(prompt, model, **kwargs)
                    if result_text:
                        break
                except Exception as e:
                    error_msg = str(e)
                    if any(code in error_msg for code in ["429", "quota", "503", "524", "500", "502", "timeout", "connection", "RateLimit"]):
                        logger.error(f"[{provider_name}] failed ({error_msg}), falling back to next provider...")
                        continue
                    logger.error(f"[{provider_name}] non-retryable error ({error_msg}), falling back...")
                    continue
            
            if not result_text:
                raise ValueError(f"All providers failed for model: {model}.")



            # Quality gate: detect truncated responses
            if result_text and len(result_text) < 150:
                if quality_attempt < max_quality_retries:
                    logger.warning(f"WARNING: Very short response ({len(result_text)} chars) — quality retry {quality_attempt+1}/{max_quality_retries}")
                    continue
                else:
                    logger.warning(f"WARNING: Very short response ({len(result_text)} chars) after {max_quality_retries} retries — using anyway")

            # Quality gate: enforce <structured_data> if prompt explicitly requires it
            if result_text and "structured_data" in prompt.lower():
                import re
                if not re.search(r'<structured_data>\s*(\{.*?\})\s*</structured_data>', result_text, re.DOTALL):
                    if quality_attempt < max_quality_retries:
                        logger.warning(f"WARNING: Missing <structured_data> JSON block in output — quality retry {quality_attempt+1}/{max_quality_retries}")
                        continue
                    else:
                        logger.warning("WARNING: Missing <structured_data> persists after retries — using anyway")

            # Quality gate: detect off-topic garbage
            garbage_keywords_str = os.getenv("LLM_GARBAGE_KEYWORDS", "h2020,erasmus,empowering women,stem education")
            garbage_keywords = [k.strip().lower() for k in garbage_keywords_str.split(",") if k.strip()]
            if result_text and any(keyword in result_text[:200].lower() for keyword in garbage_keywords):
                if quality_attempt < max_quality_retries:
                    logger.warning(f"WARNING: Off-topic response — quality retry {quality_attempt+1}/{max_quality_retries}")
                    continue
                else:
                    logger.warning("WARNING: Off-topic response persists after retries — using anyway")

            if result_text and len(result_text) < 200:
                logger.warning(f"WARNING: Short response ({len(result_text)} chars) — may be truncated")

            if cache_key and result_text:
                self._write_cache(cache_key, result_text)

            return result_text

        return result_text  # fallback

    async def _generate_default(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, response_schema: Optional[Any] = None) -> str:
        """Generate via default provider (中转站, OpenAI-compatible). Rate-limited."""
        client = self.default_client()
        max_retries = 10
        retry_delay = 15

        def _stream_generate():
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a professional financial analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": 16384,
                "stream": True,
                "stream_options": {"include_usage": True}
            }
            if response_schema:
                kwargs["response_format"] = {"type": "json_object"}
            if "deepseek" in model.lower():
                kwargs["extra_body"] = {"reasoning": {"effort": "high"}}
            response = client.chat.completions.create(**kwargs)
            content_parts = []
            char_count = 0
            usage_dict = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
            in_reasoning = False
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    text = ""
                    
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        if not in_reasoning:
                            text += "<think>\n"
                            in_reasoning = True
                        text += delta.reasoning_content
                        
                    if delta.content:
                        if in_reasoning:
                            text += "\n</think>\n\n"
                            in_reasoning = False
                        text += delta.content
                        
                    if text:
                        content_parts.append(text)
                        char_count += len(text)
                        if on_chunk:
                            on_chunk(char_count)
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_dict = {
                        "promptTokens": getattr(chunk.usage, 'prompt_tokens', 0),
                        "candidatesTokens": getattr(chunk.usage, 'completion_tokens', 0),
                        "totalTokens": getattr(chunk.usage, 'total_tokens', 0)
                    }
            text_res = "".join(content_parts)
            
            usage_ctx = current_token_usage.get()
            if usage_ctx is not None:
                usage_ctx["promptTokens"] += usage_dict["promptTokens"]
                usage_ctx["candidatesTokens"] += usage_dict["candidatesTokens"]
                usage_ctx["totalTokens"] += usage_dict["totalTokens"]
                
            return text_res

        for attempt in range(max_retries):
            if os.path.exists(".stop"):
                raise Exception("Analysis stopped by user.")
            try:
                # Rate limit: wait for slot before sending request (use tool context for faster throughput)
                async with self._default_rate_limiter.with_context("tool"):
                    result = await self._run_blocking_llm_call("default", _stream_generate)
                if not result:
                    raise ValueError("Default provider returned empty response")
                return result
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Default LLM Error ({model}) on attempt {attempt + 1}/{max_retries}: {error_msg}")
                if any(code in error_msg for code in ["429", "503", "524", "500", "502"]) or "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                    if attempt < max_retries - 1:
                        # Adaptive backoff: increase rate limiter interval on repeated failures
                        if attempt >= 2:
                            current = self._default_rate_limiter._min_interval
                            default = self._default_rate_limiter._default_min_interval
                            self._default_rate_limiter._min_interval = min(
                                current * 1.5, 30.0
                            )
                            logger.info(f"  [Rate Limiter] Increased min_interval to {self._default_rate_limiter._min_interval:.1f}s")
                        logger.info(f"Waiting {retry_delay}s before retry {attempt + 2}/{max_retries} (no model downgrade)...")
                        for _ in range(int(retry_delay)):
                            await asyncio.sleep(1)
                            if os.path.exists(".stop"):
                                raise Exception("Analysis stopped by user.")
                        retry_delay = min(retry_delay * 2, 120)
                        continue
                raise e

        raise Exception(f"Failed to generate with {model} after {max_retries} attempts.")

    async def _generate_gemini(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None, response_schema: Optional[Any] = None) -> str:
        client = self.gemini_client(api_key=api_key)
        if not client:
            raise ValueError("Gemini client not initialized (missing API key?)")
            
        max_retries = 10
        retry_delay = 15 # Initial delay in seconds
        max_delay = 120 # 2 minute cap
        
        # Strict mode: NO model degradation. Only use the user-selected model.
        # Rate limits are handled by exponential backoff with extended wait times.
        for attempt in range(max_retries):
            # CHECK FOR USER STOP SIGNAL
            if os.path.exists(".stop"):
                logger.info("User stop signal detected (.stop file). Aborting analysis...")
                raise Exception("Analysis stopped by user.")

            try:
                # Assemble generation config
                # Gemini 3.x: temperature/top_p/top_k NOT recommended (model is optimized for defaults)
                config = {
                    "max_output_tokens": 8192,
                }
                if response_schema:
                    config["response_mime_type"] = "application/json"
                    config["response_schema"] = response_schema
                if "gemini-3" in model.lower():
                    # Gemini 3.x best practice: use thinking_level instead of temperature
                    config["thinking_config"] = {"thinking_level": "medium"}
                else:
                    config["temperature"] = temperature
                if "gemini" in model.lower():
                    config["tools"] = [{"google_search": {}}]

                # Use streaming to provide progress updates via on_chunk
                def _stream_generate():
                    content_parts = []
                    char_count = 0
                    usage_dict = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
                    response = client.models.generate_content_stream(
                        model=model,
                        contents=prompt,
                        config=config
                    )
                    for chunk in response:
                        try:
                            text = chunk.text if hasattr(chunk, 'text') and chunk.text else ""
                        except (ValueError, AttributeError):
                            # Some chunks are grounding metadata without text
                            text = ""
                        if text:
                            content_parts.append(text)
                            char_count += len(text)
                            if on_chunk:
                                on_chunk(char_count)
                        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                            usage_dict = {
                                "promptTokens": getattr(chunk.usage_metadata, 'prompt_token_count', 0),
                                "candidatesTokens": getattr(chunk.usage_metadata, 'candidates_token_count', 0),
                                "totalTokens": getattr(chunk.usage_metadata, 'total_token_count', 0)
                            }
                    text_res = "".join(content_parts)
                    
                    usage_ctx = current_token_usage.get()
                    if usage_ctx is not None:
                        usage_ctx["promptTokens"] += usage_dict["promptTokens"]
                        usage_ctx["candidatesTokens"] += usage_dict["candidatesTokens"]
                        usage_ctx["totalTokens"] += usage_dict["totalTokens"]
                        
                    return text_res

                result = await self._run_blocking_llm_call("gemini", _stream_generate)
                
                if result:
                    return result
                else:
                    raise ValueError("Gemini streaming returned empty response")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Gemini Error ({model}) on attempt {attempt + 1}/{max_retries}: {error_msg}")
                
                # Retry on 429 Quota Exceeded or 503 Service Unavailable — extend wait, never degrade
                if "429" in error_msg or "quota" in error_msg.lower() or "503" in error_msg:
                    if attempt < max_retries - 1:
                        logger.info(f"Rate limit hit. Waiting {retry_delay}s before retry {attempt + 2}/{max_retries} (no model downgrade)...")
                        if on_chunk:
                            on_chunk(0, f"API 触发限流，等待 {retry_delay} 秒重试... (第 {attempt + 1} 次)")
                        # Interruptible sleep
                        for _ in range(int(retry_delay)):
                            await asyncio.sleep(1)
                            if os.path.exists(".stop"):
                                logger.info("User stop signal detected during wait. Aborting...")
                                raise Exception("Analysis stopped by user.")
                        
                        retry_delay = min(retry_delay * 2, max_delay)
                        continue
                
                # Non-retryable error: raise immediately, no fallback
                logger.error(f"Non-retryable error with {model}. Strict mode: no model downgrade.")
                raise e
                
        raise Exception(f"Failed to generate content with {model} after {max_retries} attempts due to rate limits. No model downgrade allowed.")

    async def _generate_deepseek(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None, response_schema: Optional[Any] = None) -> str:
        client = self.deepseek_client(api_key=api_key)
        max_retries = 10
        retry_delay = 15
        max_delay = 60
        
        # Only V4 models are supported; pass model name directly
        final_model = model
        
        def _stream_generate():
            """Blocking streaming call — runs in thread for async compatibility."""
            kwargs = {
                "model": final_model,
                "messages": [
                    {"role": "system", "content": "You are a professional financial analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": 16384,
                "stream": True,
                "stream_options": {"include_usage": True},
                "extra_body": {"reasoning": {"effort": "high"}},
            }
            if response_schema:
                kwargs["response_format"] = {"type": "json_object"}
            response = self.deepseek_client(api_key=api_key).chat.completions.create(**kwargs)
            content_parts = []
            char_count = 0
            usage_dict = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
            in_reasoning = False
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    text = ""
                    
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        if not in_reasoning:
                            text += "<think>\n"
                            in_reasoning = True
                        text += delta.reasoning_content
                        
                    if delta.content:
                        if in_reasoning:
                            text += "\n</think>\n\n"
                            in_reasoning = False
                        text += delta.content
                        
                    if text:
                        content_parts.append(text)
                        char_count += len(text)
                        if on_chunk:
                            on_chunk(char_count)
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_dict = {
                        "promptTokens": getattr(chunk.usage, 'prompt_tokens', 0),
                        "candidatesTokens": getattr(chunk.usage, 'completion_tokens', 0),
                        "totalTokens": getattr(chunk.usage, 'total_tokens', 0)
                    }
            text_res = "".join(content_parts)
            
            usage_ctx = current_token_usage.get()
            if usage_ctx is not None:
                usage_ctx["promptTokens"] += usage_dict["promptTokens"]
                usage_ctx["candidatesTokens"] += usage_dict["candidatesTokens"]
                usage_ctx["totalTokens"] += usage_dict["totalTokens"]
                
            return text_res
        
        for attempt in range(max_retries):
            try:
                result = await self._run_blocking_llm_call("deepseek", _stream_generate)
                if not result:
                    raise ValueError("DeepSeek returned empty streaming response")
                return result
            except Exception as e:
                error_msg = str(e)
                logger.error(f"DeepSeek Error ({final_model}) on attempt {attempt + 1}/{max_retries}: {error_msg}")
                
                # Retry on transient errors: 429 Quota, 503/524 Server, empty response, connection errors
                if "429" in error_msg or "quota" in error_msg.lower() or "503" in error_msg or "524" in error_msg or "500" in error_msg or "502" in error_msg or "empty response" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                    if attempt < max_retries - 1:
                        logger.info(f"Rate limit hit. Waiting {retry_delay}s before retry {attempt + 2}/{max_retries} (no model downgrade)...")
                        if on_chunk:
                            on_chunk(0, f"API 触发限流/网络错误，等待 {retry_delay} 秒重试... (第 {attempt + 1} 次)")
                        # Interruptible sleep
                        for _ in range(int(retry_delay)):
                            await asyncio.sleep(1)
                            if os.path.exists(".stop"):
                                logger.info("User stop signal detected during wait. Aborting...")
                                raise Exception("Analysis stopped by user.")
                        retry_delay = min(retry_delay * 2, max_delay)
                        continue
                
                # Strict mode: Do not fallback or downgrade
                logger.error(f"Strict model mode enforced. Failed to generate with {final_model}. Raising error without fallback.")
                raise e
                
        raise Exception(f"Failed to generate content with {final_model} after {max_retries} attempts due to rate limits.")

    async def _generate_openrouter(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None, response_schema: Optional[Any] = None) -> str:
        client = self.openrouter_client(api_key=api_key)
        max_retries = 10
        retry_delay = 15
        max_delay = 60

        final_model = model

        def _stream_generate():
            """Blocking streaming call — runs in thread for async compatibility."""
            kwargs = {
                "model": final_model,
                "messages": [
                    {"role": "system", "content": "You are a professional financial analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": 16384,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if response_schema:
                kwargs["response_format"] = {"type": "json_object"}
            response = self.openrouter_client(api_key=api_key).chat.completions.create(**kwargs)
            content_parts = []
            reasoning_parts = []
            char_count = 0
            usage_dict = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
            for chunk in response:
                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content_parts.append(delta.content)
                        char_count += len(delta.content)
                        if on_chunk:
                            on_chunk(char_count)
                    elif getattr(delta, "reasoning", None):
                        # Reasoning models (e.g. tencent/hy3:free) may put the answer in
                        # `reasoning` when `content` is absent — buffer it as a fallback
                        # so a reasoning-only response isn't lost as an empty result.
                        reasoning_parts.append(delta.reasoning)
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_dict = {
                        "promptTokens": getattr(chunk.usage, 'prompt_tokens', 0),
                        "candidatesTokens": getattr(chunk.usage, 'completion_tokens', 0),
                        "totalTokens": getattr(chunk.usage, 'total_tokens', 0)
                    }
            text_res = "".join(content_parts)
            if not text_res:
                text_res = "".join(reasoning_parts)

            usage_ctx = current_token_usage.get()
            if usage_ctx is not None:
                usage_ctx["promptTokens"] += usage_dict["promptTokens"]
                usage_ctx["candidatesTokens"] += usage_dict["candidatesTokens"]
                usage_ctx["totalTokens"] += usage_dict["totalTokens"]

            return text_res

        for attempt in range(max_retries):
            try:
                result = await self._run_blocking_llm_call("openrouter", _stream_generate)
                if not result:
                    raise ValueError("OpenRouter returned empty streaming response")
                return result
            except Exception as e:
                error_msg = str(e)
                logger.error(f"OpenRouter Error ({final_model}) on attempt {attempt + 1}/{max_retries}: {error_msg}")

                if "429" in error_msg or "quota" in error_msg.lower() or "503" in error_msg or "524" in error_msg or "500" in error_msg or "502" in error_msg or "empty response" in error_msg.lower() or "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                    if attempt < max_retries - 1:
                        logger.info(f"Rate limit hit. Waiting {retry_delay}s before retry {attempt + 2}/{max_retries} (no model downgrade)...")
                        if on_chunk:
                            on_chunk(0, f"API 触发限流/网络错误，等待 {retry_delay} 秒重试... (第 {attempt + 1} 次)")
                        for _ in range(int(retry_delay)):
                            await asyncio.sleep(1)
                            if os.path.exists(".stop"):
                                logger.info("User stop signal detected during wait. Aborting...")
                                raise Exception("Analysis stopped by user.")
                        retry_delay = min(retry_delay * 2, max_delay)
                        continue

                logger.error(f"Strict model mode enforced. Failed to generate with {final_model}. Raising error without fallback.")
                raise e

        raise Exception(f"Failed to generate content with {final_model} after {max_retries} attempts due to rate limits.")

llm_gateway = LLMGateway()
