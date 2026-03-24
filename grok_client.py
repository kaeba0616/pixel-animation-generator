"""Grok (xAI) 이미지/비디오 생성 API 래퍼."""

from __future__ import annotations

import base64
import io
import time

import requests
from PIL import Image

import config

XAI_API_URL = "https://api.x.ai/v1"


def _retry(fn, max_retries: int = 2, delay: float = 5):
    """재시도 래퍼: 타임아웃 및 429/503 에러 처리."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except requests.Timeout:
            if attempt == max_retries:
                raise
            time.sleep(delay)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (429, 503):
                retry_after = float(e.response.headers.get("Retry-After", delay))
                if attempt == max_retries:
                    raise
                time.sleep(retry_after)
            else:
                raise


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.XAI_API_KEY}",
        "Content-Type": "application/json",
    }


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


# ── 이미지 생성 ──────────────────────────────────────────

def generate_image(
    prompt: str,
    n: int = 1,
    resolution: str = "2k",
    aspect_ratio: str = "1:1",
    model: str = "grok-imagine-image",
) -> list[Image.Image]:
    """Grok 이미지 생성 API 호출.

    Args:
        prompt: 이미지 생성 프롬프트
        n: 생성할 이미지 수 (1~10)
        resolution: "1k" 또는 "2k"
        aspect_ratio: "1:1", "16:9", "9:16", "4:3" 등
        model: 모델명

    Returns:
        생성된 PIL Image 리스트 (RGBA)
    """

    def _call():
        resp = requests.post(
            f"{XAI_API_URL}/images/generations",
            headers=_headers(),
            json={
                "model": model,
                "prompt": prompt,
                "n": n,
                "response_format": "b64_json",
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    data = _retry(_call)
    images = []
    for item in data["data"]:
        b64 = item["b64_json"]
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        images.append(img.convert("RGBA"))
    return images


def generate_candidates(
    prompt: str,
    count: int = 4,
    resolution: str = "2k",
    aspect_ratio: str = "1:1",
    progress_callback=None,
) -> list[Image.Image]:
    """후보 이미지 N장 생성. API 배치 지원 활용.

    Args:
        prompt: 이미지 생성 프롬프트
        count: 생성할 후보 수 (1~10)
        resolution: "1k" 또는 "2k"
        aspect_ratio: aspect ratio
        progress_callback: 진행 콜백 fn(current, total)

    Returns:
        생성된 이미지 리스트
    """
    _check_connection()

    # API가 최대 10장 배치 지원
    if count <= 10:
        images = generate_image(prompt, n=count, resolution=resolution, aspect_ratio=aspect_ratio)
        if progress_callback:
            progress_callback(count, count)
        return images

    # 10장 초과 시 분할 호출
    images = []
    remaining = count
    while remaining > 0:
        batch = min(remaining, 10)
        batch_images = generate_image(prompt, n=batch, resolution=resolution, aspect_ratio=aspect_ratio)
        images.extend(batch_images)
        remaining -= batch
        if progress_callback:
            progress_callback(len(images), count)
    return images


# ── 비디오 생성 ──────────────────────────────────────────

def generate_video(
    prompt: str,
    duration: int = 5,
    aspect_ratio: str = "1:1",
    resolution: str = "720p",
    image_url: str | None = None,
    model: str = "grok-imagine-video",
    poll_interval: float = 10.0,
    max_wait: float = 300.0,
) -> str:
    """Grok 비디오 생성 API 호출 (비동기 폴링).

    Args:
        prompt: 비디오 생성 프롬프트
        duration: 비디오 길이 (1~15초)
        aspect_ratio: "1:1", "16:9", "9:16" 등
        resolution: "480p" 또는 "720p"
        image_url: 이미지→비디오 변환 시 소스 이미지 URL (선택)
        model: 모델명
        poll_interval: 폴링 간격 (초)
        max_wait: 최대 대기 시간 (초)

    Returns:
        생성된 비디오 URL
    """
    _check_connection()

    payload = {
        "model": model,
        "prompt": prompt,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
    }
    if image_url:
        payload["image_url"] = image_url

    # 생성 요청
    def _call():
        resp = requests.post(
            f"{XAI_API_URL}/videos/generations",
            headers=_headers(),
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    data = _retry(_call)
    request_id = data.get("request_id") or data.get("id")
    if not request_id:
        raise RuntimeError(f"비디오 생성 요청 실패: request_id 없음. 응답: {data}")

    # 폴링으로 완료 대기
    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(poll_interval)
        status_resp = requests.get(
            f"{XAI_API_URL}/videos/{request_id}",
            headers=_headers(),
            timeout=30,
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()

        state = status_data.get("state", status_data.get("status", ""))
        if state in ("completed", "succeeded"):
            video_url = status_data.get("video_url") or status_data.get("url", "")
            if video_url:
                return video_url
            raise RuntimeError(f"비디오 완료됐지만 URL 없음: {status_data}")
        elif state in ("failed", "error"):
            raise RuntimeError(f"비디오 생성 실패: {status_data}")
        # else: pending/processing, 계속 폴링

    raise TimeoutError(f"비디오 생성 {max_wait}초 초과 (request_id={request_id})")


def image_to_video(
    image: Image.Image,
    prompt: str,
    duration: int = 5,
    resolution: str = "720p",
    poll_interval: float = 10.0,
    max_wait: float = 300.0,
) -> str:
    """PIL Image를 base64 data URI로 변환 후 비디오 생성.

    Args:
        image: 소스 PIL Image
        prompt: 비디오 프롬프트
        duration: 비디오 길이 (초)
        resolution: "480p" 또는 "720p"

    Returns:
        생성된 비디오 URL
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    data_uri = f"data:image/png;base64,{b64}"

    return generate_video(
        prompt=prompt,
        duration=duration,
        image_url=data_uri,
        resolution=resolution,
        poll_interval=poll_interval,
        max_wait=max_wait,
    )
