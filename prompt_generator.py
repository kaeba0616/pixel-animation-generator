"""프롬프트 생성기: CharacterSpec + 액션 → FrameSpec 리스트 (LLM 호출 없음)."""

from __future__ import annotations

import random
from pathlib import Path

import yaml

import config
from models import AnimationRequest, CharacterSpec, FrameSpec

TEMPLATES_DIR = Path(__file__).parent / "templates"

NEGATIVE_PROMPT = (
    "blurry, anti-aliased, realistic, 3d render, gradient, noise, "
    "watermark, deformed, extra limbs, disfigured, bad anatomy, "
    "low quality, jpeg artifacts, text, signature"
)


def _load_actions() -> dict:
    """templates/prompts.yaml에서 액션-포즈 매핑을 로드."""
    yaml_path = TEMPLATES_DIR / "prompts.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["actions"]


def _build_positive_prompt(
    char: CharacterSpec, pose: str, emotion: str, direction: str
) -> str:
    """캐릭터 스펙 + 포즈 정보로 positive 프롬프트 조합."""
    style = ", ".join(char.style_tags) if char.style_tags else "pixel art"
    palette_hint = ""
    if char.color_palette:
        colors = ", ".join(char.color_palette[:4])
        palette_hint = f", color palette ({colors})"

    parts = [
        "pixel art",
        style,
        f"{char.body_type} character",
        char.hair,
        f"wearing {char.outfit}",
    ]
    if char.accessories:
        parts.append(char.accessories)
    parts.extend(
        [
            pose,
            f"{emotion} expression",
            f"{direction} view",
            "transparent background",
            "clean pixel edges",
            "limited color palette",
        ]
    )
    if palette_hint:
        parts.append(palette_hint)

    return ", ".join(parts)


def build_frame_specs(
    request: AnimationRequest, base_seed: int | None = None
) -> list[FrameSpec]:
    """AnimationRequest에서 프레임별 FrameSpec 리스트를 생성.

    Args:
        request: 애니메이션 요청
        base_seed: 시드 기본값 (None이면 랜덤)

    Returns:
        프레임별 FrameSpec 리스트
    """
    actions = _load_actions()
    action_data = actions.get(request.action)

    if action_data is None:
        raise ValueError(
            f"알 수 없는 액션: {request.action}. "
            f"사용 가능: {list(actions.keys())}"
        )

    poses = action_data["poses"]
    frame_count = action_data.get("frame_count", len(poses))

    if base_seed is None:
        base_seed = random.randint(1, 2**31)

    frames: list[FrameSpec] = []
    for i in range(frame_count):
        pose = poses[i % len(poses)]
        prompt = _build_positive_prompt(
            request.character, pose, request.emotion, request.direction
        )
        frames.append(
            FrameSpec(
                prompt=prompt,
                negative_prompt=NEGATIVE_PROMPT,
                seed=base_seed + i,
                width=config.SD_DEFAULT_WIDTH,
                height=config.SD_DEFAULT_HEIGHT,
            )
        )

    return frames


def build_animation_requests(
    character: CharacterSpec,
    actions: list[str],
    direction: str = "front",
    emotion: str = "neutral",
) -> list[AnimationRequest]:
    """캐릭터 + 액션 목록 → AnimationRequest 리스트."""
    all_actions = _load_actions()
    requests = []
    for action in actions:
        if action not in all_actions:
            continue
        frame_count = all_actions[action].get(
            "frame_count", len(all_actions[action]["poses"])
        )
        requests.append(
            AnimationRequest(
                character=character,
                action=action,
                direction=direction,
                frame_count=frame_count,
                emotion=emotion,
            )
        )
    return requests
