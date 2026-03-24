import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))

# Grok 후보 생성
GROK_CANDIDATES_COUNT = int(os.getenv("GROK_CANDIDATES_COUNT", "4"))

# 웹 서버
PREVIEW_PORT = int(os.getenv("PREVIEW_PORT", "5050"))
SECRET_KEY = os.getenv("SECRET_KEY", "pixel-a-factory-dev-key")
