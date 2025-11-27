from enum import Enum
from typing import Optional, List
from pydantic import BaseModel


class CategoryType(str, Enum):
    CAFE = "cafe"
    PARK = "park"
    VIEWPOINT = "viewpoint"
    MARKET = "market"
    MUSEUM = "museum"
    SHOPPING = "shopping"
    RESTAURANT = "restaurant"
    LANDMARK = "landmark"
    OTHER = "other"


class PriceLevel(str, Enum):
    LOW = "low"
    MID = "mid"
    HIGH = "high"
    UNKNOWN = "unknown"


class IndoorOutdoor(str, Enum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class TimeBucket(str, Enum):
    UNDER_30 = "≤30"
    BETWEEN_30_60 = "30-60"
    BETWEEN_60_120 = "60-120"
    OVER_120 = ">120"


class Theme(str, Enum):
    RELAX = "relax"
    SHOPPING = "shopping"
    FOOD = "food"
    ACTIVITY = "activity"


class SourceType(str, Enum):
    SERPAPI_GMAPS = "serpapi_gmaps"
    BING = "bing"
    FALLBACK = "fallback"


class Coordinates(BaseModel):
    lat: float
    lng: float


class LocaleHints(BaseModel):
    local_vibe: bool = False
    chain: bool = False
    night_safe: Optional[bool] = None


class ActivityItem(BaseModel):
    id: str
    name: str
    category: CategoryType
    price_level: PriceLevel
    rating: Optional[float] = None
    review_count: Optional[int] = None
    open_now: Optional[bool] = None
    indoor_outdoor: IndoorOutdoor
    coords: Optional[Coordinates] = None
    distance_meters: Optional[int] = None
    travel_time_min: Optional[int] = None
    
    # 다중 교통수단 시간 정보
    walking_time_min: Optional[int] = None
    driving_time_min: Optional[int] = None
    transit_time_min: Optional[int] = None
    # expected_wait_min: Optional[int] = None
    # expected_duration_min: Optional[int] = None
    budget_hint: PriceLevel
    theme_tags: List[str] = []
    source_url: Optional[str] = None
    source: SourceType
    locale_hints: LocaleHints
    reason_text: str
    directions_link: str
    open_hours_text: Optional[str] = None
    
    # 계산된 필드들
    total_score: Optional[float] = None
    time_fitness_score: Optional[float] = None
    
    # LLM 평가 필드들 (선택사항)
    # llm_score: Optional[float] = None
    llm_reason: Optional[str] = None  
    llm_recommendation: Optional[str] = None
    
    # 리뷰 관련 필드들
    review_summary: Optional[str] = None
    top_reviews: Optional[List[str]] = None
    
    # 사진 정보
    photos: Optional[List[str]] = None
    
    # 구글맵 place_id (정확한 길찾기용)
    place_id: Optional[str] = None


class Preferences(BaseModel):
    time_bucket: TimeBucket
    budget_level: PriceLevel
    themes: List[Theme]
    natural_input: Optional[str] = None  # 사용자의 자연어 추가 요청사항


class Weather(BaseModel):
    condition: str = "sunny"  # sunny, cloudy, rain, windy, unknown
    temp_c: Optional[int] = 24


class Context(BaseModel):
    location_label: str = "International Barcelona Convention Center"
    coords: Coordinates = Coordinates(lat=41.4095, lng=2.2184)
    weather: Weather = Weather()
    local_time_iso: str
