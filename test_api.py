import requests
import json

# 테스트 요청 데이터
test_data = {
    "preferences": {
        "time_bucket": "30-60",
        "budget_level": "low", 
        "themes": ["relax"]
    }
}

try:
    # API 요청
    response = requests.post(
        "http://localhost:8000/api/recommend",
        json=test_data,
        timeout=30
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Success! Got {len(data['items'])} recommendations")
        for i, item in enumerate(data['items'], 1):
            print(f"{i}. {item['name']} - {item['reason_text']}")
    else:
        print(f"❌ Error: {response.status_code}")
        
except requests.exceptions.ConnectionError:
    print("❌ Connection failed. Is the server running?")
except Exception as e:
    print(f"❌ Error: {e}")
