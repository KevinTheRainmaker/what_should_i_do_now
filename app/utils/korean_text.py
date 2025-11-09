from app.types.activity import ActivityItem, CategoryType, PriceLevel

# 카테고리 한국어 라벨
CATEGORY_LABELS = {
    CategoryType.CAFE: "카페",
    CategoryType.PARK: "공원",
    CategoryType.VIEWPOINT: "전망대",
    CategoryType.MARKET: "마켓",
    CategoryType.MUSEUM: "미술관",
    CategoryType.SHOPPING: "쇼핑",
    CategoryType.RESTAURANT: "레스토랑",
    CategoryType.LANDMARK: "랜드마크",
    CategoryType.OTHER: "기타"
}

# 예산 레벨 한국어 라벨
BUDGET_LABELS = {
    PriceLevel.LOW: "낮음",
    PriceLevel.MID: "중간", 
    PriceLevel.HIGH: "높음",
    PriceLevel.UNKNOWN: "정보 없음"
}

# 테마 한국어 라벨
THEME_LABELS = {
    "relax": "휴식",
    "shopping": "쇼핑", 
    "food": "식사",
    "activity": "액티비티"
}

def generate_reason_text(item: ActivityItem, preferences) -> str:
    """추천 이유 텍스트 생성 (한국어, 80자 이내)"""
    
    # 기본 구성 요소
    travel_time = item.travel_time_min or 5
    category_label = CATEGORY_LABELS.get(item.category, "장소")
    budget_label = BUDGET_LABELS.get(item.budget_hint, "정보 없음")
    
    # 평점 텍스트
    if item.rating:
        rating_text = f"평점 {item.rating:.1f}/5"
    else:
        rating_text = "평점 정보 없음"
    
    # 테마 매칭
    theme_text = "즐기기"
    user_themes = [theme.value for theme in preferences.themes]
    item_themes = item.theme_tags
    
    common_themes = set(user_themes).intersection(set(item_themes))
    if common_themes:
        theme = list(common_themes)[0]
        theme_text = THEME_LABELS.get(theme, "즐기기")
    
    # 템플릿 생성
    reason = f"[도보 {travel_time}분] {category_label} · {rating_text}. 예산 {budget_label}. 지금 {theme_text}에 딱 맞아요."
    
    # 80자 제한
    if len(reason) > 80:
        reason = f"[도보 {travel_time}분] {category_label}. 예산 {budget_label}, {theme_text}에 좋아요."
    
    return reason

def get_category_label(category: CategoryType) -> str:
    """카테고리 한국어 라벨 반환"""
    return CATEGORY_LABELS.get(category, "기타")

def get_budget_label(budget: PriceLevel) -> str:
    """예산 한국어 라벨 반환"""
    return BUDGET_LABELS.get(budget, "정보 없음")

def get_theme_label(theme: str) -> str:
    """테마 한국어 라벨 반환"""
    return THEME_LABELS.get(theme, theme)
