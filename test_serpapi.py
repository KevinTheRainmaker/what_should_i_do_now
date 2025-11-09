import httpx
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test_serpapi_direct():
    """SerpAPI 직접 테스트"""
    
    api_key = os.getenv("SERPAPI_KEY")
    print(f"API Key: {api_key[:10]}..." if api_key else "No API Key")
    
    params = {
        "engine": "google_maps",
        "q": "cafe near Plaça de Catalunya Barcelona",
        "api_key": api_key
    }
    
    try:
        print("📡 SerpAPI 요청 중...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://serpapi.com/search.json", params=params)
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"\n응답 키들: {list(data.keys())}")
                
                if "local_results" in data:
                    local_results = data["local_results"]
                    print(f"Local Results: {len(local_results)}개")
                    
                    for i, place in enumerate(local_results[:3], 1):
                        print(f"  {i}. {place.get('title', 'No title')}")
                        print(f"     Rating: {place.get('rating', 'N/A')}")
                        print(f"     Type: {place.get('type', 'N/A')}")
                else:
                    print("local_results 키가 없습니다.")
                    print(f"전체 응답: {data}")
            else:
                print(f"❌ 오류 응답: {response.text}")
                
    except Exception as e:
        print(f"❌ 예외 발생: {e}")

if __name__ == "__main__":
    asyncio.run(test_serpapi_direct())
