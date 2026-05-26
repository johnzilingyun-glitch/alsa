import os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__) if '__file__' in dir() else '.', '.env'), override=True)
load_dotenv('/home/zily/alsa/.env', override=True)
from google import genai
key = os.getenv("GEMINI_API_KEY")
print(f"Key: {key[:10]}..." if key else "No key found")
c = genai.Client(api_key=key)
print("Sending test request...")
r = c.models.generate_content(model="gemini-2.5-flash", contents="Say hello in Chinese, 5 words max")
print(f"Response: {r.text[:200]}")
print("SUCCESS")
