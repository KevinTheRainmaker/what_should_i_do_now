import os
from dotenv import load_dotenv

load_dotenv()

openai_key = os.getenv("OPENAI_API_KEY")
print(f"OPENAI_API_KEY: {'설정됨' if openai_key else '없음'}")
if openai_key:
    print(f"키 시작: {openai_key[:10]}...")
