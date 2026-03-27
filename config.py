import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
ASEPRITE_PATH = os.getenv("ASEPRITE_PATH", "aseprite")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
REMBG_USE_GPU = os.getenv("REMBG_USE_GPU", "true").lower() == "true"

# 픽셀 클리너 기본값
PIXEL_GRID_SIZE = int(os.getenv("PIXEL_GRID_SIZE", "32"))
QUANTIZE_COLORS = int(os.getenv("QUANTIZE_COLORS", "16"))

# Gemini 모델
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Grok 후보 생성
GROK_CANDIDATES_COUNT = int(os.getenv("GROK_CANDIDATES_COUNT", "4"))

# 웹 서버
PREVIEW_PORT = int(os.getenv("PREVIEW_PORT", "5050"))
SECRET_KEY = os.getenv("SECRET_KEY", "pixel-a-factory-dev-key")
