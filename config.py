import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SD_API_URL = os.getenv("SD_API_URL", "http://127.0.0.1:7860")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ASEPRITE_PATH = os.getenv("ASEPRITE_PATH", "aseprite")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
USE_LAYERDIFFUSE = os.getenv("USE_LAYERDIFFUSE", "false").lower() == "true"
REMBG_USE_GPU = os.getenv("REMBG_USE_GPU", "true").lower() == "true"

# SD 생성 기본값
SD_DEFAULT_WIDTH = int(os.getenv("SD_DEFAULT_WIDTH", "128"))
SD_DEFAULT_HEIGHT = int(os.getenv("SD_DEFAULT_HEIGHT", "128"))
SD_STEPS = int(os.getenv("SD_STEPS", "20"))
SD_CFG_SCALE = float(os.getenv("SD_CFG_SCALE", "7.0"))
SD_SAMPLER = os.getenv("SD_SAMPLER", "Euler a")
SD_IMG2IMG_DENOISING = float(os.getenv("SD_IMG2IMG_DENOISING", "0.5"))

# 픽셀 클리너 기본값
PIXEL_GRID_SIZE = int(os.getenv("PIXEL_GRID_SIZE", "32"))
QUANTIZE_COLORS = int(os.getenv("QUANTIZE_COLORS", "16"))

# Gemini 모델
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
