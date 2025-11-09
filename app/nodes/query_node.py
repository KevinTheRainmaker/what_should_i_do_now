import os
import asyncio
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from openai import AsyncOpenAI
from dotenv import load_dotenv
from app.types.activity import Preferences, Context
from app.config import THEME_KEYWORDS, BUDGET_KEYWORDS, SEARCH_RADIUS

# 환경변수 로드
load_dotenv()

class QuerySpec(BaseModel):
    q: str
    locale: str  # "es-ES", "ca-ES", "en"
    target: str  # "gmaps", "web"
    radius_meters: int

async def generate_llm_optimized_queries(preferences: Preferences, context: Context, location: str, radius: int = 1500) -> List[QuerySpec]:
    """LLM을 사용해 자연어 입력을 포함한 최적화된 검색 쿼리 생성"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("   ⚠️ OpenAI API 키가 없어 기본 쿼리 생성 방식 사용")
        return []
    
    try:
        client = AsyncOpenAI(api_key=api_key)
        
        # 사용자 정보 정리
        themes_str = ", ".join([theme.value for theme in preferences.themes])
        budget_str = preferences.budget_level.value
        time_str = preferences.time_bucket.value
        natural_input = preferences.natural_input or ""
        
        # LLM 프롬프트 생성
        prompt = f"""당신은 바르셀로나 관광 검색 전문가입니다. 사용자의 요구사항에 맞는 구글맵 검색 쿼리를 생성해주세요.

**사용자 정보:**
- 남은 시간: {time_str}
- 예산 수준: {budget_str}
- 관심 테마: {themes_str}
- 현재 위치: {location}
- 추가 요청사항: {natural_input if natural_input else "없음"}

**쿼리 생성 규칙:**
1. **현재 위치 활용 필수**: "{location}" 주변의 장소를 검색어에 포함
2. 구글맵에서 검색하기 좋은 키워드 사용
3. 영어와 스페인어 쿼리 조합 (각 언어당 2-3개)
4. 사용자의 추가 요청사항을 키워드로 반영
5. 현재 위치에서 접근 가능한 근처 장소 우선
6. 총 4-6개의 다양한 쿼리 생성

**위치 기반 검색 예시:**
- "cafe near {location}" (현재 위치 기준)
- "parque cerca de {location}" (현재 위치 기준)
- "restaurant near {location}" (현재 위치 기준)
- "quiet spot near {location}" (현재 위치 기준)

다음 JSON 형식으로 응답해주세요:
{{
  "queries": [
    {{"query": "검색 쿼리 텍스트", "language": "es", "explanation": "이 쿼리를 선택한 이유"}},
    {{"query": "검색 쿼리 텍스트", "language": "en", "explanation": "이 쿼리를 선택한 이유"}}
  ]
}}

예시:
- 조용한 카페: "quiet cafe near {location}", "cafeteria tranquila cerca de {location}"
- 공원: "park near {location}", "parque cerca de {location}"
- 전망대: "viewpoint near {location}", "mirador cerca de {location}"
"""

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 검색 쿼리 최적화 전문가입니다. JSON 형식으로만 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            ),
            timeout=10.0
        )
        
        result = response.choices[0].message.content.strip()
        print(f"   🤖 LLM 쿼리 생성 응답: {result[:200]}...")
        
        # JSON 파싱
        try:
            query_data = json.loads(result)
            queries = []
            
            for item in query_data.get("queries", []):
                query_text = item.get("query", "")
                language = item.get("language", "en")
                explanation = item.get("explanation", "")
                
                if query_text:
                    locale = "es-ES" if language == "es" else "en"
                    queries.append(QuerySpec(
                        q=query_text,
                        locale=locale,
                        target="gmaps",
                        radius_meters=radius
                    ))
                    print(f"   📝 생성된 쿼리 ({language}): {query_text}")
                    print(f"      💭 이유: {explanation}")
            
            return queries[:6]  # 최대 6개로 제한
            
        except json.JSONDecodeError as e:
            print(f"   ❌ LLM 응답 JSON 파싱 실패: {e}")
            return []
            
    except Exception as e:
        print(f"   ❌ LLM 쿼리 생성 실패: {e}")
        return []

def generate_search_queries(state: Dict[str, Any]) -> Dict[str, Any]:
    """검색 쿼리 생성 노드"""
    print("[에이전트] 2단계: 검색 쿼리 생성 시작")
    
    preferences: Preferences = state["preferences"]
    context: Context = state["context"]
    
    print(f"사용자 선호:")
    print(f"시간: {preferences.time_bucket}")
    print(f"예산: {preferences.budget_level}")
    print(f"테마: {[theme.value for theme in preferences.themes]}")
    print(f"자연어 입력: {preferences.natural_input}")
    
    queries = []
    
    # 시간 버킷에 따른 반경 결정
    radius = SEARCH_RADIUS[preferences.time_bucket]
    print(f"검색 반경: {radius}m")
    
    # 1. LLM 기반 최적화된 쿼리 생성 시도
    print("🤖 LLM으로 맞춤형 쿼리 생성 중...")
    try:
        import concurrent.futures
        
        def run_llm_query_generation():
            # 새 이벤트 루프 생성
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(
                    generate_llm_optimized_queries(preferences, context, context.location_label, radius)
                )
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_llm_query_generation)
            llm_queries = future.result(timeout=12)  # 12초 타임아웃
            
        if llm_queries:
            print(f"✅ LLM에서 {len(llm_queries)}개 맞춤형 쿼리 생성됨")
            queries.extend(llm_queries)
        else:
            print("⚠️ LLM 쿼리 생성 결과 없음")
            
    except Exception as e:
        print(f"❌ LLM 쿼리 생성 실패: {e}")
    
    # 2. 기본 테마별 쿼리로 보완 (LLM이 실패하거나 부족할 때)
    if len(queries) < 3:
        print("📝 기본 테마 쿼리로 보완 중...")
        for theme in preferences.themes:
            theme_queries = generate_theme_queries(
                theme.value, 
                preferences.budget_level.value,
                context.location_label,
                radius
            )
            queries.extend(theme_queries)
            print(f"{theme.value}: {len(theme_queries)}개 쿼리")
    
    # 중복 제거 및 최대 5개로 제한
    unique_queries = []
    seen_queries = set()
    
    for query in queries:
        if query.q not in seen_queries and len(unique_queries) < 5:
            unique_queries.append(query)
            seen_queries.add(query.q)
    
    # 최소 2개 보장
    if len(unique_queries) < 2:
        print("쿼리 부족 - 폴백 쿼리 추가")
        fallback_queries = generate_fallback_queries(context.location_label, radius)
        unique_queries.extend(fallback_queries[:2])
    
    print(f"최종 검색 쿼리 {len(unique_queries)}개:")
    for i, query in enumerate(unique_queries, 1):
        print(f"{i}. '{query.q}' ({query.locale}, {query.target})")
    
    state["search_queries"] = unique_queries[:5]
    print("쿼리 생성 완료\n")
    return state

def generate_theme_queries(theme: str, budget: str, location: str, radius: int) -> List[QuerySpec]:
    """테마별 쿼리 생성"""
    queries = []
    
    if theme in THEME_KEYWORDS:
        theme_words = THEME_KEYWORDS[theme]
        budget_words = BUDGET_KEYWORDS.get(budget, [""])
        
        # 스페인어 쿼리
        if "es" in theme_words:
            for word in theme_words["es"][:2]:  # 최대 2개
                budget_hint = budget_words[0] if budget_words else ""
                query_text = f"{word} cerca de {location} {budget_hint}".strip()
                queries.append(QuerySpec(
                    q=query_text,
                    locale="es-ES",
                    target="gmaps",
                    radius_meters=radius
                ))
        
        # 영어 쿼리
        if "en" in theme_words and len(queries) < 3:
            for word in theme_words["en"][:1]:
                budget_hint = budget_words[1] if len(budget_words) > 1 else ""
                query_text = f"{word} near {location} {budget_hint}".strip()
                queries.append(QuerySpec(
                    q=query_text,
                    locale="en",
                    target="gmaps",
                    radius_meters=radius
                ))
    
    return queries

def generate_fallback_queries(location: str, radius: int) -> List[QuerySpec]:
    """폴백 쿼리 생성"""
    return [
        QuerySpec(
            q=f"lugares interesantes cerca de {location}",
            locale="es-ES",
            target="gmaps",
            radius_meters=radius
        ),
        QuerySpec(
            q=f"things to do near {location}",
            locale="en",
            target="web",
            radius_meters=radius
        )
    ]
