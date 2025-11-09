from typing import Dict, Any
from app.types.activity import TimeBucket, ActivityItem
from app.config import TIME_BUCKET_LIMITS, CATEGORY_DEFAULTS, MAX_TRAVEL_TIME_BY_BUCKET
from app.utils.geo import calculate_travel_time_minutes

def classify_time_fitness(state: Dict[str, Any]) -> Dict[str, Any]:
    """시간 버킷 분류 및 적합도 계산 노드"""
    print("⏰ [에이전트] 4단계: 시간 적합도 분류 시작")
    
    preferences = state["preferences"]
    context = state["context"]
    time_bucket = preferences.time_bucket
    
    # 버킷 상한 및 이동시간 제한 가져오기
    bucket_limit = TIME_BUCKET_LIMITS[time_bucket]
    max_travel_time = MAX_TRAVEL_TIME_BY_BUCKET[time_bucket]
    
    print(f"   ⏰ 시간 버킷: {time_bucket}")
    print(f"   ⏱️ 총 시간 상한: {bucket_limit}분" if bucket_limit else "   ⏱️ 총 시간 상한: 제한 없음")
    print(f"   🚶 이동시간 제한: {max_travel_time}분 (총 시간의 25%)")
    
    # 활동 아이템들이 있다면 시간 적합도 계산
    if "activity_items" in state:
        activity_items = state["activity_items"]
        print(f"   🔢 {len(activity_items)}개 아이템의 시간 적합도 계산 중...")
        
        for i, item in enumerate(activity_items, 1):
            item.travel_time_min = calculate_travel_time_from_item(item, context)
            item.expected_wait_min = get_expected_wait_time(item)
            item.expected_duration_min = get_expected_duration(item)
            
            # 이동시간 제한 체크 (남은 시간의 25%)
            travel_time_violation = (item.travel_time_min or 5) > max_travel_time
            
            # 총 시간 계산
            total_time = (item.travel_time_min or 5) + \
                        (item.expected_wait_min or 0) + \
                        (item.expected_duration_min or 20)
            
            # 적합도 점수 계산
            if travel_time_violation:
                # 이동시간 제한 위반 시 매우 낮은 점수
                item.time_fitness_score = 1
                travel_time = item.travel_time_min or 5
                status = f"❌ 이동시간 초과 ({travel_time}분 > {max_travel_time}분)"
            elif bucket_limit is None:  # >120분
                item.time_fitness_score = 20
                status = "✅"
            elif total_time <= bucket_limit:
                item.time_fitness_score = 20
                status = "✅"
            else:
                # 총 시간 초과 시 패널티 적용
                overtime = total_time - bucket_limit
                penalty = min(20, overtime * 2)  # 패널티를 2배로 증가
                item.time_fitness_score = max(0, 20 - penalty)
                status = f"⚠️ 총시간 초과 +{overtime}분"
                
                # 30분 제한의 경우 더 엄격한 패널티
                if bucket_limit == 30 and total_time > bucket_limit + 10:
                    item.time_fitness_score = max(0, 2)  # 최대 2점으로 제한
                    status = f"❌ 총시간 초과 +{overtime}분"
                elif bucket_limit == 30 and total_time > bucket_limit + 5:
                    item.time_fitness_score = max(0, 8)  # 최대 8점으로 제한
                    status = f"⚠️ 총시간 초과 +{overtime}분"
                
                # 좌표 없음 + 시간 초과 시 추가 패널티
                if not item.coords and total_time > bucket_limit:
                    print(f"         💡 {item.name}: 좌표 없음 + 시간 초과 → 추가 패널티 적용")
                    item.time_fitness_score = max(0, item.time_fitness_score - 10)
            
            print(f"      {i}. {item.name}: {total_time}분 (이동{item.travel_time_min}+대기{item.expected_wait_min}+체류{item.expected_duration_min}) {status}")
    
    state["time_bucket_limit"] = bucket_limit
    print("   ✅ 시간 적합도 계산 완료\n")
    return state

def calculate_travel_time_from_item(item: ActivityItem, context) -> int:
    """활동 아이템의 이동 시간 계산 (다중 교통수단 포함)"""
    # 이미 Google Routes API로 계산된 값이 있으면 사용
    if hasattr(item, 'walking_time_min') and item.walking_time_min and item.walking_time_min > 0:
        print(f"      ✅ {item.name}: 이미 계산된 이동시간 사용 - 도보 {item.walking_time_min}분, 차량 {item.driving_time_min}분, 대중교통 {item.transit_time_min}분")
        return item.walking_time_min
    
    # 좌표가 있으면 좌표 기반 계산
    if item.coords and hasattr(context, 'coords') and context.coords:
        try:
            # 기본 거리 계산은 항상 수행
            from app.utils.geo import calculate_distance_meters, calculate_travel_time_minutes
            distance = calculate_distance_meters(context.coords, item.coords)
            item.distance_meters = distance
            travel_time = calculate_travel_time_minutes(distance)
            
            # 기본 추정값 설정 (더 정확한 공식 사용)
            item.walking_time_min = travel_time
            item.driving_time_min = max(3, int(distance / 500))  # 평균 30km/h
            item.transit_time_min = max(5, int(distance / 250))  # 평균 15km/h + 대기시간
            
            print(f"      🚶 {item.name}: 도보 {item.walking_time_min}분, 🚗 차량 {item.driving_time_min}분, 🚇 대중교통 {item.transit_time_min}분 (실제 거리 {distance}m)")
            return travel_time
        except Exception as e:
            print(f"      ❌ {item.name}: 거리 계산 실패 - {e}")
            # 완전 실패 시 기본값
            item.walking_time_min = 15
            item.driving_time_min = 8
            item.transit_time_min = 12
            return 15
    else:
        # 좌표가 없는 경우 장소명이나 지역 정보로 추정
        name_lower = item.name.lower()
        
        # CCIB 주변 지역 거리 기반 추정 (더 정확한 값)
        nearby_keywords = ['poblenou', 'diagonal mar', 'llull', 'forum', 'maresme', 'besòs']
        mid_distance_keywords = ['sagrada familia', 'eixample', 'fort pienc', 'sant martí'] 
        far_keywords = ['gracia', 'gothic', 'born', 'raval', 'sarria', 'les corts', 
                       'sants', 'montjuic', 'ciutadella', 'barrio gotico', 'el born', 'catalunya']
        
        if any(keyword in name_lower for keyword in nearby_keywords):
            # 1-2km 거리 (포블레누, 디아고날마르)
            walking_time = 15
            driving_time = 5
            transit_time = 10
            print(f"      📍 {item.name}: 포블레누/디아고날마르 지역 (1-2km) → 도보 {walking_time}분, 차량 {driving_time}분, 대중교통 {transit_time}분")
        elif any(keyword in name_lower for keyword in mid_distance_keywords):
            # 3-4km 거리 (사그라다 파밀리아, 엑샘플레)
            walking_time = 35
            driving_time = 10
            transit_time = 20
            print(f"      📍 {item.name}: 중거리 지역 (3-4km) → 도보 {walking_time}분, 차량 {driving_time}분, 대중교통 {transit_time}분")
        elif any(keyword in name_lower for keyword in far_keywords):
            # 5-8km 거리 (구시가지, 그라시아)
            walking_time = 60
            driving_time = 15
            transit_time = 25
            print(f"      📍 {item.name}: 원거리 지역 (5-8km) → 도보 {walking_time}분, 차량 {driving_time}분, 대중교통 {transit_time}분")
        else:
            # 알 수 없는 지역 - 중간값
            walking_time = 25
            driving_time = 8
            transit_time = 15
            print(f"      ⚠️ {item.name}: 위치 불명 (추정) → 도보 {walking_time}분, 차량 {driving_time}분, 대중교통 {transit_time}분")
        
        # 추정값 저장
        item.walking_time_min = walking_time
        item.driving_time_min = driving_time
        item.transit_time_min = transit_time
        
        return walking_time  # 기본값으로 도보 시간 반환

def get_expected_wait_time(item: ActivityItem) -> int:
    """카테고리별 예상 대기 시간"""
    category_str = item.category.value
    return CATEGORY_DEFAULTS.get(category_str, {}).get("wait_min", 5)

def get_expected_duration(item: ActivityItem) -> int:
    """카테고리별 예상 체류 시간"""
    category_str = item.category.value
    return CATEGORY_DEFAULTS.get(category_str, {}).get("duration_min", 20)
