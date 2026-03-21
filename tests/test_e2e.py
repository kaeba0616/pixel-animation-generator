"""E2E 테스트: SD Forge 연동 전체 파이프라인 검증.

사용법:
    # SD WebUI Forge가 --api 모드로 실행 중이어야 합니다.
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

import requests
from PIL import Image

import config
from models import CharacterSpec, FrameSpec


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


# ─── Step 1: SD 연결 테스트 ────────────────────────────────
def test_step1_connection(result: TestResult) -> bool:
    """SD WebUI Forge 연결 + Swagger 접근 테스트."""
    print("\n[Step 1] SD WebUI Forge 연결 테스트")
    print(f"  서버: {config.SD_API_URL}")

    # 1a. 기본 연결
    try:
        resp = requests.get(
            f"{config.SD_API_URL}/sdapi/v1/options", timeout=10
        )
        resp.raise_for_status()
        options = resp.json()
        model = options.get("sd_model_checkpoint", "unknown")
        result.ok("서버 연결", f"모델: {model}")
    except requests.ConnectionError:
        result.fail("서버 연결", f"{config.SD_API_URL}에 연결할 수 없습니다")
        return False
    except Exception as e:
        result.fail("서버 연결", str(e))
        return False

    # 1b. Swagger 문서 접근
    try:
        resp = requests.get(f"{config.SD_API_URL}/docs", timeout=5)
        resp.raise_for_status()
        result.ok("Swagger /docs 접근")
    except Exception as e:
        result.fail("Swagger /docs 접근", str(e))

    # 1c. 사용 가능한 샘플러 확인
    try:
        resp = requests.get(
            f"{config.SD_API_URL}/sdapi/v1/samplers", timeout=5
        )
        samplers = [s["name"] for s in resp.json()]
        has_euler = any("euler" in s.lower() for s in samplers)
        result.ok("샘플러 목록", f"{len(samplers)}개 (Euler: {'✓' if has_euler else '✗'})")
    except Exception as e:
        result.fail("샘플러 목록", str(e))

    return True


# ─── Step 2: txt2img 단일 프레임 생성 ─────────────────────
def test_step2_txt2img(result: TestResult) -> Image.Image | None:
    """txt2img로 단일 프레임 생성 테스트."""
    print("\n[Step 2] txt2img 단일 프레임 생성 테스트")

    import sd_client

    frame = FrameSpec(
        prompt=(
            "pixel art, chibi, black cat, blue wizard robe, "
            "transparent background, clean pixel edges"
        ),
        negative_prompt=(
            "blurry, realistic, 3d render, gradient, noise, watermark"
        ),
        seed=42,
        width=config.SD_DEFAULT_WIDTH,
        height=config.SD_DEFAULT_HEIGHT,
    )

    try:
        t0 = time.time()
        img = sd_client.txt2img(frame)
        elapsed = time.time() - t0
        result.ok(
            "txt2img 생성",
            f"{img.size[0]}x{img.size[1]} {img.mode}, {elapsed:.1f}초",
        )
    except Exception as e:
        result.fail("txt2img 생성", str(e))
        return None

    # 검증
    if img.size != (config.SD_DEFAULT_WIDTH, config.SD_DEFAULT_HEIGHT):
        result.fail("해상도 검증", f"예상: {config.SD_DEFAULT_WIDTH}x{config.SD_DEFAULT_HEIGHT}, 실제: {img.size}")
    else:
        result.ok("해상도 검증", f"{img.size[0]}x{img.size[1]}")

    if img.mode != "RGBA":
        result.fail("RGBA 모드", f"실제: {img.mode}")
    else:
        result.ok("RGBA 모드")

    # 테스트 이미지 저장
    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_path = TEST_OUTPUT_DIR / "test_txt2img.png"
    img.save(save_path)
    result.ok("이미지 저장", str(save_path))

    return img


# ─── Step 3: img2img 히어로 프레임 기반 변형 ───────────────
def test_step3_img2img(result: TestResult, hero: Image.Image) -> Image.Image | None:
    """img2img로 히어로 프레임 기반 변형 생성."""
    print("\n[Step 3] img2img 히어로 프레임 변형 테스트")

    import sd_client

    frame = FrameSpec(
        prompt=(
            "pixel art, chibi, black cat, blue wizard robe, "
            "standing, slight lean left, transparent background"
        ),
        negative_prompt=(
            "blurry, realistic, 3d render, gradient, noise, watermark"
        ),
        seed=43,
        width=config.SD_DEFAULT_WIDTH,
        height=config.SD_DEFAULT_HEIGHT,
    )

    try:
        t0 = time.time()
        img = sd_client.img2img(hero, frame, denoising_strength=0.5)
        elapsed = time.time() - t0
        result.ok(
            "img2img 생성",
            f"{img.size[0]}x{img.size[1]}, denoising=0.5, {elapsed:.1f}초",
        )
    except Exception as e:
        result.fail("img2img 생성", str(e))
        return None

    save_path = TEST_OUTPUT_DIR / "test_img2img.png"
    img.save(save_path)
    result.ok("변형 이미지 저장", str(save_path))

    return img


# ─── Step 4: 후처리 파이프라인 ─────────────────────────────
def test_step4_postprocess(
    result: TestResult, img: Image.Image, skip_rembg: bool = False
) -> Image.Image | None:
    """후처리 파이프라인: rembg → grid align → quantize."""
    print("\n[Step 4] 후처리 파이프라인 테스트")

    import pixel_cleaner

    # 4a. 배경 제거
    if skip_rembg:
        result.skip("rembg 배경 제거", "VRAM 절약을 위해 건너뜀")
        processed = img
    else:
        try:
            t0 = time.time()
            processed = pixel_cleaner.remove_background(img)
            elapsed = time.time() - t0
            result.ok("rembg 배경 제거", f"{elapsed:.1f}초")
            save_path = TEST_OUTPUT_DIR / "test_rembg.png"
            processed.save(save_path)
        except Exception as e:
            result.fail("rembg 배경 제거", str(e))
            processed = img

    # 4b. 그리드 정렬
    try:
        aligned = pixel_cleaner.align_to_grid(processed, grid_size=32)
        result.ok("그리드 정렬", f"→ {config.PIXEL_GRID_SIZE}x{config.PIXEL_GRID_SIZE} 스냅")
        save_path = TEST_OUTPUT_DIR / "test_grid_aligned.png"
        aligned.save(save_path)
    except Exception as e:
        result.fail("그리드 정렬", str(e))
        return None

    # 4c. 색상 양자화
    try:
        quantized = pixel_cleaner.index_colors(aligned, num_colors=16)
        result.ok("16색 양자화")
        save_path = TEST_OUTPUT_DIR / "test_quantized.png"
        quantized.save(save_path)
    except Exception as e:
        result.fail("16색 양자화", str(e))
        return None

    # 4d. clean() 통합 테스트
    try:
        cleaned = pixel_cleaner.clean(img, remove_bg=not skip_rembg)
        result.ok("clean() 통합")
        save_path = TEST_OUTPUT_DIR / "test_cleaned.png"
        cleaned.save(save_path)
        return cleaned
    except Exception as e:
        result.fail("clean() 통합", str(e))
        return quantized


# ─── Step 5: 멀티프레임 생성 + GIF 조립 ───────────────────
def test_step5_full_pipeline(
    result: TestResult, skip_rembg: bool = False
) -> Path | None:
    """프롬프트 생성 → SD 멀티프레임 → 후처리 → GIF 조립."""
    print("\n[Step 5] 전체 파이프라인 (idle 액션) 테스트")

    import sd_client
    import pixel_cleaner
    import aseprite_runner
    from prompt_generator import build_animation_requests, build_frame_specs

    # 5a. 프롬프트 생성
    try:
        requests_list = build_animation_requests(TEST_CHARACTER, ["idle"])
        frame_specs = build_frame_specs(requests_list[0], base_seed=100)
        result.ok("프롬프트 생성", f"idle: {len(frame_specs)}프레임")
    except Exception as e:
        result.fail("프롬프트 생성", str(e))
        return None

    # 5b. SD 프레임 생성 (2-Pass)
    try:
        t0 = time.time()
        images = sd_client.generate_frames(
            frame_specs,
            progress_callback=lambda cur, tot: print(
                f"    프레임 [{cur}/{tot}]", end="\r"
            ),
        )
        elapsed = time.time() - t0
        print()  # clear \r
        result.ok("SD 프레임 생성", f"{len(images)}프레임, {elapsed:.1f}초")
    except Exception as e:
        result.fail("SD 프레임 생성", str(e))
        return None

    # 5c. 후처리
    try:
        cleaned = pixel_cleaner.clean_batch(images, remove_bg=not skip_rembg)
        result.ok("배치 후처리", f"{len(cleaned)}프레임")
    except Exception as e:
        result.fail("배치 후처리", str(e))
        return None

    # 5d. GIF 조립
    try:
        gif_path = aseprite_runner.assemble(
            cleaned, TEST_OUTPUT_DIR, name="e2e_idle", scale=8
        )
        result.ok("GIF 조립", str(gif_path))
        return gif_path
    except Exception as e:
        result.fail("GIF 조립", str(e))
        return None


# ─── Step 6: VRAM 모니터링 ─────────────────────────────────
def test_step6_vram(result: TestResult):
    """GPU VRAM 사용량 확인."""
    print("\n[Step 6] GPU VRAM 상태")

    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        parts = out.stdout.strip().split(", ")
        used, total, util = int(parts[0]), int(parts[1]), parts[2].strip()
        pct = used / total * 100
        result.ok("VRAM", f"{used}MiB / {total}MiB ({pct:.0f}%), GPU 사용률: {util}%")
    except Exception as e:
        result.fail("VRAM 확인", str(e))


# ─── 메인 ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pixel-A-Factory E2E 테스트")
    parser.add_argument(
        "--step", type=int, default=0,
        help="특정 단계만 실행 (1-6, 0=전체)",
    )
    parser.add_argument(
        "--skip-rembg", action="store_true",
        help="rembg 배경 제거 건너뛰기 (VRAM 절약)",
    )
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════╗")
    print("║       Pixel-A-Factory E2E 테스트                 ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  SD API: {config.SD_API_URL}")
    print(f"  해상도: {config.SD_DEFAULT_WIDTH}x{config.SD_DEFAULT_HEIGHT}")
    print(f"  출력: {TEST_OUTPUT_DIR}")

    result = TestResult()
    run_step = args.step

    # Step 1: 연결
    if run_step in (0, 1):
        connected = test_step1_connection(result)
        if not connected and run_step == 0:
            print("\n⚠ SD WebUI에 연결할 수 없습니다. 이후 테스트를 건너뜁니다.")
            result.summary()
            sys.exit(1)

    hero = None
    # Step 2: txt2img
    if run_step in (0, 2):
        hero = test_step2_txt2img(result)

    # Step 3: img2img
    if run_step in (0, 3):
        if hero is None:
            # Step 2가 건너뛰어졌으면 더미 이미지 사용
            hero_path = TEST_OUTPUT_DIR / "test_txt2img.png"
            if hero_path.exists():
                hero = Image.open(hero_path).convert("RGBA")
            else:
                result.skip("img2img", "히어로 프레임 없음")
        if hero is not None:
            test_step3_img2img(result, hero)

    # Step 4: 후처리
    if run_step in (0, 4):
        test_img = hero
        if test_img is None:
            test_img_path = TEST_OUTPUT_DIR / "test_txt2img.png"
            if test_img_path.exists():
                test_img = Image.open(test_img_path).convert("RGBA")
        if test_img is not None:
            test_step4_postprocess(result, test_img, skip_rembg=args.skip_rembg)
        else:
            result.skip("후처리", "테스트 이미지 없음")

    # Step 5: 전체 파이프라인
    if run_step in (0, 5):
        test_step5_full_pipeline(result, skip_rembg=args.skip_rembg)

    # Step 6: VRAM
    if run_step in (0, 6):
        test_step6_vram(result)

    success = result.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
