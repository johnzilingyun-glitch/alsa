import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

def list_models():
    print(f"Testing API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print("\nAvailable Gemini Models:")
            for model in data.get("models", []):
                name = model.get("name")
                print(f" - {name}")
                # Print specific details for 3.x or 2.x models
                if "gemini-3" in name or "gemini-2" in name or "gemini-1.5" in name:
                    print(f"   (DisplayName: {model.get('displayName')}, Version: {model.get('version')})")
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    list_models()
