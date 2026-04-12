import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("Không tìm thấy GOOGLE_API_KEY trong file .env!")
    exit(1)

genai.configure(api_key=api_key)

try:
    print(f"Checking available models for Key: {api_key[:10]}...")
    models = genai.list_models()
    print("Available models:")
    for m in models:
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name} ({m.display_name})")
except Exception as e:
    print(f"Error: {e}")

