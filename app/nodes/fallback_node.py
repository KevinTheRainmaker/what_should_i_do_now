from typing import Dict, Any, List
from app.types.activity import ActivityItem, CategoryType, PriceLevel, SourceType, IndoorOutdoor, LocaleHints, Coordinates
from app.utils.geo import generate_directions_link
from app.utils.korean_text import generate_reason_text

# 바르셀로나 폴백 카탈로그
FALLBACK_CATALOG = [
    {
        "id": "fallback_1",
        "name": "Plaça de Catalunya 벤치 스폿",
        "category": CategoryType.PARK,
        "coords": Coordinates(lat=41.3874, lng=2.1686),
        "indoor_outdoor": IndoorOutdoor.OUTDOOR,
        "theme_tags": ["relax"],
        "reason_text": "[도보 2분] 광장 · 무료. 잠시 앉아서 휴식하기 좋아요."
    },
    {
        "id": "fallback_2", 
        "name": "Passeig de Gràcia 윈도우 쇼핑",
        "category": CategoryType.SHOPPING,
        "coords": Coordinates(lat=41.3910, lng=2.1649),
        "indoor_outdoor": IndoorOutdoor.MIXED,
        "theme_tags": ["shopping"],
        "reason_text": "[도보 5분] 쇼핑가 · 무료. 명품 거리 구경하기 좋아요."
    },
    {
        "id": "fallback_3",
        "name": "El Born 골목 포토스팟", 
        "category": CategoryType.VIEWPOINT,
        "coords": Coordinates(lat=41.3839, lng=2.1823),
        "indoor_outdoor": IndoorOutdoor.OUTDOOR,
        "theme_tags": ["activity"],
        "reason_text": "[도보 8분] 골목 · 무료. 사진 찍기에 완벽해요."
    },
    {
        "id": "fallback_4",
        "name": "Ciutadella 공원 짧은 산책",
        "category": CategoryType.PARK,
        "coords": Coordinates(lat=41.3888, lng=2.1872), 
        "indoor_outdoor": IndoorOutdoor.OUTDOOR,
        "theme_tags": ["relax", "activity"],
        "reason_text": "[도보 12분] 공원 · 무료. 자연 속에서 산책하기 좋아요."
    },
    {
        "id": "fallback_5",
        "name": "La Boquería 시장 구경",
        "category": CategoryType.MARKET,
        "coords": Coordinates(lat=41.3816, lng=2.1722),
        "indoor_outdoor": IndoorOutdoor.INDOOR,
        "theme_tags": ["food", "shopping"],
        "reason_text": "[도보 6분] 시장 · 예산 낮음. 현지 음식 구경하기 좋아요."
    },
    {
        "id": "fallback_6",
        "name": "Gothic Quarter 골목 탐방",
        "category": CategoryType.LANDMARK,
        "coords": Coordinates(lat=41.3828, lng=2.1761),
        "indoor_outdoor": IndoorOutdoor.OUTDOOR,
        "theme_tags": ["activity"],
        "reason_text": "[도보 7분] 구시가지 · 무료. 역사적 분위기 느끼기 좋아요."
    }
]

def generate_fallback(state: Dict[str, Any]) -> Dict[str, Any]:
    """폴백 추천 생성 노드"""
    print("🛡️ [에이전트] 6단계: 폴백 추천 검토 및 보충")
    
    preferences = state["preferences"]
    context = state["context"]
    # 리뷰가 포함된 LLM 선별 결과 사용
    current_items = state.get("llm_selected_items", state.get("ranked_items", []))
    
    # 부족한 개수 계산
    needed_count = max(0, 4 - len(current_items))
    
    print(f"   📊 현재 추천: {len(current_items)}개")
    print(f"   📋 목표: 4개")
    print(f"   ➕ 필요: {needed_count}개")
    
    if needed_count == 0:
        print("   ✅ 충분한 추천 확보 - 폴백 불필요")
        state["fallback_used"] = False
        return state
    
    print(f"   🔄 폴백 카탈로그에서 {needed_count}개 보충 중...")
    
    # 폴백 아이템 점수화 및 선택
    fallback_items = []
    
    for i, fallback_data in enumerate(FALLBACK_CATALOG, 1):
        item = create_fallback_item(fallback_data, context, preferences)
        score = calculate_fallback_score(item, preferences, context)
        item.total_score = score
        fallback_items.append(item)
        print(f"      {i}. {item.name}: {score:.1f}점")
    
    # 점수 순 정렬 후 필요한 개수만큼 선택
    fallback_items.sort(key=lambda x: x.total_score, reverse=True)
    selected_fallbacks = fallback_items[:needed_count]
    
    print(f"   🎯 선택된 폴백 {len(selected_fallbacks)}개:")
    for i, item in enumerate(selected_fallbacks, 1):
        print(f"      {i}. {item.name} ({item.total_score:.1f}점)")
    
    # 기존 아이템과 합치기
    combined_items = current_items + selected_fallbacks
    
    state["ranked_items"] = combined_items
    state["fallback_used"] = needed_count > 0
    
    print(f"   ✅ 최종 추천: {len(combined_items)}개 (폴백 {needed_count}개 포함)\n")
    
    return state

def create_fallback_item(data: Dict[str, Any], context, preferences) -> ActivityItem:
    """폴백 데이터에서 ActivityItem 생성"""
    
    # 거리 및 이동시간 계산
    from app.utils.geo import calculate_distance_meters, calculate_travel_time_minutes
    
    distance = calculate_distance_meters(context.coords, data["coords"])
    travel_time = calculate_travel_time_minutes(distance)
    
    item = ActivityItem(
        id=data["id"],
        name=data["name"],
        category=data["category"],
        price_level=PriceLevel.LOW,  # 대부분 무료/저렴
        rating=None,
        review_count=None,
        open_now=True,  # 공공장소는 대부분 열려있음
        indoor_outdoor=data["indoor_outdoor"],
        coords=data["coords"],
        distance_meters=distance,
        travel_time_min=travel_time,
        expected_wait_min=0,  # 대기시간 없음
        expected_duration_min=20,  # 기본 20분
        budget_hint=PriceLevel.LOW,
        theme_tags=data["theme_tags"],
        source_url=None,
        source=SourceType.FALLBACK,
        locale_hints=LocaleHints(
            local_vibe=True,
            chain=False,
            night_safe=True
        ),
        reason_text=data["reason_text"],
        directions_link=generate_directions_link(data["coords"], data["name"])
    )
    
    return item

def calculate_fallback_score(item: ActivityItem, preferences, context) -> float:
    """폴백 아이템 점수 계산"""
    
    score = 60  # 기본 점수 (검색 결과보다는 낮게)
    
    # 거리 점수 (가까울수록 좋음)
    if item.distance_meters:
        if item.distance_meters <= 500:
            score += 15
        elif item.distance_meters <= 1000:
            score += 10
        else:
            score += 5
    
    # 테마 매칭
    user_themes = set(theme.value for theme in preferences.themes)
    item_themes = set(item.theme_tags)
    
    intersection = user_themes.intersection(item_themes)
    if intersection:
        score += len(intersection) * 5
    
    # 날씨 적합도
    if context.weather.condition == "rain":
        if item.indoor_outdoor == IndoorOutdoor.INDOOR:
            score += 10
        elif item.indoor_outdoor == IndoorOutdoor.OUTDOOR:
            score -= 5
    else:
        if item.indoor_outdoor == IndoorOutdoor.OUTDOOR:
            score += 5
    
    return score
