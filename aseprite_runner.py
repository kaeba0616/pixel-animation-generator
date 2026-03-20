"""Aseprite CLI 래퍼 + Pillow/imageio 폴백."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import imageio.v3 as iio
import numpy as np
from PIL import Image

import config


def _aseprite_available() -> bool:
    """Aseprite CLI 사용 가능 여부 확인."""
    return shutil.which(config.ASEPRITE_PATH) is not None


def _save_temp_frames(
    images: list[Image.Image], output_dir: Path
) -> list[Path]:
    """이미지 리스트를 임시 PNG 파일로 저장."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, img in enumerate(images):
        path = output_dir / f"frame_{i:04d}.png"
        img.save(path, "PNG")
        paths.append(path)
    return paths


def assemble_gif_aseprite(
    frame_paths: list[Path],
    output_path: Path,
    scale: int = 1,
) -> Path:
    """Aseprite CLI로 GIF 생성.

    Args:
        frame_paths: 프레임 PNG 경로 리스트
        output_path: 출력 GIF 경로
        scale: 업스케일 배수

    Returns:
        출력 GIF 경로
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [config.ASEPRITE_PATH, "-b"]
    cmd.extend(str(p) for p in frame_paths)

    if scale > 1:
        cmd.extend(["--scale", str(scale)])

    cmd.extend(["--save-as", str(output_path)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Aseprite 실행 실패: {result.stderr}")

    return output_path


def assemble_spritesheet_aseprite(
    frame_paths: list[Path],
    output_path: Path,
) -> Path:
    """Aseprite CLI로 스프라이트시트 생성."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_path.with_suffix(".json")

    cmd = [config.ASEPRITE_PATH, "-b"]
    cmd.extend(str(p) for p in frame_paths)
    cmd.extend(["--sheet", str(output_path), "--data", str(json_path)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Aseprite 실행 실패: {result.stderr}")

    return output_path


def assemble_gif_pillow(
    images: list[Image.Image],
    output_path: Path,
    frame_duration_ms: int = 150,
    scale: int = 1,
) -> Path:
    """Pillow + imageio 폴백으로 GIF 생성.

    Args:
        images: 프레임 이미지 리스트
        output_path: 출력 GIF 경로
        frame_duration_ms: 프레임 간 딜레이 (밀리초)
        scale: Nearest Neighbor 업스케일 배수

    Returns:
        출력 GIF 경로
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frames = []
    for img in images:
        if scale > 1:
            new_size = (img.width * scale, img.height * scale)
            img = img.resize(new_size, Image.NEAREST)
        # GIF는 RGBA 직접 지원 안 함 → 투명 배경 위에 합성
        if img.mode == "RGBA":
            background = Image.new("RGBA", img.size, (0, 0, 0, 0))
            composite = Image.alpha_composite(background, img)
            frames.append(np.array(composite))
        else:
            frames.append(np.array(img))

    iio.imwrite(
        str(output_path),
        frames,
        loop=0,
        duration=frame_duration_ms,
    )

    return output_path


def upscale_for_instagram(
    img: Image.Image,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    bg_color: tuple = (30, 30, 30, 255),
) -> Image.Image:
    """인스타 Reels 해상도(1080x1920)에 맞게 업스케일 + 중앙 배치.

    Args:
        img: 입력 이미지
        canvas_width: 캔버스 너비
        canvas_height: 캔버스 높이
        bg_color: 배경 색상 (RGBA)

    Returns:
        인스타 최적화된 이미지
    """
    # 최대 정수배 Nearest Neighbor 업스케일
    max_scale_w = canvas_width // img.width
    max_scale_h = canvas_height // img.height
    scale = min(max_scale_w, max_scale_h)
    scale = max(scale, 1)

    upscaled = img.resize(
        (img.width * scale, img.height * scale), Image.NEAREST
    )

    canvas = Image.new("RGBA", (canvas_width, canvas_height), bg_color)
    x = (canvas_width - upscaled.width) // 2
    y = (canvas_height - upscaled.height) // 2
    canvas.paste(upscaled, (x, y), upscaled if upscaled.mode == "RGBA" else None)

    return canvas


def assemble(
    images: list[Image.Image],
    output_dir: Path,
    name: str = "animation",
    scale: int = 8,
    frame_duration_ms: int = 150,
) -> Path:
    """프레임을 GIF로 조립 (Aseprite 우선, 폴백 Pillow).

    Args:
        images: 후처리된 프레임 이미지 리스트
        output_dir: 출력 디렉토리
        name: 파일명 (확장자 제외)
        scale: 업스케일 배수
        frame_duration_ms: 프레임 딜레이

    Returns:
        출력 GIF 경로
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{name}.gif"

    if _aseprite_available():
        frame_paths = _save_temp_frames(images, output_dir / "frames")
        return assemble_gif_aseprite(frame_paths, output_path, scale)
    else:
        return assemble_gif_pillow(images, output_path, frame_duration_ms, scale)
