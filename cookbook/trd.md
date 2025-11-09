# 기술요구사항문서(TRD): Gap-time Companion Agent (MVP) — 바르셀로나 모바일 웹

## 0. 범위 및 목표
- 범위(MVP)
  - 사전 정의 위치/날씨/현재 시각 로딩
  - 3문항 입력(남는 시간, 예산 레벨, 테마)
  - 시간 버킷 분류, 검색 쿼리 생성, 웹 검색 수행
  - 검색 결과 정규화(ActivityItem), 랭킹, 상위 4개 카드 제시
  - 길찾기 링크 제공, 제로데이터 폴백
- 목표(SLO/KPI 대비)
  - 평균 응답 시간(검색 시작→추천 노출) ≤ 3s
  - 항상 최소 1개 추천(폴백 포함)
  - 상위 4개 카드 노출(결과 부족 시 폴백로 보충)
  - 텍스트 한국어 표기(현지 명칭 병기 허용)

---

## 1. 기술 스택
- 프론트엔드
  - Next.js 14 (App Router, React 18, TypeScript)
  - Tailwind CSS, Headless UI
- 백엔드
  - Next.js API Routes (Edge Runtime 우선, Node로 폴백)
  - 서버 통신: fetch(Web API)
  - 로깅: pino
- 데이터/분석
  - Supabase (Server-side only 사용): 이벤트 로깅, 간단한 설정값 저장
  - 분석 대안(옵트): PostHog/Google Analytics(GA4). 단, P0는 Supabase만.
- 외부 API
  - 1차: SerpAPI (engine=google_maps, google, 빠른 장소 데이터 수집)
  - 2차 폴백: Bing Web Search API(지도/장소 도메인 우선 필터)
- 국제화/텍스트
  - 템플릿 기반 한국어 문구 생성(LLM 미사용, 결정론적)
- 지도/길찾기
  - Google Maps Directions Link (universal link)

주의: Supabase/SerpAPI/Bing 키는 Next.js 서버 사이드에서만 사용하며 브라우저에 노출 금지.

---

## 2. 시스템 아키텍처
- 구성요소(노드) 및 인터랙션
  - context_initializer: 사전 정의 위치/날씨/시간 세팅
  - preference_collector: UI에서 입력 수집
  - gap_classifier: 시간 버킷 분류
  - query_writer: 검색 쿼리 자동 생성(2~5개)
  - serp_parser: 외부 검색 API 호출 및 결과 정규화(ActivityItem[])
  - activity_ranker: 점수 계산 및 상위 4개 선별
  - option_presenter: 카드 렌더링, 길찾기 링크
  - fallback_generator: 제로데이터 추천 생성
  - telemetry_logger: KPI 이벤트 로깅(Supabase)
- 데이터 흐름(동기)
  1) 초기 화면 로드 → context_initializer 로컬/서버 프리패치
  2) preference_collector 입력 완료 → gap_classifier 버킷 결정
  3) query_writer 쿼리 2~5개 생성
  4) serp_parser 병렬 호출(프로바이더 우선순위/타임아웃) → ActivityItem[]
  5) activity_ranker 점수화/상위 4개 선정 + 부족 시 fallback_generator 보충
  6) option_presenter 카드 노출(스켈레톤→완성)
  7) telemetry_logger 세션/결과/클릭 이벤트 기록

---

## 3. 프로젝트 폴더 구조
- 루트
  - app/
    - page.tsx (홈: 입력 폼 + 결과 영역)
    - api/
      - recommend/route.ts (추천 파이프라인 엔드포인트)
      - health/route.ts (헬스체크)
    - (components)/
      - PreferencesForm.tsx
      - ResultsList.tsx
      - ActivityCard.tsx
      - SkeletonCards.tsx
      - ErrorState.tsx
  - lib/
    - context.ts (사전 정의 컨텍스트 로딩)
    - classifier.ts (시간 버킷)
    - query.ts (쿼리 생성)
    - providers/
      - serpapi.ts (SerpAPI 호출)
      - bing.ts (Bing Web Search 호출)
    - normalize.ts (정규화/스키마 매핑)
    - ranker.ts (점수화/중복 제약)
    - fallback.ts (폴백 생성)
    - maps.ts (길찾기 링크 유틸)
    - telemetry.ts (Supabase 로깅)
    - cache.ts (메모리/서버 캐시)
    - errors.ts (에러 타입/코드)
    - config.ts (환경설정/상수)
  - data/
    - fallback_catalog.json (바르셀로나 제로데이터 후보)
    - categories.json (카테고리/태그 사전)
  - types/
    - activity.ts (ActivityItem 등 타입)
    - telemetry.ts (이벤트 스키마)
    - requests.ts (API I/O 스키마)
  - styles/
    - globals.css
  - .env.example
  - README.md

---

## 4. 데이터 모델 정의
- ActivityItem
  - id: string (provider:id 또는 해시)
  - name: string
  - category: "cafe" | "park" | "viewpoint" | "market" | "museum" | "shopping" | "restaurant" | "landmark" | "other"
  - priceLevel: "low" | "mid" | "high" | "unknown"
  - rating: number | null (0~5)
  - reviewCount: number | null
  - openNow: boolean | null
  - indoorOutdoor: "indoor" | "outdoor" | "mixed" | "unknown"
  - coords: { lat: number; lng: number } | null
  - distanceMeters: number | null (사용자 기준점과의 거리)
  - travelTimeMin: number | null (도보 기준 추정)
  - expectedWaitMin: number | null
  - expectedDurationMin: number | null (체류 추천치)
  - budgetHint: "low" | "mid" | "high" | "unknown"
  - themeTags: string[] (e.g., ["relax", "shopping", "food", "activity"])
  - sourceUrl: string | null
  - source: "serpapi_gmaps" | "bing" | "fallback"
  - localeHints: { localVibe: boolean; chain: boolean; nightSafe: boolean | null }
  - reasonText: string (한국어 템플릿 생성)
  - directionsLink: string
  - openHoursText: string | null
- Preferences
  - timeBucket: "≤30" | "30-60" | "60-120" | ">120"
  - budgetLevel: "low" | "mid" | "high"
  - themes: Array<"relax" | "shopping" | "food" | "activity">
- Context
  - locationLabel: string (예: "Plaça de Catalunya")
  - coords: { lat: number; lng: number }
  - weather: { condition: "sunny" | "cloudy" | "rain" | "windy" | "unknown"; tempC: number | null }
  - localTimeISO: string

---

## 5. API 명세
- POST /api/recommend
  - 요청(ReqBody)
    - contextOverride?: Partial<Context> (옵션)
    - preferences: Preferences
  - 응답(ResBody)
    - sessionId: string
    - context: Context
    - items: ActivityItem[] (최대 4개, 부족 시 폴백 포함)
    - meta: { latencyMs: number; sourceStats: Record<string, number>; fallbackUsed: boolean }
  - 에러
    - 400 INVALID_INPUT
    - 502 UPSTREAM_TIMEOUT
    - 500 INTERNAL_ERROR
  - 동작
    - 시간 예산: 2.4s(서치), 0.3s(정규화/랭킹), 0.2s(로깅) 총 ≤ 3s 목표
- GET /api/health
  - 200 OK + { status: "ok", time: ISO }

보안: 모든 키는 서버 환경변수(.env) 사용. CORS: same-origin. Rate limiting(경량): IP+세션 기준 초당 3req.

---

## 6. 컨텍스트 초기화(context_initializer)
- 입력: 없음(서버 기본값) 또는 contextOverride
- 처리:
  - 사전 정의 바르셀로나 기준점 로드
    - 기본값: locationLabel="Plaça de Catalunya", coords=(41.387, 2.170)
  - 날씨: 사전 정의(예: sunny, 24°C)
  - 현재 시각: 서버 시각 ISO
- 출력: Context
- 검증 기준:
  - 페이지 로드시 Context가 채워짐(오류 시 기본값으로 폴백)
  - 로깅: session_start 이벤트 기록

---

## 7. 선호 입력 수집(preference_collector)
- UI 요구:
  - 3문항(시간 버킷 4옵션, 예산 3옵션, 테마 4옵션 다중선택)
  - 터치 타겟 ≥ 44px, 한국어 라벨
- 출력: Preferences
- 검증 기준:
  - 입력 ≤ 3 탭 내 완료
  - 폼 재로딩 시 세션 내 상태 유지(P1)

---

## 8. 시간 버킷 분류(gap_classifier)
- 규칙:
  - 버킷: ≤30, 30-60, 60-120, >120
  - 이동+대기 포함 총 시간 ≤ 버킷 상한(>120은 상한 없음)
- 계산:
  - travelTimeMin: 거리(m)/80(m/min) 도보 추정, 최소 3분 하한
  - expectedWaitMin: 카테고리별 기본값(카페 5, 식당 10, 박물관 15, 야외 0)
  - expectedDurationMin: 카테고리 기본 체류(카페 25, 공원 20, 뷰포인트 15, 쇼핑 30, 박물관 60)
  - total = travel + wait + duration
- 결과:
  - total <= 버킷 상한이면 적합; 초과 시 패널티 부여 또는 제외
- 검증 기준:
  - 시간 초과 추천 비율 ≤ 10%

---

## 9. 쿼리 생성(query_writer)
- 입력: Context, Preferences
- 출력: 2~5개 검색 쿼리(QuerySpec[])
  - QuerySpec: { q: string; locale: "es-ES" | "ca-ES" | "en"; target: "gmaps" | "web"; radiusMeters: number }
- 규칙:
  - 테마 매핑
    - relax → "cozy cafe", "viewpoint", "quiet park"
    - shopping → "local market", "vintage shop", "stationery store"
    - food → "cheap eats", "tapas bar", "bakery"
    - activity → "small museum", "street performance", "art gallery"
  - 예산 키워드
    - low → "cheap", "€", "budget"
    - mid → "moderate", "€€"
    - high → "fine", "€€€"
  - 시간 버킷 반영(반경)
    - ≤30 → 800m
    - 30-60 → 1,500m
    - 60-120 → 3,000m
    - >120 → 5,000m
  - 언어/로컬
    - 우선 "es-ES"/"ca-ES" 키워드 + 영어 병행(혼합 2~3개)
  - 예:
    - "cozy cafe near Plaça de Catalunya €"
    - "local market Barcelona Ciutat Vella"
    - "viewpoint short walk Barcelona"
- 검증 기준:
  - 세션당 ≥ 2개 쿼리 생성
  - 테마·예산·시간 반영 키워드 포함

---

## 10. 검색 및 정규화(serp_parser, normalize)
- 프로바이더 호출 정책
  - 1차: SerpAPI (engine=google_maps) 병렬 2~3쿼리, 타임아웃 1.8s
  - 실패/부족 시: Bing Web Search 1~2쿼리, 타임아웃 1.2s
  - 전체 예산 ≤ 2.4s, 도중 완성된 결과부터 사용
- 정규화 전략
  - 카테고리: 도메인/스니펫/키워드 기반 매핑(categories.json)
  - 가격: 통화/기호(€, €€) 또는 텍스트 힌트 → low/mid/high/unknown
  - 평점/리뷰수: 리치 스니펫 또는 Maps 엔진 필드 사용
  - 영업 여부: open_now 필드 우선, 없으면 null
  - 실내/실외: 카테고리 기반 휴리스틱(카페=indoor, 공원=outdoor, 미술관=indoor, 전망=mixed)
  - 좌표: 제공 시 사용; 없으면 null
  - 거리/이동시간: Context.coords 기준 계산(Haversine → m → 도보 분)
  - 예상 대기/체류: 카테고리 기본값
  - 로컬 감성 태그: 체인 키워드(스타벅스 등) 감지 시 chain=true, 비체인 우대
- 출력: ActivityItem[]
- 검증 기준:
  - 각 후보 핵심 속성 ≥ 5개 채움(부재는 "unknown"/null 지정)
  - 영업 종료/휴무 후보 제외 또는 낮은 점수
  - 동일 체인/동일 유형 중복 방지(후술 랭킹 단계에서 강화)

---

## 11. 랭킹(activity_ranker)
- 입력: ActivityItem[], Preferences, Context
- 점수 구성(0~100)
  - distanceScore (20): exp(-distanceMeters/1000)*20 (좌표 없음=10)
  - timeFitScore (20): if total<=bucketMax then 20 else 20 - min(20, (total-bucketMax)/5)
  - budgetScore (15): match=15, adjacent=8, unknown=7, mismatch=0
  - ratingScore (15): (rating/5)*15 (null=7)
  - weatherScore (10): if rainy then indoor=10/outdoor=2/mixed=7; else outdoor boost(+3 capped)
  - themeMatch (15): themeTags 교집합 크기 기반(없음=6)
  - localVibe (5): non-chain=+5, chain=0
- 제약/후처리
  - 카테고리 다양성: 상위 4개 내 동일 카테고리 최대 2개(P1), 체인 중복 금지
  - 영업 종료/휴무: openNow=false는 점수 -15
  - 야간(22:00~05:00): nightSafe=false는 제외 또는 -20
- 선택: 상위 4개 채택, 부족분은 폴백 보충
- 카드 텍스트(reasonText) 템플릿(한국어)
  - 예: "[도보 N분] [카테고리_라벨], 평점 R/5. 예산 [낮음/중간/높음], 지금 가볍게 즐기기 좋아요."
- 검증 기준:
  - 항상 최대 4개 카드
  - 동일 체인 2개 초과 금지
  - 추천 이유 80자 이내, 한국어

---

## 12. 추천 카드(option_presenter)
- 카드 필드
  - 이름/카테고리 라벨(현지 명칭 병기 허용)
  - 예상 총 소요시간(범위 또는 합산값)
  - 예산 레벨(낮음/중간/높음)
  - 평점(정보 없음 명시)
  - 추천 이유(reasonText)
  - 길찾기 링크(directionsLink)
- 길찾기 링크 생성(maps.ts)
  - 선호: https://www.google.com/maps/dir/?api=1&destination=lat,lng
  - 좌표 없음: destination=encodeURIComponent(name + " Barcelona")
- UI/UX
  - 4개 카드 그리드/리스트(모바일 1열~2열 반응형)
  - 스켈레톤 로딩(≤1.5s 초기)
  - 오류/지연 시 4초에 폴백 우선 노출
- 검증 기준:
  - 링크 탭 시 외부 지도 열림
  - 모든 텍스트 한국어

---

## 13. 폴백(fallback_generator)
- 소스: data/fallback_catalog.json
  - 필수 필드: id, name, category, coords, indoorOutdoor, themeTags, reasonText, directionsLink
  - 예시 카테고리: 근처 산책 루트, 무료 포토스팟, 전망 포인트, 공공광장
- 선택 로직
  - Context.coords 기준 거리순 + 테마/날씨/시간 적합도 간단 점수
- 검증 기준
  - 항상 최소 1개 제공 가능
  - 폴백 카드도 길찾기 링크 포함

---

## 14. 성능/지연 예산
- 총 목표 ≤ 3.0s (서버 처리 기준)
  - API 오버헤드: 150ms
  - 쿼리 생성: 10ms
  - 외부 검색 병렬: 평균 1.2~1.6s, 타임아웃 1.8s
  - 정규화/랭킹: 150ms
  - 로깅: 비동기 100ms
- 프론트 초기 렌더 ≤ 1.5s
- 페일세이프: 4.0s 경과 시 즉시 폴백 우선 노출

---

## 15. 캐싱/중복 방지
- 서버 캐시(cache.ts)
  - Key: hash(q + radius + coords_bucket) → TTL 5분
  - 동일 세션 내 재요청 시 캐시 사용
- 디듀플리케이션
  - 동일 name+coords 또는 도메인 URL 해시 중복 제거
- 결과 샘플링
  - 동일 카테고리 과다 시 다양성 규칙 적용(P1)

---

## 16. 로깅/계측(telemetry_logger)
- 저장소: Supabase table: events
- 공통 필드
  - sessionId, eventType, ts, context(locationLabel, weather), prefs(timeBucket, budget, themes), meta
- 이벤트
  - session_start
  - input_submitted
  - results_shown { itemCount, latencyMs, fallbackUsed, sourceStats }
  - card_clicked { itemId, position, directionsLink }
  - error { code, provider, message, durationMs }
- KPI 계산(서버 사이드 배치 또는 외부 BI)
  - 추천 성공률 = (card_clicked 세션 비율)
  - 길찾기 클릭률 = (card_clicked / results_shown 아이템 노출)
  - 평균 응답 시간 = results_shown.latencyMs 평균
  - 폴백 비율 = results_shown.fallbackUsed 비율

---

## 17. 오류 처리 및 메시지
- 에러 코드
  - INVALID_INPUT(400), UPSTREAM_TIMEOUT(502), PROVIDER_ERROR(502), INTERNAL_ERROR(500)
- 사용자 메시지(한국어)
  - “잠시만요, 근처 옵션을 찾고 있어요…”
  - 타임아웃: “네트워크가 느려 산책 코스를 먼저 보여드려요.”
  - 검색결과 없음: “근처에서 가볍게 즐길 수 있는 무료 스팟을 추천드려요.”
- 재시도
  - 재시도 버튼(동일 입력) 제공
  - 다른 테마/반경 제안 문구(P1)

---

## 18. 구성/환경(env, config)
- .env
  - SERPAPI_KEY
  - BING_API_KEY (옵션 폴백)
  - NEXT_PUBLIC_APP_ENV (브라우저 노출 가능)
  - SUPABASE_URL
  - SUPABASE_SERVICE_ROLE_KEY (서버전용)
- config.ts
  - DEFAULT_CONTEXT(바르셀로나 기준점/날씨)
  - TIME_BUCKET_LIMITS
  - CATEGORY_DEFAULTS(wait/duration)
  - PROVIDER_TIMEOUTS
  - CACHE_TTL

---

## 19. 보안/프라이버시
- 개인 식별정보 수집 없음
- 위치는 사전 정의값만 사용(사용자 실시간 위치 비수집)
- API 키 서버 보관, 클라이언트 노출 금지
- Rate limiting 및 에러 은닉(스택 트레이스 미노출)

---

## 20. 접근성/현지화
- 한국어 UI/결과, 현지 명칭 병기 허용
- 키보드 포커스 순서, ARIA 라벨 적용
- 모바일 터치타겟 ≥ 44px

---

## 21. 작업 분해(원자적) 및 우선순위
- P0
  - FE: PreferencesForm 컴포넌트(3문항), ResultsList/Skeleton, ActivityCard, ErrorState
  - BE: /api/recommend 엔드포인트(파이프라인 오케스트레이션)
  - lib: context.ts, classifier.ts, query.ts, providers/serpapi.ts, normalize.ts, ranker.ts, maps.ts, fallback.ts, telemetry.ts, cache.ts
  - data: fallback_catalog.json, categories.json
  - infra: 환경변수/키 로딩, Edge 런타임 설정, 헬스체크
  - 품질: 시간·에러 슬라이스 계측, 기본 단위테스트(순수 함수)
- P1
  - 다양성 보장 로직 강화(동일 카테고리 2개 초과 제한)
  - 세션 내 입력 유지(새로고침 복원)
  - 현지 감성 배지/문구(로컬 감성 태깅 노출)
- P2
  - 테마 확장(예술·건축 산책, 해변 루트)
  - 즐겨찾기/최근 본 항목(클라이언트 로컬 스토리지)

의존성
- providers/serpapi.ts → query.ts, config.ts
- normalize.ts → categories.json, config.ts
- ranker.ts → classifier.ts, config.ts
- fallback.ts → data/fallback_catalog.json
- telemetry.ts → Supabase

완료 판단 기준
- P0: 수용 기준 충족 + 건강한 E2E 플로우 + SLA ≤ 3s
- P1: KPI 보조(다양성, 유지/재시도 UX) 적용

---

## 22. 검증/테스트 계획
- 단위 테스트
  - classifier: 버킷/시간 적합도 계산
  - query: 테마/예산/반경 반영 확인
  - normalize: 카테고리/가격/좌표/거리 계산
  - ranker: 점수 분해/합산, 제약 준수
  - maps: directionsLink 생성
- 통합 테스트
  - recommend API: 정상/부분 타임아웃/완전 타임아웃(폴백) 케이스
  - 다양성 제약(P1) 확인
- 성능 테스트
  - 병렬 쿼리 3개, 95퍼센타일 응답 ≤ 3.5s (폴백 포함)
- 수용 기준 체크리스트(요약)
  - 3문항만으로 추천 가능
  - 3초 이내 최소 1개 카드 노출
  - 최대 4개 카드(부족 시 폴백)
  - 각 카드 필수 필드 포함(이름/카테고리/총소요/예산/평점/이유/길찾기)
  - 시간 버킷 초과 ≤ 10%, 영업 종료 노출 ≤ 5%
  - 텍스트 한국어

---

## 23. UI 상태 정의(결정론적)
- Idle: 컨텍스트 표기 + 폼 노출
- Loading: 스켈레톤(최대 1.5s), 안내 문구
- Partial: 1~3개 먼저 노출 가능(옵션), 4초 경과 시 폴백 채움
- Ready: 4개 카드 또는 가능한 최대치
- Error: 친화적 메시지 + 재시도

---

## 24. 외부 API 계약(요약)
- SerpAPI(Google Maps)
  - 엔드포인트: https://serpapi.com/search.json?engine=google_maps&q=...&ll=lat,lng&api_key=...
  - 주요 필드: title, rating, reviews, type, gps_coordinates, open_state, links
- Bing Web Search
  - 엔드포인트: https://api.bing.microsoft.com/v7.0/search?q=...
  - 주요 필드: name, url, snippet, isFamilyFriendly
- 호출 제한
  - 쿼리당 최대 10 결과 수집, 상위 15개 합산 후 정규화
  - 타임아웃, 재시도 없음(속도 우선), 실패 시 즉시 폴백 플래그

---

## 25. 카테고리/태그 매핑 규칙(발췌)
- cafe|coffee|bakery → cafe (indoor)
- park|gardens|plaza|square → park (outdoor)
- viewpoint|mirador|bunkers → viewpoint (mixed/outdoor)
- market|mercat|flea|vintage → market/shopping
- museum|gallery → museum
- tapas|bar|restaurant → restaurant/food
- chain 키워드: starbucks, mcdonald, zara 등 → chain=true

---

## 26. 한국어 문구 템플릿
- 카테고리 라벨: 카페/공원/전망/마켓/미술관/쇼핑/식당/랜드마크/기타
- 예산 라벨: 낮음/중간/높음/정보 없음
- 추천 이유 패턴
  - “[도보 {travel}분] {cat} · 평점 {ratingText}. 예산 {budgetText}. 지금 {themeText}에 딱 맞아요.”
  - ratingText: “정보 없음” 처리
  - themeText: 휴식/쇼핑/식사/액티비티 중 우선 매칭 1개

---

## 27. 데이터 자산(초기)
- DEFAULT_CONTEXT
  - locationLabel: “Plaça de Catalunya”
  - coords: { lat: 41.387, lng: 2.170 }
  - weather: { condition: "sunny", tempC: 24 }
- fallback_catalog.json(샘플 항목 유형)
  - “Plaça de Catalunya 벤치 스폿”(park, outdoor)
  - “Passeig de Gràcia 윈도우 쇼핑”(shopping, outdoor)
  - “El Born 골목 포토스팟”(viewpoint, outdoor)
  - “Ciutadella 공원 짧은 산책”(park, outdoor)
  - 각 항목: 좌표, reasonText 사전 기입, directionsLink 포함

---

## 28. 릴리즈 체크리스트
- 환경변수 설정/검증(Supabase, SerpAPI, Bing)
- SerpAPI/Bing 쿼터/요금 확인(오버런 대비 타임아웃/폴백)
- Lighthouse 모니터링(모바일 성능/접근성)
- 개인정보/쿠키 배너 불필요 확인(PII 수집 없음)
- 관측성 대시보드: 응답시간/폴백비율/에러율

---

## 29. 리스크 및 대응
- 웹 검색 품질 편차 → 폴백 카탈로그 강화, 테마 대체 쿼리
- 영업 정보 최신성 부족 → open_now 불확실 시 패널티, 대안 제시
- 응답 시간 초과 → 타임아웃 단축, 부분 결과 우선 노출, 폴백 4초 규칙
- 야간 안전 → nightSafe 배지/우선순위, 어두운 골목/외곽 패널티

---

## 30. 유지보수/확장성 고려
- 모듈식 설계(lib/* 분리)
- 프로바이더 플러그형(추가 API: Foursquare/Places 교체 가능)
- 실시간 위치/날씨 추가 시 context_override만 확장
- 다국어 확장 시 템플릿/라벨 테이블화

---