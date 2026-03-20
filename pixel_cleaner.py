"""이미지 후처리: 배경 제거 + 그리드 정렬 + 색상 양자화."""

from __future__ import annotations

import numpy as np
from PIL import Image

import config

# rembg 세션을 지연 초기화 (VRAM 절약)
_rembg_session = None


def _get_rembg_session():
    """rembg 세션 싱글톤 (GPU/CPU 자동 선택)."""
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session

        if config.REMBG_USE_GPU:
            _rembg_session = new_session(
                model_name="u2net",
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
        else:
            _rembg_session = new_session(
                model_name="u2net",
                providers=["CPUExecutionProvider"],
            )
    return _rembg_session


def remove_background(img: Image.Image) -> Image.Image:
    """rembg로 배경 제거.

    Args:
        img: 입력 이미지 (RGBA or RGB)

    Returns:
        배경이 제거된 RGBA 이미지
    """
    from rembg import remove

    session = _get_rembg_session()
    result = remove(img, session=session)
    return result.convert("RGBA")


def align_to_grid(
    img: Image.Image, grid_size: int | None = None
) -> Image.Image:
    """픽셀 그리드에 정렬 (Nearest Neighbor 다운/업스케일).

    작은 크기로 줄여서 픽셀 그리드에 스냅한 후 다시 원래 크기로 키움.

    Args:
        img: 입력 RGBA 이미지
        grid_size: 다운스케일 크기 (None이면 config 기본값)

    Returns:
        그리드 정렬된 RGBA 이미지
    """
    if grid_size is None:
        grid_size = config.PIXEL_GRID_SIZE

    original_size = img.size
    small = img.resize((grid_size, grid_size), Image.NEAREST)
    aligned = small.resize(original_size, Image.NEAREST)
    return aligned


def index_colors(
    img: Image.Image, num_colors: int | None = None
) -> Image.Image:
    """색상 양자화 (알파 채널 보존).

    알파를 분리 → RGB 양자화 → 알파 재합성.

    Args:
        img: 입력 RGBA 이미지
        num_colors: 팔레트 색상 수 (None이면 config 기본값)

    Returns:
        양자화된 RGBA 이미지
    """
    if num_colors is None:
        num_colors = config.QUANTIZE_COLORS

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # 알파 채널 분리
    r, g, b, a = img.split()
    rgb = Image.merge("RGB", (r, g, b))

    # 양자화
    quantized = rgb.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
    quantized_rgb = quantized.convert("RGB")

    # 알파 재합성
    result = quantized_rgb.convert("RGBA")
    result.putalpha(a)
    return result


def clean(
    img: Image.Image,
    remove_bg: bool = True,
    grid_size: int | None = None,
    num_colors: int | None = None,
) -> Image.Image:
    """3단계 후처리 파이프라인.

    1. 배경 제거 (선택)
    2. 그리드 정렬
    3. 색상 양자화

    Args:
        img: 입력 이미지
        remove_bg: 배경 제거 수행 여부
        grid_size: 픽셀 그리드 크기
        num_colors: 팔레트 색상 수

    Returns:
        후처리된 RGBA 이미지
    """
    if remove_bg:
        img = remove_background(img)

    img = align_to_grid(img, grid_size)
    img = index_colors(img, num_colors)

    return img


def clean_batch(
    images: list[Image.Image],
    remove_bg: bool = True,
    grid_size: int | None = None,
    num_colors: int | None = None,
    progress_callback=None,
) -> list[Image.Image]:
    """이미지 배치 후처리.

    Args:
        images: 입력 이미지 리스트
        remove_bg: 배경 제거 수행 여부
        grid_size: 픽셀 그리드 크기
        num_colors: 팔레트 색상 수
        progress_callback: 진행 콜백 fn(current, total)

    Returns:
        후처리된 이미지 리스트
    """
    results = []
    for i, img in enumerate(images):
        cleaned = clean(img, remove_bg, grid_size, num_colors)
        results.append(cleaned)
        if progress_callback:
            progress_callback(i + 1, len(images))
    return results
