"""pixel_cleaner 테스트 (rembg 없이 grid/quantize만 테스트)."""

import numpy as np
import pytest
from PIL import Image

from pixel_cleaner import align_to_grid, index_colors, clean


def _make_test_image(width=128, height=128) -> Image.Image:
    """테스트용 RGBA 이미지 생성."""
    arr = np.random.randint(0, 255, (height, width, 4), dtype=np.uint8)
    # 알파: 중앙에 캐릭터, 가장자리 투명
    arr[:, :, 3] = 0
    arr[32:96, 32:96, 3] = 255
    return Image.fromarray(arr, "RGBA")


def test_align_to_grid():
    img = _make_test_image(128, 128)
    result = align_to_grid(img, grid_size=32)

    assert result.size == (128, 128)
    assert result.mode == "RGBA"

    # 그리드 정렬 후 동일 픽셀 블록이 형성되는지 확인
    arr = np.array(result)
    block_size = 128 // 32  # = 4
    # 각 4x4 블록 내 모든 픽셀이 동일해야 함
    for y in range(0, 128, block_size):
        for x in range(0, 128, block_size):
            block = arr[y : y + block_size, x : x + block_size]
            assert np.all(block == block[0, 0]), (
                f"Block at ({x},{y}) is not uniform"
            )


def test_index_colors():
    img = _make_test_image(64, 64)
    result = index_colors(img, num_colors=8)

    assert result.size == (64, 64)
    assert result.mode == "RGBA"

    # 고유 RGB 색상 수가 8 이하인지 확인
    arr = np.array(result)
    rgb = arr[:, :, :3]
    unique_colors = np.unique(rgb.reshape(-1, 3), axis=0)
    assert len(unique_colors) <= 8


def test_index_colors_preserves_alpha():
    img = _make_test_image(64, 64)
    original_alpha = np.array(img)[:, :, 3].copy()

    result = index_colors(img, num_colors=16)
    result_alpha = np.array(result)[:, :, 3]

    np.testing.assert_array_equal(original_alpha, result_alpha)


def test_clean_without_rembg():
    img = _make_test_image(128, 128)
    result = clean(img, remove_bg=False, grid_size=32, num_colors=16)

    assert result.size == (128, 128)
    assert result.mode == "RGBA"


def test_align_preserves_size():
    for size in [(64, 64), (128, 128), (256, 256)]:
        img = _make_test_image(*size)
        result = align_to_grid(img, grid_size=16)
        assert result.size == size
