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
    print("Đang truy vấn danh sách các models được hỗ trợ bởi API Key của bạn...")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"Hỗ trợ: {m.name}")
except Exception as e:
    print(f"Lỗi: {e}")
