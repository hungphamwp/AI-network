import os
import sys
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
key = os.getenv("GOOGLE_API_KEY")
print(f"Python Version: {sys.version}")
print(f"Testing Key: {key[:10]}...{key[-4:] if key else ''}")

try:
    llm = ChatGoogleGenerativeAI(temperature=0, model="gemini-2.5-flash")
    print("Sending request to Google...")
    res = llm.invoke("Hello, simple test.")
    print("SUCCESS:", res.content)
except Exception as e:
    print("FAILED!")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Detail: {str(e)}")
