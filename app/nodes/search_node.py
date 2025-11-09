import asyncio
import httpx
import os
from typing import Dict, Any, List
from app.nodes.query_node import QuerySpec
from app.types.activity import ActivityItem, CategoryType, PriceLevel, SourceType, LocaleHints, Coordinates
from app.utils.category_mapping import map_category_from_text, is_chain_establishment, get_indoor_outdoor_from_category
from app.utils.geo import generate_directions_link

async def search_and_normalize(state: Dict[str, Any]) -> Dict[str, Any]:
    """검색 및 정규화 노드"""
    print("📡 [에이전트] 3단계: 외부 검색 및 정규화 시작")
    
    queries: List[QuerySpec] = state["search_queries"]
    print(f"   🔍 검색 쿼리 {len(queries)}개 병렬 실행:")
    for i, query in enumerate(queries, 1):
        print(f"      {i}. '{query.q}' ({query.target}, {query.locale})")
    
    # 병렬 검색 실행
    all_results = []
    
    # SerpAPI 우선 실행
    serpapi_tasks = [
        search_serpapi(query) for query in queries 
        if query.target == "gmaps"
    ]
    
    if serpapi_tasks:
        print(f"   📡 SerpAPI 요청 {len(serpapi_tasks)}개 병렬 실행 중...")
        serpapi_results = await asyncio.gather(*serpapi_tasks, return_exceptions=True)
        serpapi_count = 0
        for result in serpapi_results:
            if isinstance(result, list):
                all_results.extend(result)
                serpapi_count += len(result)
        print(f"   ✅ SerpAPI 결과: {serpapi_count}개")
    
    # 결과가 부족하면 Bing 검색
    if len(all_results) < 5:
        bing_tasks = [
            search_bing(query) for query in queries
            if query.target == "web"
        ]
        
        if bing_tasks:
            print(f"   📡 Bing 요청 {len(bing_tasks)}개 보조 실행 중...")
            bing_results = await asyncio.gather(*bing_tasks, return_exceptions=True)
            bing_count = 0
            for result in bing_results:
                if isinstance(result, list):
                    all_results.extend(result)
                    bing_count += len(result)
            print(f"   ✅ Bing 결과: {bing_count}개")
    
    # 정규화 (비동기)
    print(f"   🔄 총 {len(all_results)}개 결과를 ActivityItem으로 정규화 중...")
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
            print(f"      {i}. {normalized.name} ({normalized.category.value}, {normalized.source.value})")
        elif isinstance(normalized, Exception):
            print(f"      {i}. 정규화 실패: {normalized}")
    
    state["activity_items"] = normalized_items
    state["source_stats"] = {
        "serpapi": len([r for r in all_results if r.get("source") == "serpapi"]),
        "bing": len([r for r in all_results if r.get("source") == "bing"])
    }
    
    print(f"   ✅ 정규화 완료: {len(normalized_items)}개 활동 아이템 생성\n")
    
    return state

async def search_serpapi(query: QuerySpec) -> List[Dict[str, Any]]:
    """SerpAPI 검색"""
    from app.config import USE_MOCK_SEARCH
    
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key or USE_MOCK_SEARCH:
        if USE_MOCK_SEARCH:
            print("🎭 개발 모드 - 모의 검색 결과 사용")
        else:
            print("⚠️  SERPAPI_KEY 없음 - 모의 검색 결과 사용")
        return generate_mock_serpapi_results(query)
    
    # 현재 설정된 위치 좌표 가져오기
    current_lat = os.getenv("APP_LAT", "41.4095")
    current_lng = os.getenv("APP_LNG", "2.2184")
    current_location = os.getenv("APP_LOCATION", "Barcelona")
    
    print(f"🔍 검색 위치: {current_location} ({current_lat}, {current_lng})")
    
    params = {
        "engine": "google_maps",
        "q": query.q + f" {current_location}",  # 현재 위치 기준으로 검색
        "api_key": api_key,
        "ll": f"@{current_lat},{current_lng},12z",  # 현재 위치 중심 좌표
        "type": "search"  # 검색 타입 명시
    }
    
    try:
        client = httpx.AsyncClient(timeout=1.8)
        try:
            response = await client.get("https://serpapi.com/search.json", params=params)
            data = response.json()
            
            results = []
            places = data.get("local_results", [])[:10]
            
            for place in places:
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
            
            return results
        finally:
            try:
                await client.aclose()
            except RuntimeError:
                # 이벤트 루프가 닫힌 경우 무시
                pass
            
    except Exception as e:
        print(f"SerpAPI error: {e}")
        return []

async def search_bing(query: QuerySpec) -> List[Dict[str, Any]]:
    """Bing 검색"""
    api_key = os.getenv("BING_API_KEY")
    if not api_key:
        print("⚠️  BING_API_KEY 없음 - 검색 건너뜀")
        return []
    
    headers = {
        "Ocp-Apim-Subscription-Key": api_key
    }
    
    # 현재 설정된 위치 가져오기
    current_location = os.getenv("APP_LOCATION", "Barcelona")
    
    params = {
        "q": f"{query.q} {current_location}",
        "count": 10,
        "mkt": "es-ES"
    }
    
    try:
        client = httpx.AsyncClient(timeout=1.2)
        try:
            response = await client.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers=headers,
                params=params
            )
            data = response.json()
            
            results = []
            pages = data.get("webPages", {}).get("value", [])[:10]
            
            for page in pages:
                results.append({
                    "source": "bing",
                    "title": page.get("name", ""),
                    "url": page.get("url", ""),
                    "snippet": page.get("snippet", ""),
                    "description": page.get("snippet", "")
                })
            
            return results
        finally:
            try:
                await client.aclose()
            except RuntimeError:
                # 이벤트 루프가 닫힌 경우 무시
                pass
            
    except Exception as e:
        print(f"Bing API error: {e}")
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
            "query": f"{place_name} {current_location}",
            "key": api_key,
            "fields": "place_id,name,geometry,formatted_address,rating,user_ratings_total,price_level,types"
        }
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                place = data["results"][0]  # 첫 번째 결과 사용
                return {
                    "place_id": place.get("place_id"),
                    "name": place.get("name"),
                    "geometry": place.get("geometry"),
                    "formatted_address": place.get("formatted_address"),
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("user_ratings_total"),
                    "price_level": place.get("price_level"),
                    "types": place.get("types", [])
                }
    except Exception as e:
        print(f"   ❌ Google Places API 오류 ({place_name}): {e}")
    
    return {}

async def normalize_search_result(raw_item: Dict[str, Any]) -> ActivityItem:
    """검색 결과를 ActivityItem으로 정규화"""
    
    title = raw_item.get("title", "")
    if not title:
        return None
    
    # 기본 정보 로깅
    print(f"🔍 [SEARCH ITEM] {title} (타입: {raw_item.get('type', 'N/A')})")
    
    # 카테고리 매핑
    text_for_category = f"{title} {raw_item.get('type', '')} {raw_item.get('description', '')}"
    category = map_category_from_text(text_for_category)
    
    # 초기 가격 레벨 (리뷰 분석에서 업데이트됨)
    price_level = PriceLevel.UNKNOWN
    print(f"📝 [PRICE INITIAL] {title} → 초기 가격: UNKNOWN (리뷰 분석 후 업데이트 예정)")
    
    # place_id 추출 (정확한 길찾기용)
    place_id = raw_item.get("place_id") or raw_item.get("data_id") or raw_item.get("data_cid")
    if place_id:
        print(f"   🆔 {title}: place_id 발견 - {place_id}")
    else:
        print(f"   ⚠️ {title}: place_id 없음")
    
    # 좌표 처리 - Google Places API 사용
    coords = None
    current_location = os.getenv("APP_LOCATION", "Barcelona")
    
    # 1. SerpAPI에서 좌표가 있는지 먼저 확인
    gps = raw_item.get("gps_coordinates")
    if gps and isinstance(gps, dict) and "lat" in gps and "lng" in gps:
        try:
            coords = Coordinates(lat=float(gps["lat"]), lng=float(gps["lng"]))
            print(f"   ✅ {title}: SerpAPI에서 좌표 발견 ({coords.lat}, {coords.lng})")
        except Exception as e:
            print(f"   ❌ {title}: SerpAPI 좌표 변환 실패 - {e}")
    
    # 2. SerpAPI에 좌표가 없으면 Google Places API 사용
    if not coords:
        print(f"   🔍 {title}: Google Places API로 좌표 검색 중...")
        google_data = await get_place_details_from_google(title, current_location)
        
        if google_data.get("geometry") and google_data["geometry"].get("location"):
            location = google_data["geometry"]["location"]
            try:
                coords = Coordinates(lat=float(location["lat"]), lng=float(location["lng"]))
                print(f"   ✅ {title}: Google Places API에서 좌표 발견 ({coords.lat}, {coords.lng})")
                
                # Google에서 가져온 추가 정보 업데이트
                if google_data.get("place_id"):
                    place_id = google_data["place_id"]
                    print(f"   🆔 {title}: Google place_id 발견 - {place_id}")
                
                if google_data.get("rating"):
                    rating = google_data["rating"]
                    print(f"   ⭐ {title}: Google 평점 - {rating}")
                    
            except Exception as e:
                print(f"   ❌ {title}: Google Places 좌표 변환 실패 - {e}")
        else:
            print(f"   ⚠️ {title}: Google Places API에서 좌표 없음")
    
    # 4. 주요 장소 하드코딩 좌표
    if not coords:
        known_places = {
            # 공원들
            "ciutadella park": {"lat": 41.3886, "lng": 2.1883},
            "parc de la ciutadella": {"lat": 41.3886, "lng": 2.1883},
            "parc de cervantes": {"lat": 41.3778, "lng": 2.1147},
            "parc del centre del poblenou": {"lat": 41.4069, "lng": 2.2014},  # 포블레누 (가까움)
            "parc diagonal mar": {"lat": 41.4108, "lng": 2.2266},  # 디아고날마르 (가까움)
            "parc del mirador del poble-sec": {"lat": 41.3668, "lng": 2.1640},  # 몬주익 (원거리)
            "parc de l'estació del nord": {"lat": 41.3934, "lng": 2.1814},  # 시내 (원거리)
            
            # 빈티지 샵들 (대부분 시내 중심가 - 원거리)
            "la principal retro": {"lat": 41.3818, "lng": 2.1653},  # 엘 라발 (원거리)
            "la principal": {"lat": 41.3818, "lng": 2.1653},
            "los féliz vintage": {"lat": 41.3851, "lng": 2.1734},  # 고딕 쿼터 (매우 원거리)
            "los feliz vintage": {"lat": 41.3851, "lng": 2.1734},
            "féliz vintage": {"lat": 41.3851, "lng": 2.1734},
            "feliz vintage": {"lat": 41.3851, "lng": 2.1734},
            "el maniqui vintage": {"lat": 41.3829, "lng": 2.1708},  # 엘 라발 (원거리)
            "love vintage": {"lat": 41.3866, "lng": 2.1721},  # 엘 본 (원거리)
            "vintage poblenou": {"lat": 41.4044, "lng": 2.2035},  # 포블레누 (가까움)
            "cotton vintage": {"lat": 41.3851, "lng": 2.1734},  # 고딕 쿼터 (원거리)
            "le swing vintage": {"lat": 41.3829, "lng": 2.1708},  # 엘 라발 (원거리)
            "lullaby vintage": {"lat": 41.3819, "lng": 2.1689},  # 엘 라발 (원거리)
            "neko vintage": {"lat": 41.3866, "lng": 2.1721},  # 엘 본 (원거리)
            
            # 카페들
            "faborit casa amatller": {"lat": 41.3917, "lng": 2.1649},  # 까사 바뜨요 (원거리)
            "decent cafe": {"lat": 41.4056, "lng": 2.2045},  # 포블레누 (가까움)
            "granja primavera": {"lat": 41.3869, "lng": 2.1674},  # 엘 본 (원거리)
            "coffee house barcelona": {"lat": 41.3917, "lng": 2.1649},  # 엑샘플레 (원거리)
            "cafe cometa": {"lat": 41.3829, "lng": 2.1708},  # 엘 라발 (원거리)
            "cafe caracas": {"lat": 41.3851, "lng": 2.1734},  # 고딕 쿼터 (원거리)
            "cafe de l'opera": {"lat": 41.3805, "lng": 2.1728},  # 람블라스 (원거리)
            "citizen cafe": {"lat": 41.3917, "lng": 2.1649},  # 엑샘플레 (원거리)
            "little fern": {"lat": 41.4056, "lng": 2.2045},  # 포블레누 (가까움)
            "cafe fargo": {"lat": 41.4037, "lng": 2.1744},  # 사그라다 파밀리아 (중거리)
            
            # 시장들
            "mercat de sant antoni": {"lat": 41.3745, "lng": 2.1665},  # 산트 안토니 (원거리)
            "mercat del poblenou": {"lat": 41.4044, "lng": 2.2035},  # 포블레누 (가까움)
            "mercat de la boqueria": {"lat": 41.3816, "lng": 2.1722},  # 람블라스 (원거리)
            "mercat de santa caterina": {"lat": 41.3852, "lng": 2.1814},  # 엘 본 (원거리)
            "mercat del ninot": {"lat": 41.3902, "lng": 2.1542},  # 엑샘플레 (원거리)
            "la concepció market": {"lat": 41.3937, "lng": 2.1605},  # 엑샘플레 (원거리)
            "mercat de l'abaceria": {"lat": 41.4152, "lng": 2.1563},  # 그라시아 (원거리)
            "mercat de la barceloneta": {"lat": 41.3797, "lng": 2.1889},  # 바르셀로네타 (중거리)
        }
        
        title_lower = title.lower()
        for place_key, place_coords in known_places.items():
            if place_key in title_lower:
                coords = Coordinates(lat=place_coords["lat"], lng=place_coords["lng"])
                print(f"   📍 좌표 발견 (하드코딩): {title} → {coords.lat}, {coords.lng}")
                break
    
    if not coords:
        print(f"   ⚠️ {title}: 좌표 정보 없음 - 지역 기반 시간 추정 사용")
    
    # 평점 처리
    rating = raw_item.get("rating")
    if rating:
        try:
            rating = float(rating)
        except:
            rating = None
    
    # 리뷰 수 처리
    reviews = raw_item.get("reviews")
    review_count = None
    if reviews:
        try:
            # "123 reviews" 형태에서 숫자 추출
            import re
            numbers = re.findall(r'\d+', str(reviews))
            if numbers:
                review_count = int(numbers[0])
        except:
            pass
    
    # 영업 여부
    open_now = None
    open_state = raw_item.get("open_state")
    if open_state:
        open_now = "open" in open_state.lower()
    
    # 체인 여부 및 로컬 감성
    is_chain = is_chain_establishment(title)
    
    # 소스 타입
    source_type = SourceType.SERPAPI_GMAPS if raw_item.get("source") == "serpapi" else SourceType.BING
    
    # ID 생성
    item_id = f"{source_type.value}:{hash(title + str(coords)) % 100000}"
    
    return ActivityItem(
        id=item_id,
        name=title,
        category=category,
        price_level=price_level,
        rating=rating,
        review_count=review_count,
        open_now=open_now,
        indoor_outdoor=get_indoor_outdoor_from_category(category),
        coords=coords,
        budget_hint=price_level,
        theme_tags=extract_theme_tags(text_for_category, category),
        source_url=raw_item.get("url"),
        source=source_type,
        locale_hints=LocaleHints(
            local_vibe=not is_chain,
            chain=is_chain,
            night_safe=True  # 기본값
        ),
        reason_text="",  # 랭커에서 생성
        directions_link=generate_directions_link(coords, title),
        place_id=place_id
    )

# 기존 extract_price_level 함수는 이제 사용하지 않음 (LLM 기반으로 대체)
# def extract_price_level(raw_item: Dict[str, Any]) -> PriceLevel:
#     """이 함수는 LLM 기반 가격 분석으로 대체되었습니다"""
#     return PriceLevel.UNKNOWN

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


def generate_mock_serpapi_results(query: QuerySpec) -> List[Dict[str, Any]]:
    """모의 SerpAPI 결과 생성 (개발/테스트용)"""
    mock_results = []
    
    # 쿼리에 따른 다른 결과 생성
    if "cafe" in query.q.lower() or "relax" in query.q.lower():
        mock_results = [
            {
                "source": "serpapi",
                "title": "Café Central Barcelona",
                "rating": 4.2,
                "reviews": "156 reviews",
                "type": "Coffee shop",
                "gps_coordinates": {"lat": 41.3851, "lng": 2.1734},
                "open_state": "Open now",
                "address": "Carrer del Pi, 13, Barcelona",
                "description": "Cozy traditional café in the Gothic Quarter"
            },
            {
                "source": "serpapi", 
                "title": "Federal Café Sant Antoni",
                "rating": 4.5,
                "reviews": "289 reviews",
                "type": "Café",
                "gps_coordinates": {"lat": 41.3756, "lng": 2.1665},
                "open_state": "Open now",
                "address": "Carrer del Parlament, 39, Barcelona",
                "description": "Australian-style brunch café"
            }
        ]
    elif "market" in query.q.lower() or "shopping" in query.q.lower():
        mock_results = [
            {
                "source": "serpapi",
                "title": "Mercat de Sant Josep de la Boqueria",
                "rating": 4.1,
                "reviews": "2431 reviews", 
                "type": "Market",
                "gps_coordinates": {"lat": 41.3816, "lng": 2.1722},
                "open_state": "Open now",
                "address": "La Rambla, 91, Barcelona",
                "description": "Famous food market with local products"
            }
        ]
    elif "food" in query.q.lower():
        mock_results = [
            {
                "source": "serpapi",
                "title": "Cal Pep",
                "rating": 4.3,
                "reviews": "187 reviews",
                "type": "Tapas restaurant", 
                "gps_coordinates": {"lat": 41.3839, "lng": 2.1823},
                "open_state": "Open now",
                "address": "Plaça de les Olles, 8, Barcelona",
                "description": "Traditional tapas bar"
            }
        ]
    else:
        # 기본 결과
        mock_results = [
            {
                "source": "serpapi",
                "title": "Plaça Reial",
                "rating": 4.0,
                "reviews": "1024 reviews",
                "type": "Public square",
                "gps_coordinates": {"lat": 41.3802, "lng": 2.1749},
                "open_state": "Always open",
                "address": "Plaça Reial, Barcelona",
                "description": "Beautiful historic square with restaurants"
            }
        ]
    
    print(f"🎭 모의 검색 결과 {len(mock_results)}개 생성: '{query.q}'")
    return mock_results
