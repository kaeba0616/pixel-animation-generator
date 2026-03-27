"""session.py 상태 머신 단위 테스트."""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
from session import SessionState, SessionContext, process_chat_message, is_trigger


def test_is_trigger():
    assert is_trigger("생성해줘") is True
    assert is_trigger("만들어줘") is True
    assert is_trigger("generate") is True
    assert is_trigger("안녕하세요") is False


def test_initial_state():
    ctx = SessionContext()
    assert ctx.state == SessionState.CHATTING
    assert ctx.messages == []
    assert ctx.character_name == ""


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
