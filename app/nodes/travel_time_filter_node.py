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

def calculate_travel_time_filter(state: Dict[str, Any]) -> Dict[str, Any]:
    """이동시간 기반 사전 필터링 노드"""
    print("🚗 [에이전트] 3.5단계: Google Routes API 기반 이동시간 필터링")
    
    items: List[ActivityItem] = state.get("activity_items", [])
    preferences = state.get("preferences", {})
    context = state.get("context", {})
    
    if not items:
        print("   ⚠️ 활동 아이템이 없음")
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
    
    print(f"   ⏰ 시간 제한: {time_bucket} → 이동시간 {min_travel_time}-{max_travel_time}분")
    print(f"   📍 기준 위치: CCIB (Centre de Convencions Internacional de Barcelona)")
    print(f"   🔍 총 {len(items)}개 장소의 이동시간 계산 중...")
    
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
            
        print(f"   ✅ 이동시간 필터링 완료: {len(items)}개 → {len(filtered_items)}개")
        state["activity_items"] = filtered_items
        
    except Exception as e:
        print(f"   ❌ 이동시간 계산 실패: {e}")
        print("   🔄 기본 필터링으로 대체")
        # 기본 필터링: 좌표가 있는 것들만 우선
        filtered_items = []
        for item in items:
            if item.coords or len(filtered_items) < 10:  # 좌표 있음 우선 또는 최소 10개 보장
                filtered_items.append(item)
        state["activity_items"] = filtered_items
    
    print(f"   📊 최종 결과: {len(state['activity_items'])}개 장소 선별\n")
    return state

async def calculate_travel_times_batch(items: List[ActivityItem], max_travel_time: int) -> List[ActivityItem]:
    """배치로 이동시간 계산 및 필터링"""
    import os
    
    # 현재 설정된 위치를 출발지로 사용
    origin_name = os.getenv("APP_LOCATION", "Centre de Convencions Internacional de Barcelona")
    filtered_items = []
    
    # 병렬 처리를 위해 아이템들을 작은 배치로 분할
    batch_size = 5
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        
        # 배치 내 병렬 처리
        tasks = []
        for item in batch:
            # 현재 위치의 도시명 추출
            current_city = origin_name.split(",")[-1].strip() if "," in origin_name else "Barcelona"
            destination_name = f"{item.name}, {current_city}"
            task = calculate_single_item_travel_time(origin_name, destination_name, item, max_travel_time)
            tasks.append(task)
        
        # 배치 결과 수집
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for item, result in zip(batch, batch_results):
            if isinstance(result, ActivityItem):
                filtered_items.append(result)
                print(f"   ✅ {result.name}: 도보 {result.walking_time_min}분 (포함)")
            elif isinstance(result, Exception):
                print(f"   ❌ {item.name}: 계산 실패 - {result}")
            else:
                print(f"   ⏭️ {item.name}: 시간 초과로 제외")
        
        # 배치 간 짧은 대기 (API 레이트 리밋 고려)
        if i + batch_size < len(items):
            await asyncio.sleep(0.5)
    
    return filtered_items

async def calculate_single_item_travel_time(origin_name: str, destination_name: str, item: ActivityItem, max_travel_time: int) -> ActivityItem:
    """단일 아이템의 이동시간 계산 및 필터링"""
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
        item.travel_time_min = item.walking_time_min  # 기본값으로 도보 시간 사용
        item.distance_meters = walking.get("distance_m", 2000)
        
        # 시간 제한 체크 (도보 기준)
        if item.walking_time_min <= max_travel_time:
            return item
        else:
            return None  # 시간 초과로 제외
            
    except Exception as e:
        # API 실패 시 기본값으로 추정하고 포함
        item.walking_time_min = 25
        item.driving_time_min = 8
        item.transit_time_min = 15
        item.travel_time_min = 25
        item.distance_meters = 2000
        
        # 기본값도 시간 제한 체크
        if item.walking_time_min <= max_travel_time:
            return item
        else:
            return None
