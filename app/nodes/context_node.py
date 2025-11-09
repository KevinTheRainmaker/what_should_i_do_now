from datetime import datetime
from typing import Dict, Any
import os
from app.types.activity import Context, Weather, Coordinates
from app.config import DEFAULT_CONTEXT

def initialize_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """컨텍스트 초기화 노드"""
    print("\n🏁 [에이전트] 1단계: 컨텍스트 초기화 시작")
    
    # 현재 시간 ISO 형식으로 생성
    current_time = datetime.now().isoformat()
    
    # 환경 변수에서 현재 설정된 위치 정보 가져오기
    location_label = os.getenv("APP_LOCATION", DEFAULT_CONTEXT["location_label"])
    lat = float(os.getenv("APP_LAT", DEFAULT_CONTEXT["coords"]["lat"]))
    lng = float(os.getenv("APP_LNG", DEFAULT_CONTEXT["coords"]["lng"]))
    weather_condition = os.getenv("APP_WEATHER_CONDITION", DEFAULT_CONTEXT["weather"]["condition"])
    temp_c = int(os.getenv("APP_TEMP", DEFAULT_CONTEXT["weather"]["temp_c"]))
    
    # 현재 설정된 컨텍스트 로드
    context = Context(
        location_label=location_label,
        coords=Coordinates(lat=lat, lng=lng),
        weather=Weather(condition=weather_condition, temp_c=temp_c),
        local_time_iso=current_time
    )
    
    print(f"   📍 위치: {context.location_label}")
    print(f"   🌤️  날씨: {context.weather.condition} {context.weather.temp_c}°C")
    print(f"   🕐 시간: {current_time}")
    
    # contextOverride가 있다면 병합
    if "context_override" in state and state["context_override"]:
        print("   🔄 사용자 컨텍스트 오버라이드 적용")
        override = state["context_override"]
        if "location_label" in override:
            context.location_label = override["location_label"]
        if "coords" in override:
            context.coords = Coordinates(**override["coords"])
        if "weather" in override:
            context.weather = Weather(**override["weather"])
    
    # 상태 업데이트
    state["context"] = context
    state["session_id"] = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"   ✅ 세션 ID: {state['session_id']}")
    print("   ✅ 컨텍스트 초기화 완료\n")
    
    return state
