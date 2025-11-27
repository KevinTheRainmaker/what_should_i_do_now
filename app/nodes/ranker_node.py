import math
from typing import Dict, Any, List
from app.types.activity import ActivityItem, PriceLevel
from app.utils.korean_text import generate_reason_text
from app.nodes.colored_log_handler import ColoredLogHandler
import logging
logging.basicConfig(level=logging.DEBUG, handlers=[ColoredLogHandler()])
logger = logging.getLogger(__name__)

def rank_activities(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("Step 5: 활동 랭킹 및 선별 시작")
    
    activity_items: List[ActivityItem] = state.get("activity_items", [])
    preferences = state["preferences"]
    context = state["context"]
    
    if not activity_items:
        logger.warning("활동 아이템이 없음 - 빈 결과 반환")
        state["ranked_items"] = []
        return state
    
    logger.info(f"{len(activity_items)}개 아이템 점수 계산 중...")
    
    # 각 아이템에 점수 계산
    scored_items = []
    for i, item in enumerate(activity_items, 1):
        score = calculate_total_score(item, preferences, context)
        logger.debug(item, preferences, context)
        item.total_score = score
        scored_items.append(item)
        logger.info(f"      {i}. {item.name}: {score:.1f}점")
    
    # 점수 순으로 정렬
    scored_items.sort(key=lambda x: x.total_score, reverse=True)
    logger.info("점수순 정렬 완료")
    
    # 시간 제약 사전 필터링 (이동시간 + 총 시간 제한)
    time_bucket_limit = state.get("time_bucket_limit")
    preferences = state.get("preferences", {})
    if hasattr(preferences, 'time_bucket'):
        time_bucket = preferences.time_bucket
    else:
        time_bucket = preferences.get("time_bucket", "30-60")
    
    # 이동시간 제한 가져오기
    max_travel_time_by_bucket = {
        "≤30": 10, "30-60": 20, "60-120": 40, ">120": 60
    }
    max_travel_time = max_travel_time_by_bucket.get(time_bucket, 30)
    
    logger.info(f"시간 제약 필터링 - 이동시간 {max_travel_time}분 이하, 총시간 {time_bucket_limit}분 이하")
    time_filtered = []
    
    for item in scored_items:
        travel_time = item.travel_time_min or 5
        total_time = travel_time + (item.expected_wait_min or 0) + (item.expected_duration_min or 20)
        
        # 이동시간 제한 체크
        travel_time_ok = travel_time <= max_travel_time
        
        # 총 시간 체크 (30분 제한은 더 엄격하게)
        if time_bucket_limit == 30:
            total_time_ok = total_time <= 30
        elif time_bucket_limit:
            total_time_ok = total_time <= time_bucket_limit
        else:
            total_time_ok = True
        
        if travel_time_ok and total_time_ok:
            time_filtered.append(item)
            logger.info(f"      ✅ {item.name}: 이동{travel_time}분, 총{total_time}분 - 포함")
        else:
            reason = []
            if not travel_time_ok:
                reason.append(f"이동시간 초과({travel_time}분>{max_travel_time}분)")
            if not total_time_ok:
                reason.append(f"총시간 초과({total_time}분>{time_bucket_limit}분)")
            logger.info(f"      ❌ {item.name}: {', '.join(reason)} - 제외")
    
    logger.info(f"시간 필터링 후: {len(time_filtered)}개 남음")
    scored_items = time_filtered
    
    # 제약 조건 적용 (체인 중복 금지, 영업 종료 패널티 등)
    logger.info("제약 조건 적용 중 (체인 중복 제거, 카테고리 다양성)...")
    filtered_items = apply_constraints(scored_items)
    
    # 상위 4개 선택
    top_items = filtered_items[:4]
    logger.info(f"상위 {len(top_items)}개 선별 완료:")
    
    # 추천 이유 텍스트 생성
    for i, item in enumerate(top_items, 1):
        item.reason_text = generate_reason_text(item, preferences)
        logger.info(f"      {i}. {item.name} ({item.total_score:.1f}점, {item.category.value})")
        logger.info(f"         → {item.reason_text}")
    
    state["ranked_items"] = top_items
    logger.info("랭킹 완료")
    return state

def calculate_total_score(item: ActivityItem, preferences, context) -> float:
    """총 점수 계산 (0~100)"""
    
    # 거리 점수 (20점)
    distance_score = calculate_distance_score(item)
    
    # 시간 적합도 점수 (20점) - classifier_node에서 계산된 것 사용
    time_fit_score = getattr(item, 'time_fitness_score', 15)
    
    # 예산 적합도 점수 (15점)
    budget_score = calculate_budget_score(item, preferences.budget_level)
    
    # 평점 점수 (15점)
    rating_score = calculate_rating_score(item)
    
    # 날씨 적합도 점수 (10점)
    weather_score = calculate_weather_score(item, context.weather.condition)
    
    # 테마 매칭 점수 (15점)
    theme_score = calculate_theme_score(item, preferences.themes)
    
    # 로컬 감성 점수 (5점)
    local_vibe_score = 5 if not item.locale_hints.chain else 0
    
    total = distance_score + time_fit_score + budget_score + rating_score + weather_score + theme_score + local_vibe_score
    
    # 영업 종료 패널티
    if item.open_now is False:
        total -= 15
    
    return max(0, min(100, total))

def calculate_distance_score(item: ActivityItem) -> float:
    """거리 점수 계산"""
    if not item.distance_meters:
        return 10  # 기본 점수
    
    # exp(-distance/1000) * 20
    score = math.exp(-item.distance_meters / 1000) * 20
    return min(20, score)

def calculate_budget_score(item: ActivityItem, user_budget: PriceLevel) -> float:
    """예산 적합도 점수"""
    item_price = item.price_level
    
    if item_price == PriceLevel.UNKNOWN:
        return 7
    
    # 정확히 매칭
    if item_price == user_budget:
        return 15
    
    # 인접 레벨 매칭
    budget_levels = [PriceLevel.LOW, PriceLevel.MID, PriceLevel.HIGH]
    try:
        user_idx = budget_levels.index(user_budget)
        item_idx = budget_levels.index(item_price)
        if abs(user_idx - item_idx) == 1:
            return 8
    except ValueError:
        pass
    
    return 0

def calculate_rating_score(item: ActivityItem) -> float:
    """평점 점수 계산"""
    if item.rating is None:
        return 7
    
    # (rating / 5) * 15
    return (item.rating / 5.0) * 15

def calculate_weather_score(item: ActivityItem, weather_condition: str) -> float:
    """날씨 적합도 점수"""
    if weather_condition == "rain":
        if item.indoor_outdoor.value == "indoor":
            return 10
        elif item.indoor_outdoor.value == "outdoor":
            return 2
        else:  # mixed
            return 7
    else:
        # 좋은 날씨에는 야외 활동 부스트
        base_score = 7
        if item.indoor_outdoor.value == "outdoor":
            base_score += 3
        return min(10, base_score)

def calculate_theme_score(item: ActivityItem, user_themes) -> float:
    """테마 매칭 점수"""
    user_theme_set = set(theme.value for theme in user_themes)
    item_theme_set = set(item.theme_tags)
    
    intersection = user_theme_set.intersection(item_theme_set)
    
    if len(intersection) == 0:
        return 6  # 기본 점수
    
    # 교집합 크기에 따라 점수
    return min(15, 6 + len(intersection) * 3)

def apply_constraints(items: List[ActivityItem]) -> List[ActivityItem]:
    """제약 조건 적용"""
    
    filtered = []
    seen_chains = set()
    category_counts = {}
    
    for item in items:
        # 체인 중복 금지
        if item.locale_hints.chain:
            chain_key = item.name.lower()
            if chain_key in seen_chains:
                continue
            seen_chains.add(chain_key)
        
        # 카테고리 다양성 (같은 카테고리 최대 2개)
        category = item.category.value
        count = category_counts.get(category, 0)
        if count >= 2:
            continue
        
        category_counts[category] = count + 1
        filtered.append(item)
        
        # 4개까지만
        if len(filtered) >= 4:
            break
    
    return filtered
