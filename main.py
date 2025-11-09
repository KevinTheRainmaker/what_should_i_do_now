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
    # 환경 변수에서 값 가져오기 (우선순위)
    location = os.getenv("APP_LOCATION", app_config["location"])
    weather = os.getenv("APP_WEATHER", app_config["weather"])
    
    print(f"DEBUG: serve_ui에서 location = {location}")
    print(f"DEBUG: serve_ui에서 weather = {weather}")
    print(f"DEBUG: 환경 변수 APP_LOCATION = {os.getenv('APP_LOCATION')}")
    print(f"DEBUG: 환경 변수 APP_WEATHER = {os.getenv('APP_WEATHER')}")
    
    # 새로운 하이브리드 UI 파일 읽기
    try:
        with open("hybrid_ui.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # 현재 위치와 날씨 정보로 치환
        html_content = html_content.replace("{CURRENT_LOCATION}", location)
        html_content = html_content.replace("{CURRENT_WEATHER}", weather)
        
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        # 파일이 없으면 기본 HTML 반환
        html_template = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>What should I do now?</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .skeleton {
                background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                background-size: 200% 100%;
                animation: loading 1.5s infinite;
            }
            @keyframes loading {
                0% { background-position: 200% 0; }
                100% { background-position: -200% 0; }
            }
            .progress-bar {
                transition: width 0.3s ease;
            }
        </style>
    </head>
    <body class="bg-gray-50 min-h-screen">
        <div id="app" class="container mx-auto px-4 py-8 max-w-2xl">
            <!-- 헤더 -->
            <div class="text-center mb-8">
                <h1 class="text-3xl font-bold text-gray-800 mb-2">What should I do now?</h1>
                <p class="text-gray-600">여행자를 위한 킬링타임 추천 서비스</p>
                <div class="text-sm text-gray-500 mt-2">
                    📍 {CURRENT_LOCATION} · {CURRENT_WEATHER}
                </div>
            </div>

            <!-- Progress Bar -->
            <div class="mb-8">
                <div class="flex justify-between items-center mb-2">
                    <span class="text-sm font-medium text-gray-700">진행률</span>
                    <span id="progress-text" class="text-sm text-gray-500">0%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2">
                    <div id="progress-bar" class="bg-blue-600 h-2 rounded-full progress-bar" style="width: 0%"></div>
                </div>
            </div>

            <!-- 입력 폼 -->
            <div id="input-form" class="bg-white rounded-lg shadow-md p-6 mb-6">
                <form id="preferences-form">
                    <!-- 시간 선택 -->
                    <div class="mb-6">
                        <label class="block text-sm font-medium text-gray-700 mb-3">남는 시간이 얼마나 되시나요?</label>
                        <div class="grid grid-cols-2 gap-2">
                            <button type="button" class="time-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="≤30">30분 이하</button>
                            <button type="button" class="time-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="30-60">30분~1시간</button>
                            <button type="button" class="time-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="60-120">1~2시간</button>
                            <button type="button" class="time-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value=">120">2시간 이상</button>
                        </div>
                    </div>

                    <!-- 예산 선택 -->
                    <div class="mb-6">
                        <label class="block text-sm font-medium text-gray-700 mb-3">예산은 어느 정도로 생각하시나요?</label>
                        <div class="grid grid-cols-3 gap-2">
                            <button type="button" class="budget-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="low">낮음</button>
                            <button type="button" class="budget-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="mid">중간</button>
                            <button type="button" class="budget-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="high">높음</button>
                        </div>
                    </div>

                    <!-- 테마 선택 -->
                    <div class="mb-6">
                        <label class="block text-sm font-medium text-gray-700 mb-3">어떤 분위기를 원하시나요? (여러 개 선택 가능)</label>
                        <div class="grid grid-cols-2 gap-2">
                            <button type="button" class="theme-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="relax">휴식</button>
                            <button type="button" class="theme-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="shopping">쇼핑</button>
                            <button type="button" class="theme-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="food">식사</button>
                            <button type="button" class="theme-btn p-3 border-2 border-gray-200 rounded-lg text-sm hover:border-blue-500 hover:bg-blue-50" data-value="activity">액티비티</button>
                        </div>
                    </div>

                    <!-- 자연어 입력 (옵셔널) -->
                    <div class="mb-6">
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            💬 추가 요청사항 (선택사항)
                        </label>
                        <textarea id="natural-input" 
                                  class="w-full p-3 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                  rows="3"
                                  placeholder="예: 조용한 곳을 선호해요, 아이들과 함께 갈 수 있는 곳, 사진 찍기 좋은 곳, 현지인이 많이 가는 곳 등 자유롭게 입력해주세요"></textarea>
                        <p class="text-xs text-gray-500 mt-1">
                            이 정보는 더 정확한 추천을 위해 활용됩니다
                        </p>
                    </div>

                    <button type="submit" id="submit-btn" class="w-full bg-blue-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400">
                        추천받기
                    </button>
                </form>
            </div>

            <!-- 로딩 상태 -->
            <div id="loading" class="hidden">
                <div class="text-center mb-4">
                    <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                    <p id="loading-message" class="text-gray-600 mt-2">잠시만요, 근처 옵션을 찾고 있어요...</p>
                    <div id="progress-bar" class="w-full bg-gray-200 rounded-full h-2 mt-3">
                        <div id="progress-fill" class="bg-blue-600 h-2 rounded-full transition-all duration-300" style="width: 0%"></div>
                    </div>
                    <p id="progress-step" class="text-xs text-gray-500 mt-2">1/6 단계 진행 중...</p>
                </div>
                <div class="space-y-4">
                    <div class="bg-white rounded-lg shadow-md p-4">
                        <div class="skeleton h-4 rounded mb-2"></div>
                        <div class="skeleton h-3 rounded w-3/4 mb-2"></div>
                        <div class="skeleton h-3 rounded w-1/2"></div>
                    </div>
                    <div class="bg-white rounded-lg shadow-md p-4">
                        <div class="skeleton h-4 rounded mb-2"></div>
                        <div class="skeleton h-3 rounded w-3/4 mb-2"></div>
                        <div class="skeleton h-3 rounded w-1/2"></div>
                    </div>
                </div>
            </div>

            <!-- 결과 -->
            <div id="results" class="hidden">
                <h2 class="text-lg font-semibold text-gray-800 mb-4">추천 결과</h2>
                <div id="results-list" class="space-y-4"></div>
                <button id="retry-btn" class="w-full mt-4 bg-gray-200 text-gray-700 py-2 px-4 rounded-lg hover:bg-gray-300">
                    다시 추천받기
                </button>
            </div>

            <!-- 에러 상태 -->
            <div id="error" class="hidden bg-red-50 border border-red-200 rounded-lg p-4">
                <p class="text-red-700 mb-2">추천을 가져오는 중 문제가 발생했어요.</p>
                <button id="error-retry-btn" class="bg-red-600 text-white py-2 px-4 rounded hover:bg-red-700">
                    다시 시도
                </button>
            </div>
        </div>

        <script>
            // 상태 관리
            let selectedTime = null;
            let selectedBudget = null;
            let selectedThemes = [];

            // 시간 버튼 이벤트
            document.querySelectorAll('.time-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.time-btn').forEach(b => {
                        b.classList.remove('border-blue-500', 'bg-blue-100');
                        b.classList.add('border-gray-200');
                    });
                    btn.classList.add('border-blue-500', 'bg-blue-100');
                    btn.classList.remove('border-gray-200');
                    selectedTime = btn.dataset.value;
                });
            });

            // 예산 버튼 이벤트
            document.querySelectorAll('.budget-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.budget-btn').forEach(b => {
                        b.classList.remove('border-blue-500', 'bg-blue-100');
                        b.classList.add('border-gray-200');
                    });
                    btn.classList.add('border-blue-500', 'bg-blue-100');
                    btn.classList.remove('border-gray-200');
                    selectedBudget = btn.dataset.value;
                });
            });

            // 테마 버튼 이벤트 (다중 선택)
            document.querySelectorAll('.theme-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const value = btn.dataset.value;
                    if (selectedThemes.includes(value)) {
                        selectedThemes = selectedThemes.filter(t => t !== value);
                        btn.classList.remove('border-blue-500', 'bg-blue-100');
                        btn.classList.add('border-gray-200');
                    } else {
                        selectedThemes.push(value);
                        btn.classList.add('border-blue-500', 'bg-blue-100');
                        btn.classList.remove('border-gray-200');
                    }
                });
            });

            // 폼 제출
            document.getElementById('preferences-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                
                if (!selectedTime || !selectedBudget || selectedThemes.length === 0) {
                    alert('모든 항목을 선택해주세요.');
                    return;
                }

                // UI 상태 변경
                document.getElementById('input-form').classList.add('hidden');
                document.getElementById('loading').classList.remove('hidden');
                document.getElementById('results').classList.add('hidden');
                document.getElementById('error').classList.add('hidden');

                try {
                    console.log('API 요청 시작:', {
                        time_bucket: selectedTime,
                        budget_level: selectedBudget,
                        themes: selectedThemes
                    });

                    // 진행 상황 시뮬레이션 시작
                    simulateProgress();

                    // AbortController로 타임아웃 설정 (60초)
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 60000);

                    const response = await fetch(`/api/recommend?t=${Date.now()}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Cache-Control': 'no-cache',
                        },
                        signal: controller.signal,
                        body: JSON.stringify({
                            preferences: {
                                time_bucket: selectedTime,
                                budget_level: selectedBudget,
                                themes: selectedThemes,
                                natural_input: document.getElementById('natural-input').value.trim() || null
                            }
                        })
                    });

                    clearTimeout(timeoutId);

                    console.log('API 응답 상태:', response.status, response.statusText);

                    if (!response.ok) {
                        const errorText = await response.text();
                        console.error('API 에러 응답:', errorText);
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }

                    const data = await response.json();
                    console.log('API 성공 응답:', data);
                    
                    // 진행 상황 시뮬레이션 중지 및 완료 표시
                    stopProgressSimulation();
                    updateProgress(6, "✅ 추천 완료!", 100);
                    
                    // 약간의 딜레이 후 결과 표시
                    setTimeout(() => {
                        showResults(data);
                    }, 500);
                    
                } catch (error) {
                    console.error('상세 오류 정보:', {
                        message: error.message,
                        stack: error.stack,
                        type: error.constructor.name
                    });
                    
                    // 진행 상황 시뮬레이션 중지
                    stopProgressSimulation();
                    
                    // 사용자에게 더 구체적인 오류 메시지 표시
                    document.getElementById('loading').classList.add('hidden');
                    document.getElementById('error').classList.remove('hidden');
                    
                    const errorMessage = document.querySelector('#error p');
                    if (errorMessage) {
                        if (error.name === 'AbortError') {
                            errorMessage.textContent = '요청 시간이 초과되었습니다 (60초). 네트워크가 느리거나 서버가 응답하지 않습니다.';
                        } else if (error.message.includes('timeout')) {
                            errorMessage.textContent = '요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.';
                        } else if (error.message.includes('Failed to fetch')) {
                            errorMessage.textContent = '서버에 연결할 수 없습니다. 네트워크 연결을 확인해주세요.';
                        } else if (error.message.includes('500')) {
                            errorMessage.textContent = '서버에서 오류가 발생했습니다. 잠시 후 다시 시도해주세요.';
                        } else {
                            errorMessage.textContent = `오류: ${error.message}`;
                        }
                    }
                }
            });

            // 진행 상황 업데이트
            function updateProgress(step, message, percentage) {
                const loadingMessage = document.getElementById('loading-message');
                const progressFill = document.getElementById('progress-fill');
                const progressStep = document.getElementById('progress-step');
                
                if (loadingMessage) loadingMessage.textContent = message;
                if (progressFill) progressFill.style.width = percentage + '%';
                if (progressStep) progressStep.textContent = `${step}/6 단계 진행 중...`;
            }

            // 진행 상황 시뮬레이션
            let progressInterval = null;
            function simulateProgress() {
                const steps = [
                    { step: 1, message: "🔍 상황 분석 중...", duration: 2000 },
                    { step: 2, message: "🌐 장소 검색 중...", duration: 5000 },
                    { step: 3, message: "⏰ 시간 적합도 계산 중...", duration: 3000 },
                    { step: 4, message: "🏆 활동 랭킹 중...", duration: 4000 },
                    { step: 5, message: "🧠 LLM 평가 중...", duration: 8000 },
                    { step: 6, message: "📝 리뷰 수집 및 분석 중...", duration: 10000 }
                ];

                let currentStepIndex = 0;
                let startTime = Date.now();

                updateProgress(1, steps[0].message, 0);

                progressInterval = setInterval(() => {
                    const elapsed = Date.now() - startTime;
                    const currentStep = steps[currentStepIndex];
                    
                    if (elapsed >= currentStep.duration && currentStepIndex < steps.length - 1) {
                        currentStepIndex++;
                        startTime = Date.now();
                        const nextStep = steps[currentStepIndex];
                        updateProgress(nextStep.step, nextStep.message, (currentStepIndex / steps.length) * 85);
                    } else {
                        // 현재 단계 내에서의 진행률
                        const stepProgress = Math.min(elapsed / currentStep.duration, 1);
                        const totalProgress = ((currentStepIndex + stepProgress) / steps.length) * 85;
                        updateProgress(currentStep.step, currentStep.message, totalProgress);
                    }
                }, 500);
            }

            function stopProgressSimulation() {
                if (progressInterval) {
                    clearInterval(progressInterval);
                    progressInterval = null;
                }
            }

            // 결과 표시
            function showResults(data) {
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('results').classList.remove('hidden');
                
                // 디버깅용 콘솔 출력
                console.log('받은 데이터:', data);
                data.items.forEach((item, index) => {
                    console.log(`아이템 ${index + 1}:`, {
                        name: item.name,
                        review_summary: item.review_summary,
                        has_review: !!item.review_summary
                    });
                });
                
                const resultsList = document.getElementById('results-list');
                resultsList.innerHTML = '';
                
                // 세션 정보 표시
                const sessionInfo = document.createElement('div');
                sessionInfo.className = 'bg-gray-100 p-3 rounded-lg mb-4 text-xs text-gray-600';
                resultsList.appendChild(sessionInfo);
                
                console.log('전체 아이템 데이터:', data.items.map(item => ({name: item.name, photos: item.photos?.length || 0})));
                
                data.items.forEach((item, index) => {
                    console.log(`아이템 ${index + 1}: ${item.name}, 사진 개수: ${item.photos?.length || 0}`);
                    const card = document.createElement('div');
                    card.className = 'bg-white rounded-lg shadow-md p-4 hover:shadow-lg transition-shadow';
                    card.innerHTML = `
                        <div class="flex justify-between items-start mb-2">
                            <div class="flex items-center gap-2">
                                <span class="bg-blue-600 text-white w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold">${index + 1}</span>
                                <h3 class="font-semibold text-gray-800">${item.name}</h3>
                            </div>
                            <div class="flex gap-1">
                                ${item.llm_score ? `<span class="bg-purple-100 text-purple-800 px-2 py-1 rounded-full text-xs">AI추천 ${Math.round(item.llm_score)}점</span>` : ''}
                                ${item.locale_hints.local_vibe ? '<span class="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">현지감성</span>' : ''}
                            </div>
                        </div>
                        <p class="text-sm text-gray-600 mb-3">${item.reason_text}</p>
                        <div class="flex justify-between items-center text-xs text-gray-500 mb-3">
                            <span>${item.rating ? `⭐ ${item.rating}/5` : '평점 정보 없음'}</span>
                            <span>${item.review_count ? `👥 ${item.review_count.toLocaleString()}개 리뷰` : '리뷰 없음'}</span>
                            <span>${getBudgetText(item.budget_hint, item.category, item.name)}</span>
                        </div>
                        <div class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-4 mb-3 border border-blue-200 shadow-sm">
                            <div class="flex items-center justify-between mb-2">
                                <div class="flex items-center">
                                    <span class="text-lg">💬</span>
                                    <h4 class="text-sm font-bold text-blue-900 ml-2">방문객 리뷰 요약</h4>
                                </div>

                            </div>
                            ${item.review_summary && item.review_summary.trim() ? `
                                <p class="text-sm text-blue-800 leading-relaxed">${item.review_summary}</p>
                                ${item.top_reviews && item.top_reviews.length > 0 ? `
                                    <details class="mt-2">
                                        <summary class="text-xs text-blue-700 cursor-pointer hover:text-blue-900">원본 리뷰 ${item.top_reviews.length}개 보기</summary>
                                        <div class="mt-2 space-y-1">
                                            ${item.top_reviews.map((review, idx) => `
                                                <div class="text-xs text-gray-700 bg-white p-2 rounded border-l-2 border-blue-300">
                                                    ${idx + 1}. ${review}
                                                </div>
                                            `).join('')}
                                        </div>
                                    </details>
                                ` : ''}
                            ` : `
                                <p class="text-sm text-gray-600 italic">리뷰 정보를 수집 중입니다...</p>
                            `}
                        </div>
                        <!-- 교통수단별 이동시간 표시 -->
                        ${item.photos && item.photos.length > 0 ? `
                        <div class="border-t pt-3 mb-3">
                            <h4 class="text-sm font-semibold text-gray-700 mb-2">📸 사진 (${item.photos.length}개)</h4>
                            <div class="grid grid-cols-3 gap-2">
                                ${item.photos.slice(0, 3).map((photo, idx) => `
                                    <div class="relative aspect-square rounded-lg overflow-hidden bg-gray-100 cursor-pointer hover:opacity-80 transition-opacity"
                                         onclick="showPhotoModal('${photo.replace(/'/g, "\\'")}', '${item.name.replace(/'/g, "\\'")}')">
                                        <img src="${photo}" alt="${item.name} 사진 ${idx + 1}" 
                                             class="w-full h-full object-cover"
                                             onerror="console.log('이미지 로드 실패:', this.src); this.style.display='none'; this.parentElement.innerHTML='<div class=\\'flex items-center justify-center h-full text-gray-400 text-xs\\'>이미지<br>없음</div>'"
                                             onload="console.log('이미지 로드 성공:', this.src)">
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                        ` : ''}
                        
                        <div class="border-t pt-3 mb-3">
                            <h4 class="text-sm font-semibold text-gray-700 mb-2">🚗 이동시간</h4>
                            <div class="grid grid-cols-3 gap-2 text-center text-xs">
                                ${item.walking_time_min ? `
                                    <div class="bg-green-50 border border-green-200 rounded-lg p-2">
                                        <div class="text-green-600 font-semibold">🚶 도보</div>
                                        <div class="text-green-800 font-bold">${item.walking_time_min}분</div>
                                    </div>
                                ` : ''}
                                ${item.driving_time_min ? `
                                    <div class="bg-blue-50 border border-blue-200 rounded-lg p-2">
                                        <div class="text-blue-600 font-semibold">🚗 차량</div>
                                        <div class="text-blue-800 font-bold">${item.driving_time_min}분</div>
                                    </div>
                                ` : ''}
                                ${item.transit_time_min ? `
                                    <div class="bg-orange-50 border border-orange-200 rounded-lg p-2">
                                        <div class="text-orange-600 font-semibold">🚇 대중교통</div>
                                        <div class="text-orange-800 font-bold">${item.transit_time_min}분</div>
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                        <a href="${item.directions_link}" target="_blank" 
                           class="block w-full bg-blue-600 text-white text-center py-2 rounded hover:bg-blue-700">
                            길찾기
                        </a>
                    `;
                    resultsList.appendChild(card);
                });
            }

            // 에러 표시
            function showError() {
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('error').classList.remove('hidden');
            }

            // 다시 시도
            document.getElementById('retry-btn').addEventListener('click', () => {
                document.getElementById('results').classList.add('hidden');
                document.getElementById('input-form').classList.remove('hidden');
            });

            document.getElementById('error-retry-btn').addEventListener('click', () => {
                document.getElementById('error').classList.add('hidden');
                document.getElementById('input-form').classList.remove('hidden');
            });

            // 헬퍼 함수
            function getBudgetText(level, category, name) {
                const labels = {
                    'low': '💰 저렴',
                    'mid': '💰💰 중간', 
                    'high': '💰💰💰 비쌈',
                    'unknown': '❓ 예산 정보 없음'
                };
                
                // 확실한 정보가 있으면 그대로 반환
                if (level && level !== 'unknown') {
                    return labels[level];
                }
                
                // 없으면 카테고리나 이름 기반으로 추정
                const nameText = (name || '').toLowerCase();
                const categoryText = (category || '').toLowerCase();
                
                if (categoryText === 'park' || nameText.includes('park') || nameText.includes('parc')) {
                    return '🆓 무료 (추정)';
                } else if (categoryText === 'cafe' || nameText.includes('café') || nameText.includes('cafe')) {
                    return '💰 저렴 (추정)';
                } else if (categoryText === 'restaurant' || nameText.includes('restaurant')) {
                    return '💰💰 중간 (추정)';
                } else if (categoryText === 'museum' || nameText.includes('museum')) {
                    return '💰💰 중간 (추정)';
                }
                
                return '❓ 예산 정보 없음';
            }
            
            function showPhotoModal(photoUrl, placeName) {
                const modal = document.getElementById('photo-modal');
                const img = document.getElementById('modal-photo');
                const caption = document.getElementById('modal-caption');
                
                img.src = photoUrl;
                img.alt = placeName + ' 사진';
                caption.textContent = placeName;
                modal.classList.remove('hidden');
                
                // ESC 키로 모달 닫기
                document.addEventListener('keydown', function(e) {
                    if (e.key === 'Escape') {
                        hidePhotoModal();
                    }
                });
            }
            
            function hidePhotoModal() {
                const modal = document.getElementById('photo-modal');
                modal.classList.add('hidden');
            }
        </script>
        
        <!-- 사진 확대 모달 -->
        <div id="photo-modal" class="fixed inset-0 bg-black bg-opacity-75 hidden z-50 flex items-center justify-center p-4">
            <div class="relative max-w-4xl max-h-full">
                <button onclick="hidePhotoModal()" 
                        class="absolute top-2 right-2 text-white text-2xl font-bold bg-black bg-opacity-50 rounded-full w-8 h-8 flex items-center justify-center hover:bg-opacity-75">
                    ×
                </button>
                <img id="modal-photo" src="" alt="" class="max-w-full max-h-full rounded-lg">
                <p id="modal-caption" class="text-white text-center mt-2 text-sm"></p>
            </div>
        </div>
        
        <script>
            // 모달 배경 클릭 시 닫기
            document.addEventListener('DOMContentLoaded', function() {
                document.getElementById('photo-modal').addEventListener('click', function(e) {
                    if (e.target === this) {
                        hidePhotoModal();
                    }
                });
            });
        </script>
    </body>
    </html>
    """
    
    # 변수 치환 (CSS 중괄호 이스케이프)
    print(f"DEBUG: location = {location}")
    print(f"DEBUG: weather = {weather}")
    result = html_template.replace("{CURRENT_LOCATION}", location).replace("{CURRENT_WEATHER}", weather)
    print(f"DEBUG: 치환 후 결과 = {result[200:300]}...")  # 일부만 출력
    return result


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
