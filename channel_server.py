#!/usr/bin/env python3
"""Pixel-A-Factory: Claude Code Channel MCP Server + Web UI.

Architecture:
  Browser (localhost:5050) <-HTTP-> Flask (thread) <-shared state-> MCP Server (stdio) <-> Claude Code
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_from_directory,
    stream_with_context,
)
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.types import (
    JSONRPCMessage,
    JSONRPCNotification,
    TextContent,
    Tool,
    ToolsCapability,
)

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state between Flask thread and async MCP server
# ---------------------------------------------------------------------------

# Web -> MCP: messages queued from Flask routes, consumed by async loop
message_queue: queue.Queue[dict[str, Any]] = queue.Queue()

# MCP -> Web: SSE events pushed to all connected browser clients
sse_clients: list[queue.Queue[str]] = []
sse_clients_lock = threading.Lock()

# Image state
output_dir: Path = config.OUTPUT_DIR / "channel"
output_dir.mkdir(parents=True, exist_ok=True)
candidate_paths: list[Path] = []

# Reference to the async loop (set when MCP server starts)
_async_loop: asyncio.AbstractEventLoop | None = None


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _broadcast_sse(event_data: dict[str, Any]) -> None:
    """Push an SSE event to all connected browser clients."""
    payload = f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
    with sse_clients_lock:
        dead: list[queue.Queue[str]] = []
        for q in sse_clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


# ---------------------------------------------------------------------------
# Flask HTTP server (runs in a daemon thread)
# ---------------------------------------------------------------------------

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=None,
)
app.config["SECRET_KEY"] = config.SECRET_KEY


@app.route("/")
def index():
    """Serve the web UI."""
    return send_from_directory(
        str(Path(__file__).parent / "templates"), "index.html"
    )


@app.route("/chat", methods=["POST"])
def chat():
    """Receive a chat message from the browser and queue it for MCP."""
    data = request.get_json(force=True)
    text = data.get("message", "").strip()
    if not text:
        return jsonify({"error": "empty message"}), 400

    message_queue.put(
        {
            "method": "notifications/claude/channel",
            "params": {
                "content": text,
                "meta": {"chat_id": str(uuid.uuid4()), "type": "chat"},
            },
        }
    )
    return jsonify({"status": "queued"})


@app.route("/select", methods=["POST"])
def select():
    """User selects an image candidate and provides feedback."""
    data = request.get_json(force=True)
    idx = data.get("index", 0)
    feedback = data.get("feedback", "")

    message_queue.put(
        {
            "method": "notifications/claude/channel",
            "params": {
                "content": f"[Image {idx} selected] {feedback}",
                "meta": {
                    "chat_id": str(uuid.uuid4()),
                    "type": "refine",
                    "selected_index": idx,
                    "feedback": feedback,
                },
            },
        }
    )
    return jsonify({"status": "queued"})


@app.route("/approve", methods=["POST"])
def approve():
    """User approves an image for animation generation."""
    data = request.get_json(force=True)
    idx = data.get("index", 0)

    message_queue.put(
        {
            "method": "notifications/claude/channel",
            "params": {
                "content": f"[Image {idx} approved for animation]",
                "meta": {
                    "chat_id": str(uuid.uuid4()),
                    "type": "approve",
                    "selected_index": idx,
                },
            },
        }
    )
    return jsonify({"status": "queued"})


@app.route("/events")
def events():
    """SSE stream for real-time updates to the browser."""

    def generate():
        q: queue.Queue[str] = queue.Queue(maxsize=256)
        with sse_clients_lock:
            sse_clients.append(q)
        try:
            while True:
                try:
                    payload = q.get(timeout=30)
                    yield payload
                except queue.Empty:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        except GeneratorExit:
            with sse_clients_lock:
                if q in sse_clients:
                    sse_clients.remove(q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/image/<filename>")
def serve_image(filename: str):
    """Serve generated images from the output directory."""
    return send_from_directory(str(output_dir), filename)


def _run_flask():
    """Start Flask in a daemon thread (no reloader)."""
    app.run(
        host="0.0.0.0",
        port=config.PREVIEW_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

INSTRUCTIONS = """\
You are a pixel art character designer. Users chat with you through a web interface.

Rules:
- Chat in Korean with the user
- Help them design pixel art characters through natural conversation
- When the user says "생성해줘", "만들어줘", "generate", etc., summarize the conversation \
into an English image generation prompt and call the generate_images tool
- The prompt must include: "pixel art", character description, \
"solid bright green background (#00FF00)", \
"single character sprite, centered, no text, no watermark"
- When the user selects an image and gives feedback, incorporate the feedback \
into an improved prompt and call generate_images again
- When the user approves an image, call generate_animation to create the final GIF
- Always use the reply tool to send your responses to the user
"""

server = Server(name="pixel-factory", version="1.0.0", instructions=INSTRUCTIONS)

# We store the session reference here once the server is running,
# so the queue-forwarding task can send channel notifications.
_session_ref: Any = None


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Declare the tools Claude can call."""
    return [
        Tool(
            name="reply",
            description="Send a chat reply to the user via the web UI.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The reply text to display in the browser chat.",
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="generate_images",
            description=(
                "Generate candidate pixel-art images using Grok API. "
                "Returns image URLs that appear in the browser."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "English image generation prompt.",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of candidates to generate (default 4).",
                        "default": 4,
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="generate_animation",
            description=(
                "Generate a GIF animation from the approved character prompt."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "English prompt describing the character.",
                    },
                    "actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Animation actions, e.g. ["idle", "walk"].',
                        "default": ["idle"],
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="generate_video",
            description=(
                "Generate a short video (1-15 seconds) from a prompt or from a selected image. "
                "Use this when the user wants an animated video instead of a GIF."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "English prompt describing the video.",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Video duration in seconds (1-15, default 5).",
                        "default": 5,
                    },
                    "image_index": {
                        "type": "integer",
                        "description": "Index of a candidate image to use as source (image-to-video). Omit for text-to-video.",
                    },
                    "resolution": {
                        "type": "string",
                        "description": "Video resolution: '480p' or '720p' (default '720p').",
                        "default": "720p",
                    },
                },
                "required": ["prompt"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls from Claude."""
    if name == "reply":
        return _handle_reply(arguments)
    elif name == "generate_images":
        return await _handle_generate_images(arguments)
    elif name == "generate_animation":
        return await _handle_generate_animation(arguments)
    elif name == "generate_video":
        return await _handle_generate_video(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


def _handle_reply(arguments: dict[str, Any]) -> list[TextContent]:
    """Push Claude's reply text to the browser via SSE."""
    text = arguments.get("text", "")
    _broadcast_sse({"type": "reply", "text": text})
    return [TextContent(type="text", text="Reply sent to browser.")]


async def _handle_generate_images(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Generate candidate images via Grok API and push to browser."""
    global candidate_paths

    import grok_client

    prompt = arguments.get("prompt", "")
    count = arguments.get("count", config.GROK_CANDIDATES_COUNT)

    _broadcast_sse({"type": "state_change", "state": "GENERATING"})

    try:
        batch_ts = int(time.time())

        def _generate():
            # 배치 API로 한 번에 N장 생성 (2k 해상도)
            images = grok_client.generate_candidates(
                prompt, count=count, resolution="2k", aspect_ratio="1:1",
            )
            results: list[tuple[int, Path, str]] = []
            for i, img in enumerate(images):
                filename = f"candidate_{batch_ts}_{i:02d}.png"
                path = output_dir / filename
                img.save(str(path), "PNG")
                results.append((i, path, filename))
                _broadcast_sse(
                    {
                        "type": "image_ready",
                        "index": i,
                        "url": f"/image/{filename}",
                    }
                )
            return results

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, _generate)

        candidate_paths = [path for _, path, _ in results]
        _broadcast_sse({"type": "state_change", "state": "SELECTING"})

        urls = [f"/image/{fn}" for _, _, fn in results]
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "status": "ok",
                        "count": len(results),
                        "urls": urls,
                    }
                ),
            )
        ]

    except Exception as exc:
        error_msg = f"Image generation failed: {exc}"
        _broadcast_sse({"type": "error", "message": error_msg})
        return [TextContent(type="text", text=error_msg)]


async def _handle_generate_animation(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Generate animation GIF from character prompt."""
    import aseprite_runner
    import grok_client as grok

    prompt = arguments.get("prompt", "")
    actions = arguments.get("actions", ["idle"])

    _broadcast_sse({"type": "state_change", "state": "ANIMATING"})

    try:

        def _generate_anim():
            all_gifs: list[str] = []
            for action in actions:
                # Build per-frame prompts with action/pose info
                frame_prompts = [
                    f"{prompt}, {action} pose, frame {f + 1} of 4, pixel art"
                    for f in range(4)
                ]
                frames = []
                for fp in frame_prompts:
                    imgs = grok.generate_image(fp, n=1)
                    frames.append(imgs[0])

                # Assemble GIF (Grok 출력 그대로 사용, 후처리 없음)
                gif_path = aseprite_runner.assemble(
                    frames, output_dir, name=action, scale=4
                )
                gif_filename = gif_path.name
                all_gifs.append(gif_filename)

                _broadcast_sse(
                    {
                        "type": "animation_done",
                        "gif_url": f"/image/{gif_filename}",
                    }
                )

            return all_gifs

        loop = asyncio.get_running_loop()
        gif_names = await loop.run_in_executor(None, _generate_anim)

        _broadcast_sse({"type": "state_change", "state": "DONE"})

        urls = [f"/image/{g}" for g in gif_names]
        return [
            TextContent(
                type="text",
                text=json.dumps({"status": "ok", "gifs": urls}),
            )
        ]

    except Exception as exc:
        error_msg = f"Animation generation failed: {exc}"
        _broadcast_sse({"type": "error", "message": error_msg})
        return [TextContent(type="text", text=error_msg)]


async def _handle_generate_video(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Generate a video via Grok API."""
    import requests as req_lib
    from PIL import Image
    import grok_client as grok

    prompt = arguments.get("prompt", "")
    duration = arguments.get("duration", 5)
    resolution = arguments.get("resolution", "720p")
    image_index = arguments.get("image_index")

    _broadcast_sse({"type": "state_change", "state": "ANIMATING"})
    _broadcast_sse({"type": "reply", "text": f"비디오 생성 중... ({duration}초, {resolution})"})

    try:
        def _gen_video():
            if image_index is not None and 0 <= image_index < len(candidate_paths):
                # 이미지 → 비디오
                img = Image.open(candidate_paths[image_index])
                return grok.image_to_video(
                    img, prompt, duration=duration, resolution=resolution,
                )
            else:
                # 텍스트 → 비디오
                return grok.generate_video(
                    prompt, duration=duration, resolution=resolution,
                )

        loop = asyncio.get_running_loop()
        video_url = await loop.run_in_executor(None, _gen_video)

        # 비디오 다운로드 후 로컬 저장
        def _download():
            resp = req_lib.get(video_url, timeout=120)
            resp.raise_for_status()
            video_filename = f"video_{int(time.time())}.mp4"
            video_path = output_dir / video_filename
            video_path.write_bytes(resp.content)
            return video_filename

        video_filename = await loop.run_in_executor(None, _download)

        _broadcast_sse({
            "type": "video_done",
            "video_url": f"/image/{video_filename}",
        })
        _broadcast_sse({"type": "state_change", "state": "DONE"})

        return [
            TextContent(
                type="text",
                text=json.dumps({"status": "ok", "video_url": f"/image/{video_filename}"}),
            )
        ]

    except Exception as exc:
        error_msg = f"Video generation failed: {exc}"
        _broadcast_sse({"type": "error", "message": error_msg})
        return [TextContent(type="text", text=error_msg)]


# ---------------------------------------------------------------------------
# Async task: forward queued web messages as MCP channel notifications
# ---------------------------------------------------------------------------


async def _forward_queue_to_channel(
    write_stream: Any,
) -> None:
    """Poll the thread-safe queue and send channel notifications via MCP."""
    while True:
        try:
            # Check queue in a non-blocking way, yield back to event loop
            try:
                msg = message_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue

            notification = JSONRPCNotification(
                jsonrpc="2.0",
                method=msg["method"],
                params=msg.get("params"),
            )
            session_message = SessionMessage(
                message=JSONRPCMessage(notification)
            )
            await write_stream.send(session_message)
            logger.info("Forwarded channel notification: %s", msg.get("params", {}).get("meta", {}).get("type"))

        except Exception:
            logger.exception("Error forwarding channel notification")
            await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the MCP server with Flask in a background thread."""
    global _async_loop

    _async_loop = asyncio.get_running_loop()

    # Start Flask in a daemon thread
    flask_thread = threading.Thread(target=_run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask web UI started on http://localhost:%d", config.PREVIEW_PORT)

    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options(
            experimental_capabilities={"claude/channel": {}},
        )

        # Start the queue-forwarding task alongside the server
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_forward_queue_to_channel(write_stream))
            tg.create_task(
                server.run(
                    read_stream,
                    write_stream,
                    init_options,
                    raise_exceptions=False,
                )
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(main())
