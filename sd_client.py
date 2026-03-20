"""Stable Diffusion WebUI API 래퍼: txt2img / img2img 호출."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import requests
from PIL import Image

import config
from models import FrameSpec


def _encode_image(img: Image.Image) -> str:
    """PIL Image → base64 문자열."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _decode_image(b64: str) -> Image.Image:
    """base64 문자열 → PIL Image."""
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def _check_connection() -> None:
    """SD WebUI 연결 확인."""
    try:
        resp = requests.get(f"{config.SD_API_URL}/sdapi/v1/options", timeout=5)
        resp.raise_for_status()
    except requests.ConnectionError:
        raise ConnectionError(
            f"SD WebUI에 연결할 수 없습니다: {config.SD_API_URL}\n"
            "SD WebUI를 --api 플래그로 실행하세요."
        )


def txt2img(frame: FrameSpec) -> Image.Image:
    """txt2img API 호출로 이미지 생성.

    Args:
        frame: 프레임 스펙 (프롬프트, 시드 등)

    Returns:
        생성된 PIL Image (RGBA)
    """
    _check_connection()

    payload = {
        "prompt": frame.prompt,
        "negative_prompt": frame.negative_prompt,
        "seed": frame.seed,
        "width": frame.width,
        "height": frame.height,
        "steps": config.SD_STEPS,
        "cfg_scale": config.SD_CFG_SCALE,
        "sampler_name": config.SD_SAMPLER,
        "batch_size": 1,
        "n_iter": 1,
    }

    resp = requests.post(
        f"{config.SD_API_URL}/sdapi/v1/txt2img",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()

    data = resp.json()
    img = _decode_image(data["images"][0])
    return img.convert("RGBA")


def img2img(
    ref_image: Image.Image,
    frame: FrameSpec,
    denoising_strength: float | None = None,
) -> Image.Image:
    """img2img API 호출로 레퍼런스 기반 프레임 생성.

    Args:
        ref_image: 히어로 프레임 (레퍼런스)
        frame: 프레임 스펙
        denoising_strength: 디노이징 강도 (None이면 config 기본값)

    Returns:
        생성된 PIL Image (RGBA)
    """
    _check_connection()

    if denoising_strength is None:
        denoising_strength = config.SD_IMG2IMG_DENOISING

    payload = {
        "init_images": [_encode_image(ref_image)],
        "prompt": frame.prompt,
        "negative_prompt": frame.negative_prompt,
        "seed": frame.seed,
        "width": frame.width,
        "height": frame.height,
        "steps": config.SD_STEPS,
        "cfg_scale": config.SD_CFG_SCALE,
        "sampler_name": config.SD_SAMPLER,
        "denoising_strength": denoising_strength,
        "batch_size": 1,
        "n_iter": 1,
    }

    resp = requests.post(
        f"{config.SD_API_URL}/sdapi/v1/img2img",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()

    data = resp.json()
    img = _decode_image(data["images"][0])
    return img.convert("RGBA")


def generate_frames(
    frame_specs: list[FrameSpec],
    progress_callback=None,
) -> list[Image.Image]:
    """2-Pass 전략으로 프레임 리스트 생성.

    Pass 1: 첫 프레임을 txt2img로 생성 (히어로 프레임)
    Pass 2: 나머지를 img2img로 생성 (일관성 유지)

    Args:
        frame_specs: 프레임 스펙 리스트
        progress_callback: 진행 콜백 fn(current, total)

    Returns:
        생성된 이미지 리스트
    """
    if not frame_specs:
        return []

    images: list[Image.Image] = []

    # Pass 1: 히어로 프레임
    hero = txt2img(frame_specs[0])
    images.append(hero)
    if progress_callback:
        progress_callback(1, len(frame_specs))

    # Pass 2: 나머지 프레임 (img2img)
    for i, spec in enumerate(frame_specs[1:], start=2):
        img = img2img(hero, spec)
        images.append(img)
        if progress_callback:
            progress_callback(i, len(frame_specs))

    return images
