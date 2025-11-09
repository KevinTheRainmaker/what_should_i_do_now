from typing import Dict, Any
from app.types.activity import CategoryType, IndoorOutdoor

# 카테고리 매핑 규칙
CATEGORY_MAPPING = {
    # 카페/음료
    "cafe": CategoryType.CAFE,
    "coffee": CategoryType.CAFE,
    "bakery": CategoryType.CAFE,
    "pastelería": CategoryType.CAFE,
    "cafetería": CategoryType.CAFE,
    
    # 공원/광장
    "park": CategoryType.PARK,
    "parque": CategoryType.PARK,
    "gardens": CategoryType.PARK,
    "jardines": CategoryType.PARK,
    "plaza": CategoryType.PARK,
    "plaça": CategoryType.PARK,
    "square": CategoryType.PARK,
    
    # 전망대/뷰포인트
    "viewpoint": CategoryType.VIEWPOINT,
    "mirador": CategoryType.VIEWPOINT,
    "bunkers": CategoryType.VIEWPOINT,
    "overlook": CategoryType.VIEWPOINT,
    
    # 마켓/쇼핑
    "market": CategoryType.MARKET,
    "mercado": CategoryType.MARKET,
    "mercat": CategoryType.MARKET,
    "flea": CategoryType.MARKET,
    "vintage": CategoryType.SHOPPING,
    "shop": CategoryType.SHOPPING,
    "tienda": CategoryType.SHOPPING,
    "botiga": CategoryType.SHOPPING,
    "shopping": CategoryType.SHOPPING,
    
    # 박물관/갤러리
    "museum": CategoryType.MUSEUM,
    "museo": CategoryType.MUSEUM,
    "museu": CategoryType.MUSEUM,
    "gallery": CategoryType.MUSEUM,
    "galería": CategoryType.MUSEUM,
    "galeria": CategoryType.MUSEUM,
    
    # 레스토랑/음식
    "restaurant": CategoryType.RESTAURANT,
    "restaurante": CategoryType.RESTAURANT,
    "tapas": CategoryType.RESTAURANT,
    "bar": CategoryType.RESTAURANT,
    "food": CategoryType.RESTAURANT,
    "comida": CategoryType.RESTAURANT,
    
    # 랜드마크
    "landmark": CategoryType.LANDMARK,
    "monument": CategoryType.LANDMARK,
    "monumento": CategoryType.LANDMARK,
    "cathedral": CategoryType.LANDMARK,
    "catedral": CategoryType.LANDMARK,
    "basilica": CategoryType.LANDMARK,
    "basílica": CategoryType.LANDMARK
}

# 체인 키워드 (로컬 감성 반대)
CHAIN_KEYWORDS = [
    "starbucks", "mcdonald", "burger king", "kfc", "subway",
    "h&m", "zara", "uniqlo", "nike", "adidas",
    "seven eleven", "family mart"
]

def map_category_from_text(text: str) -> CategoryType:
    """텍스트에서 카테고리를 매핑"""
    text_lower = text.lower()
    
    for keyword, category in CATEGORY_MAPPING.items():
        if keyword in text_lower:
            return category
    
    return CategoryType.OTHER

def is_chain_establishment(text: str) -> bool:
    """체인점 여부 판단"""
    text_lower = text.lower()
    return any(chain in text_lower for chain in CHAIN_KEYWORDS)

def get_indoor_outdoor_from_category(category: CategoryType) -> IndoorOutdoor:
    """카테고리에서 실내/실외 추정"""
    mapping = {
        CategoryType.CAFE: IndoorOutdoor.INDOOR,
        CategoryType.PARK: IndoorOutdoor.OUTDOOR,
        CategoryType.VIEWPOINT: IndoorOutdoor.MIXED,
        CategoryType.MARKET: IndoorOutdoor.MIXED,
        CategoryType.MUSEUM: IndoorOutdoor.INDOOR,
        CategoryType.SHOPPING: IndoorOutdoor.INDOOR,
        CategoryType.RESTAURANT: IndoorOutdoor.INDOOR,
        CategoryType.LANDMARK: IndoorOutdoor.MIXED,
        CategoryType.OTHER: IndoorOutdoor.UNKNOWN
    }
    return mapping.get(category, IndoorOutdoor.UNKNOWN)
