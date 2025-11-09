import time
import os
import argparse
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import json
import asyncio
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from app.types.requests import RecommendRequest, RecommendResponse, HealthResponse
from app.types.activity import Preferences
from app.graph.companion_graph import companion_graph
from app.config import validate_env, update_default_context

# 질의응답 시스템을 위한 새로운 모델들
class Question(BaseModel):
    id: str
    question: str
    answer: Optional[str] = None
    order: int

class QuestionAnswerPair(BaseModel):
    question: str
    answer: str
    order: int

class QuestionSession(BaseModel):
    session_id: str
    questions: List[Question]
    current_question_index: int = 0
    is_completed: bool = False
    created_at: datetime
    updated_at: datetime
    initial_preferences: Optional[Dict[str, Any]] = None

class QuestionRequest(BaseModel):
    session_id: str
    question_id: str
    answer: str

class QuestionResponse(BaseModel):
    session_id: str
    current_question: Optional[Question]
    is_completed: bool
    progress: int  # 0-100
    can_go_back: bool

# 전역 설정 변수 (argparse로 설정됨)
CURRENT_LOCATION = "Centre de Convencions Internacional de Barcelona (CCIB)"
CURRENT_WEATHER = "☀️ 맑음 24°C"
CURRENT_COORDS = {"lat": 41.4095, "lng": 2.2184}
CURRENT_WEATHER_CONDITION = "sunny"
CURRENT_TEMP = 24

# 설정을 저장할 딕셔너리
app_config = {
    "location": "Centre de Convencions Internacional de Barcelona (CCIB)",
    "weather": "☀️ 맑음 24°C",
    "coords": {"lat": 41.4095, "lng": 2.2184},
    "weather_condition": "sunny",
    "temp": 24
}

def format_weather_display(weather_condition: str, temp: int) -> str:
    """날씨 조건과 온도를 조합하여 표시 문자열 생성"""
    weather_emoji_map = {
        "sunny": "☀️ 맑음",
        "cloudy": "☁️ 흐림",
        "rain": "🌧️ 비",
        "windy": "💨 바람",
        "unknown": "❓ 알 수 없음"
    }
    emoji_text = weather_emoji_map.get(weather_condition, "❓ 알 수 없음")
    return f"{emoji_text} {temp}°C"

# 질의응답 세션 저장소 (메모리)
question_sessions: Dict[str, QuestionSession] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    # 시작 시 환경변수 검증
    try:
        validate_env()
        print("✅ Environment variables validated successfully")
    except ValueError as e:
        print(f"❌ Environment validation failed: {e}")
        # 개발 환경에서는 경고만 출력
        if os.getenv("APP_ENV") != "development":
            raise
    
    # 앱 시작 시 현재 설정 출력
    print(f"🚀 앱 시작 시 설정: {app_config}")
    
    yield
    
    # 종료 시 정리 작업
    print("Application shutting down...")


# FastAPI 앱 생성
app = FastAPI(
    title="What should I do now?",
    description="여행자를 위한 킬링타임 추천 서비스",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발용, 프로덕션에서는 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙 (UI용)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """헬스체크 엔드포인트"""
    return HealthResponse(
        status="ok",
        time=datetime.now().isoformat()
    )


@app.get("/api/context")
async def get_context():
    """현재 위치와 날씨 정보를 반환하는 엔드포인트"""
    location = os.getenv("APP_LOCATION", app_config["location"])
    weather_condition = os.getenv("APP_WEATHER_CONDITION", app_config["weather_condition"])
    temp = int(os.getenv("APP_TEMP", str(app_config["temp"])))
    weather = os.getenv("APP_WEATHER", format_weather_display(weather_condition, temp))

    return {
        "location": location,
        "weather": weather,
        "coords": app_config["coords"],
        "weather_condition": app_config["weather_condition"],
        "temp": app_config["temp"]
    }


# 노드 이름과 단계 번호 매핑
NODE_TO_STEP = {
    "initialize_context": 1,
    "generate_queries": 2,
    "search_and_normalize": 3,
    "filter_by_travel_time": 4,
    "classify_time": 5,
    "rank_activities": 6,
    "llm_evaluate": 7,
    "fetch_reviews": 8,
    "generate_fallback": 9
}

# 단계별 텍스트
STEP_TEXTS = {
    1: "🔧 컨텍스트 초기화 중...",
    2: "🤖 검색 쿼리 생성 중...",
    3: "🔍 장소 검색 및 정규화 중...",
    4: "🚗 이동시간 필터링 중...",
    5: "⏰ 시간 적합도 분류 중...",
    6: "🏆 활동 랭킹 중...",
    7: "🧠 AI 평가 및 선별 중...",
    8: "💬 리뷰 수집 및 요약 중...",
    9: "✨ 최종 결과 생성 중..."
}

@app.post("/api/recommend/stream")
async def recommend_activities_stream(request: RecommendRequest):
    """활동 추천 엔드포인트 (SSE 스트리밍)"""
    
    async def event_generator():
        start_time = time.time()
        result = None
        
        try:
            print("=================================")
            print("[Gap-time Companion Agent 시작]")
            print("=================================")
            print(f"요청: {request.preferences.time_bucket}, {request.preferences.budget_level}, {[t.value for t in request.preferences.themes]}")
            
            # 초기 상태 구성
            initial_state = {
                "preferences": request.preferences,
                "context_override": request.context_override or {},
                "start_time": start_time
            }
            
            # LangGraph 이벤트 스트리밍
            print("\nLangGraph 워크플로우 실행 중 (스트리밍)...")
            
            async for event in companion_graph.astream_events(initial_state, version="v2"):
                event_type = event.get("event")
                node_name = event.get("name", "")
                
                # 노드 시작 이벤트
                if event_type == "on_chain_start" and node_name in NODE_TO_STEP:
                    step = NODE_TO_STEP[node_name]
                    text = STEP_TEXTS.get(step, f"{node_name} 처리 중...")
                    
                    yield f"data: {json.dumps({'type': 'step_start', 'step': step, 'text': text, 'node': node_name})}\n\n"
                
                # 노드 완료 이벤트
                elif event_type == "on_chain_end" and node_name in NODE_TO_STEP:
                    step = NODE_TO_STEP[node_name]
                    
                    yield f"data: {json.dumps({'type': 'step_complete', 'step': step, 'node': node_name})}\n\n"
                    
                    # 최종 결과 저장 (마지막 노드 완료 시)
                    if node_name == "generate_fallback":
                        # 최종 상태 가져오기
                        if "data" in event and "output" in event["data"]:
                            result = event["data"]["output"]
                        elif "data" in event and isinstance(event["data"], dict):
                            result = event["data"]
            
            # 최종 결과가 없으면 전체 그래프 실행 결과 가져오기
            if not result:
                print("   ⚠️ 이벤트에서 최종 결과를 찾을 수 없음 - 전체 실행으로 대체")
                result = await companion_graph.ainvoke(initial_state)
            
            # 최종 결과 전송
            if result:
                end_time = time.time()
                latency_ms = int((end_time - start_time) * 1000)
                
                print("=================================")
                print("[최종 결과 요약]")
                print("=================================")
                print(f"총 소요시간: {latency_ms}ms")
                print(f"검색 통계: {result.get('source_stats', {})}")
                print(f"폴백 사용: {'예' if result.get('fallback_used', False) else '아니오'}")
                print(f"최종 추천: {len(result['ranked_items'])}개")
                for i, item in enumerate(result['ranked_items'], 1):
                    print(f"   {i}. {item.name} ({item.total_score:.1f}점)")
                print("=================================\n")
                
                # LLM 평가 결과가 있으면 사용, 없으면 기본 결과 사용
                final_items = result.get("llm_selected_items", result["ranked_items"])
                
                # Pydantic 모델을 dict로 변환
                def to_dict(obj):
                    if hasattr(obj, "dict"):
                        return obj.dict()
                    elif hasattr(obj, "__dict__"):
                        return {k: to_dict(v) for k, v in obj.__dict__.items()}
                    elif isinstance(obj, list):
                        return [to_dict(item) for item in obj]
                    elif isinstance(obj, dict):
                        return {k: to_dict(v) for k, v in obj.items()}
                    else:
                        return obj
                
                response_data = {
                    "session_id": result.get("session_id", ""),
                    "context": to_dict(result.get("context", {})),
                    "items": [to_dict(item) for item in final_items],
                    "meta": {
                        "latencyMs": latency_ms,
                        "sourceStats": result.get("source_stats", {}),
                        "fallbackUsed": result.get("fallback_used", False),
                        "llmEvaluated": "llm_selected_items" in result,
                        "llmEvaluation": result.get("llm_evaluation", "")
                    }
                }
                
                yield f"data: {json.dumps({'type': 'result', 'data': response_data})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': '결과를 생성할 수 없습니다.'})}\n\n"
                
        except Exception as e:
            import traceback
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
            
            print(f"❌ CRITICAL ERROR in recommend_activities_stream:")
            print(f"   Error Type: {error_details['error_type']}")
            print(f"   Error Message: {error_details['error_message']}")
            print(f"   Full Traceback:")
            print(error_details['traceback'])
            
            try:
                yield f"data: {json.dumps({'type': 'error', 'message': '추천을 생성하는 중 오류가 발생했습니다.', 'error_type': error_details['error_type']})}\n\n"
            except:
                pass  # 스트림이 이미 닫혔을 수 있음
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend_activities(request: RecommendRequest):
    """활동 추천 엔드포인트"""
    
    start_time = time.time()
    
    try:
        print("=================================")
        print("[Gap-time Companion Agent 시작]")
        print("=================================")
        print(f"요청: {request.preferences.time_bucket}, {request.preferences.budget_level}, {[t.value for t in request.preferences.themes]}")
        
        # 초기 상태 구성
        initial_state = {
            "preferences": request.preferences,
            "context_override": request.context_override or {},
            "start_time": start_time
        }
        
        # LangGraph 실행
        print("\nLangGraph 워크플로우 실행 중...")
        result = await companion_graph.ainvoke(initial_state)
        
        # 응답 생성
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        print("=================================")
        print("[최종 결과 요약]")
        print("=================================")
        print(f"총 소요시간: {latency_ms}ms")
        print(f"검색 통계: {result.get('source_stats', {})}")
        print(f"폴백 사용: {'예' if result.get('fallback_used', False) else '아니오'}")
        print(f"최종 추천: {len(result['ranked_items'])}개")
        for i, item in enumerate(result['ranked_items'], 1):
            print(f"   {i}. {item.name} ({item.total_score:.1f}점)")
        print("=================================\n")
        
        # LLM 평가 결과가 있으면 사용, 없으면 기본 결과 사용
        final_items = result.get("llm_selected_items", result["ranked_items"])
        
        response = RecommendResponse(
            session_id=result["session_id"],
            context=result["context"],
            items=final_items,
            meta={
                "latencyMs": latency_ms,
                "sourceStats": result.get("source_stats", {}),
                "fallbackUsed": result.get("fallback_used", False),
                "llmEvaluated": "llm_selected_items" in result,
                "llmEvaluation": result.get("llm_evaluation", "")
            }
        )
        
        return response
        
    except Exception as e:
        import traceback
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
        
        print(f"❌ CRITICAL ERROR in recommend_activities:")
        print(f"   Error Type: {error_details['error_type']}")
        print(f"   Error Message: {error_details['error_message']}")
        print(f"   Full Traceback:")
        print(error_details['traceback'])
        
        # 사용자에게는 간단한 메시지, 개발자에게는 상세 정보
        raise HTTPException(
            status_code=500,
            detail={
                "message": "추천을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "error_type": error_details['error_type'],
                "timestamp": datetime.now().isoformat()
            }
        )


# 질의응답 시스템 API들
class QuestionStartRequest(BaseModel):
    time_bucket: Optional[str] = None
    budget_level: Optional[str] = None
    themes: Optional[str] = None

@app.post("/api/questions/start")
async def start_question_session(request: QuestionStartRequest):
    """새로운 질의응답 세션 시작 - 첫 번째 질문만 생성"""
    session_id = str(uuid.uuid4())

    # 현재 컨텍스트 정보 수집
    current_location = os.getenv("APP_LOCATION", "Barcelona")
    current_weather_condition = os.getenv("APP_WEATHER_CONDITION", "sunny")
    current_temp = int(os.getenv("APP_TEMP", "24"))
    current_weather = os.getenv("APP_WEATHER", format_weather_display(current_weather_condition, current_temp))

    user_time = request.time_bucket if request else None
    user_budget = request.budget_level if request else None
    user_themes = request.themes if request else None

    # 첫 번째 질문만 생성
    first_question = await generate_first_question(
        location=current_location,
        weather=current_weather,
        temperature=current_temp,
        weather_condition=current_weather_condition,
        user_time=user_time,
        user_budget=user_budget,
        user_themes=user_themes
    )

    initial_preferences = {
        "time_bucket": request.time_bucket,
        "budget_level": request.budget_level,
        "themes": [request.themes]
    }
    
    session = QuestionSession(
        session_id=session_id,
        questions=[first_question],  # 첫 번째 질문만 저장
        current_question_index=0,
        is_completed=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        initial_preferences=initial_preferences
    )

    question_sessions[session_id] = session

    return QuestionResponse(
        session_id=session_id,
        current_question=first_question,
        is_completed=False,
        progress=0,
        can_go_back=False
    )

async def generate_first_question(location: str, weather: str, temperature: str, weather_condition: str,
                                  user_time: str = None, user_budget: str = None, user_themes: str = None) -> Question:
    """첫 번째 질문 생성 (컨텍스트 기반)"""
    import openai
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OpenAI API 키가 없습니다.")
        return Exception("OpenAI API 키가 없습니다. 개발자에게 문의해주세요.")

    try:
        client = AsyncOpenAI(api_key=api_key)

        # 사용자 선택 정보를 프롬프트에 포함
        user_info = ""
        if user_time or user_budget or user_themes:
            user_info = "\n**사용자 선택 정보:**\n"
            if user_time:
                user_info += f"- 선택한 시간: {user_time}\n"
            if user_budget:
                user_info += f"- 선택한 예산: {user_budget}\n"
            if user_themes:
                user_info += f"- 선택한 테마: {user_themes}\n"

        prompt = f"""당신은 사용자의 여행지 탐색을 돕는 에이전트입니다. 다음 컨텍스트를 바탕으로 사용자에게 첫 번째 질문을 생성해주세요.

**현재 컨텍스트:**
- 위치: {location}
- 날씨: {format_weather_display(weather_condition, temperature)}
- 사용자가 원하는 장소 테마: {user_themes}

**질문 생성 규칙:**
1. 사용자 선호 장소 테마에 맞춰, 적절한 장소를 탐색하기 위한 예비 질문을 생성
2. 사용자의 선호도를 이끌어낼 수 있는 넛지형 질문을 생성
3. 사용자가 이미 선택한 정보는 중복 질문하지 말고, 더 구체적인 세부사항을 묻는 질문 생성

다음 JSON 형식으로 응답해주세요:
{{
  "question": "질문 내용"
}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 사용자의 여행지 탐색을 돕는 에이전트입니다. JSON 형식으로만 응답하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"LLM 첫 번째 질문 생성 응답: {result}")

        # JSON 파싱 
        try:
            # ```json ``` 블록에서 JSON 추출
            if "```json" in result:
                json_start = result.find("```json") + 7
                json_end = result.find("```", json_start)
                json_content = result[json_start:json_end].strip()
            elif "```" in result:
                json_start = result.find("```") + 3
                json_end = result.find("```", json_start)
                json_content = result[json_start:json_end].strip()
            else:
                json_content = result
            
            data = json.loads(json_content)
            question_text = data.get("question", "")
            
            if question_text:
                return Question(
                    id=str(uuid.uuid4()),
                    question=question_text,
                    order=1
                )
            else:
                logger.error(f"질문 내용이 비어있음")
                return Exception(f"질문 내용이 비어있습니다.")

        except json.JSONDecodeError as e:
            logger.error(f"LLM 응답 JSON 파싱 실패: {e}")
            logger.debug(f"파싱 실패한 응답: {result}")
            return Exception(f"LLM 응답 JSON 파싱 실패: {e}")

    except Exception as e:
        logger.error(f"LLM 질문 생성 실패: {e}")
        return Exception(f"LLM 질문 생성 실패: {e}")


async def generate_next_question(location: str, weather: str, temperature: str, weather_condition: str,
                                  previous_qa: List[QuestionAnswerPair], question_number: int,
                                  user_time: str = None, user_budget: str = None, user_themes: str = None) -> Question:
    """이전 질문과 답변을 바탕으로, 다음 질문을 생성"""
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OpenAI API 키가 없습니다.")
        return Exception("OpenAI API 키가 없습니다. 개발자에게 문의해주세요.")
    try:
        client = AsyncOpenAI(api_key=api_key)

        # 이전 질문-답변 페어를 프롬프트에 포함
        qa_history = "\n**이전 질문과 답변:**\n"
        for qa in previous_qa:
            qa_history += f"Q{qa.order}: {qa.question}\nA{qa.order}: {qa.answer}\n\n"

        # 사용자 선택 정보
        user_info = ""
        if user_time or user_budget or user_themes:
            user_info = "\n**사용자 선택 정보:**\n"
            if user_time:
                user_info += f"- 선택한 남은 시간: {user_time}\n"
            if user_budget:
                user_info += f"- 선택한 예산 수준: {user_budget}\n"
            if user_themes:
                user_info += f"- 선택한 장소 테마: {user_themes}\n"

        # 질문 번호에 따라 다른 프롬프트 사용
        if question_number == 2:
            # 두 번째 질문: 탐색적 질문, 범위를 넓히는 질문
            prompt = f"""당신은 사용자의 여행지 탐색을 돕는 에이전트입니다. 이전 질문과 답변을 고려하여 두 번째 질문을 생성해주세요.

**현재 컨텍스트:**
- 위치: {location}
- 날씨: {format_weather_display(weather_condition, temperature)}
- 사용자가 원하는 장소 테마: {user_themes}

**이전 질문과 답변:**
{qa_history}

**질문 생성 규칙 (두 번째 질문 - 탐색 단계):**
1. 첫 번째 질문에서 다루지 않은 새로운 측면이나 관점을 탐색하는 질문을 생성
2. 사용자의 선호도 범위를 넓히기 위해 다양한 옵션을 제시하거나, 다른 카테고리나 특성을 탐색할 수 있도록 유도
3. 예를 들어, 활동 유형, 분위기, 경험 방식, 특별한 요구사항 등 새로운 차원을 탐색
4. 사용자가 이미 선택한 정보는 중복 질문하지 말고, 더 넓은 범위의 선호도를 파악할 수 있는 질문 생성
5. 단, 현재 컨텍스트(위치, 날씨, 테마)에서 벗어나면 안됨

다음 JSON 형식으로 응답해주세요:
{{
  "question": "질문 내용"
}}"""
        elif question_number == 3:
            # 세 번째 질문: 범위를 좁히고 디테일을 추가하는 질문
            prompt = f"""당신은 사용자의 여행지 탐색을 돕는 에이전트입니다. 이전 두 개의 질문과 답변을 바탕으로 세 번째 질문을 생성해주세요.

**현재 컨텍스트:**
- 위치: {location}
- 날씨: {format_weather_display(weather_condition, temperature)}
- 사용자가 원하는 장소 테마: {user_themes}

**이전 질문과 답변:**
{qa_history}

**질문 생성 규칙 (세 번째 질문 - 구체화 단계):**
1. 이전 두 개의 질문과 답변에서 수집한 정보를 종합하여, 사용자의 선호도를 구체화하고 디테일을 추가하는 질문을 생성
2. 범위를 좁혀서 더 구체적이고 세밀한 선호도를 파악할 수 있도록 유도
3. 예를 들어, 특정 분위기, 가격대, 활동 강도, 소요 시간, 접근성 등 구체적인 세부사항을 묻는 질문
4. 이전 답변에서 언급된 내용을 바탕으로, 더 깊이 있는 정보를 얻을 수 있는 후속 질문 생성
5. 최종적으로 적합한 장소를 추천하기 위해 필요한 핵심 정보를 수집하는 질문

다음 JSON 형식으로 응답해주세요:
{{
  "question": "질문 내용"
}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 사용자의 여행지 탐색을 돕는 에이전트입니다. JSON 형식으로만 응답하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"LLM {question_number}번째 질문 생성 응답: {result}")

        # JSON 파싱 
        try:
            # ```json ``` 블록에서 JSON 추출
            if "```json" in result:
                json_start = result.find("```json") + 7
                json_end = result.find("```", json_start)
                json_content = result[json_start:json_end].strip()
            elif "```" in result:
                json_start = result.find("```") + 3
                json_end = result.find("```", json_start)
                json_content = result[json_start:json_end].strip()
            else:
                json_content = result
            
            data = json.loads(json_content)
            question_text = data.get("question", "")
            
            if question_text:
                return Question(
                    id=str(uuid.uuid4()),
                    question=question_text,
                    order=question_number
                )
            else:
                logger.error(f"질문 내용이 비어있음")
                return Exception(f"질문 내용이 비어있습니다.")

        except json.JSONDecodeError as e:
            logger.error(f"LLM 응답 JSON 파싱 실패: {e}")
            logger.debug(f"파싱 실패한 응답: {result}")
            return Exception(f"LLM 응답 JSON 파싱 실패: {e}")   
    except Exception as e:
        logger.error(f"LLM 질문 생성 실패: {e}")
        return Exception(f"LLM 질문 생성 실패: {e}")


# async def generate_contextual_questions(location: str, weather: str, temperature: str, weather_condition: str,
#                                        user_time: str = None, user_budget: str = None, user_themes: str = None) -> List[Question]:
#     """현재 컨텍스트를 기반으로 LLM이 질문을 동적으로 생성"""
#     import openai
#     from openai import AsyncOpenAI
    
#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         logger.error("OpenAI API 키가 없습니다.")
#         return Exception("OpenAI API 키가 없습니다. 개발자에게 문의해주세요.")
#         return get_default_questions(location, weather, user_time, user_budget, user_themes)
    
#     try:
#         client = AsyncOpenAI(api_key=api_key)
        
#         # 사용자 선택 정보를 프롬프트에 포함
#         user_info = ""
#         if user_time or user_budget or user_themes:
#             user_info = "\n**사용자 선택 정보:**\n"
#             if user_time:
#                 user_info += f"- 선택한 시간: {user_time}\n"
#             if user_budget:
#                 user_info += f"- 선택한 예산: {user_budget}\n"
#             if user_themes:
#                 user_info += f"- 선택한 테마: {user_themes}\n"
        
#         prompt = f"""당신은 사용자의 여행지 탐색을 돕는 에이전트입니다. 다음 컨텍스트를 바탕으로 사용자에게 3개의 질문을 생성해주세요.

# **현재 컨텍스트:**
# - 위치: {location}
# - 날씨: {format_weather_display(weather_condition, temperature)}
# - 사용자가 원하는 장소 테마: {user_themes}

# **질문 생성 규칙:**
# 1. 현재 위치와 날씨를 고려한 질문
# 2. 사용자의 구체적인 선호도를 파악할 수 있는 질문
# 3. 각 질문은 서로 다른 측면을 다뤄야 함 (활동 유형, 분위기, 특별한 요구사항 등)
# 4. 자연스럽고 친근한 톤으로 작성
# 5. 구체적인 예시를 포함하여 사용자가 쉽게 답변할 수 있도록 함
# 6. 사용자가 이미 선택한 정보는 중복 질문하지 말고, 더 구체적인 세부사항을 묻는 질문 생성

# 다음 JSON 형식으로 응답해주세요:
# {{
#   "questions": [
#     {{
#       "question": "질문 내용",
#       "order": 1
#     }},
#     {{
#       "question": "질문 내용", 
#       "order": 2
#     }},
#     {{
#       "question": "질문 내용",
#       "order": 3
#     }}
#   ]
# }}"""

#         response = await client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "당신은 여행 추천 전문가입니다. JSON 형식으로만 응답하세요."},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.7,
#             max_tokens=500
#         )
        
#         result = response.choices[0].message.content.strip()
#         print(f"🤖 LLM 질문 생성 응답: {result[:200]}...")
        
#         # JSON 파싱
#         import json
#         try:
#             data = json.loads(result)
#             questions = []
            
#             for item in data.get("questions", []):
#                 question = Question(
#                     id=str(uuid.uuid4()),
#                     question=item.get("question", ""),
#                     order=item.get("order", 1)
#                 )
#                 questions.append(question)
            
#             # 순서대로 정렬
#             questions.sort(key=lambda x: x.order)
#             return questions[:3]  # 최대 3개
            
#         except json.JSONDecodeError as e:
#             print(f"❌ LLM 응답 JSON 파싱 실패: {e}")
#             return get_default_questions(location, weather)
            
#     except Exception as e:
#         print(f"❌ LLM 질문 생성 실패: {e}")
#         return get_default_questions(location, weather)






@app.post("/api/questions/answer", response_model=QuestionResponse)
async def answer_question(request: QuestionRequest):
    """질문에 답변하고 다음 질문 생성"""
    if request.session_id not in question_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    session = question_sessions[request.session_id]

    # 현재 질문에 답변 저장
    for question in session.questions:
        if question.id == request.question_id:
            question.answer = request.answer
            break

    # 다음 질문 번호 계산
    next_question_number = len(session.questions) + 1

    # 총 3개 질문이면 완료
    if next_question_number > 3:
        session.is_completed = True
        session.updated_at = datetime.now()
        return QuestionResponse(
            session_id=session.session_id,
            current_question=None,
            is_completed=True,
            progress=100,
            can_go_back=True
        )

    # 컨텍스트 정보
    current_location = os.getenv("APP_LOCATION", "Barcelona")
    current_weather_condition = os.getenv("APP_WEATHER_CONDITION", "sunny")
    current_temp = int(os.getenv("APP_TEMP", "24"))
    current_weather = os.getenv("APP_WEATHER", format_weather_display(current_weather_condition, current_temp))

    # 이전 질문-답변 페어 생성
    previous_qa = []
    for q in session.questions:
        if q.answer:
            previous_qa.append(QuestionAnswerPair(
                question=q.question,
                answer=q.answer,
                order=q.order
            ))

    # 다음 질문 생성 (이전 답변 기반)
    next_question = await generate_next_question(
        location=current_location,
        weather=current_weather,
        temperature=current_temp,
        weather_condition=current_weather_condition,
        previous_qa=previous_qa,
        question_number=next_question_number
    )

    # 세션에 질문 추가
    session.questions.append(next_question)
    session.current_question_index = len(session.questions) - 1
    session.updated_at = datetime.now()

    # 진행률 계산 (3개 질문 기준)
    progress = int((next_question_number - 1) / 3 * 100)

    return QuestionResponse(
        session_id=session.session_id,
        current_question=next_question,
        is_completed=False,
        progress=progress,
        can_go_back=True
    )

@app.post("/api/questions/back")
async def go_back_question(session_id: str):
    """이전 질문으로 돌아가기"""
    if session_id not in question_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    session = question_sessions[session_id]
    
    if session.current_question_index > 0:
        session.current_question_index -= 1
        session.updated_at = datetime.now()
    
    current_question = session.questions[session.current_question_index]
    progress = int((session.current_question_index / len(session.questions)) * 100)
    
    return QuestionResponse(
        session_id=session.session_id,
        current_question=current_question,
        is_completed=False,
        progress=progress,
        can_go_back=session.current_question_index > 0
    )

@app.get("/api/questions/{session_id}")
async def get_question_session(session_id: str):
    """질의응답 세션 정보 조회"""
    if session_id not in question_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    session = question_sessions[session_id]
    current_question = session.questions[session.current_question_index] if not session.is_completed else None
    progress = int((session.current_question_index / len(session.questions)) * 100)
    
    return QuestionResponse(
        session_id=session.session_id,
        current_question=current_question,
        is_completed=session.is_completed,
        progress=progress,
        can_go_back=session.current_question_index > 0
    )

@app.post("/api/questions/{session_id}/recommend", response_model=RecommendResponse)
async def get_recommendations_from_questions(session_id: str):
    """질의응답 결과를 기반으로 추천 생성"""
    if session_id not in question_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    session = question_sessions[session_id]
    
    if not session.is_completed:
        raise HTTPException(status_code=400, detail="모든 질문에 답변하지 않았습니다")
    
    # 질의응답 결과를 Preferences로 변환
    preferences = convert_question_answers_to_preferences(session)
    
    # 기존 추천 시스템 호출
    try:
        start_time = time.time()
        
        initial_state = {
            "preferences": preferences,
            "context_override": None
        }
        
        result = await companion_graph.ainvoke(initial_state)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # LLM 평가 결과가 있으면 사용, 없으면 기본 결과 사용
        final_items = result.get("llm_selected_items", result["ranked_items"])
        
        response = RecommendResponse(
            session_id=result["session_id"],
            context=result["context"],
            items=final_items,
            meta={
                "latencyMs": latency_ms,
                "sourceStats": result.get("source_stats", {}),
                "fallbackUsed": result.get("fallback_used", False),
                "llmEvaluated": "llm_selected_items" in result,
                "llmEvaluation": result.get("llm_evaluation", ""),
                "questionSessionId": session_id
            }
        )
        
        return response
        
    except Exception as e:
        import traceback
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
        
        print(f"❌ CRITICAL ERROR in get_recommendations_from_questions:")
        print(f"   Error Type: {error_details['error_type']}")
        print(f"   Error Message: {error_details['error_message']}")
        
        raise HTTPException(
            status_code=500,
            detail={
                "message": "추천을 생성하는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "error_type": error_details['error_type'],
                "timestamp": datetime.now().isoformat()
            }
        )

def convert_question_answers_to_preferences(session: QuestionSession) -> Preferences:
    """질의응답 결과를 Preferences 객체로 변환"""
    # 질문-응답 페어 생성
    question_answer_pairs = []
    for question in session.questions:
        if question.answer:
            question_answer_pairs.append(QuestionAnswerPair(
                question=question.question,
                answer=question.answer,
                order=question.order
            ))
    
    # 질문-응답 페어를 자연어로 변환
    natural_input = ""
    for pair in sorted(question_answer_pairs, key=lambda x: x.order):
        natural_input += f"Q: {pair.question} A: {pair.answer} "
    
    initial_prefs = session.initial_preferences
    
    from app.types.activity import TimeBucket, PriceLevel, Theme
    
    return Preferences(
        time_bucket=TimeBucket(initial_prefs["time_bucket"]),
        budget_level=PriceLevel(initial_prefs["budget_level"]),
        themes=[Theme(theme) for theme in initial_prefs["themes"]],
        natural_input=natural_input.strip()
    )


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """메인 UI 페이지 서빙"""
    # 환경 변수에서 값 가져오기
    location = os.getenv("APP_LOCATION", app_config["location"])
    weather_condition = os.getenv("APP_WEATHER_CONDITION", app_config["weather_condition"])
    temp = int(os.getenv("APP_TEMP", str(app_config["temp"])))
    weather = os.getenv("APP_WEATHER", format_weather_display(weather_condition, temp))

    print(f"📍 위치: {location}")
    print(f"🌤️ 날씨: {weather}")

    # static/index.html 파일 읽기
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()

        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        # 파일이 없으면 에러 메시지 반환
        return HTMLResponse(
            content="""
            <html>
            <body>
                <h1>Error: static/index.html not found</h1>
                <p>Please make sure the static files are properly set up.</p>
            </body>
            </html>
            """,
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    
    # argparse 설정
    parser = argparse.ArgumentParser(description="What should I do now? - 여행자를 위한 킬링타임 추천 서비스")
    parser.add_argument("--location", type=str, default="Centre de Convencions Internacional de Barcelona (CCIB)", 
                       help="현재 위치 (기본값: CCIB)")
    parser.add_argument("--lat", type=float, default=41.4095, 
                       help="위도 (기본값: 41.4095)")
    parser.add_argument("--lng", type=float, default=2.2184, 
                       help="경도 (기본값: 2.2184)")
    parser.add_argument("--weather-condition", type=str, default="sunny", 
                       choices=["sunny", "cloudy", "rain", "windy", "unknown"],
                       help="날씨 조건 (기본값: sunny)")
    parser.add_argument("--temp", type=int, default=24, 
                       help="온도 (섭씨, 기본값: 24)")
    parser.add_argument("--port", type=int, default=8000, 
                       help="서버 포트 (기본값: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", 
                       help="서버 호스트 (기본값: 0.0.0.0)")
    
    args = parser.parse_args()
    
    # 날씨 표시 문자열 생성
    weather_display = format_weather_display(args.weather_condition, args.temp)
    
    # 전역 변수 업데이트
    CURRENT_LOCATION = args.location
    CURRENT_WEATHER = weather_display
    CURRENT_COORDS = {"lat": args.lat, "lng": args.lng}
    CURRENT_WEATHER_CONDITION = args.weather_condition
    CURRENT_TEMP = args.temp
    
    # app_config 업데이트
    app_config["location"] = args.location
    app_config["weather"] = weather_display
    app_config["coords"] = {"lat": args.lat, "lng": args.lng}
    app_config["weather_condition"] = args.weather_condition
    app_config["temp"] = args.temp
    
    # 환경 변수로도 설정 (FastAPI에서 사용할 수 있도록)
    os.environ["APP_LOCATION"] = args.location
    os.environ["APP_WEATHER"] = weather_display
    os.environ["APP_WEATHER_CONDITION"] = args.weather_condition
    os.environ["APP_TEMP"] = str(args.temp)
    os.environ["APP_LAT"] = str(args.lat)
    os.environ["APP_LNG"] = str(args.lng)
    
    print(f"DEBUG: app_config 업데이트 후 = {app_config}")
    print(f"DEBUG: 환경 변수 설정 완료")
    
    # config.py의 DEFAULT_CONTEXT 업데이트
    update_default_context(
        location_label=args.location,
        lat=args.lat,
        lng=args.lng,
        weather_condition=args.weather_condition,
        temp_c=args.temp
    )
    
    print(f"🌍 위치: {CURRENT_LOCATION}")
    print(f"📍 좌표: {CURRENT_COORDS['lat']}, {CURRENT_COORDS['lng']}")
    print(f"🌤️ 날씨: {CURRENT_WEATHER_CONDITION} {CURRENT_TEMP}°C")
    print(f"🌐 서버: {args.host}:{args.port}")
    
    uvicorn.run(
        "main:app", 
        host=args.host, 
        port=args.port, 
        reload=True,
        log_level="info"
    )
