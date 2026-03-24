from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CharacterSpec:
    name: str
    body_type: str = "medium"
    hair: str = ""
    outfit: str = ""
    accessories: str = ""
    color_palette: list[str] = field(default_factory=list)
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
