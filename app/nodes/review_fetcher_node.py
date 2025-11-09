import asyncio
import httpx
import os
import json
from typing import Dict, Any, List, Tuple, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
from app.types.activity import ActivityItem

# 환경변수 로드
load_dotenv()

async def fetch_and_summarize_reviews(state: Dict[str, Any]) -> Dict[str, Any]:
    """구글맵 리뷰 수집 및 LLM 요약 노드"""
    print("📝 [에이전트] 5.5단계: 구글맵 리뷰 수집 및 요약")
    
    # LLM 선별 결과 가져오기
    selected_items: List[ActivityItem] = state.get("llm_selected_items", state.get("ranked_items", []))
    
    if not selected_items:
        print("   ⚠️  선별된 활동이 없음 - 리뷰 수집 건너뜀")
        return state
    
    print(f"   📍 {len(selected_items)}개 장소의 실제 구글맵 리뷰 수집 중...")
    
    # 병렬로 리뷰 수집 (timeout 및 에러 처리 강화)
    review_tasks = []
    for item in selected_items:
        task = asyncio.create_task(fetch_place_reviews_safe(item))
        review_tasks.append(task)
    
    # 전체 리뷰 수집에 대한 timeout 설정 (30초로 증가)
    try:
        review_results = await asyncio.wait_for(
            asyncio.gather(*review_tasks, return_exceptions=True),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        print(f"   ⏰ 리뷰 수집 전체 timeout (30초) - 부분 결과 사용")
        # timeout 발생 시 완료된 작업들의 결과만 수집
        review_results = []
        for task in review_tasks:
            if task.done():
                try:
                    result = task.result()
                    review_results.append(result)
                except Exception as e:
                    print(f"   ❌ 작업 결과 오류: {e}")
                    review_results.append([])
            else:
                task.cancel()
                review_results.append([])
    
    # 수집 결과 통계
    total_reviews = sum(len(reviews) if isinstance(reviews, list) else 0 for reviews in review_results)
    successful_collections = sum(1 for reviews in review_results if isinstance(reviews, list) and len(reviews) > 0)
    print(f"   📊 총 {total_reviews}개의 실제 리뷰 수집 완료 ({successful_collections}/{len(selected_items)}개 장소 성공)")
    
    # OpenAI 클라이언트 초기화 (리뷰 요약용)
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = AsyncOpenAI(api_key=api_key)
        print("   🤖 LLM으로 리뷰 요약 중...")
        
        # 각 장소별로 리뷰 요약
        for i, (item, reviews) in enumerate(zip(selected_items, review_results)):
            if isinstance(reviews, list) and reviews:
                try:
                    # 사용자 preferences에서 자연어 입력 가져오기
                    preferences = state.get("preferences", {})
                    natural_input = getattr(preferences, 'natural_input', None) if hasattr(preferences, 'natural_input') else None
                    
                    summary, price_level = await summarize_reviews_with_llm(client, item.name, reviews, natural_input)
                    item.review_summary = summary
                    item.top_reviews = reviews[:3]  # 상위 3개 리뷰 저장
                    
                    # LLM에서 추출한 가격 레벨 적용
                    if price_level in ["low", "mid", "high"]:
                        from app.types.activity import PriceLevel
                        if price_level == "low":
                            item.price_level = PriceLevel.LOW
                            item.budget_hint = PriceLevel.LOW
                        elif price_level == "mid":
                            item.price_level = PriceLevel.MID
                            item.budget_hint = PriceLevel.MID
                        elif price_level == "high":
                            item.price_level = PriceLevel.HIGH
                            item.budget_hint = PriceLevel.HIGH
                        print(f"      💰 {item.name}: 가격 레벨 업데이트 → {price_level}")
                    
                    print(f"      {i+1}. {item.name}: {len(reviews)}개 리뷰 요약 완료")
                except Exception as e:
                    print(f"      {i+1}. {item.name}: 리뷰 요약 실패 - {e}")
                    item.review_summary = f"총 {len(reviews)}개의 리뷰가 있습니다. 리뷰 요약 처리 중 문제가 발생했습니다."
                    item.top_reviews = reviews[:3] if reviews else []
            else:
                print(f"      {i+1}. {item.name}: 리뷰 수집 실패 또는 없음")
                # 평점 기반 기본 정보 제공
                if item.rating and item.review_count:
                    if item.rating >= 4.0:
                        item.review_summary = f"평점 {item.rating}/5 ({item.review_count:,}개 리뷰) - 높은 평점을 받고 있는 장소입니다."
                    elif item.rating >= 3.5:
                        item.review_summary = f"평점 {item.rating}/5 ({item.review_count:,}개 리뷰) - 괜찮은 평가를 받고 있는 장소입니다."
                    else:
                        item.review_summary = f"평점 {item.rating}/5 ({item.review_count:,}개 리뷰) - 방문 전 추가 정보를 확인해보세요."
                else:
                    item.review_summary = "리뷰 정보를 가져올 수 없습니다."
                item.top_reviews = []
    else:
        print("   ⚠️  OPENAI_API_KEY 없음 - 원본 리뷰만 저장")
        for i, (item, reviews) in enumerate(zip(selected_items, review_results)):
            if isinstance(reviews, list) and reviews:
                item.top_reviews = reviews[:3]
                item.review_summary = f"{len(reviews)}개의 리뷰가 있습니다."
                print(f"      {i+1}. {item.name}: {len(reviews)}개 리뷰 저장")
            else:
                item.top_reviews = []
                item.review_summary = "리뷰가 없습니다."
    
    print("   ✅ 리뷰 수집 및 요약 완료\n")
    return state

async def fetch_place_reviews_safe(item: ActivityItem) -> List[str]:
    """안전한 리뷰 수집 (timeout 및 에러 처리 포함)"""
    try:
        # 개별 장소마다 timeout 설정 (10초로 증가)
        reviews = await asyncio.wait_for(
            fetch_place_reviews(item),
            timeout=10.0
        )
        return reviews
    except asyncio.TimeoutError:
        print(f"   ⏰ {item.name}: 리뷰 수집 timeout (10초)")
        return []
    except Exception as e:
        print(f"   ❌ {item.name}: 리뷰 수집 오류 - {str(e)[:100]}")
        return []

async def fetch_place_reviews(item: ActivityItem) -> List[str]:
    """특정 장소의 실제 구글맵 리뷰 수집"""
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        print(f"   ⚠️  SERPAPI_KEY 없음 - {item.name} 리뷰 수집 건너뜀")
        return []
    
    try:
        # 1단계: 장소 검색으로 place_id 가져오기 (현재 위치 기반)
        current_location = os.getenv("APP_LOCATION", "Barcelona")
        
        # 더 구체적인 검색 쿼리 생성
        # 1. 정확한 이름 + 주소가 있으면 주소 포함
        if hasattr(item, 'address') and item.address:
            search_query = f'"{item.name}" {item.address}'
        # 2. 카테고리가 있으면 카테고리 포함
        elif hasattr(item, 'category') and item.category:
            search_query = f'"{item.name}" {item.category} {current_location}'
        # 3. 기본: 이름 + 현재 위치
        else:
            search_query = f'"{item.name}" {current_location}'
        
        search_params = {
            "engine": "google_maps",
            "q": search_query,
            "api_key": api_key,
            "type": "search"
        }
        
        print(f"   🔍 {item.name}: 검색 쿼리 = '{search_query}'")
        
        async with httpx.AsyncClient(timeout=8.0) as client:  # timeout 증가
            search_response = await client.get("https://serpapi.com/search.json", params=search_params)
            search_data = search_response.json()
            
            # 디버깅: API 응답 확인
            print(f"   🔍 {item.name} 검색 API 응답 키: {list(search_data.keys())}")
            if "error" in search_data:
                print(f"   ❌ API 오류: {search_data['error']}")
                return []
            
            # place_id 찾기 (multiple possible keys)
            places_data = (search_data.get("local_results", []) or 
                          search_data.get("place_results", []) or 
                          search_data.get("places_results", []))
            
            if not places_data:
                print(f"   ⚠️  {item.name}: 모든 검색 결과 키에서 데이터 없음")
                return []
            
            # places_data의 타입 확인
            print(f"   📍 {item.name}: places_data 타입: {type(places_data)}")
            
            if isinstance(places_data, dict):
                print(f"   📄 dict 키들: {list(places_data.keys())}")
                first_result = places_data
            elif isinstance(places_data, list) and places_data:
                print(f"   📍 {item.name}: {len(places_data)}개 장소 발견")
                
                # 정확한 장소 찾기 - 이름 매칭 우선
                best_match = None
                for place in places_data:
                    if isinstance(place, dict):
                        place_title = place.get('title', '').lower()
                        item_name_lower = item.name.lower()
                        
                        # 정확한 이름 매칭 확인
                        if item_name_lower in place_title or place_title in item_name_lower:
                            best_match = place
                            print(f"   ✅ {item.name}: 정확한 매칭 발견 - {place.get('title', 'Unknown')}")
                            break
                        # 부분 매칭 확인
                        elif any(word in place_title for word in item_name_lower.split() if len(word) > 3):
                            if not best_match:  # 첫 번째 부분 매칭 저장
                                best_match = place
                                print(f"   🔍 {item.name}: 부분 매칭 발견 - {place.get('title', 'Unknown')}")
                
                # 매칭된 장소가 없으면 첫 번째 결과 사용
                if not best_match:
                    best_match = places_data[0]
                    print(f"   ⚠️  {item.name}: 정확한 매칭 없음, 첫 번째 결과 사용 - {best_match.get('title', 'Unknown')}")
                
                first_result = best_match
            else:
                print(f"   ⚠️  {item.name}: 예상하지 못한 데이터 형태")
                return []
            
            # place_id 찾기 - 다양한 키 시도
            place_id = None
            
            # 좌표 정보도 함께 추출해서 item에 업데이트
            if isinstance(first_result, dict) and "gps_coordinates" in first_result:
                gps_coords = first_result.get("gps_coordinates")
                if gps_coords and isinstance(gps_coords, dict):
                    try:
                        from app.types.activity import Coordinates
                        lat = gps_coords.get("lat")
                        lng = gps_coords.get("lng")
                        if lat and lng:
                            item.coords = Coordinates(lat=float(lat), lng=float(lng))
                            print(f"   📍 {item.name}: 리뷰 검색에서 좌표 발견 및 업데이트 {lat}, {lng}")
                            
                            # Google Routes API를 사용한 정확한 시간 계산
                            from app.utils.geo import get_multi_modal_travel_times, calculate_distance_meters
                            # CCIB 좌표
                            ccib_coords = Coordinates(lat=41.4095, lng=2.2184)
                            try:
                                # Google Routes API 호출
                                import asyncio
                                
                                # 이벤트 루프가 이미 실행 중인지 확인
                                try:
                                    loop = asyncio.get_running_loop()
                                    # 이미 루프가 실행 중이면 별도 스레드에서 실행
                                    import concurrent.futures
                                    import threading
                                    
                                    def run_in_new_loop():
                                        new_loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(new_loop)
                                        try:
                                            return new_loop.run_until_complete(
                                                get_multi_modal_travel_times(ccib_coords, item.coords)
                                            )
                                        finally:
                                            new_loop.close()
                                    
                                    with concurrent.futures.ThreadPoolExecutor() as executor:
                                        future = executor.submit(run_in_new_loop)
                                        travel_times = future.result(timeout=15)
                                        
                                except RuntimeError:
                                    # 루프가 실행 중이 아니면 직접 실행
                                    travel_times = asyncio.run(get_multi_modal_travel_times(ccib_coords, item.coords))
                                
                                # 결과 적용
                                walking = travel_times.get("walking", {})
                                driving = travel_times.get("driving", {})
                                transit = travel_times.get("transit", {})
                                
                                item.distance_meters = walking.get("distance_m", 0)
                                item.travel_time_min = walking.get("time_min", 20)
                                item.walking_time_min = walking.get("time_min", 20)
                                item.driving_time_min = driving.get("time_min", 8)
                                item.transit_time_min = transit.get("time_min", 15)
                                
                                print(f"   📏 {item.name}: Google Routes API 시간 업데이트 - 도보 {item.walking_time_min}분, 차량 {item.driving_time_min}분, 대중교통 {item.transit_time_min}분 (거리: {item.distance_meters}m)")
                                
                            except Exception as e:
                                print(f"   ❌ {item.name}: Google Routes API 실패, 기본 계산 사용 - {e}")
                                # 기본 거리 계산으로 대체
                                distance = calculate_distance_meters(ccib_coords, item.coords)
                                from app.utils.geo import calculate_travel_time_minutes
                                walking_time = calculate_travel_time_minutes(distance)
                                
                                item.distance_meters = distance
                                item.travel_time_min = walking_time
                                item.walking_time_min = walking_time
                                item.driving_time_min = max(3, int(distance / 500))
                                item.transit_time_min = max(5, int(distance / 250))
                    except Exception as e:
                        print(f"   ❌ {item.name}: 좌표 업데이트 실패 - {e}")
            
            # 사진 정보 추출 - 다양한 키에서 시도
            photo_urls = []
            
            # 1. images 키에서 추출
            images = first_result.get("images", [])
            if images and isinstance(images, list):
                for img in images[:3]:  # 최대 3개만
                    if isinstance(img, dict) and "thumbnail" in img:
                        photo_urls.append(img["thumbnail"])
            
            # 2. photos_link 키에서 추출
            if not photo_urls:
                photos_link = first_result.get("photos_link")
                if photos_link:
                    # photos_link가 있으면 별도 API 호출로 사진 가져오기
                    try:
                        photos_params = {
                            "engine": "google_maps_photos",
                            "place_id": place_id,
                            "api_key": api_key
                        }
                        # 사진 API 호출도 짧은 타임아웃 적용
                        import asyncio
                        photos_response = await asyncio.wait_for(
                            client.get("https://serpapi.com/search.json", params=photos_params),
                            timeout=5.0
                        )
                        photos_data = photos_response.json()
                        
                        if "photos" in photos_data and isinstance(photos_data["photos"], list):
                            for photo in photos_data["photos"][:3]:
                                if isinstance(photo, dict) and "thumbnail" in photo:
                                    photo_urls.append(photo["thumbnail"])
                    except Exception as e:
                        print(f"   ❌ {item.name}: 사진 API 호출 실패 - {e}")
            
            # 3. thumbnail 키에서 추출
            if not photo_urls:
                thumbnail = first_result.get("thumbnail")
                if thumbnail:
                    photo_urls.append(thumbnail)
            
            # 4. serpapi_thumbnail 키에서 추출
            if not photo_urls:
                serpapi_thumbnail = first_result.get("serpapi_thumbnail")
                if serpapi_thumbnail:
                    photo_urls.append(serpapi_thumbnail)
            
            if photo_urls:
                item.photos = photo_urls
                print(f"   📸 {item.name}: {len(photo_urls)}개 사진 발견")
            else:
                print(f"   📸 {item.name}: 사진 없음")
                # 디버깅: 사용 가능한 키들 출력
                available_keys = [k for k in first_result.keys() if 'photo' in k.lower() or 'image' in k.lower() or 'thumbnail' in k.lower()]
                if available_keys:
                    print(f"   🔍 사진 관련 키들: {available_keys}")
            
            for key in ["place_id", "data_id", "cid", "place_data_id"]:
                if key in first_result:
                    place_id = first_result[key]
                    print(f"   📍 {item.name}: {key}에서 place_id {place_id} 발견")
                    
                    # place_id를 item에 저장하고 directions_link 업데이트 (좌표 기반)
                    item.place_id = place_id
                    from app.utils.geo import generate_directions_link
                    # 현재 위치를 출발지로 사용하여 길찾기 링크 생성
                    current_location = os.getenv("APP_LOCATION", "Barcelona")
                    item.directions_link = generate_directions_link(item.coords, item.name, origin_param=current_location)
                    print(f"   🔗 {item.name}: 정확한 길찾기 링크 업데이트 (좌표 기반, 출발지: {current_location})")
                    break
            
            if not place_id:
                print(f"   ⚠️  {item.name}: place_id 없음")
                print(f"   🔍 첫 번째 결과 키들: {list(first_result.keys())}")
                # 첫 번째 결과의 일부 내용도 출력
                if first_result:
                    print(f"   📄 첫 번째 결과 샘플: {str(first_result)[:300]}...")
                return []
            
            
            # 2단계: place_id로 리뷰 가져오기
            review_params = {
                "engine": "google_maps_reviews",
                "place_id": place_id,
                "api_key": api_key,
                "sort_by": "most_relevant"
                # num 파라미터 제거 (초기 페이지에서는 사용 불가)
            }
            
            review_response = await client.get("https://serpapi.com/search.json", params=review_params)
            review_data = review_response.json()
            
            # 리뷰 API 응답 디버깅
            print(f"   🔍 {item.name} 리뷰 API 응답 키: {list(review_data.keys())}")
            if "error" in review_data:
                print(f"   ❌ 리뷰 API 오류: {review_data['error']}")
                return []
            
            reviews = []
            review_items = review_data.get("reviews", [])
            print(f"   📊 {item.name}: API에서 {len(review_items)}개 리뷰 반환")
            
            for i, review in enumerate(review_items):
                snippet = review.get("snippet", "").strip()
                if snippet and len(snippet) > 10:  # 최소 길이 확인
                    reviews.append(snippet)
                    print(f"      리뷰 {i+1}: {snippet[:50]}...")
                else:
                    print(f"      리뷰 {i+1}: 빈 snippet 또는 너무 짧음")
            
            print(f"   ✅ {item.name}: {len(reviews)}개 실제 리뷰 수집")
            return reviews[:5]  # 최대 5개 리뷰
                
    except Exception as e:
        print(f"   ❌ {item.name} 리뷰 수집 실패: {e}")
        import traceback
        print(f"   📄 상세 오류:")
        traceback.print_exc()
        return []

async def summarize_reviews_with_llm(client: AsyncOpenAI, place_name: str, reviews: List[str], natural_input: Optional[str] = None) -> Tuple[str, str]:
    """LLM을 사용해 리뷰들을 요약하고 가격 레벨도 분석"""
    if not reviews:
        return "리뷰가 없습니다.", "unknown"
    
    # 리뷰 텍스트 합치기 (최대 길이 제한)
    combined_reviews = "\n\n".join(reviews[:5])  # 최대 5개 리뷰만 사용
    if len(combined_reviews) > 2000:  # 토큰 절약을 위해 길이 제한
        combined_reviews = combined_reviews[:2000] + "..."
    
    # 자연어 입력이 있으면 추가 고려사항에 포함
    additional_context = ""
    if natural_input:
        additional_context = f"""

**사용자 추가 요청사항**: {natural_input}
위 요청사항을 고려하여 리뷰를 요약해주세요."""

    prompt = f"""다음은 "{place_name}"에 대한 구글맵 리뷰들입니다. 

리뷰들:
{combined_reviews}{additional_context}

다음 두 가지를 분석해주세요:

1. **리뷰 요약**: 2-3문장으로 간결하게 요약
   - 긍정적인 점과 주의할 점을 균형있게 포함
   - 방문객들이 가장 많이 언급하는 특징 위주로 작성
   - 사용자의 추가 요청사항이 있다면 해당 관점에서 리뷰를 분석
   - 한국어로 작성

2. **가격 레벨 분석**: 리뷰에서 언급된 가격 관련 정보를 바탕으로 판단
   - "low": 무료, 저렴, 합리적, cheap, affordable, free, inexpensive, budget-friendly 등
   - "mid": 보통, 적당한, moderate, reasonable, worth the price 등
   - "high": 비싸다, expensive, overpriced, costly, pricey 등
   - "unknown": 가격 관련 언급이 없는 경우

다음 형식으로 응답해주세요:
SUMMARY: [요약 내용]
PRICE_LEVEL: [low/mid/high/unknown]"""

    try:
        # LLM 호출에도 timeout 설정 (10초)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 여행 리뷰를 요약하는 전문가입니다. 객관적이고 유용한 요약을 제공합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            ),
            timeout=15.0
        )
        
        result = response.choices[0].message.content.strip()
        
        # 응답 파싱
        summary = "리뷰 요약을 생성할 수 없습니다."
        price_level = "unknown"
        
        lines = result.split('\n')
        for line in lines:
            if line.startswith('SUMMARY:'):
                summary = line.replace('SUMMARY:', '').strip()
            elif line.startswith('PRICE_LEVEL:'):
                price_level = line.replace('PRICE_LEVEL:', '').strip()
        
        print(f"   💰 [PRICE FROM LLM] {place_name}: {price_level}")
        return summary, price_level
        
    except asyncio.TimeoutError:
        print(f"리뷰 요약 LLM timeout (10초)")
        return f"총 {len(reviews)}개의 리뷰가 있습니다. 요약 처리 시간이 초과되었습니다.", "unknown"
    except Exception as e:
        print(f"리뷰 요약 LLM 오류: {e}")
        return f"총 {len(reviews)}개의 리뷰가 있습니다. 직접 확인해보세요!", "unknown"
