"""전체 파이프라인 오케스트레이터: 대화 → 캐릭터 추출 → 프레임 생성 → 후처리 → GIF 조립."""

from __future__ import annotations

from pathlib import Path

from tqdm import tqdm

import config
import sd_client
import pixel_cleaner
import aseprite_runner
from models import CharacterSpec
from prompt_generator import build_animation_requests, build_frame_specs


def _sanitize_name(name: str) -> str:
    """파일명에 안전한 문자열로 변환."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return safe.lower().strip("_") or "character"


def run_single_action(
    character: CharacterSpec,
    action: str,
    output_dir: Path,
    remove_bg: bool = True,
) -> Path:
    """단일 액션에 대한 애니메이션 생성.

    Args:
        character: 캐릭터 스펙
        action: 액션 이름 (idle, walk, attack_sword 등)
        output_dir: 출력 디렉토리
        remove_bg: 배경 제거 수행 여부

    Returns:
        생성된 GIF 경로
    """
    requests = build_animation_requests(character, [action])
    if not requests:
        raise ValueError(f"지원하지 않는 액션: {action}")

    request = requests[0]
    frame_specs = build_frame_specs(request)

    # SD 이미지 생성
    print(f"  ⟳ {action} 프레임 생성 중 ({len(frame_specs)}프레임)...")
    images = sd_client.generate_frames(
        frame_specs,
        progress_callback=lambda cur, tot: print(
            f"    [{cur}/{tot}]", end="\r"
        ),
    )
    print()

    # 후처리
    print(f"  ⟳ 후처리 중...")
    cleaned = pixel_cleaner.clean_batch(images, remove_bg=remove_bg)

    # GIF 조립
    print(f"  ⟳ GIF 조립 중...")
    gif_path = aseprite_runner.assemble(
        cleaned, output_dir, name=action, scale=8
    )
    print(f"  ✓ {gif_path}")

    return gif_path


def run(
    character: CharacterSpec,
    actions: list[str],
    remove_bg: bool = True,
) -> list[Path]:
    """전체 파이프라인 실행.

    Args:
        character: 캐릭터 스펙
        actions: 액션 목록
        remove_bg: 배경 제거 수행 여부

    Returns:
        생성된 GIF 경로 리스트
    """
    char_dir = config.OUTPUT_DIR / _sanitize_name(character.name)
    char_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"캐릭터: {character.name}")
    print(f"액션: {', '.join(actions)}")
    print(f"출력: {char_dir}")
    print(f"{'='*50}\n")

    results = []
    for action in actions:
        try:
            gif_path = run_single_action(
                character, action, char_dir, remove_bg
            )
            results.append(gif_path)
        except Exception as e:
            print(f"  ✗ {action} 실패: {e}")

    return results
