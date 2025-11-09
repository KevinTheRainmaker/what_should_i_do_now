/**
 * What should I do now? - 여행자를 위한 킬링타임 추천 서비스
 * JavaScript Application
 */

class HybridInterface {
    constructor() {
        this.sessionId = null;
        this.currentQuestion = null;
        this.isCompleted = false;
        this.answers = {};
        this.questionAnswers = {}; // 질의응답 결과 저장
        this.questions = []; // 질문 정보 저장

        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // 기존 폼 이벤트
        document.getElementById('preferences-form').addEventListener('submit', (e) => this.submitForm(e));

        // 시간/예산/테마 선택 이벤트
        document.querySelectorAll('.time-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.selectOption(e, 'time'));
        });
        document.querySelectorAll('.budget-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.selectOption(e, 'budget'));
        });
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.selectOption(e, 'theme'));
        });

        // 질의응답 이벤트
        const startQuestionsBtn = document.getElementById('start-questions-btn');
        if (startQuestionsBtn) {
            startQuestionsBtn.addEventListener('click', () => this.startQuestions());
        }
    }

    selectOption(event, type) {
        const button = event.target;
        const value = button.dataset.value;

        // 기존 선택 해제
        document.querySelectorAll(`.${type}-btn`).forEach(btn => {
            btn.classList.remove('border-blue-500', 'bg-blue-50');
            btn.classList.add('border-gray-200');
        });

        // 새 선택 적용
        button.classList.remove('border-gray-200');
        button.classList.add('border-blue-500', 'bg-blue-50');

        // 값 저장
        if (type === 'theme') {
            // 테마는 단일 선택으로 변경
            this[type] = value;
        } else {
            this[type] = value;
        }
    }

    async startQuestions() {
        try {
            // 사용자 선택 정보 수집
            const requestData = {
                time_bucket: this.time || null,
                budget_level: this.budget || null,
                themes: this.theme || null
            };

            // 로딩 상태 표시
            this.showQuestionLoading();

            const response = await fetch('/api/questions/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();
            this.sessionId = data.session_id;
            this.currentQuestion = data.current_question;
            this.isCompleted = data.is_completed;

            // 질문 정보 저장
            if (data.current_question) {
                this.questions.push(data.current_question);
            }

            this.showQuestionInterface();
            this.updateProgress(data.progress);
            this.displayCurrentQuestion();

        } catch (error) {
            console.error('질문 시작 실패:', error);
            alert('질문을 시작할 수 없습니다. 다시 시도해주세요.');
        }
    }

    showQuestionLoading() {
        // 질문 로딩 중 표시
        const questionInterface = document.getElementById('question-interface');
        const currentQuestion = document.getElementById('current-question');

        if (questionInterface && currentQuestion) {
            questionInterface.classList.remove('hidden');
            currentQuestion.innerHTML = `
                <div class="text-center py-8">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p class="text-gray-600">AI가 맞춤형 질문을 생성하고 있습니다...</p>
                </div>
            `;
        }
    }

    showQuestionInterface() {
        const inputForm = document.getElementById('input-form');
        const questionInterface = document.getElementById('question-interface');

        if (inputForm) inputForm.classList.add('hidden');
        if (questionInterface) questionInterface.classList.remove('hidden');

        // 추천 버튼 텍스트 변경
        const submitButton = document.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.textContent = '🤖 AI 질문 진행 중...';
            submitButton.disabled = true;
        }
    }

    getQuestionById(questionId) {
        // 저장된 질문 정보에서 질문 내용 찾기
        const question = this.questions.find(q => q.id === questionId);
        return question ? question.question : null;
    }

    displayCurrentQuestion() {
        if (this.currentQuestion) {
            // 질문 내용 복원
            const currentQuestionDiv = document.getElementById('current-question');
            if (!currentQuestionDiv) return;

            currentQuestionDiv.innerHTML = `
                <div class="mb-4">
                    <h3 id="question-text" class="text-lg font-medium text-gray-800 mb-4">${this.currentQuestion.question}</h3>
                    <div class="mb-4">
                        <textarea id="answer-input"
                                  class="w-full p-3 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                  rows="4"
                                  placeholder="답변을 입력해주세요...">${this.answers[this.currentQuestion.id] || ''}</textarea>
                    </div>
                    <div class="flex justify-between">
                        <button id="back-btn"
                                class="px-4 py-2 text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                disabled>
                            ← 이전 질문
                        </button>
                        <button id="next-btn"
                                class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed">
                            <span id="next-btn-text">다음 질문 →</span>
                            <span id="next-btn-loading" class="hidden">
                                <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                처리 중...
                            </span>
                        </button>
                    </div>
                </div>
            `;

            // 이벤트 리스너 재등록
            document.getElementById('next-btn').addEventListener('click', () => this.submitAnswer());
            document.getElementById('back-btn').addEventListener('click', () => this.goBack());

            // 포커스 설정
            document.getElementById('answer-input').focus();
        }
    }

    async submitAnswer() {
        const answerInput = document.getElementById('answer-input');
        if (!answerInput) return;

        const answer = answerInput.value.trim();
        if (!answer) {
            alert('답변을 입력해주세요.');
            return;
        }

        // 로딩 상태 시작
        this.setNextButtonLoading(true);

        try {
            const response = await fetch('/api/questions/answer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    question_id: this.currentQuestion.id,
                    answer: answer
                })
            });

            const data = await response.json();
            this.answers[this.currentQuestion.id] = answer;
            this.questionAnswers[this.currentQuestion.id] = answer;
            this.currentQuestion = data.current_question;
            this.isCompleted = data.is_completed;

            // 다음 질문 정보 저장
            if (data.current_question) {
                this.questions.push(data.current_question);
            }

            this.updateProgress(data.progress);

            if (this.isCompleted) {
                this.showCompletionSection();
                // 질문 완료 후 바로 추천 생성
                setTimeout(() => {
                    this.generateRecommendations();
                }, 1000); // 1초 후 추천 생성
            } else {
                // 질문 전환 시 페이드 효과
                this.fadeOutCurrentQuestion(() => {
                    this.displayCurrentQuestion();
                    this.fadeInCurrentQuestion();
                });
            }

        } catch (error) {
            console.error('답변 제출 실패:', error);
            alert('답변을 제출할 수 없습니다. 다시 시도해주세요.');
        } finally {
            // 로딩 상태 종료
            this.setNextButtonLoading(false);
        }
    }

    setNextButtonLoading(loading) {
        const nextBtn = document.getElementById('next-btn');
        const nextBtnText = document.getElementById('next-btn-text');
        const nextBtnLoading = document.getElementById('next-btn-loading');

        if (nextBtn && nextBtnText && nextBtnLoading) {
            if (loading) {
                nextBtn.disabled = true;
                nextBtnText.classList.add('hidden');
                nextBtnLoading.classList.remove('hidden');
            } else {
                nextBtn.disabled = false;
                nextBtnText.classList.remove('hidden');
                nextBtnLoading.classList.add('hidden');
            }
        }
    }

    fadeOutCurrentQuestion(callback) {
        const questionDiv = document.getElementById('current-question');
        if (!questionDiv) return;

        questionDiv.style.transition = 'opacity 0.3s ease-out';
        questionDiv.style.opacity = '0';

        setTimeout(() => {
            callback();
        }, 300);
    }

    fadeInCurrentQuestion() {
        const questionDiv = document.getElementById('current-question');
        if (!questionDiv) return;

        questionDiv.style.transition = 'opacity 0.3s ease-in';
        questionDiv.style.opacity = '1';
    }

    async generateRecommendations() {
        try {
            // 질문-응답 페어를 자연어 입력에 추가
            const naturalInput = document.getElementById('natural-input');
            let questionAnswerText = "";

            // 질문-응답 페어를 순서대로 정렬해서 저장
            const sortedAnswers = Object.entries(this.questionAnswers)
                .sort((a, b) => a[0].localeCompare(b[0]))
                .map(([questionId, answer]) => {
                    // 질문 ID로 질문 내용 찾기
                    const question = this.getQuestionById(questionId);
                    return question ? `Q: ${question} A: ${answer}` : `A: ${answer}`;
                });

            questionAnswerText = sortedAnswers.join('\n');
            if (naturalInput) {
                naturalInput.value = questionAnswerText;
            }

            // 폼 데이터 수집 (API 형식에 맞게)
            const formData = {
                preferences: {
                    time_bucket: this.time || '30-60',
                    budget_level: this.budget || 'mid',
                    themes: this.theme ? [this.theme] : ['relax'],
                    natural_input: questionAnswerText
                },
                context_override: null
            };

            this.showLoading();

            // 단계별 진행 상황 시뮬레이션 (await 제거 - 백그라운드에서 실행)
            const progressPromise = this.simulateProgress();

            const response = await fetch('/api/recommend', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            // API 응답이 왔으면 프로그레스 시뮬레이션 중단하고 결과 표시
            this.stopProgressSimulation();
            await this.completeAllSteps(); // 모든 단계 완료 표시

            // 약간의 딜레이 후 결과 표시
            setTimeout(() => {
                this.displayResults(data);
            }, 300);

        } catch (error) {
            console.error('추천 생성 실패:', error);
            alert('추천을 생성할 수 없습니다. 다시 시도해주세요.');
            this.stopProgressSimulation();
            this.hideLoading();
        }
    }

    async goBack() {
        try {
            const response = await fetch(`/api/questions/back?session_id=${this.sessionId}`, {
                method: 'POST'
            });

            const data = await response.json();
            this.currentQuestion = data.current_question;
            this.isCompleted = data.is_completed;

            this.updateProgress(data.progress);
            this.displayCurrentQuestion();

            // 뒤로 가기 버튼 상태 업데이트
            const backBtn = document.getElementById('back-btn');
            if (backBtn) {
                backBtn.disabled = !data.can_go_back;
            }

        } catch (error) {
            console.error('이전 질문으로 이동 실패:', error);
            alert('이전 질문으로 이동할 수 없습니다. 다시 시도해주세요.');
        }
    }

    showCompletionSection() {
        const currentQuestion = document.getElementById('current-question');
        const completionSection = document.getElementById('completion-section');

        if (currentQuestion) currentQuestion.classList.add('hidden');
        if (completionSection) completionSection.classList.remove('hidden');
    }

    updateProgress(progress) {
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');

        if (progressBar) progressBar.style.width = `${progress}%`;
        if (progressText) progressText.textContent = `${progress}%`;
    }

    async submitForm(event) {
        event.preventDefault();

        // AI 질문이 완료되지 않았으면 AI 질문부터 시작
        if (!this.sessionId || !this.isCompleted) {
            await this.startQuestions();
            return;
        }

        // 폼 데이터 수집 (API 형식에 맞게)
        const naturalInputEl = document.getElementById('natural-input');
        const formData = {
            preferences: {
                time_bucket: this.time || '30-60',
                budget_level: this.budget || 'mid',
                themes: this.theme ? [this.theme] : ['relax'],
                natural_input: naturalInputEl ? naturalInputEl.value : ''
            },
            context_override: null
        };

        this.showLoading();

        // 단계별 진행 상황 시뮬레이션 (백그라운드에서 실행)
        const progressPromise = this.simulateProgress();

        try {
            const response = await fetch('/api/recommend', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            const data = await response.json();

            // API 응답이 왔으면 프로그레스 시뮬레이션 중단하고 결과 표시
            this.stopProgressSimulation();
            await this.completeAllSteps(); // 모든 단계 완료 표시

            // 약간의 딜레이 후 결과 표시
            setTimeout(() => {
                this.displayResults(data);
            }, 300);

        } catch (error) {
            console.error('추천 생성 실패:', error);
            alert('추천을 생성할 수 없습니다. 다시 시도해주세요.');
            this.stopProgressSimulation();
            this.hideLoading();
        }
    }

    showLoading() {
        const inputForm = document.getElementById('input-form');
        const questionInterface = document.getElementById('question-interface');
        const completionSection = document.getElementById('completion-section');
        const loadingSection = document.getElementById('loading-section');

        if (inputForm) inputForm.classList.add('hidden');
        if (questionInterface) questionInterface.classList.add('hidden');
        if (completionSection) completionSection.classList.add('hidden');
        if (loadingSection) loadingSection.classList.remove('hidden');

        // 모든 단계 초기화
        this.resetAllSteps();
    }

    resetAllSteps() {
        for (let i = 1; i <= 9; i++) {
            const step = document.getElementById(`step-${i}`);
            if (!step) continue;

            const circle = step.querySelector('div');
            const text = step.querySelector('span:last-child');

            if (circle) circle.className = 'w-6 h-6 rounded-full bg-gray-300 flex items-center justify-center mr-3';
            if (text) text.className = 'text-sm text-gray-600';
        }
    }

    updateStep(stepNumber, status = 'active') {
        const step = document.getElementById(`step-${stepNumber}`);
        if (!step) return;

        const circle = step.querySelector('div');
        const text = step.querySelector('span:last-child');

        if (status === 'active') {
            if (circle) {
                circle.className = 'w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center mr-3';
                circle.innerHTML = '<div class="animate-spin rounded-full h-3 w-3 border-b-2 border-white"></div>';
            }
            if (text) text.className = 'text-sm text-blue-600 font-medium';
        } else if (status === 'completed') {
            if (circle) {
                circle.className = 'w-6 h-6 rounded-full bg-green-600 flex items-center justify-center mr-3';
                circle.innerHTML = '<svg class="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path></svg>';
            }
            if (text) text.className = 'text-sm text-green-600 font-medium';
        }
    }

    hideLoading() {
        const loadingSection = document.getElementById('loading-section');
        if (loadingSection) loadingSection.classList.add('hidden');
    }

    async simulateProgress() {
        // companion_graph 워크플로우에 맞춘 실제 처리 시간 기반 시뮬레이션
        const steps = [
            { step: 1, delay: 600, text: '🔧 컨텍스트 초기화 중...' },           // initialize_context
            { step: 2, delay: 1800, text: '🤖 검색 쿼리 생성 중...' },          // generate_queries (LLM 호출)
            { step: 3, delay: 3500, text: '🔍 장소 검색 및 정규화 중...' },     // search_and_normalize (API 호출)
            { step: 4, delay: 2200, text: '🚗 이동시간 필터링 중...' },         // filter_by_travel_time (API 호출)
            { step: 5, delay: 800, text: '⏰ 시간 적합도 분류 중...' },          // classify_time
            { step: 6, delay: 1000, text: '🏆 활동 랭킹 중...' },               // rank_activities
            { step: 7, delay: 3000, text: '🧠 AI 평가 및 선별 중...' },         // llm_evaluate (LLM 호출)
            { step: 8, delay: 5000, text: '💬 리뷰 수집 및 요약 중...' },       // fetch_reviews (API + LLM)
            { step: 9, delay: 800, text: '✨ 최종 결과 생성 중...' }            // generate_fallback
        ];

        this.progressRunning = true;
        this.currentProgressStep = 0;

        for (const { step, delay, text } of steps) {
            if (!this.progressRunning) break; // 중단 요청이 있으면 멈춤

            this.currentProgressStep = step;

            // 현재 단계 활성화
            this.updateStep(step, 'active');

            // 텍스트 업데이트
            const stepElement = document.getElementById(`step-${step}`);
            if (stepElement) {
                const textElement = stepElement.querySelector('span:last-child');
                if (textElement) textElement.textContent = text;
            }

            // 지연 시간 대기
            await new Promise(resolve => setTimeout(resolve, delay));

            if (!this.progressRunning) break; // 대기 후에도 확인

            // 단계 완료 표시
            this.updateStep(step, 'completed');
        }
    }

    stopProgressSimulation() {
        this.progressRunning = false;
    }

    async completeAllSteps() {
        // 현재 단계부터 9단계까지 빠르게 완료 표시
        for (let step = this.currentProgressStep || 1; step <= 9; step++) {
            this.updateStep(step, 'completed');
            await new Promise(resolve => setTimeout(resolve, 50)); // 빠른 애니메이션
        }
    }

    displayResults(data) {
        this.hideLoading();

        const resultsSection = document.getElementById('results-section');
        if (resultsSection) resultsSection.classList.remove('hidden');

        // 디버깅용 콘솔 출력
        console.log('받은 데이터:', data);
        if (data.items) {
            data.items.forEach((item, index) => {
                console.log(`아이템 ${index + 1}:`, {
                    name: item.name,
                    review_summary: item.review_summary,
                    has_review: !!item.review_summary
                });
            });
        }

        const resultsContent = document.getElementById('results-content');
        if (!resultsContent) return;

        resultsContent.innerHTML = '';

        // 세션 정보 표시
        const sessionInfo = document.createElement('div');
        sessionInfo.className = 'bg-gray-100 p-3 rounded-lg mb-4 text-xs text-gray-600';
        resultsContent.appendChild(sessionInfo);

        if (!data.items) {
            resultsContent.innerHTML += '<p class="text-gray-600">추천 결과가 없습니다.</p>';
            return;
        }

        console.log('전체 아이템 데이터:', data.items.map(item => ({name: item.name, photos: item.photos?.length || 0})));

        data.items.forEach((item, index) => {
            console.log(`아이템 ${index + 1}: ${item.name}, 사진 개수: ${item.photos?.length || 0}`);
            const card = document.createElement('div');
            card.className = 'bg-white rounded-lg shadow-md p-4 hover:shadow-lg transition-shadow mb-4';
            card.innerHTML = `
                <div class="flex justify-between items-start mb-2">
                    <div class="flex items-center gap-2">
                        <span class="bg-blue-600 text-white w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold">${index + 1}</span>
                        <h3 class="font-semibold text-gray-800">${item.name}</h3>
                    </div>
                    <div class="flex gap-1">
                        ${item.llm_score ? `<span class="bg-purple-100 text-purple-800 px-2 py-1 rounded-full text-xs">AI추천 ${Math.round(item.llm_score)}점</span>` : ''}
                        ${item.locale_hints && item.locale_hints.local_vibe ? '<span class="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">현지감성</span>' : ''}
                    </div>
                </div>
                <p class="text-sm text-gray-600 mb-3">${item.reason_text || item.description || '설명 없음'}</p>
                <div class="flex justify-between items-center text-xs text-gray-500 mb-3">
                    <span>${item.rating ? `⭐ ${item.rating}/5` : '평점 정보 없음'}</span>
                    <span>${item.review_count ? `👥 ${item.review_count.toLocaleString()}개 리뷰` : '리뷰 없음'}</span>
                    <span>${this.getBudgetText(item.budget_hint, item.category, item.name)}</span>
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
                <!-- 사진 표시 -->
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

                <!-- 이동시간 -->
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
                <a href="${item.directions_link || '#'}" target="_blank"
                   class="block w-full bg-blue-600 text-white text-center py-2 rounded hover:bg-blue-700">
                    길찾기
                </a>
            `;
            resultsContent.appendChild(card);
        });
    }

    // 헬퍼 함수들
    getBudgetText(level, category, name) {
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
}

// 전역 함수들
function showPhotoModal(photoUrl, placeName) {
    const modal = document.getElementById('photo-modal');
    const img = document.getElementById('modal-photo');
    const caption = document.getElementById('modal-caption');

    if (modal && img && caption) {
        img.src = photoUrl;
        img.alt = placeName + ' 사진';
        caption.textContent = placeName;
        modal.classList.remove('hidden');
    }

    // ESC 키로 모달 닫기
    const handleEscape = (e) => {
        if (e.key === 'Escape') {
            hidePhotoModal();
            document.removeEventListener('keydown', handleEscape);
        }
    };
    document.addEventListener('keydown', handleEscape);
}

function hidePhotoModal() {
    const modal = document.getElementById('photo-modal');
    if (modal) modal.classList.add('hidden');
}

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', () => {
    new HybridInterface();

    // 모달 배경 클릭 시 닫기
    const photoModal = document.getElementById('photo-modal');
    if (photoModal) {
        photoModal.addEventListener('click', function(e) {
            if (e.target === this) {
                hidePhotoModal();
            }
        });
    }
});
