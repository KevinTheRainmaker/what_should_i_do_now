"""
이동시간 기반 필터링 노드
Google Routes API를 사용하여 장소 이름으로 직접 이동시간을 계산하고
여유시간의 25-35% 이내인 장소만 필터링
"""

import asyncio
import concurrent.futures
from typing import Dict, Any, List
from app.types.activity import ActivityItem, TimeBucket
from app.utils.geo import get_multi_modal_travel_times_by_name
import logging
from app.nodes.colored_log_handler import ColoredLogHandler
logging.basicConfig(level=logging.DEBUG, handlers=[ColoredLogHandler()])
logger = logging.getLogger(__name__)
import os
def calculate_travel_time_filter(state: Dict[str, Any]) -> Dict[str, Any]:
    """이동시간 기반 사전 필터링 노드"""
    logger.info("Google Routes API 기반 이동시간 필터링")
    
    items: List[ActivityItem] = state.get("activity_items", [])
    preferences = state.get("preferences", {})
    context = state.get("context", {})
    
    if not items:
        logger.warning("활동 아이템이 없음")
        return state
    
    # 시간 제한 계산
    time_bucket = preferences.time_bucket if hasattr(preferences, 'time_bucket') else preferences.get("time_bucket", "30-60")
    time_limits = {
        "≤30": {"total": 30, "travel_min": 8, "travel_max": 10},      # 25-35% of 30min = 7.5-10.5min
        "30-60": {"total": 60, "travel_min": 15, "travel_max": 21},    # 25-35% of 60min = 15-21min
        "60-120": {"total": 120, "travel_min": 30, "travel_max": 42},  # 25-35% of 120min = 30-42min
        ">120": {"total": 180, "travel_min": 45, "travel_max": 63}     # 25-35% of 180min = 45-63min
    }
    
    time_limit = time_limits.get(time_bucket, time_limits["30-60"])
    max_travel_time = time_limit["travel_max"]
    min_travel_time = time_limit["travel_min"]
    
    logger.info(f"시간 제한: {time_bucket} → 이동시간 {min_travel_time}-{max_travel_time}분")
    logger.info(f"기준 위치: {os.getenv('APP_LOCATION')}")
    logger.info(f"총 {len(items)}개 장소의 이동시간 계산 중...")
    
    # 비동기 이동시간 계산을 위한 함수
    def calculate_travel_times_for_items():
        """새 이벤트 루프에서 이동시간 계산"""
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(
                calculate_travel_times_batch(items, max_travel_time)
            )
        finally:
            new_loop.close()
    
    try:
        # 별도 스레드에서 비동기 작업 실행
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(calculate_travel_times_for_items)
            filtered_items = future.result(timeout=45)  # 45초 타임아웃
            
        logger.info(f"이동시간 필터링 완료: {len(items)}개 → {len(filtered_items)}개")
        state["activity_items"] = filtered_items
        
    except Exception as e:
        logger.error(f"이동시간 계산 실패: {e}")
        logger.info("기본 필터링으로 대체")
        # 기본 필터링: 좌표가 있는 것들만 우선
        filtered_items = []
        for item in items:
            if item.coords or len(filtered_items) < 10:  # 좌표 있음 우선 또는 최소 10개 보장
                filtered_items.append(item)
        state["activity_items"] = filtered_items
    
    logger.info(f"최종 결과: {len(state['activity_items'])}개 장소 선별\n")
    return state

async def calculate_travel_times_batch(items: List[ActivityItem], max_travel_time: int) -> List[ActivityItem]:
    """배치로 이동시간 계산 및 필터링"""
    
    # 현재 설정된 위치를 출발지로 사용
    origin_name = os.getenv("APP_LOCATION")
    filtered_items = []
    
    # 병렬 처리를 위해 아이템들을 작은 배치로 분할
    batch_size = 5
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        
        # 배치 내 병렬 처리
        tasks = []
        for item in batch:
            destination_name = f"{item.name}"
            task = calculate_single_item_travel_time(origin_name, destination_name, item, max_travel_time)
            tasks.append(task)
        
        # 배치 결과 수집
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for item, result in zip(batch, batch_results):
            if isinstance(result, ActivityItem):
                filtered_items.append(result)
                # 이동시간 점수에 따라 로그 메시지 구분
                if result.time_fitness_score == 20.0:
                    logger.info(f"{result.name}: 도보 {result.walking_time_min}분 - 시간 적합도 20점")
                elif result.time_fitness_score == 15.0:
                    logger.info(f"{result.name}: 대중교통 {result.transit_time_min}분 - 시간 적합도 15점")
                elif result.time_fitness_score == 10.0:
                    logger.info(f"{result.name}: 차량 {result.driving_time_min}분 - 시간 적합도 10점")
            elif isinstance(result, Exception):
                logger.error(f"{item.name}: 계산 실패 - {result}")
            else:
                logger.info(f"{item.name}: 모든 수단 시간 초과로 제외")
        
        if i + batch_size < len(items):
            await asyncio.sleep(0.5)
    
    return filtered_items

async def calculate_single_item_travel_time(origin_name: str, destination_name: str, item: ActivityItem, max_travel_time: int) -> ActivityItem:
    """단일 아이템의 이동시간 계산 및 필터링
    
    필터링 및 점수 조정 규칙:
    1. 도보 시간이 제한 시간 이내면 최상점 (time_fitness_score = 20)
    2. 도보로는 제한 시간 오버지만 차량이나 대중교통으로는 제한 시간 이내면 중간점수 (time_fitness_score = 10)
    3. 모든 방법에서 제한시간 오버면 제외 (None 반환)
    """
    try:
        # Google Routes API로 이동시간 계산
        travel_times = await get_multi_modal_travel_times_by_name(origin_name, destination_name)
        
        # 결과 적용
        walking = travel_times.get("walking", {})
        driving = travel_times.get("driving", {})
        transit = travel_times.get("transit", {})
        
        item.walking_time_min = walking.get("time_min", 25)
        item.driving_time_min = driving.get("time_min", 8)
        item.transit_time_min = transit.get("time_min", 15)
        # item.distance_meters = walking.get("distance_m", 2000)
        
        # 이동시간 필터링 및 점수 조정
        walking_ok = item.walking_time_min <= max_travel_time
        driving_ok = item.driving_time_min <= max_travel_time
        transit_ok = item.transit_time_min <= max_travel_time
        
        if walking_ok:
            item.time_fitness_score = 20.0  # 최상점
            item.travel_time_min = item.walking_time_min  # 도보 시간을 기본으로 사용
            return item        
        elif transit_ok:
            item.time_fitness_score = 15.0  # 중간점수
            item.travel_time_min = item.transit_time_min
            return item
        elif driving_ok:
            item.time_fitness_score = 10.0  # 낮은점수
            item.travel_time_min = item.driving_time_min
            return item
        else:
            return None
            
    except Exception as e:
        logger.error(f"이동시간 계산 실패: {e}")
        return None
