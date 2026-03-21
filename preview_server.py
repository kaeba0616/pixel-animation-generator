"""Flask 기반 이미지 미리보기 서버: 후보 이미지 표시 + 선택 + 피드백."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file


@dataclass
class PreviewState:
    """CLI ↔ Flask 간 공유 상태."""

    candidates: list[Path] = field(default_factory=list)
    selected_index: int | None = None
    feedback: str = ""
    approve: bool = False
    selection_event: threading.Event = field(default_factory=threading.Event)
    round_number: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set_candidates(self, paths: list[Path]) -> None:
        """새 후보 이미지 설정 (라운드 번호 증가)."""
        with self._lock:
            self.candidates = paths
            self.selected_index = None
            self.feedback = ""
            self.approve = False
            self.round_number += 1
            self.selection_event.clear()

    def submit_selection(self, index: int, feedback: str, approve: bool) -> None:
        """사용자 선택 제출."""
        with self._lock:
            self.selected_index = index
            self.feedback = feedback
            self.approve = approve
            self.selection_event.set()

    def wait_for_selection(self, timeout: float | None = None) -> bool:
        """선택 완료 대기. 타임아웃 시 False 반환."""
        return self.selection_event.wait(timeout=timeout)

    def get_result(self) -> dict:
        """현재 선택 결과 반환."""
        with self._lock:
            return {
                "selected_index": self.selected_index,
                "feedback": self.feedback,
                "approve": self.approve,
            }


def create_app(state: PreviewState) -> Flask:
    """Flask 앱 생성."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
    )

    @app.route("/")
    def index():
        count = len(state.candidates)
        return render_template(
            "preview.html",
            count=count,
            round_number=state.round_number,
        )

    @app.route("/image/<int:idx>")
    def serve_image(idx: int):
        if 0 <= idx < len(state.candidates):
            return send_file(state.candidates[idx], mimetype="image/png")
        return "Not found", 404

    @app.route("/status")
    def status():
        return jsonify({
            "round": state.round_number,
            "count": len(state.candidates),
            "selected": state.selected_index,
        })

    @app.route("/select", methods=["POST"])
    def select():
        data = request.get_json(force=True)
        idx = data.get("index")
        feedback = data.get("feedback", "")
        approve = data.get("approve", False)

        if idx is None or not (0 <= idx < len(state.candidates)):
            return jsonify({"error": "잘못된 인덱스"}), 400

        state.submit_selection(idx, feedback, approve)
        return jsonify({"ok": True})

    return app


def start_server(state: PreviewState, port: int = 5050) -> threading.Thread:
    """Flask 서버를 daemon thread로 시작."""
    app = create_app(state)

    def _run():
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
