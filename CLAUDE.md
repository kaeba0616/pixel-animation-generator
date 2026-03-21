# 프로젝트: Pixel-A-Factory (AI 기반 픽셀 애니메이션 자동화)

## 🎯 목표
RTX 4060 환경에서 Stable Diffusion Forge, Python, Aseprite를 연동하여 인스타그램용 고화질 픽셀 캐릭터 애니메이션 제작 공정을 90% 이상 자동화한다.

## 💻 개발 환경 (Stack)
- **OS:** WSL2 on Windows 11 (RTX 4060 GPU 패스스루)
- **AI Chat:** Gemini API (google-genai SDK) — 캐릭터 대화 + 구조화 추출
- **AI Generation:** Stable Diffusion WebUI Forge with `--api` mode
- **Backend/Scripting:** Python 3.12+ (rembg[gpu], OpenCV, Pillow)
- **Animation Tool:** Aseprite (CLI 모드) 또는 Pillow/imageio 폴백
- **Target Platform:** Instagram Reels (9:16 비율, 고화질 픽셀 업스케일링)

## 🛠 파이프라인 단계 (Workflow)

### 1. Chat Phase (Gemini API)
- **Tool:** google-genai SDK + function calling
- **Task:** 사용자와 대화하며 캐릭터 스펙 구조화 추출

### 2. Generation Phase (SD Forge API)
- **Tool:** SD WebUI Forge + img2img 2-Pass 전략
- **Task:** 투명 배경(Alpha channel)을 포함한 캐릭터 애니메이션 프레임 생성
- **Goal:** 히어로 프레임 기반 캐릭터 일관성 유지

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
5. **SD 백엔드:** A1111이 아닌 Forge를 기준으로 안내해줘. API는 동일하지만 Forge가 VRAM 최적화 및 Python 3.12 호환이 더 좋음.

---

## 🚀 로드맵 (Roadmap)
- [x] Step 1: 데이터 모델 + 설정 (models.py, config.py)
- [x] Step 2: Gemini 대화 엔진 (story_engine.py)
- [x] Step 3: 프롬프트 템플릿 (prompt_generator.py, templates/prompts.yaml)
- [x] Step 4: SD API 래퍼 (sd_client.py)
- [x] Step 5: 이미지 후처리 (pixel_cleaner.py)
- [x] Step 6: Aseprite/Pillow 조립 (aseprite_runner.py)
- [x] Step 7: 파이프라인 통합 (pipeline.py, chat.py)
- [x] Step 8: SD Forge 설치 및 E2E 테스트 (scripts/install_forge.sh, tests/test_e2e.py)
- [ ] Step 9: (선택) n8n 워크플로우 설계
