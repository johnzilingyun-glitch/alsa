import asyncio
import os
from app.services.llm_gateway import LLMGateway

async def test():
    # Set fake API key so it tries to make the call. Or maybe use a real one if env has it.
    os.environ["LLM_STREAM_TIMEOUT_SECONDS"] = "10"
    gateway = LLMGateway()
    # It might fail with auth error or validation error.
    # Validation error happens before network call if it's Pydantic.
    try:
        res = await gateway.generate_content("Hello", model="deepseek-v4-pro")
        print("Success:", res)
    except Exception as e:
        print("Error type:", type(e))
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
