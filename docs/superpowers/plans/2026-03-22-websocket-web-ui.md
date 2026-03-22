# WebSocket 웹 완결형 UI 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI+브라우저 분리 구조를 Flask-SocketIO 기반 웹 완결형 UI로 전환하여, 브라우저 하나에서 대화→이미지 생성→선택→수정→GIF 출력 전체 워크플로우를 처리한다.

**Architecture:** Flask-SocketIO(`async_mode='threading'`)로 WebSocket 서버를 구성. API 호출(Grok/Gemini)은 `start_background_task()`로 백그라운드 스레드 실행. 생성된 이미지는 디스크 저장 후 HTTP로 서빙. 단일 SessionContext로 상태 관리.

**Tech Stack:** Flask, Flask-SocketIO, Socket.IO JS client (CDN), Jinja2 템플릿

**Spec:** `docs/superpowers/specs/2026-03-22-websocket-web-ui-design.md`

---

## 파일 구조

| 파일 | 역할 | 변경 |
|------|------|------|
| `app.py` | Flask-SocketIO 메인 서버 + WebSocket 이벤트 핸들러 | **신규** |
| `templates/index.html` | 웹 완결형 UI (채팅 + 이미지 + 상태 전환) | **신규** |
| `session.py` | 상태 머신 로직 (CLI 의존성 제거, 함수 인터페이스) | **수정** |
| `chat.py` | CLI 모드 유지 (--cli), 기본은 app.py 안내 | **수정** |
| `config.py` | SECRET_KEY 추가 | **수정** |
| `requirements.txt` | flask-socketio 추가 | **수정** |
| `preview_server.py` | app.py로 대체 | **삭제** |
| `templates/preview.html` | index.html로 대체 | **삭제** |
| `tests/test_e2e.py` | SocketIO test_client 기반 테스트 추가 | **수정** |

변경 없음: `grok_client.py`, `story_engine.py`, `pipeline.py`, `pixel_cleaner.py`, `prompt_generator.py`, `models.py`, `aseprite_runner.py`

---

### Task 1: 의존성 추가 + config 업데이트

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`

- [ ] **Step 1: requirements.txt에 flask-socketio 추가**

```
# requirements.txt 끝에 추가
flask-socketio>=5.3.0
```

- [ ] **Step 2: config.py에 SECRET_KEY 추가**

```python
# config.py — 기존 설정 아래에 추가
SECRET_KEY = os.getenv("SECRET_KEY", "pixel-a-factory-dev-key")
```

- [ ] **Step 3: flask-socketio 설치 확인**

Run: `pip install --break-system-packages flask-socketio && python3 -c "from flask_socketio import SocketIO; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt config.py
git commit -m "feat: add flask-socketio dependency and SECRET_KEY config"
```

---

### Task 2: session.py 리팩토링 — CLI 의존성 제거

**Files:**
- Modify: `session.py`
- Test: `tests/test_session.py` (신규)

- [ ] **Step 1: 테스트 파일 작성**

```python
# tests/test_session.py
"""session.py 상태 머신 단위 테스트."""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
from session import SessionState, SessionContext, process_chat_message, process_refine, is_trigger


def test_is_trigger():
    assert is_trigger("생성해줘") is True
    assert is_trigger("만들어줘") is True
    assert is_trigger("generate") is True
    assert is_trigger("안녕하세요") is False


def test_initial_state():
    ctx = SessionContext()
    assert ctx.state == SessionState.CHATTING
    assert ctx.messages == []
    assert ctx.character is None


def test_cancel_flag():
    ctx = SessionContext()
    assert ctx.cancel_requested is False
    ctx.cancel_requested = True
    ctx.reset()
    assert ctx.cancel_requested is False
    assert ctx.state == SessionState.CHATTING


if __name__ == "__main__":
    test_is_trigger()
    test_initial_state()
    test_cancel_flag()
    print("All session tests passed!")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_session.py`
Expected: ImportError (`process_chat_message` 없음)

- [ ] **Step 3: session.py 리팩토링**

`session.py`를 다음과 같이 재작성:
- `input()` 호출 전부 제거
- `PreviewState` 임포트 및 의존성 제거
- `webbrowser` 임포트 제거
- `start_server` 임포트 제거
- `run_session()` 함수 제거
- `handle_*` 함수들을 순수 함수로 변환:
  - `process_chat_message(ctx, message) -> dict` — 메시지 처리 후 결과 반환
  - `process_generate(ctx) -> Generator[dict]` — 이미지 1장씩 yield
  - `process_refine(ctx, index, feedback) -> dict` — 프롬프트 개선 결과 반환
  - `process_animate(ctx) -> Generator[dict]` — 애니메이션 진행률 yield
- `SessionContext`에 `cancel_requested: bool` 필드 추가
- `SessionContext`에 `_lock: threading.Lock` 필드 추가 (상태 전환 보호)
- `SessionContext`에 `reset()` 메서드 추가
- `is_trigger(text)` 함수 유지 (export)
- `_save_candidates(images, output_dir)` 함수 유지

```python
# session.py 핵심 구조
"""세션 상태 머신: WebSocket 이벤트 기반 인터페이스."""

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
from models import CharacterSpec
from prompt_generator import build_animation_requests, build_frame_specs


class SessionState(Enum):
    CHATTING = auto()
    GENERATING = auto()
    PREVIEWING = auto()
    REFINING = auto()
    ANIMATING = auto()
    DONE = auto()


TRIGGER_KEYWORDS = [
    "생성해줘", "만들어줘", "시작해줘", "생성해", "만들어", "시작해",
    "generate", "create", "make it", "go",
]


def is_trigger(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in TRIGGER_KEYWORDS)


@dataclass
class SessionContext:
    state: SessionState = SessionState.CHATTING
    messages: list[dict] = field(default_factory=list)
    character: CharacterSpec | None = None
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

    def reset(self):
        """세션을 초기 상태로 리셋."""
        self.state = SessionState.CHATTING
        self.messages = []
        self.character = None
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
    """채팅 메시지 처리. 결과 dict 반환.

    Returns:
        {"type": "response", "text": str} — 일반 응답
        {"type": "trigger", "character": dict, "actions": list} — 생성 트리거
        {"type": "error", "message": str} — 에러
        {"type": "need_more"} — 대화 부족
    """
    if message.lower() in ("quit", "exit", "종료"):
        ctx.state = SessionState.DONE
        return {"type": "done"}

    if is_trigger(message):
        if len(ctx.messages) < 2:
            return {"type": "need_more"}

        try:
            spec, actions = story_engine.extract_character(ctx.messages)
        except Exception as e:
            return {"type": "error", "message": f"캐릭터 추출 실패: {e}"}

        ctx.character = spec
        ctx.actions = actions or ["idle"]

        # 초기 프롬프트 생성
        reqs = build_animation_requests(spec, ["idle"])
        if reqs:
            specs = build_frame_specs(reqs[0])
            if specs:
                ctx.current_prompt = grok_client._build_grok_prompt(specs[0])

        # 출력 디렉토리
        char_dir = (ctx.output_dir or config.OUTPUT_DIR) / pipeline._sanitize_name(spec.name)
        char_dir.mkdir(parents=True, exist_ok=True)
        ctx.output_dir = char_dir
        spec.save(char_dir / "character.json")

        ctx.state = SessionState.GENERATING
        return {"type": "trigger", "character": spec.to_dict(), "actions": ctx.actions}

    # 일반 대화
    try:
        response, ctx.messages = story_engine.chat_turn(ctx.messages, message)
        return {"type": "response", "text": response}
    except Exception as e:
        return {"type": "error", "message": f"AI 응답 실패: {e}"}


def process_generate(ctx: SessionContext) -> Generator[dict, None, None]:
    """후보 이미지 생성. 1장씩 yield.

    Yields:
        {"type": "image_ready", "index": int, "path": Path}
        {"type": "progress", "current": int, "total": int}
        {"type": "done"}
        {"type": "error", "message": str}
    """
    count = config.GROK_CANDIDATES_COUNT
    try:
        grok_client._check_connection()
    except ConnectionError as e:
        ctx.state = SessionState.CHATTING
        yield {"type": "error", "message": str(e)}
        return

    ctx.candidates = []
    ctx.candidate_paths = []
    candidates_dir = (ctx.output_dir or config.OUTPUT_DIR) / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        if ctx.cancel_requested:
            ctx.cancel_requested = False
            ctx.state = SessionState.PREVIEWING if ctx.candidates else SessionState.CHATTING
            yield {"type": "cancelled"}
            return

        try:
            img = grok_client.generate_image(ctx.current_prompt)
            ctx.candidates.append(img)
            path = candidates_dir / f"candidate_{i:02d}.png"
            img.save(path, "PNG")
            ctx.candidate_paths.append(path)
            yield {"type": "image_ready", "index": i, "filename": path.name}
            yield {"type": "progress", "current": i + 1, "total": count}
        except Exception as e:
            ctx.state = SessionState.CHATTING
            yield {"type": "error", "message": f"이미지 생성 실패: {e}"}
            return

    ctx.state = SessionState.PREVIEWING
    yield {"type": "done"}


def process_refine(ctx: SessionContext, index: int, feedback: str) -> dict:
    """선택 이미지 + 피드백 → 프롬프트 개선.

    Returns:
        {"type": "refined", "summary": str, "prompt": str}
        {"type": "error", "message": str}
    """
    ctx.selected_index = index
    ctx.selected_image = ctx.candidates[index]
    ctx.state = SessionState.REFINING

    try:
        refined, summary, ctx.messages = story_engine.refine_prompt(
            ctx.messages, ctx.selected_image, feedback, ctx.current_prompt,
        )
        ctx.current_prompt = refined
        ctx.state = SessionState.GENERATING
        return {"type": "refined", "summary": summary, "prompt": refined}
    except Exception as e:
        ctx.state = SessionState.PREVIEWING
        return {"type": "error", "message": f"프롬프트 개선 실패: {e}"}


def process_animate(ctx: SessionContext, index: int) -> Generator[dict, None, None]:
    """확정 이미지 기반 애니메이션 생성.

    Yields:
        {"type": "progress", "current": int, "total": int, "label": str}
        {"type": "done", "gif_filename": str}
        {"type": "error", "message": str}
    """
    ctx.selected_index = index
    ctx.selected_image = ctx.candidates[index]
    ctx.state = SessionState.ANIMATING

    try:
        results = pipeline.run(
            ctx.character,
            ctx.actions,
            remove_bg=ctx.remove_bg,
            instagram=ctx.instagram,
            output_dir=ctx.output_dir,
        )

        if results:
            gif_path = results[0]
            ctx.state = SessionState.DONE
            yield {"type": "done", "gif_filename": gif_path.name, "gif_path": str(gif_path)}
        else:
            ctx.state = SessionState.PREVIEWING
            yield {"type": "error", "message": "생성된 파일이 없습니다."}
    except Exception as e:
        ctx.state = SessionState.PREVIEWING
        yield {"type": "error", "message": f"애니메이션 생성 실패: {e}"}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_session.py`
Expected: `All session tests passed!`

- [ ] **Step 5: Commit**

```bash
git add session.py tests/test_session.py
git commit -m "refactor: remove CLI deps from session.py, add function-based interface"
```

---

### Task 3: app.py — Flask-SocketIO 서버

**Files:**
- Create: `app.py`
- Test: 수동 (`python3 app.py` 후 브라우저 접속)

- [ ] **Step 1: app.py 작성**

```python
# app.py
"""Flask-SocketIO 메인 서버: 웹 완결형 UI."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit

import config
from session import SessionContext, SessionState, process_chat_message, process_generate, process_refine, process_animate

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# 단일 세션 (로컬 도구)
ctx = SessionContext()


# ── HTTP 라우트 ──

@app.route("/")
def index():
    return app.send_static_file("index.html") if Path(app.static_folder, "index.html").exists() \
        else send_from_directory("templates", "index.html")


@app.route("/image/<path:filename>")
def serve_image(filename):
    """생성된 이미지 서빙."""
    if ctx.output_dir and (ctx.output_dir / "candidates" / filename).exists():
        return send_from_directory(ctx.output_dir / "candidates", filename)
    if ctx.output_dir and (ctx.output_dir / filename).exists():
        return send_from_directory(ctx.output_dir, filename)
    return "Not found", 404


# ── WebSocket 이벤트 ──

@socketio.on("connect")
def handle_connect():
    """재접속 시 현재 상태 전송."""
    state_data = {"state": ctx.state.name}
    if ctx.character:
        state_data["character"] = ctx.character.to_dict()
    if ctx.candidate_paths:
        state_data["candidates"] = [
            {"index": i, "url": f"/image/{p.name}"}
            for i, p in enumerate(ctx.candidate_paths)
        ]
    emit("state_change", state_data)


@socketio.on("chat")
def handle_chat(data):
    """사용자 채팅 메시지 처리 — Gemini API 호출은 백그라운드 스레드."""
    message = data.get("message", "").strip()
    if not message:
        return
    socketio.start_background_task(_run_chat, message)


def _run_chat(message: str):
    """백그라운드: 채팅 메시지 처리 (Gemini API 호출 포함)."""
    result = process_chat_message(ctx, message)

    if result["type"] == "response":
        socketio.emit("response", {"text": result["text"]})
    elif result["type"] == "trigger":
        socketio.emit("character", result["character"])
        socketio.emit("state_change", {"state": "GENERATING"})
        _run_generate()
    elif result["type"] == "need_more":
        socketio.emit("response", {"text": "아직 캐릭터 정보가 부족해요! 좀 더 이야기해주세요."})
    elif result["type"] == "error":
        socketio.emit("error", {"message": result["message"], "fallback_state": "CHATTING"})
    elif result["type"] == "done":
        socketio.emit("state_change", {"state": "DONE"})


@socketio.on("refine")
def handle_refine(data):
    """이미지 선택 + 피드백 → 프롬프트 개선 + 재생성."""
    index = data.get("index", 0)
    feedback = data.get("feedback", "")

    emit("state_change", {"state": "REFINING"})
    socketio.start_background_task(_run_refine, index, feedback)


@socketio.on("approve")
def handle_approve(data):
    """이미지 확정 → 애니메이션 생성."""
    index = data.get("index", 0)

    emit("state_change", {"state": "ANIMATING"})
    socketio.start_background_task(_run_animate, index)


@socketio.on("cancel")
def handle_cancel():
    """진행 중인 작업 취소."""
    ctx.cancel_requested = True


@socketio.on("reset")
def handle_reset():
    """세션 초기화."""
    ctx.reset()
    emit("state_change", {"state": "CHATTING"})


# ── 백그라운드 태스크 ──

def _run_generate():
    """백그라운드: 이미지 생성 + 실시간 emit."""
    for event in process_generate(ctx):
        if event["type"] == "image_ready":
            socketio.emit("image_ready", {
                "index": event["index"],
                "url": f"/image/{event['filename']}",
            })
        elif event["type"] == "progress":
            socketio.emit("progress", {
                "current": event["current"],
                "total": event["total"],
                "label": f"이미지 생성 중 ({event['current']}/{event['total']})",
            })
        elif event["type"] == "done":
            socketio.emit("state_change", {"state": "PREVIEWING"})
        elif event["type"] == "error":
            socketio.emit("error", {
                "message": event["message"],
                "fallback_state": ctx.state.name,
            })
        elif event["type"] == "cancelled":
            socketio.emit("state_change", {"state": ctx.state.name})


def _run_refine(index: int, feedback: str):
    """백그라운드: 프롬프트 개선 + 재생성."""
    result = process_refine(ctx, index, feedback)

    if result["type"] == "refined":
        socketio.emit("refine_result", {
            "summary": result["summary"],
            "prompt": result["prompt"],
        })
        socketio.emit("state_change", {"state": "GENERATING"})
        _run_generate()
    elif result["type"] == "error":
        socketio.emit("error", {
            "message": result["message"],
            "fallback_state": "PREVIEWING",
        })


def _run_animate(index: int):
    """백그라운드: 애니메이션 생성."""
    for event in process_animate(ctx, index):
        if event["type"] == "progress":
            socketio.emit("progress", {
                "current": event["current"],
                "total": event["total"],
                "label": event.get("label", "애니메이션 생성 중..."),
            })
        elif event["type"] == "done":
            socketio.emit("animation_done", {
                "gif_url": f"/image/{event['gif_filename']}",
            })
            socketio.emit("state_change", {"state": "DONE"})
        elif event["type"] == "error":
            socketio.emit("error", {
                "message": event["message"],
                "fallback_state": "PREVIEWING",
            })


if __name__ == "__main__":
    print(f"\n🎮 Pixel-A-Factory 서버 시작")
    print(f"   http://localhost:{config.PREVIEW_PORT}\n")
    socketio.run(app, host="127.0.0.1", port=config.PREVIEW_PORT, debug=False)
```

- [ ] **Step 2: 구문 검사**

Run: `python3 -c "import ast; ast.parse(open('app.py').read())" && echo "OK"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add Flask-SocketIO main server (app.py)"
```

---

### Task 4: templates/index.html — 웹 UI

**Files:**
- Create: `templates/index.html`
- Delete: `templates/preview.html`

- [ ] **Step 1: index.html 작성**

상하 분할 레이아웃:
- 상단: 이미지 패널 (상태에 따라 표시/숨김)
- 하단: 채팅 패널
- Socket.IO 클라이언트 (CDN)
- 상태별 UI 전환 로직

구현 내용:
- `CHATTING`: 채팅 전체화면, 이미지 패널 숨김
- `GENERATING`: 이미지 패널 슬라이드 표시, 1장씩 추가, 진행률 바
- `PREVIEWING`: 이미지 그리드 (클릭 선택 → 초록 테두리, 더블클릭 → 확대 모달) + 채팅 + 수정/확정 버튼
- `REFINING`: 로딩 스피너 + "프롬프트 개선 중..." 표시
- `ANIMATING`: 진행률 바 + "애니메이션 생성 중..." 표시
- `DONE`: GIF 미리보기 + 다운로드 + "새 캐릭터 만들기" 버튼

CSS:
- 다크 테마 (`#1a1a2e`, `#16213e`, `#0f3460` 기존 팔레트 재활용)
- `image-rendering: pixelated` (픽셀아트 선명하게)
- 이미지 패널 높이 전환 애니메이션 (`transition: max-height 0.3s`)

JS:
- Socket.IO 이벤트 리스너 (response, state_change, image_ready, progress, error 등)
- 상태별 UI 전환 함수 `setState(state)`
- 이미지 선택/확대 핸들러
- 채팅 메시지 전송 핸들러

(전체 HTML 코드는 길어서 구현 시 작성 — 약 300줄)

- [ ] **Step 2: preview.html 삭제**

```bash
rm templates/preview.html
```

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git rm templates/preview.html
git commit -m "feat: add web UI template, remove old preview.html"
```

---

### Task 5: preview_server.py 삭제 + chat.py 업데이트

**Files:**
- Delete: `preview_server.py`
- Modify: `chat.py`

- [ ] **Step 1: preview_server.py 삭제**

```bash
rm preview_server.py
```

- [ ] **Step 2: chat.py 수정 — 기본 모드를 웹 서버 안내로 변경**

```python
# chat.py
"""CLI 인터페이스: 기본은 웹 모드 안내, --cli로 CLI 모드 사용."""

from __future__ import annotations

import argparse
import sys

import config


def _cli_mode(args) -> None:
    """CLI 전용 대화 모드 (레거시)."""
    from pathlib import Path
    import pipeline
    import story_engine
    from models import CharacterSpec
    from session import SessionContext, SessionState, process_chat_message

    print("\n🎮 Pixel-A-Factory (CLI 모드)\n")
    print("캐릭터에 대해 이야기해주세요!")
    print("준비가 되면 '생성해줘'라고 말해주세요.\n")

    ctx = SessionContext(
        output_dir=Path(args.output) if args.output else None,
        remove_bg=not args.no_rembg,
        instagram=args.instagram,
    )

    try:
        while ctx.state != SessionState.DONE:
            try:
                user_input = input("> ").strip()
            except EOFError:
                break
            if not user_input:
                continue

            result = process_chat_message(ctx, user_input)
            if result["type"] == "response":
                print(f"\n[Pixel-A-Factory] {result['text']}\n")
            elif result["type"] == "trigger":
                print(f"\n  ✓ 캐릭터: {result['character']['name']}")
                print(f"  → 웹 모드에서 이미지 미리보기를 사용하세요: python3 app.py\n")
            elif result["type"] == "need_more":
                print("\n[Pixel-A-Factory] 아직 캐릭터 정보가 부족해요!\n")
            elif result["type"] == "error":
                print(f"\n[오류] {result['message']}\n")
            elif result["type"] == "done":
                print("\n안녕히 가세요!")
                break
    except KeyboardInterrupt:
        print("\n\n안녕히 가세요!")


def _direct_mode(args) -> None:
    """저장된 캐릭터로 직접 생성 모드."""
    from pathlib import Path
    import pipeline
    from models import CharacterSpec

    spec = CharacterSpec.load(args.load)
    print(f"  ✓ 캐릭터 로드: {spec.name} ({args.load})")
    actions = args.actions.split(",") if args.actions else ["idle"]
    output_dir = Path(args.output) if args.output else None

    results = pipeline.run(spec, actions, remove_bg=not args.no_rembg,
                           instagram=args.instagram, output_dir=output_dir)
    if results:
        for path in results:
            print(f"  → {path}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Pixel-A-Factory")
    parser.add_argument("--cli", action="store_true", help="CLI 대화 모드 (기본: 웹 모드)")
    parser.add_argument("--load", type=str, default=None, help="캐릭터 JSON 로드")
    parser.add_argument("--actions", type=str, default=None, help="액션 목록 (콤마 구분)")
    parser.add_argument("--no-rembg", action="store_true", help="배경 제거 건너뛰기")
    parser.add_argument("--instagram", action="store_true", help="인스타 최적화")
    parser.add_argument("--output", type=str, default=None, help="출력 디렉토리")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.load:
        _direct_mode(args)
    elif args.cli:
        _cli_mode(args)
    else:
        print("\n🎮 Pixel-A-Factory")
        print(f"\n  웹 모드: python3 app.py")
        print(f"  CLI 모드: python3 chat.py --cli\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 구문 검사**

Run: `python3 -c "import ast; ast.parse(open('chat.py').read())" && echo "OK"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git rm preview_server.py
git add chat.py
git commit -m "refactor: remove preview_server.py, update chat.py for web mode"
```

---

### Task 6: E2E 테스트 업데이트

**Files:**
- Modify: `tests/test_e2e.py`

- [ ] **Step 1: SocketIO 테스트 추가**

`test_e2e.py`에 기존 Step 4 (미리보기 서버) 테스트를 SocketIO 기반으로 교체:

```python
# Step 4를 다음으로 교체:
def test_step4_socketio_server(result: TestResult):
    """Flask-SocketIO 서버 이벤트 테스트."""
    print("\n[Step 4] SocketIO 서버 테스트")

    from app import app, socketio, ctx
    ctx.reset()

    test_client = socketio.test_client(app)

    # connect → state_change 수신
    received = test_client.get_received()
    state_events = [r for r in received if r["name"] == "state_change"]
    if state_events and state_events[0]["args"][0]["state"] == "CHATTING":
        result.ok("connect → state_change CHATTING")
    else:
        result.fail("connect → state_change", f"받은 이벤트: {received}")

    # chat 이벤트 (빈 메시지)
    test_client.emit("chat", {"message": ""})
    received = test_client.get_received()
    if not received:
        result.ok("빈 메시지 무시")
    else:
        result.fail("빈 메시지 무시", f"예상: 무응답, 실제: {received}")

    # reset 이벤트
    test_client.emit("reset", {})
    received = test_client.get_received()
    reset_events = [r for r in received if r["name"] == "state_change"]
    if reset_events and reset_events[0]["args"][0]["state"] == "CHATTING":
        result.ok("reset → state_change CHATTING")
    else:
        result.fail("reset", f"받은 이벤트: {received}")

    test_client.disconnect()
    result.ok("disconnect 정상")
```

- [ ] **Step 2: 테스트 실행**

Run: `python3 tests/test_e2e.py --offline --skip-rembg`
Expected: 전체 통과

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: update E2E tests for SocketIO server"
```

---

### Task 7: 통합 테스트 + 정리

- [ ] **Step 1: 전체 구문 검사**

Run: `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['app.py','session.py','chat.py','config.py']]" && echo "OK"`

- [ ] **Step 2: 오프라인 E2E 테스트**

Run: `python3 tests/test_e2e.py --offline --skip-rembg`

- [ ] **Step 3: app.py 수동 실행 테스트**

Run: `python3 app.py &` → 브라우저에서 `http://localhost:5050` 접속 → UI 확인 → 서버 종료

- [ ] **Step 4: CLAUDE.md 업데이트**

진입점을 `app.py`로 변경 사항 반영.

- [ ] **Step 5: 최종 Commit + Push**

```bash
git add -A
git commit -m "feat: complete WebSocket web UI integration"
git push
```
