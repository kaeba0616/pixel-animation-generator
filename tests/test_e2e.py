"""E2E 테스트: Grok API + 미리보기 서버 + 프롬프트 개선 파이프라인 검증.

사용법:
    python3 tests/test_e2e.py              # 전체 테스트
    python3 tests/test_e2e.py --step 1     # 특정 단계만 실행
    python3 tests/test_e2e.py --skip-rembg # rembg 제외 (VRAM 절약)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image

import config
from models import CharacterSpec


# ─── 유틸리티 ─────────────────────────────────────────────
class TestResult:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.skipped: list[str] = []

    def ok(self, name: str, detail: str = ""):
        self.passed.append(name)
        msg = f"  ✓ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)

    def fail(self, name: str, error: str):
        self.failed.append(name)
        print(f"  ✗ {name} — {error}")

    def skip(self, name: str, reason: str = ""):
        self.skipped.append(name)
        print(f"  ⊘ {name} (건너뜀: {reason})")

    def summary(self):
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        print(f"\n{'='*50}")
        print(f"결과: {len(self.passed)}/{total} 통과", end="")
        if self.skipped:
            print(f", {len(self.skipped)} 건너뜀", end="")
        if self.failed:
            print(f", {len(self.failed)} 실패", end="")
        print()
        if self.failed:
            print("실패 항목:")
            for name in self.failed:
                print(f"  - {name}")
        print(f"{'='*50}")
        return len(self.failed) == 0


# ─── 테스트 캐릭터 ────────────────────────────────────────
TEST_CHARACTER = CharacterSpec(
    name="TestCat",
    body_type="small",
    hair="short blue spiky hair",
    outfit="dark blue wizard robe with silver stars",
    accessories="wooden staff, leather boots",
    color_palette=["#1a1a2e", "#16213e", "#0f3460", "#e94560"],
    style_tags=["pixel art", "chibi", "16-bit"],
    personality="curious",
    backstory="A test wizard cat",
)

TEST_OUTPUT_DIR = PROJECT_ROOT / "output" / "_e2e_test"


# ─── Step 1: Grok API 연결 테스트 ────────────────────────
def test_step1_grok_connection(result: TestResult) -> bool:
    """xAI Grok API 연결 테스트."""
    print("\n[Step 1] Grok API 연결 테스트")

    import grok_client

    try:
        grok_client._check_connection()
        result.ok("Grok API 연결")
        return True
    except ConnectionError as e:
        result.fail("Grok API 연결", str(e))
        return False


# ─── Step 2: 단일 이미지 생성 ─────────────────────────────
def test_step2_single_image(result: TestResult) -> Image.Image | None:
    """Grok으로 단일 이미지 생성 테스트."""
    print("\n[Step 2] Grok 단일 이미지 생성 테스트")

    import grok_client

    prompt = (
        "pixel art, chibi, black cat, blue wizard robe, "
        "solid bright green background (#00FF00), "
        "single character sprite, centered, no text"
    )

    try:
        t0 = time.time()
        img = grok_client.generate_image(prompt)
        elapsed = time.time() - t0
        result.ok(
            "이미지 생성",
            f"{img.size[0]}x{img.size[1]} {img.mode}, {elapsed:.1f}초",
        )
    except Exception as e:
        result.fail("이미지 생성", str(e))
        return None

    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_path = TEST_OUTPUT_DIR / "test_single.png"
    img.save(save_path)
    result.ok("이미지 저장", str(save_path))

    return img


# ─── Step 3: 후보 이미지 복수 생성 ───────────────────────
def test_step3_candidates(result: TestResult) -> list[Image.Image]:
    """Grok으로 후보 이미지 3장 생성 테스트."""
    print("\n[Step 3] 후보 이미지 생성 테스트 (3장)")

    import grok_client

    prompt = (
        "pixel art, chibi, black cat, blue wizard robe, "
        "solid bright green background (#00FF00), "
        "single character sprite, centered, no text"
    )

    try:
        t0 = time.time()
        images = grok_client.generate_candidates(
            prompt, count=3,
            progress_callback=lambda cur, tot: print(f"  [{cur}/{tot}]", end="\r"),
        )
        print()
        elapsed = time.time() - t0
        result.ok("후보 생성", f"{len(images)}장, {elapsed:.1f}초")

        TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(images):
            img.save(TEST_OUTPUT_DIR / f"test_candidate_{i}.png")
        result.ok("후보 저장")

        return images
    except Exception as e:
        result.fail("후보 생성", str(e))
        return []


# ─── Step 4: 미리보기 서버 테스트 ─────────────────────────
def test_step4_preview_server(result: TestResult):
    """Flask 미리보기 서버 라우트 테스트."""
    print("\n[Step 4] 미리보기 서버 테스트")

    from preview_server import PreviewState, create_app

    state = PreviewState()
    app = create_app(state)

    # 더미 이미지 생성
    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dummy_paths = []
    for i in range(3):
        path = TEST_OUTPUT_DIR / f"preview_test_{i}.png"
        Image.new("RGBA", (64, 64), (50 + i * 50, 100, 150, 255)).save(path)
        dummy_paths.append(path)

    state.set_candidates(dummy_paths)

    with app.test_client() as client:
        # GET /
        resp = client.get("/")
        if resp.status_code == 200:
            result.ok("GET /", "메인 페이지 렌더링")
        else:
            result.fail("GET /", f"status={resp.status_code}")

        # GET /image/0
        resp = client.get("/image/0")
        if resp.status_code == 200 and resp.content_type.startswith("image/"):
            result.ok("GET /image/0", "이미지 서빙")
        else:
            result.fail("GET /image/0", f"status={resp.status_code}")

        # GET /image/99 (범위 초과)
        resp = client.get("/image/99")
        if resp.status_code == 404:
            result.ok("GET /image/99", "404 반환")
        else:
            result.fail("GET /image/99", f"예상 404, 실제 {resp.status_code}")

        # GET /status
        resp = client.get("/status")
        if resp.status_code == 200:
            data = resp.get_json()
            if data["count"] == 3 and data["round"] == 1:
                result.ok("GET /status", f"count={data['count']}, round={data['round']}")
            else:
                result.fail("GET /status", f"예상 count=3 round=1, 실제 {data}")
        else:
            result.fail("GET /status", f"status={resp.status_code}")

        # POST /select
        resp = client.post("/select", json={"index": 1, "feedback": "test", "approve": False})
        if resp.status_code == 200:
            r = state.get_result()
            if r["selected_index"] == 1 and r["feedback"] == "test":
                result.ok("POST /select", "선택+피드백 정상")
            else:
                result.fail("POST /select", f"상태 불일치: {r}")
        else:
            result.fail("POST /select", f"status={resp.status_code}")

        # POST /select 잘못된 인덱스
        resp = client.post("/select", json={"index": 99})
        if resp.status_code == 400:
            result.ok("POST /select 잘못된 인덱스", "400 반환")
        else:
            result.fail("POST /select 잘못된 인덱스", f"예상 400, 실제 {resp.status_code}")


# ─── Step 5: 후처리 파이프라인 ─────────────────────────────
def test_step5_postprocess(
    result: TestResult, img: Image.Image | None = None, skip_rembg: bool = False
) -> Image.Image | None:
    """후처리 파이프라인: rembg → grid align → quantize."""
    print("\n[Step 5] 후처리 파이프라인 테스트")

    import pixel_cleaner

    if img is None:
        img = Image.new("RGBA", (128, 128), (100, 150, 200, 255))

    if skip_rembg:
        result.skip("rembg 배경 제거", "건너뜀 옵션 활성화")
        processed = img
    else:
        try:
            t0 = time.time()
            processed = pixel_cleaner.remove_background(img)
            elapsed = time.time() - t0
            result.ok("rembg 배경 제거", f"{elapsed:.1f}초")
        except Exception as e:
            result.fail("rembg 배경 제거", str(e))
            processed = img

    try:
        aligned = pixel_cleaner.align_to_grid(processed, grid_size=32)
        result.ok("그리드 정렬")
    except Exception as e:
        result.fail("그리드 정렬", str(e))
        return None

    try:
        quantized = pixel_cleaner.index_colors(aligned, num_colors=16)
        result.ok("16색 양자화")
        return quantized
    except Exception as e:
        result.fail("16색 양자화", str(e))
        return None


# ─── Step 6: GIF 조립 ────────────────────────────────────
def test_step6_gif_assembly(result: TestResult) -> Path | None:
    """더미 프레임으로 GIF 조립 테스트."""
    print("\n[Step 6] GIF 조립 테스트")

    import aseprite_runner

    dummy_frames = [
        Image.new("RGBA", (64, 64), (30 + i * 20, 50, 100, 255))
        for i in range(4)
    ]

    try:
        gif_path = aseprite_runner.assemble(
            dummy_frames, TEST_OUTPUT_DIR, name="test_gif", scale=2,
        )
        assert gif_path.exists(), "GIF 파일 생성 안 됨"
        size_kb = gif_path.stat().st_size / 1024
        result.ok("GIF 조립", f"{gif_path} ({size_kb:.1f}KB)")
        return gif_path
    except Exception as e:
        result.fail("GIF 조립", str(e))
        return None


# ─── Step 7: 캐릭터 저장/로드 ────────────────────────────
def test_step7_character_save_load(result: TestResult):
    """CharacterSpec 저장/로드 검증."""
    print("\n[Step 7] 캐릭터 저장/로드 테스트")

    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_path = TEST_OUTPUT_DIR / "test_character.json"

    try:
        TEST_CHARACTER.save(save_path)
        result.ok("캐릭터 JSON 저장")
    except Exception as e:
        result.fail("캐릭터 JSON 저장", str(e))
        return

    try:
        loaded = CharacterSpec.load(save_path)
        assert loaded.name == TEST_CHARACTER.name
        assert loaded.body_type == TEST_CHARACTER.body_type
        assert loaded.color_palette == TEST_CHARACTER.color_palette
        result.ok("캐릭터 JSON 로드")
    except Exception as e:
        result.fail("캐릭터 JSON 로드", str(e))

    try:
        d = TEST_CHARACTER.to_dict()
        roundtrip = CharacterSpec.from_dict(d)
        assert roundtrip.name == TEST_CHARACTER.name
        result.ok("to_dict/from_dict 라운드트립")
    except Exception as e:
        result.fail("to_dict/from_dict 라운드트립", str(e))


# ─── Step 8: 인스타 업스케일 ──────────────────────────────
def test_step8_instagram_upscale(result: TestResult):
    """인스타 Reels 업스케일 테스트."""
    print("\n[Step 8] 인스타 업스케일 테스트")

    import aseprite_runner

    try:
        small = Image.new("RGBA", (64, 64), (100, 100, 200, 255))
        upscaled = aseprite_runner.upscale_for_instagram(small)
        assert upscaled.size == (1080, 1920), f"크기 불일치: {upscaled.size}"
        result.ok("인스타 업스케일", f"{small.size} → {upscaled.size}")
    except Exception as e:
        result.fail("인스타 업스케일", str(e))


# ─── 메인 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pixel-A-Factory E2E 테스트")
    parser.add_argument(
        "--step", type=int, default=0,
        help="특정 단계만 실행 (1-8, 0=전체)",
    )
    parser.add_argument(
        "--skip-rembg", action="store_true",
        help="rembg 배경 제거 건너뛰기 (VRAM 절약)",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="API 호출 없이 오프라인 테스트만 실행 (Step 4-8)",
    )
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════╗")
    print("║       Pixel-A-Factory E2E 테스트                 ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  출력: {TEST_OUTPUT_DIR}")

    result = TestResult()
    run_step = args.step

    # Step 1: Grok 연결
    if run_step in (0, 1) and not args.offline:
        connected = test_step1_grok_connection(result)
        if not connected and run_step == 0:
            print("\n⚠ Grok API에 연결할 수 없습니다. API 테스트를 건너뜁니다.")

    # Step 2: 단일 이미지 생성
    test_img = None
    if run_step in (0, 2) and not args.offline:
        test_img = test_step2_single_image(result)

    # Step 3: 후보 이미지 생성
    if run_step in (0, 3) and not args.offline:
        test_step3_candidates(result)

    # Step 4: 미리보기 서버
    if run_step in (0, 4):
        test_step4_preview_server(result)

    # Step 5: 후처리
    if run_step in (0, 5):
        test_step5_postprocess(result, test_img, skip_rembg=args.skip_rembg)

    # Step 6: GIF 조립
    if run_step in (0, 6):
        test_step6_gif_assembly(result)

    # Step 7: 캐릭터 저장/로드
    if run_step in (0, 7):
        test_step7_character_save_load(result)

    # Step 8: 인스타 업스케일
    if run_step in (0, 8):
        test_step8_instagram_upscale(result)

    success = result.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
