from google import genai
import os
from dotenv import load_dotenv

load_dotenv(override=True)
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

try:
    for model in client.models.list():
        print(model)
except Exception as e:
    print(f"Error: {e}")
