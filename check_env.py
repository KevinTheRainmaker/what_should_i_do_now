import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

print("=== 환경변수 확인 ===")
serpapi_key = os.getenv("SERPAPI_KEY")
bing_key = os.getenv("BING_API_KEY")

print(f"SERPAPI_KEY: {'설정됨' if serpapi_key else '없음'}")
if serpapi_key:
    print(f"  값: {serpapi_key[:10]}...")

print(f"BING_API_KEY: {'설정됨' if bing_key else '없음'}")
if bing_key:
    print(f"  값: {bing_key[:10]}...")

print(f"\nUSE_MOCK_SEARCH: {os.getenv('USE_MOCK_SEARCH', 'False')}")

# config.py에서 USE_MOCK_SEARCH 확인
try:
    from app.config import USE_MOCK_SEARCH
    print(f"config.USE_MOCK_SEARCH: {USE_MOCK_SEARCH}")
except ImportError as e:
    print(f"config 로드 오류: {e}")
