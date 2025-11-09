import time
import os
import argparse
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel

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
    weather = os.getenv("APP_WEATHER", app_config["weather"])

    return {
        "location": location,
        "weather": weather,
        "coords": app_config["coords"],
        "weather_condition": app_config["weather_condition"],
        "temp": app_config["temp"]
    }


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
    """새로운 질의응답 세션 시작"""
    session_id = str(uuid.uuid4())
    
    # 현재 컨텍스트 정보 수집
    current_location = os.getenv("APP_LOCATION", "Barcelona")
    current_weather = os.getenv("APP_WEATHER", "☀️ 맑음 24°C")
    current_temp = os.getenv("APP_TEMP", "24")
    current_weather_condition = os.getenv("APP_WEATHER_CONDITION", "sunny")
    
    # 사용자 선택 정보 (있는 경우)
    user_time = request.time_bucket if request else None
    user_budget = request.budget_level if request else None
    user_themes = request.themes if request else None
    
    # LLM이 컨텍스트 기반으로 질문 생성
    questions = await generate_contextual_questions(
        location=current_location,
        weather=current_weather,
        temperature=current_temp,
        weather_condition=current_weather_condition,
        user_time=user_time,
        user_budget=user_budget,
        user_themes=user_themes
    )
    
    session = QuestionSession(
        session_id=session_id,
        questions=questions,
        current_question_index=0,
        is_completed=False,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    question_sessions[session_id] = session
    
    return QuestionResponse(
        session_id=session_id,
        current_question=questions[0],
        is_completed=False,
        progress=0,
        can_go_back=False
    )

async def generate_contextual_questions(location: str, weather: str, temperature: str, weather_condition: str, 
                                       user_time: str = None, user_budget: str = None, user_themes: str = None) -> List[Question]:
    """현재 컨텍스트를 기반으로 LLM이 질문을 동적으로 생성"""
    import openai
    from openai import AsyncOpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # API 키가 없으면 기본 질문 사용
        return get_default_questions(location, weather, user_time, user_budget, user_themes)
    
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
        
        prompt = f"""당신은 여행 추천 전문가입니다. 다음 컨텍스트를 바탕으로 사용자에게 3개의 질문을 생성해주세요.

**현재 컨텍스트:**
- 위치: {location}
- 날씨: {weather} ({temperature}°C)
- 날씨 조건: {weather_condition}{user_info}

**질문 생성 규칙:**
1. 현재 위치와 날씨를 고려한 질문
2. 사용자의 구체적인 선호도를 파악할 수 있는 질문
3. 각 질문은 서로 다른 측면을 다뤄야 함 (활동 유형, 분위기, 특별한 요구사항 등)
4. 자연스럽고 친근한 톤으로 작성
5. 구체적인 예시를 포함하여 사용자가 쉽게 답변할 수 있도록 함
6. 사용자가 이미 선택한 정보는 중복 질문하지 말고, 더 구체적인 세부사항을 묻는 질문 생성

다음 JSON 형식으로 응답해주세요:
{{
  "questions": [
    {{
      "question": "질문 내용",
      "order": 1
    }},
    {{
      "question": "질문 내용", 
      "order": 2
    }},
    {{
      "question": "질문 내용",
      "order": 3
    }}
  ]
}}"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 여행 추천 전문가입니다. JSON 형식으로만 응답하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        result = response.choices[0].message.content.strip()
        print(f"🤖 LLM 질문 생성 응답: {result[:200]}...")
        
        # JSON 파싱
        import json
        try:
            data = json.loads(result)
            questions = []
            
            for item in data.get("questions", []):
                question = Question(
                    id=str(uuid.uuid4()),
                    question=item.get("question", ""),
                    order=item.get("order", 1)
                )
                questions.append(question)
            
            # 순서대로 정렬
            questions.sort(key=lambda x: x.order)
            return questions[:3]  # 최대 3개
            
        except json.JSONDecodeError as e:
            print(f"❌ LLM 응답 JSON 파싱 실패: {e}")
            return get_default_questions(location, weather)
            
    except Exception as e:
        print(f"❌ LLM 질문 생성 실패: {e}")
        return get_default_questions(location, weather)

def get_default_questions(location: str, weather: str, user_time: str = None, user_budget: str = None, user_themes: str = None) -> List[Question]:
    """기본 질문들 (LLM 실패 시 사용)"""
    questions = []
    
    # 사용자 선택 정보에 따라 질문 조정
    if not user_themes:
        questions.append(Question(
            id=str(uuid.uuid4()),
            question=f"{location}에서 어떤 종류의 활동을 하고 싶으신가요?",
            order=1
        ))
    else:
        questions.append(Question(
            id=str(uuid.uuid4()),
            question=f"선택하신 {user_themes} 활동 중에서 어떤 분위기를 원하시나요?",
            order=1
        ))
    
    questions.append(Question(
        id=str(uuid.uuid4()),
        question=f"현재 {weather}인데, 실내/실외 활동 중 어떤 것을 선호하시나요?",
        order=2
    ))
    
    questions.append(Question(
        id=str(uuid.uuid4()),
        question="혼자서 하시나요, 아니면 함께 하시나요?",
        order=3
    ))
    
    return questions

@app.post("/api/questions/answer", response_model=QuestionResponse)
async def answer_question(request: QuestionRequest):
    """질문에 답변하고 다음 질문으로 이동"""
    if request.session_id not in question_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    session = question_sessions[request.session_id]
    
    # 현재 질문에 답변 저장
    for question in session.questions:
        if question.id == request.question_id:
            question.answer = request.answer
            break
    
    # 다음 질문으로 이동
    session.current_question_index += 1
    session.updated_at = datetime.now()
    
    # 모든 질문이 완료되었는지 확인
    if session.current_question_index >= len(session.questions):
        session.is_completed = True
        return QuestionResponse(
            session_id=session.session_id,
            current_question=None,
            is_completed=True,
            progress=100,
            can_go_back=True
        )
    
    # 다음 질문 반환
    current_question = session.questions[session.current_question_index]
    progress = int((session.current_question_index / len(session.questions)) * 100)
    
    return QuestionResponse(
        session_id=session.session_id,
        current_question=current_question,
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
    
    # 기본값 설정 (질문 답변에서 추출할 수 없는 경우)
    time_bucket = "30-60"
    budget_level = "mid"
    themes = ["relax"]
    
    # 질문 답변들을 분석해서 기본값 업데이트
    for pair in question_answer_pairs:
        answer_lower = pair.answer.lower()
        
        # 시간 관련 키워드 분석
        if "30분" in answer_lower or "30분 이하" in answer_lower:
            time_bucket = "≤30"
        elif "1시간" in answer_lower or "60분" in answer_lower:
            time_bucket = "30-60"
        elif "2시간" in answer_lower:
            time_bucket = "60-120"
        elif "2시간 이상" in answer_lower:
            time_bucket = ">120"
        
        # 예산 관련 키워드 분석
        if "낮음" in answer_lower or "저렴" in answer_lower or "싸게" in answer_lower:
            budget_level = "low"
        elif "높음" in answer_lower or "비싸게" in answer_lower or "고급" in answer_lower:
            budget_level = "high"
        
        # 테마 관련 키워드 분석
        if "휴식" in answer_lower or "조용" in answer_lower:
            themes = ["relax"]
        elif "쇼핑" in answer_lower or "구매" in answer_lower:
            themes = ["shopping"]
        elif "식사" in answer_lower or "음식" in answer_lower or "맛집" in answer_lower:
            themes = ["food"]
        elif "액티비티" in answer_lower or "활동" in answer_lower or "운동" in answer_lower:
            themes = ["activity"]
    
    from app.types.activity import TimeBucket, PriceLevel, Theme
    
    return Preferences(
        time_bucket=TimeBucket(time_bucket),
        budget_level=PriceLevel(budget_level),
        themes=[Theme(theme) for theme in themes],
        natural_input=natural_input.strip()
    )


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """메인 UI 페이지 서빙"""
    # 환경 변수에서 값 가져오기
    location = os.getenv("APP_LOCATION", app_config["location"])
    weather = os.getenv("APP_WEATHER", app_config["weather"])

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
    parser.add_argument("--weather-display", type=str, default="☀️ 맑음 24°C", 
                       help="화면에 표시될 날씨 정보 (기본값: ☀️ 맑음 24°C)")
    parser.add_argument("--port", type=int, default=8000, 
                       help="서버 포트 (기본값: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", 
                       help="서버 호스트 (기본값: 0.0.0.0)")
    
    args = parser.parse_args()
    
    # 전역 변수 업데이트
    CURRENT_LOCATION = args.location
    CURRENT_WEATHER = args.weather_display
    CURRENT_COORDS = {"lat": args.lat, "lng": args.lng}
    CURRENT_WEATHER_CONDITION = args.weather_condition
    CURRENT_TEMP = args.temp
    
    # app_config 업데이트
    app_config["location"] = args.location
    app_config["weather"] = args.weather_display
    app_config["coords"] = {"lat": args.lat, "lng": args.lng}
    app_config["weather_condition"] = args.weather_condition
    app_config["temp"] = args.temp
    
    # 환경 변수로도 설정 (FastAPI에서 사용할 수 있도록)
    os.environ["APP_LOCATION"] = args.location
    os.environ["APP_WEATHER"] = args.weather_display
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
