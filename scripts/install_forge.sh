#!/usr/bin/env bash
# SD WebUI Forge 설치 스크립트 (WSL2 + RTX 4060 Ti)
set -euo pipefail

FORGE_DIR="${FORGE_DIR:-$HOME/sd-forge}"
FORGE_REPO="https://github.com/lllyasviel/stable-diffusion-webui-forge.git"

echo "╔══════════════════════════════════════════════════╗"
echo "║     SD WebUI Forge 설치 스크립트 (WSL2)          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# 1. 사전 조건 확인
echo "[1/4] 사전 조건 확인..."

if ! command -v nvidia-smi &>/dev/null; then
    echo "  ✗ nvidia-smi를 찾을 수 없습니다. NVIDIA 드라이버를 설치하세요."
    exit 1
fi
echo "  ✓ NVIDIA 드라이버 감지됨"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | sed 's/^/    /'

if ! command -v python3 &>/dev/null; then
    echo "  ✗ python3를 찾을 수 없습니다."
    exit 1
fi
PYVER=$(python3 --version 2>&1)
echo "  ✓ $PYVER"

if ! command -v git &>/dev/null; then
    echo "  ✗ git을 찾을 수 없습니다."
    exit 1
fi
echo "  ✓ git 감지됨"

# python3-venv 확인
if ! python3 -c "import venv" 2>/dev/null; then
    echo "  ⚠ python3-venv 누락. 설치 시도..."
    sudo apt-get update && sudo apt-get install -y python3-venv
fi
echo "  ✓ python3-venv 사용 가능"
echo ""

# 2. Forge 클론
echo "[2/4] SD WebUI Forge 클론..."
if [ -d "$FORGE_DIR" ]; then
    echo "  ⚠ $FORGE_DIR 이미 존재합니다. 업데이트합니다..."
    cd "$FORGE_DIR"
    git pull --ff-only || echo "  ⚠ git pull 실패. 기존 버전을 사용합니다."
else
    git clone "$FORGE_REPO" "$FORGE_DIR"
    echo "  ✓ 클론 완료: $FORGE_DIR"
fi
echo ""

# 3. webui.sh 실행 권한
echo "[3/4] 실행 권한 설정..."
chmod +x "$FORGE_DIR/webui.sh"
echo "  ✓ webui.sh 실행 권한 부여됨"
echo ""

# 4. 안내
echo "[4/4] 설치 완료!"
echo ""
echo "═══════════════════════════════════════════════════"
echo " 다음 단계:"
echo ""
echo " 1. Forge 실행 (첫 실행 시 venv + 모델 자동 다운로드, 10~20분):"
echo "    cd $FORGE_DIR && bash webui.sh --listen --api"
echo ""
echo " 2. 서버 준비 확인:"
echo "    curl -s http://127.0.0.1:7860/sdapi/v1/options | head -c 100"
echo ""
echo " 3. E2E 테스트 실행:"
echo "    cd ~/dev/pixel-animation-generator"
echo "    python3 tests/test_e2e.py"
echo ""
echo " 4. (선택) 픽셀아트 체크포인트 설치:"
echo "    모델을 $FORGE_DIR/models/Stable-diffusion/ 에 배치"
echo "═══════════════════════════════════════════════════"
