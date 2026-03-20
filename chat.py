"""CLI 채팅 인터페이스: 사용자 ↔ AI 대화 → 픽셀 애니메이션 생성."""

from __future__ import annotations

import sys

import story_engine
import pipeline

# 생성 트리거 키워드
TRIGGER_KEYWORDS = [
    "생성해줘", "만들어줘", "시작해줘", "생성해", "만들어", "시작해",
    "generate", "create", "make it", "go",
]

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


def _is_trigger(text: str) -> bool:
    """생성 트리거 키워드 포함 여부 확인."""
    text_lower = text.lower().strip()
    return any(kw in text_lower for kw in TRIGGER_KEYWORDS)


def main():
    print(WELCOME_MESSAGE)

    messages: list[dict] = []

    try:
        while True:
            try:
                user_input = input("\n> ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "종료"):
                print("\n안녕히 가세요!")
                break

            if _is_trigger(user_input):
                # 대화 기록이 너무 짧으면 더 대화 유도
                if len(messages) < 2:
                    print("\n[Pixel-A-Factory] 아직 캐릭터 정보가 부족해요! 좀 더 이야기해주세요.")
                    continue

                # 캐릭터 추출
                print("\n[Pixel-A-Factory] 캐릭터 스펙 추출 중...")
                try:
                    spec, actions = story_engine.extract_character(messages)
                except Exception as e:
                    print(f"\n[오류] 캐릭터 추출 실패: {e}")
                    continue

                if not actions:
                    actions = ["idle"]

                print(f"  ✓ 캐릭터: {spec.name}")
                print(f"  ✓ 체형: {spec.body_type}")
                print(f"  ✓ 외형: {spec.hair}, {spec.outfit}")
                print(f"  ✓ 액션: {', '.join(actions)}")
                print()

                # 파이프라인 실행
                try:
                    results = pipeline.run(spec, actions)
                    if results:
                        print(f"\n{'='*50}")
                        print("완료! 생성된 파일:")
                        for path in results:
                            print(f"  → {path}")
                        print(f"{'='*50}")
                    else:
                        print("\n생성된 파일이 없습니다.")
                except ConnectionError as e:
                    print(f"\n[오류] SD WebUI 연결 실패: {e}")
                    print("SD WebUI를 --api 플래그로 실행해주세요.")
                except Exception as e:
                    print(f"\n[오류] 파이프라인 실행 실패: {e}")

                continue

            # 일반 대화
            try:
                response, messages = story_engine.chat_turn(messages, user_input)
                print(f"\n[Pixel-A-Factory] {response}")
            except Exception as e:
                print(f"\n[오류] AI 응답 실패: {e}")

    except KeyboardInterrupt:
        print("\n\n안녕히 가세요!")
        sys.exit(0)


if __name__ == "__main__":
    main()
