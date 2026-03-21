"""SD WebUI Forge 연결 빠른 확인 스크립트.

사용법:
    python3 tests/test_sd_connection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import config


def main():
    url = config.SD_API_URL
    print(f"SD WebUI 연결 확인: {url}")

    # 1. 기본 연결
    try:
        resp = requests.get(f"{url}/sdapi/v1/options", timeout=5)
        resp.raise_for_status()
    except requests.ConnectionError:
        print(f"✗ 연결 실패: {url}")
        print("  → SD WebUI Forge를 --api 플래그로 실행하세요:")
        print(f"    cd ~/sd-forge && bash webui.sh --listen --api")
        sys.exit(1)
    except Exception as e:
        print(f"✗ 오류: {e}")
        sys.exit(1)

    options = resp.json()
    print(f"✓ 연결 성공")
    print(f"  모델: {options.get('sd_model_checkpoint', 'N/A')}")

    # 2. 샘플러 목록
    resp = requests.get(f"{url}/sdapi/v1/samplers", timeout=5)
    samplers = [s["name"] for s in resp.json()]
    print(f"  샘플러: {len(samplers)}개")

    # 3. SD 모델 목록
    resp = requests.get(f"{url}/sdapi/v1/sd-models", timeout=5)
    models = resp.json()
    print(f"  모델 파일: {len(models)}개")
    for m in models:
        print(f"    - {m.get('model_name', m.get('title', 'unknown'))}")

    print("\n✓ SD WebUI Forge 준비 완료!")


if __name__ == "__main__":
    main()
