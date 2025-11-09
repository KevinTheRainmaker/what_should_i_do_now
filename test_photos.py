#!/usr/bin/env python3
import httpx
import json

# API 호출
data = {
    "preferences": {
        "time_bucket": "≤30",
        "budget_level": "mid",
        "themes": ["relax"]
    }
}

try:
    with httpx.Client(timeout=60.0) as client:
        response = client.post("http://localhost:8000/api/recommend", json=data)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Got {len(result['items'])} recommendations\n")
            
            for i, item in enumerate(result["items"], 1):
                print(f"{i}. {item['name']}")
                photos = item.get('photos', [])
                if photos:
                    print(f"   📸 사진 {len(photos)}개:")
                    for j, photo in enumerate(photos):
                        print(f"     {j+1}. {photo[:80]}...")
                else:
                    print("   ❌ 사진 없음")
                print()
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
except Exception as e:
    print(f"❌ Error: {e}")
