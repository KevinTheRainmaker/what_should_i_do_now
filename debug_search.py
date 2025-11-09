import asyncio
from app.nodes.query_node import generate_search_queries
from app.nodes.search_node import search_and_normalize
from app.nodes.context_node import initialize_context
from app.types.activity import Preferences, TimeBucket, PriceLevel, Theme

async def debug_search():
    """검색 과정을 디버깅"""
    
    # 초기 상태 설정
    state = {
        "preferences": Preferences(
            time_bucket=TimeBucket.BETWEEN_30_60,
            budget_level=PriceLevel.LOW,
            themes=[Theme.RELAX]
        ),
        "context_override": {}
    }
    
    print("=== 1. 컨텍스트 초기화 ===")
    state = initialize_context(state)
    print(f"Context: {state['context'].location_label}")
    
    print("\n=== 2. 쿼리 생성 ===")
    state = generate_search_queries(state)
    print(f"생성된 쿼리 {len(state['search_queries'])}개:")
    for i, query in enumerate(state['search_queries'], 1):
        print(f"  {i}. '{query.q}' ({query.target}, {query.locale})")
    
    print("\n=== 3. 검색 및 정규화 ===")
    state = await search_and_normalize(state)
    print(f"검색 결과: {len(state.get('activity_items', []))}개")
    
    for item in state.get('activity_items', [])[:3]:  # 상위 3개만 출력
        print(f"  - {item.name} ({item.source.value})")
    
    return state

if __name__ == "__main__":
    result = asyncio.run(debug_search())
