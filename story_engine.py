"""AI 대화 엔진: Gemini API로 캐릭터 스토리 대화 + 구조화 추출."""

from __future__ import annotations

import json

from google import genai
from google.genai import types

import config
from models import CharacterSpec

SYSTEM_PROMPT = """\
당신은 '픽셀 캐릭터 디자이너'입니다. 사용자와 자연스럽게 대화하며 픽셀 애니메이션 캐릭터를 함께 만들어갑니다.

역할:
- 캐릭터의 외형, 의상, 무기, 성격, 배경 스토리를 자연스럽게 질문하세요.
- 구체적인 시각적 디테일을 끌어내세요 (색상, 형태, 스타일).
- 픽셀아트 스타일(chibi, 16-bit, jrpg 등)을 제안하세요.
- 어떤 애니메이션(idle, walk, attack 등)을 원하는지 물어보세요.

대화 스타일:
- 한국어로 대화합니다.
- 열정적이고 창의적인 톤을 유지하세요.
- 짧고 핵심적인 답변을 하되, 디테일한 후속 질문을 하세요.
- 사용자의 아이디어를 구체화하고 발전시키세요.

사용자가 "생성해줘", "만들어줘", "시작해줘" 등 생성 트리거를 말하면,
지금까지의 대화 내용을 바탕으로 캐릭터 정보가 충분한지 확인하고,
부족하면 추가 질문을, 충분하면 생성을 진행하겠다고 안내하세요."""

EXTRACT_CHARACTER_SCHEMA = types.FunctionDeclaration(
    name="extract_character",
    description="대화에서 추출한 캐릭터 스펙을 구조화된 형태로 반환합니다.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "name": types.Schema(type="STRING", description="캐릭터 이름"),
            "body_type": types.Schema(
                type="STRING",
                enum=["small", "medium", "tall"],
                description="체형 (small=chibi, medium=표준, tall=장신)",
            ),
            "hair": types.Schema(type="STRING", description="머리 스타일과 색상"),
            "outfit": types.Schema(type="STRING", description="의상 설명"),
            "accessories": types.Schema(type="STRING", description="장신구, 무기 등"),
            "color_palette": types.Schema(
                type="ARRAY",
                items=types.Schema(type="STRING"),
                description="주요 색상 헥스코드 목록",
            ),
            "style_tags": types.Schema(
                type="ARRAY",
                items=types.Schema(type="STRING"),
                description="스타일 태그 (예: pixel art, chibi, 16-bit)",
            ),
            "personality": types.Schema(type="STRING", description="성격 요약"),
            "backstory": types.Schema(type="STRING", description="배경 스토리 요약"),
            "actions": types.Schema(
                type="ARRAY",
                items=types.Schema(type="STRING"),
                description="원하는 애니메이션 액션 목록 (idle, walk, attack_sword 등)",
            ),
        },
        required=["name", "body_type", "hair", "outfit", "accessories"],
    ),
)


def _get_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _to_gemini_messages(messages: list[dict]) -> list[types.Content]:
    """내부 메시지 형식 → Gemini Content 리스트로 변환."""
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=msg["content"])])
        )
    return contents


def chat_turn(
    messages: list[dict], user_input: str
) -> tuple[str, list[dict]]:
    """대화 한 턴을 진행하고 (응답 텍스트, 업데이트된 messages)를 반환."""
    client = _get_client()
    messages.append({"role": "user", "content": user_input})

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=_to_gemini_messages(messages),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1024,
        ),
    )

    assistant_text = response.text
    messages.append({"role": "assistant", "content": assistant_text})
    return assistant_text, messages


def extract_character(messages: list[dict]) -> tuple[CharacterSpec, list[str]]:
    """대화 기록에서 CharacterSpec을 function calling으로 구조화 추출.

    Returns:
        (CharacterSpec, 요청된 액션 리스트)
    """
    client = _get_client()

    extraction_messages = messages + [
        {
            "role": "user",
            "content": (
                "지금까지의 대화를 바탕으로 캐릭터 정보를 추출해주세요. "
                "extract_character 함수를 호출하세요."
            ),
        }
    ]

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=_to_gemini_messages(extraction_messages),
        config=types.GenerateContentConfig(
            system_instruction="대화 내용에서 캐릭터 정보를 정확히 추출하세요. 반드시 extract_character 함수를 호출하세요.",
            max_output_tokens=1024,
            tools=[types.Tool(function_declarations=[EXTRACT_CHARACTER_SCHEMA])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=["extract_character"],
                )
            ),
        ),
    )

    # function call 응답 파싱
    tool_input = None
    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "extract_character":
            tool_input = dict(part.function_call.args)
            break

    if tool_input is None:
        raise RuntimeError("캐릭터 추출 실패: function call 응답을 받지 못했습니다.")

    actions = tool_input.pop("actions", ["idle"])
    if isinstance(actions, str):
        actions = [actions]

    spec = CharacterSpec(
        name=tool_input["name"],
        body_type=tool_input["body_type"],
        hair=tool_input["hair"],
        outfit=tool_input["outfit"],
        accessories=tool_input["accessories"],
        color_palette=list(tool_input.get("color_palette", [])),
        style_tags=list(tool_input.get("style_tags", ["pixel art", "16-bit"])),
        personality=tool_input.get("personality", ""),
        backstory=tool_input.get("backstory", ""),
    )

    return spec, actions
