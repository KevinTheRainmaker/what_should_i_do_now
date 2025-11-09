from haversine import haversine
from typing import Optional, Tuple
import os
import httpx
import json
from app.types.activity import Coordinates

def calculate_distance_meters(coord1: Coordinates, coord2: Coordinates) -> int:
    """두 좌표 간 거리를 미터로 계산"""
    distance_km = haversine(
        (coord1.lat, coord1.lng),
        (coord2.lat, coord2.lng)
    )
    return int(distance_km * 1000)

def calculate_travel_time_minutes(distance_meters: int) -> int:
    """거리를 기반으로 도보 시간 계산 (80m/min 기준, 최소 3분)"""
    travel_time = distance_meters / 80
    return max(3, int(travel_time))

async def get_multi_modal_travel_times(origin_coords: Coordinates, dest_coords: Coordinates) -> dict:
    """모든 교통수단별 이동시간과 거리를 계산 (Google Routes API 우선 사용)"""
    # Google Routes API 우선 시도
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if google_api_key:
        print(f"   🌐 Google Routes API 사용")
        return await get_google_routes_travel_times(origin_coords, dest_coords)
    
    # Google API가 없으면 SerpAPI 사용 (기존 로직)
    serpapi_key = os.getenv("SERPAPI_KEY")
    
    # 기본 거리 계산
    distance = calculate_distance_meters(origin_coords, dest_coords)
    
    # 기본값 설정
    result = {
        "walking": {"time_min": calculate_travel_time_minutes(distance), "distance_m": distance},
        "driving": {"time_min": max(3, int(distance / 500)), "distance_m": distance},  # 평균 30km/h
        "transit": {"time_min": max(5, int(distance / 300)), "distance_m": distance}   # 평균 18km/h + 대기시간
    }
    
    if not serpapi_key:
        print(f"   📐 기본 계산: 도보 {result['walking']['time_min']}분, 차량 {result['driving']['time_min']}분, 대중교통 {result['transit']['time_min']}분")
        return result
    
    # SerpAPI Google Directions로 각 교통수단별 시간 계산 (폴백)
    try:
        print(f"   🔄 SerpAPI 폴백 사용")
        origin = f"{origin_coords.lat},{origin_coords.lng}"
        destination = f"{dest_coords.lat},{dest_coords.lng}"
        
        # 교통수단별 API 호출
        travel_modes = ["walking", "driving", "transit"]
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            for mode in travel_modes:
                try:
                    params = {
                        "engine": "google_maps_directions",
                        "api_key": serpapi_key,
                        "start_addr": origin,
                        "end_addr": destination,
                        "travel_mode": mode
                    }
                    
                    response = await client.get("https://serpapi.com/search.json", params=params)
                    data = response.json()
                    
                    directions = data.get("directions", [])
                    if directions and len(directions) > 0:
                        duration = directions[0].get("duration", {})
                        distance_info = directions[0].get("distance", {})
                        
                        if duration and distance_info:
                            duration_seconds = duration.get("seconds", 0)
                            travel_time_min = max(1, int(duration_seconds / 60))
                            distance_meters = distance_info.get("meters", 0)
                            
                            result[mode] = {
                                "time_min": travel_time_min,
                                "distance_m": distance_meters
                            }
                            print(f"   🌐 SerpAPI {mode}: {travel_time_min}분, {distance_meters}m")
                    
                except Exception as e:
                    print(f"   ⚠️ SerpAPI {mode} 실패: {e}")
                    continue
        
        print(f"   📊 최종 계산: 도보 {result['walking']['time_min']}분, 차량 {result['driving']['time_min']}분, 대중교통 {result['transit']['time_min']}분")
        return result
        
    except Exception as e:
        print(f"   ❌ SerpAPI 전체 오류: {e}")
        return result

async def get_google_travel_time(origin_coords: Coordinates, dest_coords: Coordinates) -> Tuple[int, int]:
    """기존 함수 호환성 유지 (도보 시간만 반환)"""
    result = await get_multi_modal_travel_times(origin_coords, dest_coords)
    walking = result["walking"]
    return walking["time_min"], walking["distance_m"]

def generate_directions_link(coords: Optional[Coordinates], name: str, place_id: Optional[str] = None, origin_param: str = None) -> str:
    """구글 지도 길찾기 링크 생성 (장소 이름 우선 사용)"""
    
    # 현재 설정된 위치를 출발지로 사용
    if origin_param is None:
        current_location = os.getenv("APP_LOCATION", "Centre de Convencions Internacional de Barcelona")
        origin_param = current_location.replace(" ", "+")
    
    import urllib.parse
    
    # 장소 이름을 그대로 사용 (가장 정확하고 사용자 친화적)
    encoded_name = urllib.parse.quote(name)
    return f"https://www.google.com/maps/dir/?api=1&origin={origin_param}&destination={encoded_name}"

def generate_search_link(name: str, coords: Optional[Coordinates] = None) -> str:
    """구글맵 검색 링크 생성 (장소 이름으로 검색)"""
    import urllib.parse
    current_city = os.getenv("APP_LOCATION", "Barcelona").split(",")[-1].strip() if "," in os.getenv("APP_LOCATION", "Barcelona") else "Barcelona"
    encoded_name = urllib.parse.quote(f"{name} {current_city}")
    return f"https://www.google.com/maps/search/{encoded_name}"

async def get_travel_time_by_place_name(origin_name: str, destination_name: str, travel_mode: str = "WALK") -> Optional[int]:
    """장소 이름으로 Google Routes API를 통해 이동시간 계산"""
    api_key = os.getenv("GOOGLE_API_KEY")
    
    print(f"   🔑 API 키 확인: {'있음' if api_key else '없음'}")
    if api_key:
        print(f"      길이: {len(api_key)}, 시작: {api_key[:10]}...")
    
    if not api_key:
        print(f"   ⚠️ Google API 키 없음 - 기본값 사용")
        return None
    
    try:
        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"
        }
        
        payload = {
            "origin": {
                "address": origin_name
            },
            "destination": {
                "address": destination_name
            },
            "travelMode": travel_mode
        }
        
        # routingPreference는 DRIVE 모드에서만 설정 가능
        if travel_mode == "DRIVE":
            payload["routingPreference"] = "TRAFFIC_AWARE"
        
        print(f"   🌐 Routes API 요청:")
        print(f"      URL: {url}")
        print(f"      출발지: {origin_name}")
        print(f"      도착지: {destination_name}")
        print(f"      교통수단: {travel_mode}")
        print(f"      헤더: {dict(headers)}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            print(f"   📊 응답 상태: {response.status_code}")
            print(f"   📊 응답 헤더: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ 성공 응답: {json.dumps(data, indent=2)[:200]}...")
                routes = data.get("routes", [])
                
                if routes and len(routes) > 0:
                    route = routes[0]
                    duration = route.get("duration", {})
                    distance_meters = route.get("distanceMeters", 0)
                    
                    if duration:
                        # duration은 직접 "1519s" 형태의 문자열
                        if isinstance(duration, str):
                            duration_str = duration
                        else:
                            duration_str = duration.get("duration", "0s")
                        duration_seconds = int(duration_str.replace("s", ""))
                        travel_time_min = max(1, int(duration_seconds / 60))
                        
                        print(f"   🌐 Routes API ({travel_mode}): {origin_name} → {destination_name} = {travel_time_min}분, {distance_meters}m")
                        return travel_time_min
                    else:
                        print(f"   ⚠️ Routes API: duration 정보 없음")
                        return None
            else:
                print(f"   ❌ Routes API 오류: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   📄 오류 응답 전체: {json.dumps(error_data, indent=2)}")
                    if 'error' in error_data:
                        error_info = error_data['error']
                        print(f"      오류 코드: {error_info.get('code', 'N/A')}")
                        print(f"      오류 메시지: {error_info.get('message', 'N/A')}")
                        print(f"      오류 상태: {error_info.get('status', 'N/A')}")
                        if 'details' in error_info:
                            print(f"      오류 상세: {error_info['details']}")
                except Exception as parse_error:
                    print(f"   ❌ 오류 응답 파싱 실패: {parse_error}")
                    print(f"   📄 원본 응답: {response.text}")
                return None
                
    except Exception as e:
        print(f"   ❌ Routes API 예외: {e}")
        import traceback
        print(f"   📄 전체 오류 추적: {traceback.format_exc()}")
        return None

async def get_travel_time_by_directions_api(origin_name: str, destination_name: str, travel_mode: str = "walking") -> Optional[int]:
    """Google Directions API를 사용한 이동시간 계산 (무료 쿼터 있음)"""
    api_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        print(f"   ⚠️ Google API 키 없음")
        return None
    
    try:
        # Google Directions API (무료 쿼터 포함)
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": origin_name,
            "destination": destination_name,
            "mode": travel_mode,  # walking, driving, transit
            "key": api_key
        }
        
        print(f"   🗺️ Directions API 요청: {origin_name} → {destination_name} ({travel_mode})")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK" and data.get("routes"):
                    route = data["routes"][0]
                    leg = route["legs"][0]
                    
                    duration_seconds = leg["duration"]["value"]
                    distance_meters = leg["distance"]["value"]
                    travel_time_min = max(1, int(duration_seconds / 60))
                    
                    print(f"   ✅ Directions API ({travel_mode}): {travel_time_min}분, {distance_meters}m")
                    return travel_time_min
                else:
                    print(f"   ⚠️ Directions API 오류: {data.get('status', 'Unknown')}")
                    if data.get("error_message"):
                        print(f"      메시지: {data['error_message']}")
                    return None
            else:
                print(f"   ❌ Directions API HTTP 오류: {response.status_code}")
                return None
                
    except Exception as e:
        print(f"   ❌ Directions API 예외: {e}")
        return None

async def get_travel_time_by_distance_estimation(origin_name: str, destination_name: str) -> dict:
    """장소 이름을 분석하여 현재 위치로부터의 거리를 추정"""
    
    # 현재 위치 기준 지역별 거리 추정 (더 정확한 데이터)
    distance_estimates = {
        # 매우 가까운 지역 (1-2km)
        'poblenou': 1500, 'diagonal mar': 1800, '22@': 1200, 'llull': 800,
        'maresme': 2000, 'besòs': 2200, 'forum': 1600, 'glòries': 1800,
        
        # 가까운 지역 (2-4km) 
        'born': 3000, 'barceloneta': 2800, 'ciutadella': 3200, 'marina': 2500,
        'port olímpic': 2200, 'villa olímpica': 2000, 'gothic': 3500,
        'eixample': 3800, 'sagrada familia': 4000, 'gràcia': 4500,
        
        # 중간 거리 (4-7km)
        'montjuïc': 5500, 'poble sec': 5000, 'sants': 6000, 'les corts': 6500,
        'zona universitària': 7000, 'pedralbes': 7500, 'sarrià': 7200,
        'tibidabo': 8000, 'park güell': 5500, 'carmel': 6000,
        
        # 먼 거리 (7km+)
        'nou barris': 8500, 'horta': 9000, 'sant andreu': 7500,
        'badal': 8000, 'collblanc': 7800, 'cornellà': 9500,
        'esplugues': 8500, 'sant just': 9000, 'airport': 12000
    }
    
    destination_lower = destination_name.lower()
    estimated_distance = 2500  # 기본값: 2.5km
    
    # 키워드 매칭으로 거리 추정
    for keyword, distance in distance_estimates.items():
        if keyword in destination_lower:
            estimated_distance = distance
            print(f"   📍 위치 매칭: '{keyword}' → 예상 거리 {distance}m")
            break
    else:
        print(f"   ❓ 위치 불명: 기본 거리 {estimated_distance}m 사용")
    
    # 거리 기반 시간 계산 (더 현실적인 공식)
    walking_time = max(5, int(estimated_distance / 70))  # 70m/min (4.2km/h)
    driving_time = max(3, int(estimated_distance / 450))  # 27km/h (도시 교통 고려)
    transit_time = max(5, int(estimated_distance / 200))  # 12km/h (환승 + 대기시간)
    
    return {
        "walking": {"time_min": walking_time, "distance_m": estimated_distance},
        "driving": {"time_min": driving_time, "distance_m": estimated_distance},
        "transit": {"time_min": transit_time, "distance_m": estimated_distance}
    }

async def get_multi_modal_travel_times_by_name(origin_name: str, destination_name: str) -> dict:
    """장소 이름으로 모든 교통수단별 이동시간 계산"""
    
    print(f"   🔄 이동시간 계산 시작: {destination_name}")
    
    # Google APIs 시도 (Routes API → Directions API)
    api_success = False
    result = {
        "walking": {"time_min": 25, "distance_m": 2000},
        "driving": {"time_min": 8, "distance_m": 2000},
        "transit": {"time_min": 15, "distance_m": 2000}
    }
    
    # 1단계: Routes API 시도 (403 빌링 오류 예상)
    try:
        walking_time = await get_travel_time_by_place_name(origin_name, destination_name, "WALK")
        if walking_time and walking_time > 0:
            result["walking"]["time_min"] = walking_time
            # 성공하면 다른 모드도 시도하지만, 시간 단축을 위해 하나만 성공해도 사용
            api_success = True
            print(f"   ✅ Routes API 성공: 도보 {walking_time}분")
    except Exception as e:
        print(f"   ❌ Routes API 실패 (예상됨): {str(e)[:50]}...")
    
    # 2단계: Directions API 시도 (REQUEST_DENIED 예상)  
    if not api_success:
        try:
            walking_time = await get_travel_time_by_directions_api(origin_name, destination_name, "walking")
            if walking_time and walking_time > 0:
                result["walking"]["time_min"] = walking_time
                api_success = True
                print(f"   ✅ Directions API 성공: 도보 {walking_time}분")
        except Exception as e:
            print(f"   ❌ Directions API 실패 (예상됨): {str(e)[:50]}...")
    
    # 3단계: 지능형 추정 (API 실패 시)
    if not api_success:
        print(f"   🧠 Google APIs 모두 실패, 지능형 추정 사용")
        result = await get_travel_time_by_distance_estimation(origin_name, destination_name)
    
    print(f"   📊 최종 결과: 도보 {result['walking']['time_min']}분, 차량 {result['driving']['time_min']}분, 대중교통 {result['transit']['time_min']}분")
    return result

async def get_google_routes_travel_times(origin_coords: Coordinates, dest_coords: Coordinates) -> dict:
    """Google Routes API를 사용해 정확한 이동시간과 거리를 계산"""
    api_key = os.getenv("GOOGLE_API_KEY")
    
    # 기본 거리 계산
    distance = calculate_distance_meters(origin_coords, dest_coords)
    
    # 기본값 설정 (Haversine 기반)
    result = {
        "walking": {"time_min": calculate_travel_time_minutes(distance), "distance_m": distance},
        "driving": {"time_min": max(3, int(distance / 500)), "distance_m": distance},  # 평균 30km/h
        "transit": {"time_min": max(5, int(distance / 300)), "distance_m": distance}   # 평균 18km/h + 대기시간
    }
    
    if not api_key:
        print(f"   📐 기본 계산: 도보 {result['walking']['time_min']}분, 차량 {result['driving']['time_min']}분, 대중교통 {result['transit']['time_min']}분")
        return result
    
    # Google Routes API로 정확한 시간 계산
    try:
        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"
        }
        
        # 교통수단별 API 호출
        travel_modes = {
            "walking": "WALK",
            "driving": "DRIVE", 
            "transit": "TRANSIT"
        }
        
        async with httpx.AsyncClient(timeout=8.0) as client:
            for mode_key, api_mode in travel_modes.items():
                try:
                    payload = {
                        "origin": {
                            "location": {
                                "latLng": {
                                    "latitude": origin_coords.lat,
                                    "longitude": origin_coords.lng
                                }
                            }
                        },
                        "destination": {
                            "location": {
                                "latLng": {
                                    "latitude": dest_coords.lat,
                                    "longitude": dest_coords.lng
                                }
                            }
                        },
                        "travelMode": api_mode
                    }
                    
                    # routingPreference는 DRIVE 모드에서만 설정 가능
                    if api_mode == "DRIVE":
                        payload["routingPreference"] = "TRAFFIC_AWARE"
                    
                    response = await client.post(url, headers=headers, json=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        routes = data.get("routes", [])
                        
                        if routes and len(routes) > 0:
                            route = routes[0]
                            duration = route.get("duration", {})
                            distance_meters = route.get("distanceMeters", 0)
                            
                            if duration:
                                # duration은 직접 "1519s" 형태의 문자열
                                if isinstance(duration, str):
                                    duration_str = duration
                                else:
                                    duration_str = duration.get("duration", "0s")
                                duration_seconds = int(duration_str.replace("s", ""))
                                travel_time_min = max(1, int(duration_seconds / 60))
                                
                                result[mode_key] = {
                                    "time_min": travel_time_min,
                                    "distance_m": distance_meters or distance
                                }
                                print(f"   🌐 Google Routes API {mode_key}: {travel_time_min}분, {distance_meters or distance}m")
                            else:
                                print(f"   ⚠️ Google Routes API {mode_key}: duration 정보 없음")
                    else:
                        print(f"   ❌ Google Routes API {mode_key} 오류: {response.status_code}")
                        if response.status_code == 403:
                            print(f"      API 키 권한 확인 필요")
                        elif response.status_code == 400:
                            print(f"      요청 형식 오류: {response.text[:200]}")
                        
                except Exception as e:
                    print(f"   ❌ Google Routes API {mode_key} 예외: {e}")
                    continue
        
        print(f"   📊 최종 계산: 도보 {result['walking']['time_min']}분, 차량 {result['driving']['time_min']}분, 대중교통 {result['transit']['time_min']}분")
        return result
        
    except Exception as e:
        print(f"   ❌ Google Routes API 전체 오류: {e}")
        return result
