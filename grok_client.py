"""Grok (xAI) 이미지 생성 API 래퍼."""

from __future__ import annotations

import base64
import io
import time

import requests
from PIL import Image

import config
from models import FrameSpec

XAI_API_URL = "https://api.x.ai/v1"


def _retry(fn, max_retries: int = 2, delay: float = 5):
    """재시도 래퍼: 타임아웃 및 429/503 에러 처리."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except requests.Timeout:
            if attempt == max_retries:
                raise
            print(f"  ⚠ 타임아웃, {delay}초 후 재시도 ({attempt+1}/{max_retries})...")
            time.sleep(delay)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (429, 503):
                retry_after = float(e.response.headers.get("Retry-After", delay))
                if attempt == max_retries:
                    raise
                print(f"  ⚠ {e.response.status_code}, {retry_after}초 후 재시도 ({attempt+1}/{max_retries})...")
                time.sleep(retry_after)
            else:
                raise


def _check_connection() -> None:
    """xAI API 연결 확인."""
    if not config.XAI_API_KEY:
        raise ConnectionError("XAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    try:
        resp = requests.get(
            f"{XAI_API_URL}/models",
            headers={"Authorization": f"Bearer {config.XAI_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        raise ConnectionError("xAI API에 연결할 수 없습니다.")


def generate_image(prompt: str, model: str = "grok-imagine-image") -> Image.Image:
    """Grok 이미지 생성 API 호출.

    Args:
        prompt: 이미지 생성 프롬프트
        model: 모델명

    Returns:
        생성된 PIL Image (RGBA)
    """

    def _call():
        resp = requests.post(
            f"{XAI_API_URL}/images/generations",
            headers={
                "Authorization": f"Bearer {config.XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "prompt": prompt,
                "n": 1,
                "response_format": "b64_json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    data = _retry(_call)
    b64 = data["data"][0]["b64_json"]
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    return img.convert("RGBA")


def _build_grok_prompt(frame: FrameSpec) -> str:
    """FrameSpec의 SD 프롬프트를 Grok용으로 변환.

    초록 배경을 추가하여 rembg로 쉽게 배경 제거 가능하게 한다.
    """
    # SD negative 프롬프트의 핵심 요소를 positive에 반영
    prompt = frame.prompt
    # 투명 배경 → 초록 배경 (크로마키)으로 교체
    prompt = prompt.replace("transparent background", "solid bright green background (#00FF00)")
    # Grok에 맞는 추가 지시
    prompt += ", single character sprite, centered, no text, no watermark"
    return prompt


def generate_candidates(
    prompt: str,
    count: int = 4,
    progress_callback=None,
) -> list[Image.Image]:
    """후보 이미지 N장 생성 (단일 프롬프트, 독립 생성).

    Args:
        prompt: 이미지 생성 프롬프트
        count: 생성할 후보 수
        progress_callback: 진행 콜백 fn(current, total)

    Returns:
        생성된 이미지 리스트
    """
    _check_connection()

    images: list[Image.Image] = []
    for i in range(count):
        img = generate_image(prompt)
        images.append(img)
        if progress_callback:
            progress_callback(i + 1, count)

    return images


def generate_frames(
    frame_specs: list[FrameSpec],
    progress_callback=None,
) -> list[Image.Image]:
    """프레임 리스트를 Grok API로 생성.

    SD의 2-Pass와 달리 각 프레임을 독립적으로 생성한다.
    프롬프트에 포즈 정보가 포함되어 있어 프레임별 변화가 발생한다.

    Args:
        frame_specs: 프레임 스펙 리스트
        progress_callback: 진행 콜백 fn(current, total)

    Returns:
        생성된 이미지 리스트
    """
    if not frame_specs:
        return []

    _check_connection()

    images: list[Image.Image] = []

    for i, spec in enumerate(frame_specs):
        prompt = _build_grok_prompt(spec)
        img = generate_image(prompt)
        images.append(img)
        if progress_callback:
            progress_callback(i + 1, len(frame_specs))

    return images
