import asyncio
import httpx
import os
import re

from typing import Dict, Any, List
from app.nodes.query_node import QuerySpec
from app.types.activity import ActivityItem, CategoryType, PriceLevel, SourceType, LocaleHints, Coordinates
from app.utils.category_mapping import map_category_from_text, is_chain_establishment, get_indoor_outdoor_from_category
from app.utils.geo import generate_directions_link
import logging
from app.nodes.colored_log_handler import ColoredLogHandler
logging.basicConfig(level=logging.DEBUG, handlers=[ColoredLogHandler()])
logger = logging.getLogger(__name__)
import os

async def search_and_normalize(state: Dict[str, Any]) -> Dict[str, Any]:
    """검색 및 정규화 노드"""
    logger.info("외부 검색 및 정규화 시작")
    
    queries: List[QuerySpec] = state["search_queries"]
    logger.info(f"검색 쿼리 {len(queries)}개 병렬 실행:")
    for i, query in enumerate(queries, 1):
        logger.info(f"      {i}. '{query.q}' ({query.target}, {query.locale})")
    
    all_results = []
    
    serpapi_queries = [query for query in queries if query.target == "gmaps"]
    
    if serpapi_queries:
        logger.info(f"SerpAPI 요청 {len(serpapi_queries)}개 병렬 실행 중...")
        shared_client = httpx.AsyncClient(
            timeout=15.0,  # 타임아웃을 15초로 증가
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
        try:
            serpapi_tasks = [
                search_serpapi_with_client(query, shared_client) 
                for query in serpapi_queries
            ]
            serpapi_results = await asyncio.gather(*serpapi_tasks, return_exceptions=True)
            serpapi_count = 0
            for i, result in enumerate(serpapi_results, 1):
                if isinstance(result, list):
                    all_results.extend(result)
                    serpapi_count += len(result)
                elif isinstance(result, Exception):
                    logger.error(f"SerpAPI 검색 {i}번 실패: {type(result).__name__}: {result}")
                else:
                    logger.warning(f"SerpAPI 검색 {i}번 예상치 못한 결과 타입: {type(result)}")
            logger.info(f"SerpAPI 결과: {serpapi_count}개")
        finally:
            try:
                await shared_client.aclose()
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    pass
                else:
                    logger.warning(f"httpx 클라이언트 정리 중 경고: {e}")
            except Exception as e:
                logger.warning(f"httpx 클라이언트 정리 중 경고: {e}")
    
    # 정규화 (비동기)
    logger.info(f"총 {len(all_results)}개 결과를 ActivityItem으로 정규화 중...")
    normalized_items = []
    
    # 비동기 정규화 작업 생성
    normalize_tasks = [
        normalize_search_result(raw_item) for raw_item in all_results[:15]  # 최대 15개만 처리
    ]
    
    # 병렬로 정규화 실행
    normalized_results = await asyncio.gather(*normalize_tasks, return_exceptions=True)
    
    for i, normalized in enumerate(normalized_results, 1):
        if normalized and not isinstance(normalized, Exception):
            normalized_items.append(normalized)
            logger.info(f"      {i}. {normalized.name} ({normalized.category.value}, {normalized.source.value})")
        elif isinstance(normalized, Exception):
            logger.info(f"      {i}. 정규화 실패: {normalized}")
    
    state["activity_items"] = normalized_items
    state["source_stats"] = {
        "serpapi": len([r for r in all_results if r.get("source") == "serpapi"]),
        # "bing": len([r for r in all_results if r.get("source") == "bing"])
    }
    
    logger.info(f"정규화 완료: {len(normalized_items)}개 활동 아이템 생성\n")
    
    return state

async def search_serpapi(query: QuerySpec) -> List[Dict[str, Any]]:
    """SerpAPI 검색 (독립 실행용 - 호환성 유지)"""
    async with httpx.AsyncClient(
        timeout=15.0,  # 타임아웃을 15초로 증가
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
    ) as client:
        return await search_serpapi_with_client(query, client)

async def search_serpapi_with_client(query: QuerySpec, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """SerpAPI 검색 (공유 클라이언트 사용)"""
    from app.config import USE_MOCK_SEARCH
    
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key or USE_MOCK_SEARCH:
        if USE_MOCK_SEARCH:
            logger.info("개발 모드 - 모의 검색 결과 사용")
        else:
            logger.warning("SERPAPI_KEY 없음 - 모의 검색 결과 사용")
        return generate_mock_serpapi_results(query)
    
    # 현재 설정된 위치 좌표 가져오기
    current_lat = os.getenv("APP_LAT", "41.4095")
    current_lng = os.getenv("APP_LNG", "2.2184")
    current_location = os.getenv("APP_LOCATION", "Centre de Convencions Internacional de Barcelona")
    
    logger.info(f"검색 위치: {current_location} ({current_lat}, {current_lng})")
    
    params = {
        "engine": "google_maps",
        "q": query.q,
        "api_key": api_key,
        "ll": f"@{current_lat},{current_lng},12z",  # 현재 위치 중심 좌표
        "type": "search"  # 검색 타입 명시
    }
    
    try:
        response = await client.get("https://serpapi.com/search.json", params=params)
        
        if response.status_code != 200:
            logger.error(f"SerpAPI HTTP 오류: {response.status_code} - {response.text[:200]}")
            return []
        
        data = response.json()
        
        # 에러 응답 확인
        if "error" in data:
            logger.error(f"SerpAPI API 오류: {data.get('error', 'Unknown error')}")
            return []
        
        results = []
        places = data.get("local_results", [])[:10]
        
        if not places:
            logger.warning(f"SerpAPI 검색 결과 없음: '{query.q}'")
            # 다른 키에서도 시도
            places = data.get("place_results", []) or data.get("places_results", [])
            if isinstance(places, dict):
                places = [places]
        
        for place in places:
            if isinstance(place, dict):
                results.append({
                    "source": "serpapi",
                    "title": place.get("title", ""),
                    "rating": place.get("rating"),
                    "reviews": place.get("reviews"),
                    "type": place.get("type", ""),
                    "gps_coordinates": place.get("gps_coordinates"),
                    "open_state": place.get("open_state"),
                    "address": place.get("address", ""),
                    "description": place.get("description", "")
                })
        
        logger.info(f"SerpAPI 검색 성공: '{query.q}' → {len(results)}개 결과")
        return results
        
    except httpx.TimeoutException as e:
        logger.error(f"SerpAPI 타임아웃: '{query.q}' - {e}")
        return []
    except httpx.RequestError as e:
        logger.error(f"SerpAPI 요청 오류: '{query.q}' - {e}")
        return []
    except Exception as e:
        logger.error(f"SerpAPI 오류: '{query.q}' - {type(e).__name__}: {e}")
        import traceback
        logger.debug(f"상세 오류: {traceback.format_exc()}")
        return []

async def get_place_details_from_google(place_name: str, current_location: str) -> Dict[str, Any]:
    """Google Places API를 사용해서 장소의 정확한 좌표와 정보를 가져오기"""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {}
    
    try:
        # Google Places Text Search API 사용
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            "query": f"{place_name}",
            "key": api_key,
            "fields": "place_id,name,geometry,formatted_address,rating,user_ratings_total,price_level,types"
        }
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)
            data = response.json()

            if data.get("status") == "OK" and data.get("results"):
                place = data["results"][0]  # 첫 번째 결과 사용
                if place.get("business_status") == "OPERATIONAL":
                    return {
                        "place_id": place.get("place_id"),
                        "name": place.get("name"),
                        "formatted_address": place.get("formatted_address"),
                        "geometry": place.get("geometry"),
                        "open_now": place.get("open_now"),
                        "rating": place.get("rating"),
                        "user_ratings_total": place.get("user_ratings_total"),
                        "types": place.get("types", [])
                    }
                else:
                    return {
                        "open_now": False
                    }
    except Exception as e:
        logger.error(f"Google Places API 오류 ({place_name}): {e}")
    
    return {}

async def normalize_search_result(raw_item: Dict[str, Any]) -> ActivityItem:
    """검색 결과를 ActivityItem으로 정규화"""
    
    title = raw_item.get("title", "")
    if not title:
        return None
    
    # 기본 정보 로깅
    logger.info(f"SEARCH ITEM: {title} (TYPE: {raw_item.get('type', 'N/A')})")
    
    # 카테고리 매핑
    text_for_category = f"{title} {raw_item.get('type', '')} {raw_item.get('description', '')}"
    category = map_category_from_text(text_for_category) # 확인 필요
    
    price_level = PriceLevel.UNKNOWN

    place_id = raw_item.get("place_id")
    if place_id:
        logger.info(f"{title}: FOUND place_id - {place_id}")
    else:
        logger.warning(f"{title}: NO place_id")
    
    coords = None
    current_location = os.getenv("APP_LOCATION", "Centre de Convencions Internacional de Barcelona")
    
    gps = raw_item.get("gps_coordinates")
    if gps and isinstance(gps, dict) and "latitude" in gps and "longitude" in gps:
        try:
            coords = Coordinates(lat=float(gps["latitude"]), lng=float(gps["longitude"]))
            logger.debug('FROM SERPAPI')
            logger.info(f"{title}: FOUND coordinates - {coords.lat}, {coords.lng}")
        except Exception as e:
            logger.error(f"{title}: ERROR - {e}")
    
    if not coords:
        logger.info(f"{title}: SEARCHING coordinates...")
        google_data = await get_place_details_from_google(title, current_location)
        
        if google_data.get("geometry") and google_data["geometry"].get("location"):
            location = google_data["geometry"]["location"]
            try:
                coords = Coordinates(lat=float(location["lat"]), lng=float(location["lng"]))
                logger.debug('FROM GOOGLE')
                logger.info(f"{title}: FOUND coordinates - {coords.lat}, {coords.lng}")
                
                if google_data.get("place_id"):
                    place_id = google_data["place_id"]
                    logger.info(f"{title}: FOUND place_id - {place_id}")
                
                if google_data.get("rating"):
                    rating = google_data["rating"]
                    logger.info(f"{title}: FOUND rating - {rating}")
                if google_data.get("user_ratings_total"):
                    review_count = google_data["user_ratings_total"]
                    logger.info(f"{title}: FOUND review_count - {review_count}")
                    
            except Exception as e:
                logger.error(f"{title}: ERROR - {e}")
        else:
            logger.warning(f"{title}: NO coordinates")
    
    if not coords:
        logger.error(f"{title}: NO coordinates")

    rating = raw_item.get("rating")
    if rating:
        try:
            rating = float(rating)
        except:
            logger.error(f"{title}: ERROR - {rating}")
            rating = None
    
    reviews = raw_item.get("reviews")
    review_count = None
    if reviews:
        try:
            numbers = re.findall(r'\d+', str(reviews))
            if numbers:
                review_count = int(numbers[0])
        except:
            logger.error(f"{title}: ERROR - {reviews}")
            review_count = None
    
    open_now = None
    open_state = raw_item.get("open_state")
    if open_state:
        open_now = open_state.lower().split(" ")[0] == "open" or open_state.lower().split(" ")[0] == "always"
    
    is_chain = is_chain_establishment(title) # 확인 필요
    
    source_type = SourceType.SERPAPI_GMAPS if raw_item.get("source") == "serpapi" else SourceType.FALLBACK

    coords_num = re.findall(r'\d+', str(coords))
    coords_num = ''.join(coords_num)

    # build hash id - can be used as a unique identifier for the activity item
    item_id = f"{hash(title + coords_num) % 100000}"

    return ActivityItem(
        id=item_id,
        name=title,
        category=category,
        price_level=price_level,
        rating=rating,
        review_count=review_count,
        open_now=open_now,
        indoor_outdoor=get_indoor_outdoor_from_category(category), # 확인 필요
        coords=coords,
        theme_tags=extract_theme_tags(text_for_category, category),
        source_url=raw_item.get("url"),
        source=source_type,
        locale_hints=LocaleHints(
            local_vibe=not is_chain,
            chain=is_chain,
        ),
        reason_text="",  # 랭커에서 생성
        directions_link=generate_directions_link(coords, title),
        place_id=place_id,
        budget_hint=price_level  # price_level과 동일하게 설정
    )

def extract_theme_tags(text: str, category: CategoryType) -> List[str]:
    """텍스트와 카테고리에서 테마 태그 추출"""
    tags = []
    text_lower = text.lower()
    
    # 카테고리 기반 태그
    category_tags = {
        CategoryType.CAFE: ["relax"],
        CategoryType.PARK: ["relax"],
        CategoryType.VIEWPOINT: ["activity"],
        CategoryType.MARKET: ["shopping"],
        CategoryType.MUSEUM: ["activity"],
        CategoryType.SHOPPING: ["shopping"],
        CategoryType.RESTAURANT: ["food"],
        CategoryType.LANDMARK: ["activity"]
    }
    
    tags.extend(category_tags.get(category, []))
    
    # 텍스트 키워드 기반 태그
    if any(word in text_lower for word in ["quiet", "tranquil", "peaceful", "cozy"]):
        tags.append("relax")
    if any(word in text_lower for word in ["shop", "market", "store"]):
        tags.append("shopping")
    if any(word in text_lower for word in ["food", "eat", "restaurant", "cafe"]):
        tags.append("food")
    if any(word in text_lower for word in ["museum", "gallery", "tour", "experience"]):
        tags.append("activity")
    
    return list(set(tags))  # 중복 제거
