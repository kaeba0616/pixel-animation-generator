"""세션 상태 머신: CHATTING → GENERATING → PREVIEWING → REFINING → ANIMATING."""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from PIL import Image

import config
import grok_client
import pipeline
import pixel_cleaner
import story_engine
from models import CharacterSpec
from preview_server import PreviewState, start_server
from prompt_generator import build_animation_requests, build_frame_specs


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

# 확정 트리거 키워드
APPROVE_KEYWORDS = ["확정", "좋아", "이걸로", "진행", "approve", "ok", "yes"]


@dataclass
class SessionContext:
    """세션 전체 상태를 담는 컨텍스트."""

    state: SessionState = SessionState.CHATTING
    messages: list[dict] = field(default_factory=list)
    character: CharacterSpec | None = None
    actions: list[str] = field(default_factory=lambda: ["idle"])
    current_prompt: str = ""
    candidates: list[Image.Image] = field(default_factory=list)
    candidate_paths: list[Path] = field(default_factory=list)
    selected_image: Image.Image | None = None
    selected_index: int | None = None
    preview_state: PreviewState = field(default_factory=PreviewState)
    output_dir: Path | None = None
    remove_bg: bool = True
    instagram: bool = False
    cli_actions: str | None = None


def _is_trigger(text: str) -> bool:
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in TRIGGER_KEYWORDS)


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


def handle_chatting(ctx: SessionContext) -> None:
    """CHATTING 상태: Gemini 대화 + 캐릭터 추출."""
    try:
        user_input = input("\n> ").strip()
    except EOFError:
        ctx.state = SessionState.DONE
        return

    if not user_input:
        return
    if user_input.lower() in ("quit", "exit", "종료"):
        print("\n안녕히 가세요!")
        ctx.state = SessionState.DONE
        return

    if _is_trigger(user_input):
        if len(ctx.messages) < 2:
            print("\n[Pixel-A-Factory] 아직 캐릭터 정보가 부족해요! 좀 더 이야기해주세요.")
            return

        print("\n[Pixel-A-Factory] 캐릭터 스펙 추출 중...")
        try:
            spec, actions = story_engine.extract_character(ctx.messages)
        except Exception as e:
            print(f"\n[오류] 캐릭터 추출 실패: {e}")
            return

        ctx.character = spec
        ctx.actions = ctx.cli_actions.split(",") if ctx.cli_actions else (actions or ["idle"])

        print(f"  ✓ 캐릭터: {spec.name}")
        print(f"  ✓ 체형: {spec.body_type}")
        print(f"  ✓ 외형: {spec.hair}, {spec.outfit}")
        print(f"  ✓ 액션: {', '.join(ctx.actions)}")

        # 초기 프롬프트 생성
        reqs = build_animation_requests(spec, ["idle"])
        if reqs:
            specs = build_frame_specs(reqs[0])
            if specs:
                ctx.current_prompt = grok_client._build_grok_prompt(specs[0])

        # 출력 디렉토리 설정
        char_dir = (ctx.output_dir or config.OUTPUT_DIR) / pipeline._sanitize_name(spec.name)
        char_dir.mkdir(parents=True, exist_ok=True)
        ctx.output_dir = char_dir

        # 캐릭터 저장
        spec.save(char_dir / "character.json")

        ctx.state = SessionState.GENERATING
        return

    # 일반 대화
    try:
        response, ctx.messages = story_engine.chat_turn(ctx.messages, user_input)
        print(f"\n[Pixel-A-Factory] {response}")
    except Exception as e:
        print(f"\n[오류] AI 응답 실패: {e}")


def handle_generating(ctx: SessionContext) -> None:
    """GENERATING 상태: Grok으로 후보 이미지 생성."""
    count = config.GROK_CANDIDATES_COUNT
    print(f"\n[Pixel-A-Factory] 후보 이미지 {count}장 생성 중...")

    try:
        ctx.candidates = grok_client.generate_candidates(
            ctx.current_prompt,
            count=count,
            progress_callback=lambda cur, tot: print(f"  [{cur}/{tot}]", end="\r"),
        )
        print()

        # 디스크에 저장 + 미리보기 업데이트
        ctx.candidate_paths = _save_candidates(ctx.candidates, ctx.output_dir)
        ctx.preview_state.set_candidates(ctx.candidate_paths)

        port = config.PREVIEW_PORT
        print(f"  ✓ 후보 {count}장 생성 완료!")
        print(f"  🌐 미리보기: http://localhost:{port}")
        print(f"  웹에서 이미지를 선택하고 피드백을 입력하세요.")

        ctx.state = SessionState.PREVIEWING

    except Exception as e:
        print(f"\n[오류] 이미지 생성 실패: {e}")
        ctx.state = SessionState.CHATTING


def handle_previewing(ctx: SessionContext) -> None:
    """PREVIEWING 상태: 웹에서 사용자 선택 대기."""
    print("\n[Pixel-A-Factory] 웹에서 이미지를 선택해주세요... (대기 중)")

    # 선택 대기 (타임아웃 없음, Ctrl+C로 중단 가능)
    while not ctx.preview_state.wait_for_selection(timeout=2.0):
        pass  # 2초마다 확인, KeyboardInterrupt 가능

    result = ctx.preview_state.get_result()
    ctx.selected_index = result["selected_index"]
    ctx.selected_image = ctx.candidates[ctx.selected_index]

    if result["approve"]:
        print(f"\n  ✓ 후보 {ctx.selected_index + 1}번 확정!")
        ctx.state = SessionState.ANIMATING
    else:
        feedback = result["feedback"]
        print(f"\n  ✓ 후보 {ctx.selected_index + 1}번 선택")
        if feedback:
            print(f"  📝 피드백: {feedback}")
        ctx.state = SessionState.REFINING


def handle_refining(ctx: SessionContext) -> None:
    """REFINING 상태: Gemini 멀티모달로 프롬프트 개선."""
    result = ctx.preview_state.get_result()
    feedback = result["feedback"] or ""

    if not feedback:
        # 피드백 없이 선택만 한 경우 CLI에서 입력 받기
        print("\n[Pixel-A-Factory] 수정하고 싶은 점을 알려주세요 (또는 '확정'으로 진행):")
        try:
            feedback = input("> ").strip()
        except EOFError:
            ctx.state = SessionState.DONE
            return

        if not feedback:
            ctx.state = SessionState.PREVIEWING
            return

        # 확정 키워드 체크
        if any(kw in feedback.lower() for kw in APPROVE_KEYWORDS):
            ctx.state = SessionState.ANIMATING
            return

    print(f"\n[Pixel-A-Factory] 프롬프트 개선 중...")
    try:
        refined, summary, ctx.messages = story_engine.refine_prompt(
            ctx.messages,
            ctx.selected_image,
            feedback,
            ctx.current_prompt,
        )
        ctx.current_prompt = refined
        print(f"  ✓ 변경사항: {summary}")
        ctx.state = SessionState.GENERATING
    except Exception as e:
        print(f"\n[오류] 프롬프트 개선 실패: {e}")
        ctx.state = SessionState.PREVIEWING


def handle_animating(ctx: SessionContext) -> None:
    """ANIMATING 상태: 최종 애니메이션 프레임 생성 + GIF 조립."""
    print(f"\n[Pixel-A-Factory] 애니메이션 생성을 시작합니다!")
    print(f"  캐릭터: {ctx.character.name}")
    print(f"  액션: {', '.join(ctx.actions)}")

    try:
        results = pipeline.run(
            ctx.character,
            ctx.actions,
            remove_bg=ctx.remove_bg,
            instagram=ctx.instagram,
            output_dir=ctx.output_dir.parent if ctx.output_dir else None,
        )
        if results:
            print(f"\n{'='*50}")
            print("완료! 생성된 파일:")
            for path in results:
                print(f"  → {path}")
            print(f"{'='*50}")
        else:
            print("\n생성된 파일이 없습니다.")
    except Exception as e:
        print(f"\n[오류] 애니메이션 생성 실패: {e}")

    ctx.state = SessionState.DONE


def run_session(
    cli_actions: str | None = None,
    output_dir: Path | None = None,
    remove_bg: bool = True,
    instagram: bool = False,
) -> None:
    """상태 머신 기반 인터랙티브 세션 실행."""
    ctx = SessionContext(
        output_dir=output_dir,
        remove_bg=remove_bg,
        instagram=instagram,
        cli_actions=cli_actions,
    )

    # 미리보기 서버 시작
    start_server(ctx.preview_state, port=config.PREVIEW_PORT)
    print(f"[미리보기 서버] http://localhost:{config.PREVIEW_PORT}")

    # 브라우저 자동 열기
    webbrowser.open(f"http://localhost:{config.PREVIEW_PORT}")

    handlers = {
        SessionState.CHATTING: handle_chatting,
        SessionState.GENERATING: handle_generating,
        SessionState.PREVIEWING: handle_previewing,
        SessionState.REFINING: handle_refining,
        SessionState.ANIMATING: handle_animating,
    }

    while ctx.state != SessionState.DONE:
        handler = handlers.get(ctx.state)
        if handler:
            handler(ctx)
        else:
            break
