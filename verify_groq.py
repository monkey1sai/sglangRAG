import os
import sys
from saga.adapters.groq_adapter import GroqAdapter
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("❌ Error: GROQ_API_KEY not found in .env")
    print("Please add your key to .env file:")
    print("GROQ_API_KEY=gsk_your_key_here")
    sys.exit(1)

print(f"✅ Found API Key: {api_key[:4]}...{api_key[-4:]}")

try:
    print("Testing GroqAdapter connection...")
    adapter = GroqAdapter(api_key=api_key, model="openai/gpt-oss-120b")
    response = adapter.call("Hello, are you working? Please reply with 'Yes, Groq is working!'.")
    content = response["choices"][0]["message"]["content"]
    print(f"\nResponse:\n{content}")
    print("\n✅ Verification Successful!")
except Exception as e:
    print(f"\n❌ Verification Failed: {e}")
