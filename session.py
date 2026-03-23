"""세션 상태 머신: CHATTING → GENERATING → PREVIEWING → REFINING → ANIMATING.

CLI 의존성 없는 함수 기반 인터페이스.
app.py (Flask-SocketIO)에서 호출하여 사용한다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Generator

from PIL import Image

import config
import grok_client
import pipeline
import story_engine


class SessionState(Enum):
    CHATTING = auto()
    GENERATING = auto()
    PREVIEWING = auto()
    REFINING = auto()
    ANIMATING = auto()
    DONE = auto()


# 생성 트리거 키워드
TRIGGER_KEYWORDS = [
    "생성해줘", "만들어줘", "시작해줘", "생성해", "만들어", "시작해",
    "generate", "create", "make it", "go",
]


def is_trigger(text: str) -> bool:
    """텍스트가 생성 트리거 키워드를 포함하는지 확인."""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in TRIGGER_KEYWORDS)


@dataclass
class SessionContext:
    """세션 전체 상태를 담는 컨텍스트."""

    state: SessionState = SessionState.CHATTING
    messages: list[dict] = field(default_factory=list)
    character_name: str = ""
    actions: list[str] = field(default_factory=lambda: ["idle"])
    current_prompt: str = ""
    candidates: list[Image.Image] = field(default_factory=list)
    candidate_paths: list[Path] = field(default_factory=list)
    selected_image: Image.Image | None = None
    selected_index: int | None = None
    output_dir: Path | None = None
    remove_bg: bool = True
    instagram: bool = False
    cancel_requested: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        """상태 초기화 (output_dir, remove_bg, instagram은 유지)."""
        self.state = SessionState.CHATTING
        self.messages = []
        self.character_name = ""
        self.actions = ["idle"]
        self.current_prompt = ""
        self.candidates = []
        self.candidate_paths = []
        self.selected_image = None
        self.selected_index = None
        self.cancel_requested = False


def _save_candidates(images: list[Image.Image], output_dir: Path) -> list[Path]:
    """후보 이미지를 디스크에 저장."""
    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, img in enumerate(images):
        path = candidates_dir / f"candidate_{i:02d}.png"
        img.save(path, "PNG")
        paths.append(path)
    return paths


def process_chat_message(ctx: SessionContext, message: str) -> dict:
    """CHATTING 상태에서 사용자 메시지를 처리.

    Returns:
        {"type": "response", "text": str} — 일반 Gemini 응답
        {"type": "trigger", "character": dict, "actions": list} — 생성 트리거
        {"type": "need_more"} — 대화가 부족함
        {"type": "error", "message": str} — 에러
        {"type": "done"} — 종료 요청
    """
    message = message.strip()
    if not message:
        return {"type": "response", "text": ""}

    if message.lower() in ("quit", "exit", "종료"):
        ctx.state = SessionState.DONE
        return {"type": "done"}

    if is_trigger(message):
        if len(ctx.messages) < 2:
            return {"type": "need_more"}

        try:
            name, prompt = story_engine.generate_image_prompt(ctx.messages)
        except Exception as e:
            return {"type": "error", "message": f"프롬프트 생성 실패: {e}"}

        ctx.character_name = name
        ctx.current_prompt = prompt

        # 출력 디렉토리 설정
        char_dir = (ctx.output_dir or config.OUTPUT_DIR) / pipeline._sanitize_name(name)
        char_dir.mkdir(parents=True, exist_ok=True)
        ctx.output_dir = char_dir

        ctx.state = SessionState.GENERATING
        return {
            "type": "trigger",
            "name": name,
            "prompt": prompt,
        }

    # 일반 대화
    try:
        response, ctx.messages = story_engine.chat_turn(ctx.messages, message)
        return {"type": "response", "text": response}
    except Exception as e:
        return {"type": "error", "message": f"AI 응답 실패: {e}"}


def process_generate(ctx: SessionContext) -> Generator[dict, None, None]:
    """GENERATING 상태: Grok으로 후보 이미지 생성.

    Yields:
        {"type": "progress", "current": int, "total": int}
        {"type": "image_ready", "index": int, "filename": str}
        {"type": "done"}
        {"type": "error", "message": str}
        {"type": "cancelled"}
    """
    count = config.GROK_CANDIDATES_COUNT

    try:
        images: list[Image.Image] = []
        for i in range(count):
            if ctx.cancel_requested:
                ctx.state = SessionState.CHATTING
                yield {"type": "cancelled"}
                return

            img = grok_client.generate_image(ctx.current_prompt)
            images.append(img)

            yield {"type": "progress", "current": i + 1, "total": count}

            # 개별 이미지 저장
            candidates_dir = (ctx.output_dir or config.OUTPUT_DIR) / "candidates"
            candidates_dir.mkdir(parents=True, exist_ok=True)
            filename = f"candidate_{i:02d}.png"
            path = candidates_dir / filename
            img.save(path, "PNG")

            yield {"type": "image_ready", "index": i, "filename": filename}

        ctx.candidates = images
        ctx.candidate_paths = [
            (ctx.output_dir or config.OUTPUT_DIR) / "candidates" / f"candidate_{i:02d}.png"
            for i in range(len(images))
        ]
        ctx.state = SessionState.PREVIEWING
        yield {"type": "done"}

    except Exception as e:
        ctx.state = SessionState.CHATTING
        yield {"type": "error", "message": str(e)}


def process_refine(ctx: SessionContext, index: int, feedback: str) -> dict:
    """REFINING 상태: Gemini 멀티모달로 프롬프트 개선.

    Args:
        ctx: 세션 컨텍스트
        index: 선택된 후보 이미지 인덱스
        feedback: 사용자 피드백 텍스트

    Returns:
        {"type": "refined", "summary": str, "prompt": str}
        {"type": "error", "message": str}
    """
    try:
        if 0 <= index < len(ctx.candidates):
            ctx.selected_index = index
            ctx.selected_image = ctx.candidates[index]
        elif ctx.selected_image is None:
            return {"type": "error", "message": "선택된 이미지가 없습니다."}

        refined, summary, ctx.messages = story_engine.refine_prompt(
            ctx.messages,
            ctx.selected_image,
            feedback,
            ctx.current_prompt,
        )
        ctx.current_prompt = refined
        ctx.state = SessionState.GENERATING
        return {"type": "refined", "summary": summary, "prompt": refined}
    except Exception as e:
        return {"type": "error", "message": f"프롬프트 개선 실패: {e}"}


def process_animate(ctx: SessionContext, index: int) -> Generator[dict, None, None]:
    """ANIMATING 상태: 최종 애니메이션 프레임 생성 + GIF 조립.

    Args:
        ctx: 세션 컨텍스트
        index: 확정된 후보 이미지 인덱스

    Yields:
        {"type": "done", "gif_filename": str, "gif_path": str}
        {"type": "error", "message": str}
    """
    try:
        if 0 <= index < len(ctx.candidates):
            ctx.selected_index = index
            ctx.selected_image = ctx.candidates[index]

        ctx.state = SessionState.ANIMATING

        results = pipeline.run(
            ctx.character,
            ctx.actions,
            remove_bg=ctx.remove_bg,
            instagram=ctx.instagram,
            output_dir=ctx.output_dir.parent if ctx.output_dir else None,
        )

        if results:
            for path in results:
                yield {
                    "type": "done",
                    "gif_filename": path.name,
                    "gif_path": str(path),
                }
        else:
            yield {"type": "error", "message": "생성된 파일이 없습니다."}

    except Exception as e:
        yield {"type": "error", "message": f"애니메이션 생성 실패: {e}"}
    finally:
        ctx.state = SessionState.DONE
