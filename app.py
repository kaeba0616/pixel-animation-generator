"""Flask-SocketIO 메인 서버: 웹 완결형 UI."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit

import config
from session import (
    SessionContext, SessionState,
    process_chat_message, process_generate, process_refine, process_animate,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# 단일 세션 (로컬 도구)
ctx = SessionContext()


# ── HTTP 라우트 ──

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/image/<path:filename>")
def serve_image(filename):
    """생성된 이미지/GIF 서빙."""
    if ctx.output_dir:
        # candidates 디렉토리 확인
        candidates_path = ctx.output_dir / "candidates" / filename
        if candidates_path.exists():
            return send_from_directory(ctx.output_dir / "candidates", filename)
        # output_dir 직접 확인 (GIF 등)
        direct_path = ctx.output_dir / filename
        if direct_path.exists():
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
    """사용자 채팅 메시지 처리 — 백그라운드 스레드."""
    message = data.get("message", "").strip()
    if not message:
        return
    socketio.start_background_task(_run_chat, message)


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

def _run_chat(message: str):
    """백그라운드: 채팅 메시지 처리."""
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
        if event["type"] == "done":
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
