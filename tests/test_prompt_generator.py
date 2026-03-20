"""prompt_generator 테스트."""

import pytest
from models import AnimationRequest, CharacterSpec
from prompt_generator import build_frame_specs, build_animation_requests


@pytest.fixture
def sample_character():
    return CharacterSpec(
        name="사무라이 고양이",
        body_type="medium",
        hair="orange striped fur",
        outfit="black samurai armor with gold trim",
        accessories="twin katanas on back, traditional kabuto helmet with cat ear holes",
        color_palette=["#FF6600", "#1A1A1A", "#FFD700"],
        style_tags=["pixel art", "chibi", "16-bit", "jrpg style"],
        personality="fierce but loyal",
        backstory="A wandering ronin cat",
    )


def test_build_frame_specs_idle(sample_character):
    request = AnimationRequest(
        character=sample_character,
        action="idle",
        frame_count=4,
    )
    frames = build_frame_specs(request, base_seed=42)

    assert len(frames) == 4
    assert frames[0].seed == 42
    assert frames[1].seed == 43
    assert "pixel art" in frames[0].prompt
    assert "orange striped fur" in frames[0].prompt
    assert "black samurai armor" in frames[0].prompt
    assert "transparent background" in frames[0].prompt
    assert "blurry" in frames[0].negative_prompt


def test_build_frame_specs_attack(sample_character):
    request = AnimationRequest(
        character=sample_character,
        action="attack_sword",
        frame_count=6,
    )
    frames = build_frame_specs(request)

    assert len(frames) == 6
    # 각 프레임마다 다른 포즈
    prompts = [f.prompt for f in frames]
    assert "sword held at side" in prompts[0]
    assert "sword raised overhead" in prompts[1]


def test_build_frame_specs_unknown_action(sample_character):
    request = AnimationRequest(
        character=sample_character,
        action="fly",
        frame_count=4,
    )
    with pytest.raises(ValueError, match="알 수 없는 액션"):
        build_frame_specs(request)


def test_build_animation_requests(sample_character):
    requests = build_animation_requests(
        sample_character, ["idle", "walk", "nonexistent"]
    )
    assert len(requests) == 2
    assert requests[0].action == "idle"
    assert requests[1].action == "walk"


def test_color_palette_in_prompt(sample_character):
    request = AnimationRequest(
        character=sample_character,
        action="idle",
        frame_count=4,
    )
    frames = build_frame_specs(request)
    assert "#FF6600" in frames[0].prompt


def test_direction_and_emotion(sample_character):
    request = AnimationRequest(
        character=sample_character,
        action="idle",
        direction="side",
        emotion="angry",
    )
    frames = build_frame_specs(request)
    assert "side view" in frames[0].prompt
    assert "angry expression" in frames[0].prompt
