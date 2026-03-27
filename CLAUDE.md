# 프로젝트: Pixel-A-Factory (AI 기반 픽셀 애니메이션 자동화)

## 🎯 목표
Grok API, Gemini API, Python, Aseprite를 연동하여 인스타그램용 고화질 픽셀 캐릭터 애니메이션 제작 공정을 90% 이상 자동화한다.

## 💻 개발 환경 (Stack)
- **OS:** WSL2 on Windows 11 (RTX 4060 GPU 패스스루)
- **AI Chat:** Gemini API (google-genai SDK) — 캐릭터 대화 + 구조화 추출 + 멀티모달 프롬프트 개선
- **AI Generation:** xAI Grok API — 이미지 생성
- **Backend/Scripting:** Python 3.12+ (rembg[gpu], Pillow, Flask-SocketIO)
- **Animation Tool:** Aseprite (CLI 모드) 또는 Pillow/imageio 폴백
- **Target Platform:** Instagram Reels (9:16 비율, 고화질 픽셀 업스케일링)

## 🛠 파이프라인 단계 (Workflow)

### 1. Chat Phase (Gemini API)
- **Tool:** google-genai SDK + function calling
- **Task:** 사용자와 대화하며 캐릭터 스펙 구조화 추출

### 2. Generation + Preview Phase (Grok API + Flask-SocketIO)
- **Tool:** xAI Grok 이미지 생성 API + Flask-SocketIO 웹 UI (WebSocket)
- **Task:** 후보 이미지 3~5장 생성 → 웹 브라우저에서 실시간 미리보기 → 사용자 선택
- **Goal:** Gemini 멀티모달 분석으로 선택 이미지 + 피드백 → 프롬프트 개선 반복
- **진입점:** `python3 app.py` → `http://localhost:5050`

### 3. Processing Phase (Python Cleanup)
- **Script:** `pixel_cleaner.py`
- **Functions:**
  - `rembg`를 통한 배경 제거
  - 픽셀 그리드 정렬 (Nearest Neighbor)
  - 색상 양자화 (16색 팔레트)

### 4. Assembly Phase (Aseprite CLI / Pillow 폴백)
- **Task:** 개별 PNG 프레임을 GIF 또는 Sprite Sheet로 병합
- **Goal:** 인스타 업로드용 정수배(8x) 업스케일링 적용

## 📝 Claude에게 내리는 지침 (Instructions)
1. **코드 작성 시:** 모든 Python 코드는 RTX 4060의 CUDA 가속(`rembg[gpu]`)을 사용하도록 작성해줘.
2. **Aseprite 활용:** 수동 GUI 조작 대신 CLI 명령어나 Lua 스크립트를 우선적으로 제안해줘. Aseprite 미설치 시 Pillow/imageio 폴백을 사용해줘.
3. **인스타 최적화:** 결과물의 해상도가 1080x1920에 적합하도록 픽셀 보존형 업스케일링(Nearest Neighbor) 로직을 포함해줘.
4. **단계별 진행:** 내가 "Step [N] 진행해줘"라고 하면 해당 단계에 필요한 코드와 설정법을 상세히 알려줘.
5. **이미지 생성:** xAI Grok API를 기본 백엔드로 사용. Gemini 멀티모달로 이미지 분석 + 프롬프트 개선 반복.

---

## 🚀 로드맵 (Roadmap)
- [x] Step 1: 데이터 모델 + 설정 (models.py, config.py)
- [x] Step 2: Gemini 대화 엔진 (story_engine.py)
- [x] Step 3: 프롬프트 템플릿 (prompt_generator.py, templates/prompts.yaml)
- [x] Step 4: Grok 이미지 생성 API (grok_client.py) — SD Forge 제거, Grok 전용
- [x] Step 5: 이미지 후처리 (pixel_cleaner.py)
- [x] Step 6: Aseprite/Pillow GIF 조립 (aseprite_runner.py) — MP4 제거, GIF 전용
- [x] Step 7: 파이프라인 통합 (pipeline.py, chat.py)
- [x] Step 8: E2E 테스트 (tests/test_e2e.py)
- [x] Step 9: 캐릭터 저장/로드, CLI 옵션, 에러 핸들링, rembg GPU 검증
- [x] Step 10: 웹 미리보기 서버 (preview_server.py, templates/preview.html)
- [x] Step 11: Gemini 멀티모달 프롬프트 개선 (story_engine.py refine_prompt)
- [x] Step 12: 상태 머신 워크플로우 (session.py) — 대화→생성→미리보기→수정→애니메이션
- [ ] Step 13: (선택) n8n 워크플로우 설계
