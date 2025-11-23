import asyncio
import httpx
import os
import json
from typing import Dict, Any, List, Tuple, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
from app.types.activity import ActivityItem
from app.utils.geo import calculate_travel_time_minutes, get_multi_modal_travel_times, calculate_distance_meters, generate_directions_link

from app.nodes.colored_log_handler import ColoredLogHandler
import logging
logging.basicConfig(level=logging.DEBUG, handlers=[ColoredLogHandler()])
logger = logging.getLogger(__name__)

# 환경변수 로드
load_dotenv()

async def fetch_and_summarize_reviews(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("Step 6: 구글맵 리뷰 수집 및 요약")
    
    selected_items: List[ActivityItem] = state.get("llm_selected_items", state.get("ranked_items", []))
    
    logger.info(f"{len(selected_items)}개 장소의 실제 구글맵 리뷰 수집 중...")
    
    review_tasks = []
    for item in selected_items:
        # task = asyncio.create_task(fetch_place_reviews_safe(item))
        task = asyncio.create_task(fetch_place_reviews(item))
        review_tasks.append(task)
    
    try:
        review_results = await asyncio.wait_for(
            asyncio.gather(*review_tasks, return_exceptions=True),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        # timeout 발생 시 완료된 작업들의 결과만 수집
        logger.warning("리뷰 수집 전체 timeout (30초)")
        review_results = []
        for task in review_tasks:
            if task.done():
                try:
                    result = task.result()
                    review_results.append(result)
                except Exception as e:
                    logger.error(f"작업 결과 오류: {e}")
                    review_results.append([])
            else:
                task.cancel()
                review_results.append([])
    
    # 수집 결과 통계
    total_reviews = sum(len(reviews) if isinstance(reviews, list) else 0 for reviews in review_results)
    successful_collections = sum(1 for reviews in review_results if isinstance(reviews, list) and len(reviews) > 0)
    logger.info(f"총 {total_reviews}개의 실제 리뷰 수집 완료 ({successful_collections}/{len(selected_items)}개 장소 성공)")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = AsyncOpenAI(api_key=api_key)
        logger.info("LLM으로 리뷰 요약 중...")
        
        for i, (item, reviews) in enumerate(zip(selected_items, review_results)):
            if isinstance(reviews, list) and reviews:
                try:
                    preferences = state.get("preferences", {})
                    natural_input = getattr(preferences, 'natural_input', None) if hasattr(preferences, 'natural_input') else None
                    
                    summary, price_level, price_reason = await curate_places(client, item.name, reviews, natural_input)
                    item.review_summary = summary
                    item.price_level = price_level
                    item.reason_text = price_reason
                    item.top_reviews = reviews[:3]
                    
                    logger.info(f"      {i+1}. {item.name}: {len(reviews)}개 리뷰 요약 완료")
                except Exception as e:
                    logger.error(f"      {i+1}. {item.name}: 리뷰 요약 실패 - {e}")
                    item.review_summary = f"리뷰 요약 처리 중 문제가 발생했습니다. 하단 링크에서 직접 확인해주세요."
                    item.top_reviews = reviews[:3] if reviews else []
            else:
                logger.error(f"      {i+1}. {item.name}: 리뷰 수집 실패 또는 없음")
                item.review_summary = "리뷰 정보를 가져올 수 없습니다. 하단 링크에서 직접 확인해주세요."
                item.top_reviews = []
    else:
        logger.error("OPENAI_API_KEY 없음 - 원본 리뷰만 저장")
        for i, (item, reviews) in enumerate(zip(selected_items, review_results)):
            if isinstance(reviews, list) and reviews:
                item.top_reviews = reviews[:3]
                item.review_summary = f"{len(reviews)}개의 리뷰가 있습니다."
                logger.info(f"      {i+1}. {item.name}: {len(reviews)}개 리뷰 저장")
            else:
                item.top_reviews = []
                item.review_summary = "리뷰가 없습니다."
    
    logger.info("리뷰 수집 및 요약 완료")
    return state

# async def fetch_place_reviews_safe(item: ActivityItem) -> List[str]:
#     try:
#         reviews = await asyncio.wait_for(
#             fetch_place_reviews(item),
#             timeout=15.0
#         )
#         return reviews
#     except asyncio.TimeoutError:
#         logger.warning(f"{item.name}: 리뷰 수집 timeout (15초)")
#         return []
#     except Exception as e:
#         logger.error(f"{item.name}: 리뷰 수집 오류 - {str(e)[:100]}")
#         return []

async def fetch_place_reviews(item: ActivityItem) -> List[str]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        logger.error(f"SERPAPI_KEY 없음 - {item.name} 리뷰 수집 건너뜀")
        return []
    
    try:
        current_location = os.getenv("APP_LOCATION")
        
        if hasattr(item, 'address') and item.address:
            search_query = f'{item.name}, {item.address}'
        else:
            search_query = f'{item.name}'
        logger.info(f"{item.name}: Searching for '{search_query}'")

        search_params = {
            "engine": "google_maps",
            "q": search_query,
            "api_key": api_key,
            "type": "search",
            "ll": f"@{current_location.lat},{current_location.lng},12z"
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            search_response = await client.get("https://serpapi.com/search.json", params=search_params)
            search_data = search_response.json()
            
            # 디버깅: API 응답 확인
            logger.debug(f"{item.name} Search API response keys: {list(search_data.keys())}")
            if "error" in search_data:
                logger.error(f"API error: {search_data['error']}")
                return []
            
            places_data = (search_data.get("local_results", []) or 
                          search_data.get("place_results", []) or 
                          search_data.get("places_results", []))
            
            if not places_data:
                logger.error(f"{item.name}: No data found in all search result keys")
                return []
            
            if isinstance(places_data, dict):
                first_result = places_data
            elif isinstance(places_data, list) and places_data:
                best_match = None
                for place in places_data:
                    if isinstance(place, dict):
                        place_title = place.get('title', '').lower()
                        item_name_lower = item.name.lower()
                        
                        if item_name_lower in place_title or place_title in item_name_lower:
                            best_match = place
                            break
                        elif any(word in place_title for word in item_name_lower.split() if len(word) > 3):
                            if not best_match:
                                best_match = place
                
                if not best_match:
                    best_match = places_data[0]
                
                first_result = best_match
            else:
                logger.error(f"{item.name}: Unexpected data type")
                return []
            
            place_id = None
            
            if isinstance(first_result, dict) and "gps_coordinates" in first_result:
                gps_coords = first_result.get("gps_coordinates")
                if gps_coords and isinstance(gps_coords, dict):
                    try:
                        from app.types.activity import Coordinates
                        lat = gps_coords.get("lat")
                        lng = gps_coords.get("lng")
                        if lat and lng:
                            item.coords = Coordinates(lat=float(lat), lng=float(lng))
                            logger.info(f"{item.name}: Found coordinates - {lat}, {lng}")
                            
                            curr_coords = Coordinates(lat=current_location.lat, lng=current_location.lng)
                            try:
                                import asyncio
                                
                                try:
                                    loop = asyncio.get_running_loop()
                                    import concurrent.futures
                                    import threading
                                    
                                    def run_in_new_loop():
                                        new_loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(new_loop)
                                        try:
                                            return new_loop.run_until_complete(
                                                get_multi_modal_travel_times(curr_coords, item.coords) # 확인필요
                                            )
                                        finally:
                                            new_loop.close()
                                    
                                    with concurrent.futures.ThreadPoolExecutor() as executor:
                                        future = executor.submit(run_in_new_loop)
                                        travel_times = future.result(timeout=15)
                                        
                                except RuntimeError:
                                    travel_times = asyncio.run(get_multi_modal_travel_times(curr_coords, item.coords))
                                
                                walking = travel_times.get("walking", {})
                                driving = travel_times.get("driving", {})
                                transit = travel_times.get("transit", {})
                                
                                item.distance_meters = walking.get("distance_m", 'unknown')
                                item.travel_time_min = walking.get("time_min", 'unknown')
                                item.walking_time_min = walking.get("time_min", 'unknown')
                                item.driving_time_min = driving.get("time_min", 'unknown')
                                item.transit_time_min = transit.get("time_min", 'unknown')
                                
                                logger.info(f"{item.name}: Google Routes API time updated - walking {item.walking_time_min}min, driving {item.driving_time_min}min, transit {item.transit_time_min}min (distance: {item.distance_meters}m)")
                                
                            except Exception as e:
                                logger.error(f"{item.name}: Google Routes API failed, using default calculation - {e}")
                                distance = calculate_distance_meters(curr_coords, item.coords) # 확인필요
                                walking_time = calculate_travel_time_minutes(distance) # 확인필요
                                
                                item.distance_meters = distance
                                item.travel_time_min = walking_time
                                item.walking_time_min = walking_time
                                item.driving_time_min = max(3, int(distance / 500))
                                item.transit_time_min = max(5, int(distance / 250))
                    except Exception as e:
                        logger.error(f"{item.name}: Coordinate update failed - {e}")
            
            photo_urls = []
            
            images = first_result.get("images", [])
            if images and isinstance(images, list):
                for img in images: # 개수 제한 부분
                    if isinstance(img, dict) and "thumbnail" in img:
                        photo_urls.append(img["thumbnail"])
            
            if not photo_urls:
                photos_link = first_result.get("photos_link")
                if photos_link:
                    try:
                        photos_params = {
                            "engine": "google_maps_photos",
                            "place_id": place_id,
                            "api_key": api_key
                        }
                        import asyncio
                        photos_response = await asyncio.wait_for(
                            client.get("https://serpapi.com/search.json", params=photos_params),
                            timeout=15.0
                        )
                        photos_data = photos_response.json()
                        
                        if "photos" in photos_data and isinstance(photos_data["photos"], list):
                            for photo in photos_data["photos"]:
                                if isinstance(photo, dict) and "thumbnail" in photo:
                                    photo_urls.append(photo["thumbnail"])
                    except Exception as e:
                        logger.error(f"{item.name}: Photos API call failed - {e}")
            
            if not photo_urls:
                thumbnail = first_result.get("thumbnail")
                if thumbnail:
                    photo_urls.append(thumbnail)
            
            if not photo_urls:
                serpapi_thumbnail = first_result.get("serpapi_thumbnail")
                if serpapi_thumbnail:
                    photo_urls.append(serpapi_thumbnail)
            
            if photo_urls:
                item.photos = photo_urls
                logger.info(f"{item.name}: Found {len(photo_urls)} photos")
            else:
                logger.info(f"{item.name}: No photos found")
                available_keys = [k for k in first_result.keys() if 'photo' in k.lower() or 'image' in k.lower() or 'thumbnail' in k.lower()]
                if available_keys:
                    logger.debug(f"{item.name} photo related keys: {available_keys}")
            
            for key in ["place_id", "data_id", "cid", "place_data_id"]:
                if key in first_result:
                    place_id = first_result[key]
                    logger.info(f"{item.name}: Found place_id {place_id} in {key}")
                    
                    item.place_id = place_id
                    current_location = os.getenv("APP_LOCATION")
                    item.directions_link = generate_directions_link(item.coords, item.name, origin_param=current_location)
                    logger.info(f"{item.name}: Updated directions link (origin: {current_location})")
                    break
            
            if not place_id:
                logger.error(f"{item.name}: place_id not found")
                logger.debug(f"{item.name} first result keys: {list(first_result.keys())}")
                if first_result:
                    logger.debug(f"{item.name} first result: {first_result}")
                return []
            
            review_params = {
                "engine": "google_maps_reviews",
                "place_id": place_id,
                "api_key": api_key,
                "sort_by": "most_relevant"
            }
            
            review_response = await client.get("https://serpapi.com/search.json", params=review_params)
            review_data = review_response.json()
            
            logger.debug(f"{item.name} review API response keys: {list(review_data.keys())}")
            if "error" in review_data:
                logger.error(f"{item.name} review API error: {review_data['error']}")
                return []
            
            reviews = []
            review_items = review_data.get("reviews", [])
            logger.info(f"{item.name}: API returned {len(review_items)} reviews")
            
            for i, review in enumerate(review_items):
                snippet = review.get("snippet", "").strip()
                if snippet and len(snippet) > 10:  # 최소 길이 확인
                    reviews.append(snippet)
            logger.info(f"{item.name}: Collected {len(reviews)} reviews")
            return reviews[:5]
                
    except Exception as e:
        logger.error(f"{item.name}: Review collection failed - {e}")
        return []

async def curate_places(client: AsyncOpenAI, place_name: str, reviews: List[str], natural_input: Optional[str] = None) -> Tuple[str, str]:
    if not reviews:
        return "리뷰가 없습니다.", "unknown"
    
    # 각 리뷰의 길이를 제한
    truncated_reviews = [review[:500] + "..." if len(review) > 500 else review for review in reviews[:5]]
    combined_reviews = "\n\n".join(truncated_reviews)

    price_level, reason = await analyze_price_level(client, place_name, combined_reviews)
    summary = await summarize_reviews(client, place_name, combined_reviews, natural_input, price_level, reason)
    return summary, price_level, reason

async def analyze_price_level(client: AsyncOpenAI, place_name: str, combined_reviews: str) -> str:
    prompt = f"""다음은 "{place_name}"에 대한 구글맵 리뷰들입니다.
    리뷰들:
    {combined_reviews}
    **가격 레벨 분석**: 리뷰에서 언급된 가격 관련 정보를 바탕으로 판단
    - "low": 무료, 저렴, 합리적, cheap, affordable, free, inexpensive, budget-friendly 등
    - "mid": 보통, 적당한, moderate, reasonable, worth the price 등
    - "high": 비싸다, expensive, overpriced, costly, pricey 등
    - "unknown": 리뷰 내에 가격 관련 언급이 없는 경우
    
    다음 스키마에 따라 응답해주세요.
    - PRICE_LEVEL: [low/mid/high/unknown]
    - REASON: [리뷰에서 가격 관련 언급을 바탕으로 한 이유 설명 (최대 100자)]
"""

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": """
                        당신은 리뷰에서 가격 정보(입장료, 이용료 포함)를 분석하는 전문가입니다. 객관적으로 가격 레벨을 판단합니다. 
                        low, mid, high 중 하나를 선택해서 PRICE_LEVEL 필드에 채워주세요.
                        리뷰 내에 가격과 관련된 언급이 없다면 unknown을 선택해주세요.
                        리뷰 내의 가격 관련 언급을 바탕으로 해당 선택을 한 이유를 REASON 필드에 채워주세요.
                        이유 설명은 최대 50자 이내의 줄바꿈 없는 줄글로 작성해주세요.
                        """
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=300
            ),
            timeout=15.0
        )
        
        result = response.choices[0].message.content.strip()
        
        # 응답 파싱
        lines = result.split('\n')
        price_level = None
        reason = None
        for line in lines:
            if line.startswith('PRICE_LEVEL:'):
                price_level = line.replace('PRICE_LEVEL:', '').strip()
            if line.startswith('REASON:'):
                reason = line.replace('REASON:', '').strip()
                break
        
        return price_level, reason
        
    except asyncio.TimeoutError:
        logger.error(f"{place_name}: 가격 레벨 분석 timeout (15초)")
        return None, None
    except Exception as e:
        logger.error(f"{place_name}: 가격 레벨 분석 오류: {e}")
        return None, None

async def summarize_reviews(client: AsyncOpenAI, place_name: str, combined_reviews: str, natural_input: Optional[str] = None) -> str:
    prompt = f"""
    리뷰들:
    {combined_reviews}

    다음 사용자 선호 관련 정보를 고려하여 리뷰를 요약해주세요.
    **사용자 선호 관련 정보**: {natural_input}

    **리뷰 요약 방법**: 
    - 2-3문장으로 간결하게 요약
    - 리뷰에서 가장 많이 언급되는 특징 위주로 작성
    - 긍정적인 점과 주의할 점을 균형있게 포함하여 작성
    - 사용자의 추가 요청사항이 있다면 해당 관점에서 리뷰를 요약하여 작성
    
    다음 스키마에 따라 응답해주세요.
    SUMMARY: [요약 내용]"""

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": """
                        당신은 리뷰를 바탕으로 여행지를 큐레이션하는 여행 전문가입니다. 
                        다음은 "{place_name}"에 대한 구글맵 리뷰들입니다. 이 장소의 리뷰를 바탕으로 해당 여행지에 대한 정보를 알려주세요.
                        객관적이고 유용한 요약을 작성해야합니다.
                        한국어로 작성해주세요."""    
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=500
            ),
            timeout=15.0
        )
        
        result = response.choices[0].message.content.strip()
        
        summary = None
        lines = result.split('\n')
        try:
            for line in lines:
                if line.startswith('SUMMARY:'):
                    summary = line.replace('SUMMARY:', '').strip()
                    break
        except:
            summary = result

        return summary
        
    except asyncio.TimeoutError:
        logger.error(f"{place_name}: 리뷰 요약 timeout (15초)")
        return None
    except Exception as e:
        logger.error(f"{place_name}: 리뷰 요약 오류: {e}")
        return None