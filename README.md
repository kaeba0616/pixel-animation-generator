# Pixel-A-Factory

AI 기반 픽셀 캐릭터 애니메이션 자동 생성기.
Gemini API와 대화하며 캐릭터를 디자인하고, Stable Diffusion Forge로 픽셀 애니메이션을 자동 생성합니다.

## 설치

### 1. Python 의존성

```bash
pip install -r requirements.txt
```

> **GPU 사용 시:** `rembg[gpu]`와 `onnxruntime-gpu`가 CUDA를 필요로 합니다. RTX 4060 기준 CUDA 12.6 권장.
>
> ```bash
> # CUDA 라이브러리 설치 (Ubuntu 24.04 / WSL2)
> wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
> sudo dpkg -i cuda-keyring_1.1-1_all.deb
> sudo apt-get update && sudo apt-get install -y cuda-libraries-12-6 libcudnn9-cuda-12
>
> # .bashrc에 추가 (한 번만)
> echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.6/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
> source ~/.bashrc
> ```

### 2. SD WebUI Forge 설치 (WSL)

```bash
bash scripts/install_forge.sh
# 또는 수동 설치:
git clone https://github.com/lllyasviel/stable-diffusion-webui-forge.git ~/sd-forge
cd ~/sd-forge
bash webui.sh --listen --api
```

첫 실행 시 모델 자동 다운로드 (10~20분). `Running on local URL: http://127.0.0.1:7860` 나오면 성공.

> **픽셀아트 체크포인트 (선택):** [Civitai](https://civitai.com)에서 SD 1.5 기반 픽셀아트 모델(.safetensors)을 다운로드하여 `~/sd-forge/models/Stable-diffusion/`에 넣으면 품질이 향상됩니다.

## 환경 설정

`.env` 파일을 편집하세요:

```bash
# 필수
GEMINI_API_KEY=your-api-key-here    # Google AI Studio에서 발급
SD_API_URL=http://127.0.0.1:7860    # SD Forge 주소 (기본값)

# 출력 포맷 (선택)
OUTPUT_FORMAT=gif                    # gif 또는 mp4
```

Gemini API 키: [Google AI Studio](https://aistudio.google.com/apikey)에서 무료 발급

---

## 사용법

SD Forge가 `--api` 모드로 실행 중인 상태에서 사용합니다.

### 모드 1: 대화 모드 (Gemini AI와 캐릭터 디자인)

```bash
python3 chat.py
```

AI와 대화하며 캐릭터를 디자인합니다:

```
> 파란 망토 입은 마법사 고양이 만들어줘. 별 모양 지팡이 들고 있어.
> 성격은 호기심 많고 장난기 있어
> 생성해줘
```

"생성해줘"라고 입력하면 자동으로:
1. 캐릭터 스펙 추출
2. SD Forge로 프레임 생성
3. 배경 제거 + 픽셀 정리
4. GIF/MP4로 조립
5. `output/{캐릭터명}/` 폴더에 저장

### 모드 2: 직접 생성 (저장된 캐릭터 사용)

이전에 생성한 캐릭터를 재사용하거나 Gemini 대화 없이 바로 생성합니다:

```bash
# 저장된 캐릭터로 idle 애니메이션 생성
python3 chat.py --load output/testcat/character.json

# 특정 액션 지정
python3 chat.py --load output/testcat/character.json --actions idle,walk,attack_sword

# MP4로 출력
python3 chat.py --load output/testcat/character.json --format mp4

# 인스타 Reels 최적화 (1080x1920 업스케일)
python3 chat.py --load output/testcat/character.json --format mp4 --instagram

# 배경 제거 건너뛰기 (빠른 테스트용)
python3 chat.py --load output/testcat/character.json --no-rembg

# 출력 디렉토리 지정
python3 chat.py --load output/testcat/character.json --output ./my_output
```

### CLI 옵션 전체 목록

```
python3 chat.py --help

옵션:
  --load PATH           저장된 캐릭터 JSON 파일 경로 (대화 건너뛰기)
  --actions ACTIONS     생성할 액션 (콤마 구분: idle,walk,attack_sword,cast_spell)
  --format {gif,mp4}    출력 포맷 (기본: gif)
  --no-rembg            배경 제거 건너뛰기
  --instagram           인스타 Reels 최적화 (1080x1920)
  --output PATH         출력 디렉토리 지정 (기본: ./output)
```

### 출력 구조

```
output/
└── 마법사고양이/
    ├── character.json      ← 캐릭터 스펙 (재사용 가능)
    ├── idle.gif            ← 대기 애니메이션
    ├── walk.gif            ← 걷기 애니메이션
    └── idle.mp4            ← MP4 버전 (--format mp4 사용 시)
```

---

## 테스트

### E2E 테스트 (SD Forge 필요)

```bash
python3 tests/test_e2e.py              # 전체 (Step 1~9)
python3 tests/test_e2e.py --step 7     # 캐릭터 저장/로드만
python3 tests/test_e2e.py --step 8     # MP4 출력만
python3 tests/test_e2e.py --skip-rembg # rembg 제외 (VRAM 절약)
```

| Step | 테스트 내용 | SD 필요 |
|------|-----------|---------|
| 1 | SD Forge 연결 + 샘플러 | O |
| 2 | txt2img 단일 프레임 | O |
| 3 | img2img 히어로 변형 | O |
| 4 | 후처리 (rembg + 그리드 + 양자화) | X |
| 5 | 전체 파이프라인 (4프레임 → GIF) | O |
| 6 | GPU VRAM 모니터링 | X |
| 7 | 캐릭터 JSON 저장/로드 | X |
| 8 | MP4 출력 + 인스타 업스케일 | X |
| 9 | rembg GPU 검증 | X |

### 단위 테스트 (SD Forge 불필요)

```bash
python3 -m pytest tests/ -v
```

| 테스트 파일 | 대상 | 검증 내용 |
|------------|------|----------|
| `test_prompt_generator.py` | `prompt_generator.py` | 프롬프트 조합, 액션 매핑, 시드 순번, 색상 팔레트 포함 여부 |
| `test_pixel_cleaner.py` | `pixel_cleaner.py` | 그리드 정렬(블록 균일성), 색상 양자화(팔레트 수 제한), 알파 채널 보존 |
