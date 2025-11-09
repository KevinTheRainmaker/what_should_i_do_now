import asyncio
from app.nodes.llm_evaluator_node import llm_evaluate_and_select
from app.types.activity import ActivityItem, CategoryType, PriceLevel, SourceType, LocaleHints, Coordinates, Preferences, TimeBucket, Theme, Context, Weather

async def test_llm_node():
    """LLM 노드를 단독으로 테스트"""
    
    # 테스트 데이터 생성
    test_items = [
        ActivityItem(
            id="test_1",
            name="Café Central Barcelona",
            category=CategoryType.CAFE,
            price_level=PriceLevel.MID,
            rating=4.2,
            review_count=156,
            open_now=True,
            indoor_outdoor="indoor",
            coords=Coordinates(lat=41.3851, lng=2.1734),
            budget_hint=PriceLevel.MID,
            theme_tags=["relax"],
            source=SourceType.SERPAPI_GMAPS,
            locale_hints=LocaleHints(local_vibe=True, chain=False),
            reason_text="테스트",
            directions_link="https://test.com"
        ),
        ActivityItem(
            id="test_2",
            name="Park Güell",
            category=CategoryType.PARK,
            price_level=PriceLevel.LOW,
            rating=4.6,
            review_count=7500,
            open_now=True,
            indoor_outdoor="outdoor",
            coords=Coordinates(lat=41.4145, lng=2.1527),
            budget_hint=PriceLevel.LOW,
            theme_tags=["relax", "activity"],
            source=SourceType.SERPAPI_GMAPS,
            locale_hints=LocaleHints(local_vibe=True, chain=False),
            reason_text="테스트",
            directions_link="https://test.com"
        )
    ]
    
    state = {
        "activity_items": test_items,
        "preferences": Preferences(
            time_bucket=TimeBucket.BETWEEN_30_60,
            budget_level=PriceLevel.LOW,
            themes=[Theme.RELAX]
        ),
        "context": Context(
            location_label="Plaça de Catalunya",
            coords=Coordinates(lat=41.387, lng=2.170),
            weather=Weather(condition="sunny", temp_c=24),
            local_time_iso="2025-09-24T21:00:00"
        )
    }
    
    try:
        result = await llm_evaluate_and_select(state)
        print("✅ LLM 노드 테스트 성공!")
        print(f"선별된 아이템: {len(result.get('llm_selected_items', []))}개")
        
        for item in result.get('llm_selected_items', []):
            print(f"- {item.name}: {getattr(item, 'llm_score', 'N/A')}점")
            print(f"  추천: {getattr(item, 'llm_recommendation', 'N/A')}")
        
    except Exception as e:
        print(f"❌ LLM 노드 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_llm_node())
