# 프로젝트: Pixel-A-Factory (AI 기반 픽셀 애니메이션 자동화)

## 🎯 목표
RTX 4060 환경에서 Stable Diffusion, Python, Aseprite를 연동하여 인스타그램용 고화질 픽셀 캐릭터 애니메이션 제작 공정을 90% 이상 자동화한다. (n8n 기반 오케스트레이션)

## 💻 개발 환경 (Stack)
- **OS:** Windows 11 (RTX 4060 GPU 활용)
- **AI Generation:** Stable Diffusion WebUI (A1111) with `--api` mode
- **Backend/Scripting:** Python 3.10+ (rembg[gpu], OpenCV, Pillow)
- **Animation Tool:** Aseprite (CLI 모드 활용)
- **Automation:** n8n (Docker 기반 로컬 실행 권장)
- **Target Platform:** Instagram Reels (9:16 비율, 고화질 픽셀 업스케일링)

## 🛠 파이프라인 단계 (Workflow)

### 1. Generation Phase (SD API)
- **Tool:** SD WebUI + LayerDiffusion
- **Task:** 투명 배경(Alpha channel)을 포함한 캐릭터 애니메이션 프레임 생성.
- **Goal:** 배경 제거 수작업 최소화.

### 2. Processing Phase (Python Cleanup)
- **Script Name:** `pixel_cleaner.py`
- **Functions:**
  - `rembg`를 통한 미세 잔상 제거.
  - `OpenCV`를 활용한 선화(Inking) 강화 및 이진화.
  - 픽셀 그리드 정렬 및 색상 인덱싱 최적화.

### 3. Assembly Phase (Aseprite CLI)
- **Task:** 개별 PNG 프레임을 하나의 GIF 또는 Sprite Sheet로 병합.
- **CLI Command:** `aseprite -b frame*.png --save-as animation.gif`
- **Goal:** 인스타 업로드용 정수배(4x, 8x) 업스케일링 적용.

### 4. Automation Phase (n8n)
- **Flow:** HTTP Request(SD) -> Python Script(Cleanup) -> Aseprite(Export) -> Final Output.

## 📝 Claude에게 내리는 지침 (Instructions)
1. **코드 작성 시:** 모든 Python 코드는 RTX 4060의 CUDA 가속(`rembg[gpu]`)을 사용하도록 작성해줘.
2. **Aseprite 활용:** 수동 GUI 조작 대신 CLI 명령어나 Lua 스크립트를 우선적으로 제안해줘.
3. **인스타 최적화:** 결과물의 해상도가 1080x1920에 적합하도록 픽셀 보존형 업스케일링(Nearest Neighbor) 로직을 포함해줘.
4. **단계별 진행:** 내가 "Step [N] 진행해줘"라고 하면 해당 단계에 필요한 코드와 설정법을 상세히 알려줘.

---

## 🚀 로드맵 (Roadmap)
- [ ] Step 1: SD WebUI API 연동 및 테스트 프롬프트 작성
- [ ] Step 2: Python `pixel_cleaner.py` 핵심 로직 구현
- [ ] Step 3: Aseprite CLI 자동화 명령어 세트 구성
- [ ] Step 4: n8n 워크플로우 설계 및 로컬 연동
