import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

# 환경변수 검증
def validate_env():
    required_vars = ["SERPAPI_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")

# 기본 설정
DEFAULT_CONTEXT = {
    "location_label": "Centre de Convencions Internacional de Barcelona (CCIB)",
    "coords": {"lat": 41.4095, "lng": 2.2184},
    "weather": {"condition": "sunny", "temp_c": 24}
}

def update_default_context(location_label: str, lat: float, lng: float, weather_condition: str, temp_c: int):
    """DEFAULT_CONTEXT를 동적으로 업데이트"""
    global DEFAULT_CONTEXT
    DEFAULT_CONTEXT = {
        "location_label": location_label,
        "coords": {"lat": lat, "lng": lng},
        "weather": {"condition": weather_condition, "temp_c": temp_c}
    }

# 시간 버킷 제한 (분)
TIME_BUCKET_LIMITS = {
    "≤30": 30,
    "30-60": 60,
    "60-120": 120,
    ">120": None  # 상한 없음
}

# 시간 버킷별 최대 이동시간 (남은 시간의 30-40% 정도로 조정)
MAX_TRAVEL_TIME_BY_BUCKET = {
    "≤30": 10,      # 30분 → 10분 이동시간 (33%)
    "30-60": 20,    # 60분 → 20분 이동시간 (33%)
    "60-120": 40,   # 120분 → 40분 이동시간 (33%)
    ">120": 60      # 무제한이지만 합리적인 상한선 60분
}

# 카테고리별 기본값
CATEGORY_DEFAULTS = {
    "cafe": {"wait_min": 5, "duration_min": 20, "indoor_outdoor": "indoor"},
    "park": {"wait_min": 0, "duration_min": 15, "indoor_outdoor": "outdoor"},
    "viewpoint": {"wait_min": 0, "duration_min": 10, "indoor_outdoor": "mixed"},
    "market": {"wait_min": 3, "duration_min": 15, "indoor_outdoor": "mixed"},  # 30분 제한 고려
    "museum": {"wait_min": 15, "duration_min": 60, "indoor_outdoor": "indoor"},
    "shopping": {"wait_min": 0, "duration_min": 20, "indoor_outdoor": "indoor"},  # 30분 제한 고려
    "restaurant": {"wait_min": 10, "duration_min": 45, "indoor_outdoor": "indoor"},
    "landmark": {"wait_min": 3, "duration_min": 15, "indoor_outdoor": "mixed"},
    "other": {"wait_min": 3, "duration_min": 15, "indoor_outdoor": "unknown"}
}

# 프로바이더 타임아웃 (초)
PROVIDER_TIMEOUTS = {
    "serpapi": 1.8,
    "bing": 1.2,
    "total_search": 2.4
}

# 캐시 설정
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 5분

# 레이트 리밋
RATE_LIMITS = {
    "requests_per_minute": int(os.getenv("RATE_LIMIT_REQUESTS", "3")),
    "window_seconds": int(os.getenv("RATE_LIMIT_WINDOW", "60"))
}

# API URLs
API_URLS = {
    "serpapi": "https://serpapi.com/search.json",
    "bing": "https://api.bing.microsoft.com/v7.0/search"
}

# 시간 버킷별 검색 반경 (미터)
SEARCH_RADIUS = {
    "≤30": 800,
    "30-60": 1500,
    "60-120": 3000,
    ">120": 5000
}

# 테마 키워드 매핑
THEME_KEYWORDS = {
    "relax": {
        "es": ["cafe acogedor", "parque tranquilo", "mirador"],
        "en": ["cozy cafe", "quiet park", "viewpoint"],
        "ca": ["cafè acollidor", "parc tranquil"]
    },
    "shopping": {
        "es": ["mercado local", "tienda vintage", "papelería"],
        "en": ["local market", "vintage shop", "stationery store"],
        "ca": ["mercat local", "botiga vintage"]
    },
    "food": {
        "es": ["comida barata", "bar de tapas", "panadería"],
        "en": ["cheap eats", "tapas bar", "bakery"],
        "ca": ["menjar barat", "bar de tapes"]
    },
    "activity": {
        "es": ["museo pequeño", "galería de arte", "espectáculo callejero"],
        "en": ["small museum", "art gallery", "street performance"],
        "ca": ["museu petit", "galeria d'art"]
    }
}

# 예산 키워드
BUDGET_KEYWORDS = {
    "low": ["barato", "€", "budget", "económico"],
    "mid": ["moderado", "€€", "moderate"],
    "high": ["fino", "€€€", "fine", "premium"]
}

# 개발 모드 설정
USE_MOCK_SEARCH = False
