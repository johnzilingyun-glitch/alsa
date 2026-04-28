import os
from google import genai
from openai import OpenAI
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load .env
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
load_dotenv(os.path.join(root_dir, ".env"), override=True)

class LLMGateway:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self._gemini_client = None
        self._deepseek_client = None
        
        if not self.gemini_api_key:
            print("WARNING: GEMINI_API_KEY not found in LLMGateway.")
        if not self.deepseek_api_key:
            print("WARNING: DEEPSEEK_API_KEY not found in LLMGateway.")

    @property
    def gemini_client(self):
        if self._gemini_client is None:
            if self.gemini_api_key:
                try:
                    self._gemini_client = genai.Client(api_key=self.gemini_api_key)
                except Exception as e:
                    print(f"Failed to initialize Gemini Client: {e}")
                    return None
            else:
                return None
        return self._gemini_client

    @property
    def deepseek_client(self):
        if self._deepseek_client is None:
            if self.deepseek_api_key:
                self._deepseek_client = OpenAI(
                    api_key=self.deepseek_api_key,
                    base_url="https://api.deepseek.com"
                )
            else:
                raise ValueError("DEEPSEEK_API_KEY is missing.")
        return self._deepseek_client

    async def generate_content(self, prompt: str, model: str = "gemini-3.1-pro-preview", temperature: float = 0.7) -> str:
        """
        Generate content using the specified model (Gemini or DeepSeek).
        """
        if "deepseek" in model.lower():
            return await self._generate_deepseek(prompt, model, temperature)
        else:
            return await self._generate_gemini(prompt, model, temperature)

    async def _generate_gemini(self, prompt: str, model: str, temperature: float) -> str:
        try:
            client = self.gemini_client
            if not client:
                raise ValueError("Gemini client not initialized (missing API key?)")
                
            import asyncio
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
                config={
                    "temperature": temperature,
                }
            )
            
            if response and hasattr(response, 'text'):
                return response.text
            elif response and isinstance(response, str):
                return response
            else:
                raise ValueError(f"Unexpected response type from Gemini: {type(response)}")
        except Exception as e:
            print(f"Gemini Error ({model}): {e}")
            # Fallback to DeepSeek if Gemini fails and we have a key
            if self.deepseek_api_key:
                print("Gemini failed, falling back to DeepSeek (deepseek-v4-pro)...")
                return await self._generate_deepseek(prompt, "deepseek-v4-pro", temperature)
            raise e

    async def _generate_deepseek(self, prompt: str, model: str, temperature: float) -> str:
        try:
            # Map legacy aliases to V4 equivalents for future-proofing
            model_map = {
                "deepseek-chat": "deepseek-v4-pro",
                "deepseek-reasoner": "deepseek-v4-pro"
            }
            final_model = model_map.get(model, model)
            
            import asyncio
            response = await asyncio.to_thread(
                self.deepseek_client.chat.completions.create,
                model=final_model,
                messages=[
                    {"role": "system", "content": "You are a professional financial analyst expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"DeepSeek Error ({model}): {e}")
            # Fallback to Gemini if DeepSeek fails and we have a key
            if self.gemini_api_key:
                print("DeepSeek failed, falling back to Gemini (gemini-3.1-flash-lite-preview)...")
                return await self._generate_gemini(prompt, "gemini-3.1-flash-lite-preview", temperature)
            raise e

llm_gateway = LLMGateway()
