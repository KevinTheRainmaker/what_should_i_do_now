import asyncio
import os
from dotenv import load_dotenv
from app.nodes.review_fetcher_node import fetch_place_reviews
from app.types.activity import ActivityItem, CategoryType, PriceLevel, SourceType, LocaleHints, Coordinates

load_dotenv()

async def test_review_collection():
    """리뷰 수집 기능을 개별적으로 테스트"""
    
    # 테스트용 아이템 생성
    test_item = ActivityItem(
        id="test_1",
        name="Ciutadella Park",
        category=CategoryType.PARK,
        price_level=PriceLevel.UNKNOWN,
        rating=4.6,
        review_count=75385,
        open_now=True,
        indoor_outdoor="outdoor",
        coords=Coordinates(lat=41.3851, lng=2.1734),
        budget_hint=PriceLevel.LOW,
        theme_tags=["relax"],
        source=SourceType.SERPAPI_GMAPS,
        locale_hints=LocaleHints(local_vibe=True, chain=False),
        reason_text="테스트",
        directions_link="https://test.com"
    )
    
    print("🔍 리뷰 수집 테스트 시작...")
    print(f"SERPAPI_KEY 상태: {'설정됨' if os.getenv('SERPAPI_KEY') else '없음'}")
    
    try:
        reviews = await fetch_place_reviews(test_item)
        print(f"✅ 수집된 리뷰 개수: {len(reviews)}")
        
        for i, review in enumerate(reviews, 1):
            print(f"   {i}. {review[:100]}...")
            
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_review_collection())
