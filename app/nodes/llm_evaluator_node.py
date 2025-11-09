import os
import json
from typing import Dict, Any, List
from openai import AsyncOpenAI
from dotenv import load_dotenv
from app.types.activity import ActivityItem

# 환경변수 로드
load_dotenv()

async def llm_evaluate_and_select(state: Dict[str, Any]) -> Dict[str, Any]:
    """LLM을 사용한 활동 평가 및 선별 노드"""
    print("🧠 [에이전트] 5.5단계: LLM 기반 지능적 평가 및 선별")
    
    activity_items: List[ActivityItem] = state.get("activity_items", [])
    preferences = state["preferences"]
    context = state["context"]
    
    if not activity_items:
        print("   ⚠️  활동 아이템이 없음 - 빈 결과 반환")
        state["llm_selected_items"] = []
        return state
    
    # OpenAI 클라이언트 초기화
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("   ⚠️  OPENAI_API_KEY 없음 - LLM 평가 건너뜀")
        state["llm_selected_items"] = activity_items[:4]  # 기본 상위 4개
        return state
    
    client = AsyncOpenAI(api_key=api_key)
    
    print(f"   🤖 OpenAI GPT-4를 사용해 {len(activity_items)}개 아이템 평가 중...")
    
    # 활동 아이템들을 LLM이 이해할 수 있는 형태로 변환
    items_for_llm = []
    for i, item in enumerate(activity_items, 1):
        item_info = {
            "번호": i,
            "이름": item.name,
            "카테고리": item.category.value,
            "평점": f"{item.rating}/5" if item.rating else "정보 없음",
            "리뷰수": item.review_count if item.review_count else "정보 없음",
            "영업상태": "영업중" if item.open_now else "영업종료" if item.open_now is False else "정보 없음",
            "실내외": item.indoor_outdoor.value,
            "예상소요시간": f"{(item.travel_time_min or 5) + (item.expected_wait_min or 0) + (item.expected_duration_min or 20)}분",
            "테마태그": item.theme_tags,
            "현지감성": "높음" if item.locale_hints.local_vibe else "낮음",
            "체인여부": "체인" if item.locale_hints.chain else "독립매장"
        }
        items_for_llm.append(item_info)
    
    # 사용자 선호를 문자열로 변환
    user_prefs = {
        "시간": preferences.time_bucket.value,
        "예산": preferences.budget_level.value,
        "테마": [theme.value for theme in preferences.themes],
        "날씨": context.weather.condition,
        "위치": context.location_label,
        "추가요청": preferences.natural_input if preferences.natural_input else None
    }
    
    # LLM 프롬프트 생성
    prompt = f"""당신은 바르셀로나 여행 전문가입니다. 사용자의 선호에 맞는 최적의 활동 4개를 선별하고 평가해주세요.

**사용자 정보:**
- 남은 시간: {user_prefs['시간']}
- 예산 수준: {user_prefs['예산']}
- 원하는 테마: {', '.join(user_prefs['테마'])}
- 현재 날씨: {user_prefs['날씨']}
- 현재 위치: {user_prefs['위치']}{f"- 추가 요청사항: {user_prefs['추가요청']}" if user_prefs['추가요청'] else ""}

**고려사항:**
1. **시간 제약 (최우선)**: "30분 이하" 선택 시 예상소요시간이 30분을 초과하는 활동은 최대 70점으로 제한
2. 예산 수준에 적합한 선택
3. 테마 선호도와 일치성
4. 현지 감성과 독특함
5. 카테고리 다양성 (같은 카테고리 최대 2개)
6. 영업 상태 및 접근성
{f"7. **사용자 추가 요청사항 반영**: {user_prefs['추가요청']}" if user_prefs['추가요청'] else ""}

**후보 활동들:**
{json.dumps(items_for_llm, ensure_ascii=False, indent=2)}

다음 형식으로 응답해주세요:

```json
{{
  "selected_activities": [
    {{
      "번호": 선택된_활동_번호,
      "점수": 85,
      "선택이유": "구체적인 이유 (200자 이내)",
      "추천문구": "사용자에게 전달할 매력적인 추천 문구 (100자 이내)"
    }}
  ],
  "전체평가": "선별 기준과 전체적인 평가 (200자 이내)"
}}
```

정확히 4개를 선별하고, 다양성과 사용자 만족도를 모두 고려해주세요."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 여행 전문가이며, 사용자의 선호를 정확히 파악해 최적의 추천을 제공합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        
        llm_response = response.choices[0].message.content
        print(f"   📝 LLM 응답 받음 ({len(llm_response)} 문자)")
        
        # JSON 응답 파싱
        try:
            # ```json ``` 블록에서 JSON 추출
            if "```json" in llm_response:
                json_start = llm_response.find("```json") + 7
                json_end = llm_response.find("```", json_start)
                json_content = llm_response[json_start:json_end].strip()
            else:
                json_content = llm_response
            
            llm_result = json.loads(json_content)
            selected_numbers = [item["번호"] for item in llm_result["selected_activities"]]
            
            print(f"   🎯 LLM 선별 결과: {selected_numbers}번 활동들")
            print(f"   💭 전체 평가: {llm_result.get('전체평가', 'N/A')}")
            
            # 선별된 아이템들 가져오기
            selected_items = []
            for llm_item in llm_result["selected_activities"]:
                item_idx = llm_item["번호"] - 1
                if 0 <= item_idx < len(activity_items):
                    original_item = activity_items[item_idx]
                    # LLM 평가 정보 추가
                    original_item.llm_score = llm_item.get("점수", 75)
                    original_item.llm_reason = llm_item.get("선택이유", "LLM 추천")
                    original_item.llm_recommendation = llm_item.get("추천문구", original_item.name)
                    # reason_text를 LLM 추천 문구로 업데이트
                    original_item.reason_text = original_item.llm_recommendation
                    selected_items.append(original_item)
                    
                    print(f"      {llm_item['번호']}. {original_item.name} ({llm_item.get('점수', 0)}점)")
                    print(f"         이유: {llm_item.get('선택이유', 'N/A')}")
                    print(f"         추천: {llm_item.get('추천문구', 'N/A')}")
            
            state["llm_selected_items"] = selected_items
            state["llm_evaluation"] = llm_result.get("전체평가", "")
            
        except json.JSONDecodeError as e:
            print(f"   ❌ LLM 응답 JSON 파싱 실패: {e}")
            print(f"   📄 원본 응답: {llm_response[:200]}...")
            # 폴백: 기존 랭킹 방식 사용
            state["llm_selected_items"] = activity_items[:4]
    
    except Exception as e:
        print(f"   ❌ OpenAI API 호출 실패: {e}")
        # 폴백: 기존 랭킹 방식 사용
        state["llm_selected_items"] = activity_items[:4]
    
    print("   ✅ LLM 평가 완료\n")
    return state
