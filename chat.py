"""CLI 채팅 인터페이스: 사용자 ↔ AI 대화 → 이미지 미리보기 → 수정 → 애니메이션 생성."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
import pipeline
from models import CharacterSpec
from session import run_session


WELCOME_MESSAGE = """
╔══════════════════════════════════════════════════╗
║           🎮 Pixel-A-Factory 🎮                  ║
║   AI 기반 픽셀 캐릭터 애니메이션 생성기          ║
╚══════════════════════════════════════════════════╝

캐릭터에 대해 이야기해주세요!
어떤 캐릭터를 만들고 싶나요? (외형, 의상, 무기, 성격 등)

준비가 되면 "생성해줘"라고 말해주세요.
종료: Ctrl+C 또는 "quit"
"""


def _interactive_mode(args) -> None:
    """상태 머신 기반 인터랙티브 모드."""
    print(WELCOME_MESSAGE)

    try:
        run_session(
            cli_actions=args.actions,
            output_dir=Path(args.output) if args.output else None,
            remove_bg=not args.no_rembg,
            instagram=args.instagram,
        )
    except KeyboardInterrupt:
        print("\n\n안녕히 가세요!")
        sys.exit(0)


def _direct_mode(args) -> None:
    """저장된 캐릭터로 직접 생성 모드."""
    spec = CharacterSpec.load(args.load)
    print(f"  ✓ 캐릭터 로드: {spec.name} ({args.load})")

    actions = args.actions.split(",") if args.actions else ["idle"]
    output_dir = Path(args.output) if args.output else None

    try:
        results = pipeline.run(
            spec, actions,
            remove_bg=not args.no_rembg,
            instagram=args.instagram,
            output_dir=output_dir,
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
        print(f"\n[오류] 파이프라인 실행 실패: {e}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pixel-A-Factory: AI 기반 픽셀 캐릭터 애니메이션 생성기",
    )
    parser.add_argument(
        "--load", type=str, default=None,
        help="저장된 캐릭터 JSON 파일 경로 (Gemini 대화 건너뛰기)",
    )
    parser.add_argument(
        "--actions", type=str, default=None,
        help="생성할 액션 목록 (콤마 구분, 예: idle,walk,attack_sword)",
    )
    parser.add_argument(
        "--no-rembg", action="store_true",
        help="배경 제거 건너뛰기",
    )
    parser.add_argument(
        "--instagram", action="store_true",
        help="인스타 Reels 최적화 (1080x1920 업스케일)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="출력 디렉토리 지정 (기본: ./output)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    if args.load:
        _direct_mode(args)
    else:
        _interactive_mode(args)


if __name__ == "__main__":
    main()
