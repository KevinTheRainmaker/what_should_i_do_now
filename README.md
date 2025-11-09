# Gap-time Companion Agent (MVP)

바르셀로나 여행자를 위한 LangGraph 기반 즉시 추천 에이전트입니다.

## 🎯 프로젝트 개요

여행 중 생기는 애매한 빈 시간(30분~2시간)을 의미있게 채울 수 있도록 돕는 지능형 추천 서비스입니다. 사용자의 남는 시간, 예산, 테마 선호를 입력받아 바르셀로나 현지의 감성있는 활동을 즉시 추천합니다.

## 🏗️ 시스템 아키텍처

### LangGraph 워크플로우
```
initialize_context → generate_queries → search_and_normalize → classify_time → rank_activities → generate_fallback
```

### 핵심 노드들
- **context_initializer**: 바르셀로나 기준 위치/날씨/시간 초기화
- **query_writer**: 테마/예산/시간별 검색 쿼리 생성 (2-5개)
- **serp_parser**: SerpAPI(Google Maps) 우선, Bing 폴백 검색
- **activity_ranker**: 거리/시간/예산/평점/테마 종합 점수화
- **fallback_generator**: 검색 실패시 사전정의 추천 제공

## 🚀 시작하기

### 1. 환경 설정

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정 (.env 파일 생성)
cp env.example .env
```

### 2. 필수 API 키 설정

`.env` 파일에 다음 키들을 설정하세요:

```env
SERPAPI_KEY=your_serpapi_key_here
BING_API_KEY=your_bing_search_api_key_here
SUPABASE_URL=your_supabase_url_here
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
```

### 3. 서버 실행

```bash
# 개발 서버 실행
python main.py

# 또는 uvicorn 직접 실행
uvicorn main:app --reload
```

서버가 실행되면 http://localhost:8000 에서 웹 인터페이스를 확인할 수 있습니다.

## 📱 사용법

1. **시간 선택**: 30분 이하 ~ 2시간 이상 중 선택
2. **예산 설정**: 낮음(€) / 중간(€€) / 높음(€€€) 중 선택  
3. **테마 선택**: 휴식/쇼핑/식사/액티비티 중 다중 선택
4. **추천받기**: 상위 4개 현지 감성 추천 카드 확인
5. **길찾기**: 각 카드의 길찾기 버튼으로 Google Maps 연결

## 🔧 주요 기능

### ✅ 구현 완료 (P0)
- [x] LangGraph 기반 에이전트 워크플로우
- [x] 사전 정의 바르셀로나 컨텍스트 (Plaça de Catalunya 기준)
- [x] 3문항 입력 시스템 (시간/예산/테마)
- [x] SerpAPI + Bing Search 병렬 검색
- [x] 검색 결과 정규화 및 ActivityItem 변환
- [x] 거리/시간/예산/평점/테마 종합 랭킹
- [x] 상위 4개 추천 + 폴백 보장
- [x] Google Maps 길찾기 링크 생성
- [x] 한국어 UI 및 추천 이유 텍스트
- [x] FastAPI 기반 REST API
- [x] 반응형 모바일 웹 UI

### 🎯 SLA 목표
- 평균 응답 시간: ≤ 3초
- 추천 성공률: ≥ 35%
- 항상 최소 1개 추천 보장 (폴백 포함)
- 상위 4개 카드 노출

## 📁 프로젝트 구조

```
├── app/
│   ├── graph/
│   │   └── companion_graph.py      # LangGraph 워크플로우 정의
│   ├── nodes/                      # 각 에이전트 노드 구현
│   │   ├── context_node.py         # 컨텍스트 초기화
│   │   ├── query_node.py           # 검색 쿼리 생성
│   │   ├── search_node.py          # 외부 API 검색 & 정규화
│   │   ├── classifier_node.py      # 시간 버킷 분류
│   │   ├── ranker_node.py          # 활동 랭킹
│   │   └── fallback_node.py        # 폴백 추천
│   ├── types/                      # 타입 정의
│   │   ├── activity.py             # ActivityItem, Preferences 등
│   │   └── requests.py             # API 요청/응답 스키마
│   ├── utils/                      # 유틸리티
│   │   ├── category_mapping.py     # 카테고리 매핑 규칙
│   │   ├── geo.py                  # 지리 계산 함수
│   │   └── korean_text.py          # 한국어 텍스트 생성
│   └── config.py                   # 설정 및 상수
├── static/                         # 정적 파일
├── main.py                         # FastAPI 서버
├── requirements.txt                # Python 의존성
└── README.md
```

## 🔌 API 엔드포인트

### POST /api/recommend
활동 추천 요청
```json
{
  "preferences": {
    "time_bucket": "30-60",
    "budget_level": "mid", 
    "themes": ["relax", "food"]
  },
  "context_override": null
}
```

응답:
```json
{
  "session_id": "session_20241124_143022",
  "context": {
    "location_label": "Plaça de Catalunya",
    "coords": {"lat": 41.387, "lng": 2.170},
    "weather": {"condition": "sunny", "temp_c": 24}
  },
  "items": [
    {
      "name": "Café Central",
      "category": "cafe",
      "reason_text": "[도보 5분] 카페 · 평점 4.2/5. 예산 중간. 지금 휴식에 딱 맞아요.",
      "directions_link": "https://www.google.com/maps/dir/?api=1&destination=41.387,2.170"
    }
  ],
  "meta": {
    "latencyMs": 2340,
    "sourceStats": {"serpapi": 8, "bing": 2},
    "fallbackUsed": false
  }
}
```

### GET /api/health
헬스체크
```json
{
  "status": "ok",
  "time": "2024-11-24T14:30:22.123Z"
}
```

## 🧪 테스트

```bash
# API 테스트
curl -X POST "http://localhost:8000/api/recommend" \
  -H "Content-Type: application/json" \
  -d '{
    "preferences": {
      "time_bucket": "30-60",
      "budget_level": "low",
      "themes": ["relax"]
    }
  }'
```

## 🛠️ 개발 가이드

### 새 노드 추가하기
1. `app/nodes/` 에 새 노드 파일 생성
2. `app/graph/companion_graph.py` 에서 그래프에 노드 추가
3. 상태 타입 `CompanionState` 업데이트 (필요시)

### 새 카테고리 추가하기
1. `app/types/activity.py` 의 `CategoryType` 에 추가
2. `app/utils/category_mapping.py` 에 매핑 규칙 추가
3. `app/utils/korean_text.py` 에 한국어 라벨 추가

## 📈 확장 계획

### P1 개선사항
- [ ] 카테고리 다양성 제약 강화 (동일 카테고리 최대 2개)
- [ ] 세션 내 입력 유지 (localStorage)
- [ ] 현지 감성 배지 UI 표시

### P2 확장기능  
- [ ] 테마 확장 (예술/건축, 해변 루트)
- [ ] 즐겨찾기/최근 본 항목
- [ ] 실시간 위치/날씨 API 연동
- [ ] 다국어 지원

## 🤝 기여하기

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 📞 문의

프로젝트에 대한 문의나 제안사항이 있으시면 이슈를 생성해 주세요.

---

Made with ❤️ using LangGraph & FastAPI
