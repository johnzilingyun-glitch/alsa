from google import genai
import os
from dotenv import load_dotenv

load_dotenv(override=True)
api_key = os.getenv("GEMINI_API_KEY")
print(f"API Key: {api_key[:10]}...")

client = genai.Client(api_key=api_key)
try:
    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents="Hello, say 'Key Working'"
    )
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
