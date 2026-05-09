import os
import sys

# Add the project root to the python path so imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.llm_gateway import llm_gateway
import asyncio

async def test_gemini():
    try:
        res = await llm_gateway._generate_gemini("Hello, who are you?", "gemini-3.1-pro-preview", 0.7)
        print("Success! Response:", res[:50])
    except Exception as e:
        print("Failed!", e)

asyncio.run(test_gemini())
