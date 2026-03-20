from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CharacterSpec:
    name: str
    body_type: str  # "small", "medium", "tall"
    hair: str  # "short blue spiky hair"
    outfit: str  # "red plate armor with gold trim"
    accessories: str  # "iron shield, leather boots"
    color_palette: list[str] = field(default_factory=list)  # ["#C41E3A", "#FFD700"]
    style_tags: list[str] = field(default_factory=lambda: ["pixel art", "16-bit"])
    personality: str = ""
    backstory: str = ""


@dataclass
class AnimationRequest:
    character: CharacterSpec
    action: str  # "idle", "walk", "attack_sword", "cast_spell"
    direction: str = "front"  # "front", "side", "back"
    frame_count: int = 4
    emotion: str = "neutral"  # "neutral", "angry", "happy"


@dataclass
class FrameSpec:
    prompt: str
    negative_prompt: str
    seed: int
    width: int = 128
    height: int = 128
    controlnet_args: dict | None = None
    img2img_ref: str | None = None  # 레퍼런스 이미지 경로
