"""CLI 인터페이스: 기본은 웹 모드 안내, --cli로 CLI 모드 사용."""

from __future__ import annotations

import argparse
import sys

import config


def _cli_mode(args) -> None:
    """CLI 전용 대화 모드 (레거시)."""
    from pathlib import Path
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
