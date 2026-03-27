from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CharacterSpec:
        return cls(**data)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, path: str | Path) -> CharacterSpec:
        return cls.from_dict(json.loads(Path(path).read_text()))


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
