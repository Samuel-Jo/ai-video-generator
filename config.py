import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
UNSPLASH_API_KEY = os.getenv("UNSPLASH_API_KEY", "")

# --- CapCutAPI 로컬 서버 ---
CAPCUT_API_BASE = os.getenv("CAPCUT_API_BASE", "http://localhost:9001")

# --- CapCut 경로 (Windows) ---
_username = os.environ.get("USERNAME", os.environ.get("USER", "user"))
_appdata = os.environ.get("LOCALAPPDATA", rf"C:\Users\{_username}\AppData\Local")

CAPCUT_DRAFT_DIR = Path(
    os.getenv(
        "CAPCUT_DRAFT_DIR",
        rf"{_appdata}\CapCut\User Data\Projects\com.lveditor.draft",
    )
)
MOTION_BLUR_CACHE = Path(
    os.getenv(
        "MOTION_BLUR_CACHE",
        rf"{_appdata}\CapCut\User Data\Cache\MotionBlurCache",
    )
)
CAPCUT_EXE = Path(
    os.getenv("CAPCUT_EXE", r"C:\Program Files\CapCut\CapCut.exe")
)

# --- 영상 출력 설정 ---
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
VIDEO_ASPECT = "16:9"

# --- 프로젝트 경로 ---
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
SCRIPTS_DIR = BASE_DIR / "scripts"
OUTPUT_DIR = BASE_DIR / "output"

for _d in (ASSETS_DIR, SCRIPTS_DIR, OUTPUT_DIR):
    _d.mkdir(exist_ok=True)
