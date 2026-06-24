with open("app/services/llm_gateway.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update imports to include Any if not already imported
if "from typing import Optional, List, Dict, Any" not in content:
    content = content.replace("from typing import Optional, List, Dict, Any", "from typing import Optional, List, Dict, Any, Any")

# 2. Update generate_content signature and invocation of _generate_content_inner
content = content.replace(
    'async def generate_content(self, prompt: str, model: str = None, temperature: float = 0.3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None, cache_key: Optional[str] = None, prompt_version_id: Optional[str] = None) -> str:',
    'async def generate_content(self, prompt: str, model: str = None, temperature: float = 0.3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None, cache_key: Optional[str] = None, prompt_version_id: Optional[str] = None, response_schema: Optional[Any] = None) -> str:'
)
content = content.replace(
    'result_text = await self._generate_content_inner(prompt, model, temperature, on_chunk, gemini_api_key, deepseek_api_key, cache_key)',
    'result_text = await self._generate_content_inner(prompt, model, temperature, on_chunk, gemini_api_key, deepseek_api_key, cache_key, response_schema)'
)

# 3. Update _generate_content_inner signature and kwargs construction
content = content.replace(
    'async def _generate_content_inner(self, prompt: str, model: str = None, temperature: float = 0.3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None, cache_key: Optional[str] = None) -> str:',
    'async def _generate_content_inner(self, prompt: str, model: str = None, temperature: float = 0.3, on_chunk: Optional[callable] = None, gemini_api_key: Optional[str] = None, deepseek_api_key: Optional[str] = None, cache_key: Optional[str] = None, response_schema: Optional[Any] = None) -> str:'
)
content = content.replace(
    'kwargs = {"temperature": temperature, "on_chunk": on_chunk}',
    'kwargs = {"temperature": temperature, "on_chunk": on_chunk, "response_schema": response_schema}'
)

# 4. Update _generate_default signature and kwargs
content = content.replace(
    'async def _generate_default(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None) -> str:',
    'async def _generate_default(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, response_schema: Optional[Any] = None) -> str:'
)
old_default_kwargs = """            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a professional financial analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": 16384,
                "stream": True,
                "stream_options": {"include_usage": True}
            }"""
new_default_kwargs = """            kwargs = {
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
                kwargs["response_format"] = {"type": "json_object"}"""
content = content.replace(old_default_kwargs, new_default_kwargs)

# 5. Update _generate_gemini signature and config config
content = content.replace(
    'async def _generate_gemini(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None) -> str:',
    'async def _generate_gemini(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None, response_schema: Optional[Any] = None) -> str:'
)
old_gemini_config = """                config = {
                    "max_output_tokens": 8192,
                }"""
new_gemini_config = """                config = {
                    "max_output_tokens": 8192,
                }
                if response_schema:
                    config["response_mime_type"] = "application/json"
                    config["response_schema"] = response_schema"""
content = content.replace(old_gemini_config, new_gemini_config)

# 6. Update _generate_deepseek signature and kwargs
content = content.replace(
    'async def _generate_deepseek(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None) -> str:',
    'async def _generate_deepseek(self, prompt: str, model: str, temperature: float, on_chunk: Optional[callable] = None, api_key: Optional[str] = None, response_schema: Optional[Any] = None) -> str:'
)
old_deepseek_stream = """        def _stream_generate():
            \"\"\"Blocking streaming call — runs in thread for async compatibility.\"\"\"
            response = self.deepseek_client(api_key=api_key).chat.completions.create(
                model=final_model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=16384,
                stream=True,
                stream_options={"include_usage": True},
                extra_body={"reasoning": {"effort": "high"}},
            )"""
new_deepseek_stream = """        def _stream_generate():
            \"\"\"Blocking streaming call — runs in thread for async compatibility.\"\"\"
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
            response = self.deepseek_client(api_key=api_key).chat.completions.create(**kwargs)"""
content = content.replace(old_deepseek_stream, new_deepseek_stream)

with open("app/services/llm_gateway.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully refactored app/services/llm_gateway.py with response_schema support")
