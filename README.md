# Pixel-A-Factory

AI 기반 픽셀 캐릭터 애니메이션 자동 생성기.
Gemini API와 대화하며 캐릭터를 디자인하고, Stable Diffusion Forge로 픽셀 애니메이션을 자동 생성합니다.

## 설치

### 1. Python 의존성

```bash
pip install -r requirements.txt
```

> **GPU 사용 시:** `rembg[gpu]`와 `onnxruntime-gpu`가 CUDA를 필요로 합니다. RTX 4060 기준 CUDA 11.8+ 권장.

### 2. SD WebUI Forge 설치 (WSL)

```bash
git clone https://github.com/lllyasviel/stable-diffusion-webui-forge.git ~/sd-forge
cd ~/sd-forge
bash webui.sh --api
```

첫 실행 시 모델 자동 다운로드 (10~20분). `Running on local URL: http://127.0.0.1:7860` 나오면 성공.

> **픽셀아트 체크포인트 (선택):** [Civitai](https://civitai.com)에서 SD 1.5 기반 픽셀아트 모델(.safetensors)을 다운로드하여 `~/sd-forge/models/Stable-diffusion/`에 넣으면 품질이 향상됩니다.

## 환경 설정

`.env` 파일을 편집하세요:

```bash
# 필수
GEMINI_API_KEY=your-api-key-here    # Google AI Studio에서 발급
SD_API_URL=http://127.0.0.1:7860    # SD Forge 주소 (기본값)
```

Gemini API 키: [Google AI Studio](https://aistudio.google.com/apikey)에서 무료 발급

## 실행

SD Forge가 실행 중인 상태에서:

```bash
python3 chat.py
```

AI와 대화하며 캐릭터를 디자인한 후, "생성해줘"라고 입력하면 애니메이션이 `output/` 폴더에 생성됩니다.

---

## 테스트

### 단위 테스트 실행

```bash
python3 -m pytest tests/ -v
```

외부 서비스(SD Forge, Gemini API) 없이 실행 가능합니다.

| 테스트 파일 | 대상 | 검증 내용 |
|------------|------|----------|
| `test_prompt_generator.py` | `prompt_generator.py` | 프롬프트 조합, 액션 매핑, 시드 순번, 색상 팔레트 포함 여부 |
| `test_pixel_cleaner.py` | `pixel_cleaner.py` | 그리드 정렬(블록 균일성), 색상 양자화(팔레트 수 제한), 알파 채널 보존 |

### 개별 모듈 수동 테스트

#### 1. SD Forge 연결 확인

```bash
python3 -c "
import sd_client
from models import FrameSpec

frame = FrameSpec(
    prompt='pixel art, chibi character, knight, transparent background',
    negative_prompt='blurry, realistic, 3d render',
    seed=42,
)
img = sd_client.txt2img(frame)
img.save('test_output.png')
print(f'생성 완료: {img.size}')
"
```

#### 2. 이미지 후처리 확인

```bash
python3 -c "
from PIL import Image
import pixel_cleaner

img = Image.open('test_output.png')
cleaned = pixel_cleaner.clean(img, remove_bg=True, grid_size=32, num_colors=16)
cleaned.save('test_cleaned.png')
print('후처리 완료')
"
```

> `rembg` 미설치 시 `remove_bg=False`로 배경 제거를 건너뛸 수 있습니다.

#### 3. 프롬프트 생성 확인

```bash
python3 -c "
from models import CharacterSpec, AnimationRequest
from prompt_generator import build_frame_specs

char = CharacterSpec(
    name='테스트 기사',
    body_type='medium',
    hair='blonde short hair',
    outfit='silver plate armor',
    accessories='longsword, round shield',
)
req = AnimationRequest(character=char, action='idle')
frames = build_frame_specs(req, base_seed=100)

for i, f in enumerate(frames):
    print(f'[Frame {i}] seed={f.seed}')
    print(f'  {f.prompt[:80]}...')
"
```

#### 4. GIF 조립 확인 (Aseprite 없이)

```bash
python3 -c "
from PIL import Image
import numpy as np
import aseprite_runner
from pathlib import Path

frames = []
for i in range(4):
    arr = np.zeros((128, 128, 4), dtype=np.uint8)
    arr[30:90, 30+i*5:90+i*5, :3] = 200
    arr[30:90, 30+i*5:90+i*5, 3] = 255
    frames.append(Image.fromarray(arr, 'RGBA'))

path = aseprite_runner.assemble(frames, Path('./output/test'), name='test_anim', scale=4)
print(f'GIF 생성: {path}')
"
```

#### 5. E2E 테스트

```bash
# SD Forge 실행 + GEMINI_API_KEY 설정 후
python3 chat.py
```

대화 예시:
```
> 파란 망토 입은 마법사 고양이 만들어줘. 별 모양 지팡이 들고 있어.
> 생성해줘
```

`output/` 폴더에 GIF가 생성되면 성공입니다.
