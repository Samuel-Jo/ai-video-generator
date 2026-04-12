"""
전체 환경 점검 스크립트
python setup_check.py
"""

import sys
import io
# Windows cp949 인코딩 문제 해결
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import importlib
from pathlib import Path

BASE = Path(__file__).parent
OK   = "[OK]  "
WARN = "[WARN]"
ERR  = "[ERR] "

results = []

def chk(label, ok, detail=""):
    icon = OK if ok else ERR
    results.append((ok, f"{icon} {label}" + (f"  ({detail})" if detail else "")))

def warn(label, detail=""):
    results.append((None, f"{WARN} {label}" + (f"  ({detail})" if detail else "")))

# 1. Python 버전
ver = sys.version_info
chk(f"Python {ver.major}.{ver.minor}.{ver.micro}", ver >= (3, 10), "3.10+ 필요")

# 2. 필수 패키지
for pkg, import_name in [
    ("google-genai",   "google.genai"),
    ("requests",       "requests"),
    ("python-dotenv",  "dotenv"),
    ("flask",          "flask"),
]:
    try:
        importlib.import_module(import_name)
        chk(f"패키지: {pkg}", True)
    except ImportError:
        chk(f"패키지: {pkg}", False, "pip install 필요")

# 3. .env 파일
env_path = BASE / ".env"
chk(".env 파일 존재", env_path.exists())

if env_path.exists():
    env_content = env_path.read_text(encoding="utf-8")

    gemini_set = ("GEMINI_API_KEY=" in env_content
                  and "여기에_Gemini_API_키_입력" not in env_content
                  and len([l for l in env_content.splitlines()
                           if l.startswith("GEMINI_API_KEY=") and len(l) > 20]) > 0)
    pexels_set = ("PEXELS_API_KEY=" in env_content
                  and "여기에_Pexels_API_키_입력" not in env_content)

    if gemini_set:
        chk("Gemini API 키", True, "설정됨")
    else:
        chk("Gemini API 키", False, ".env에 GEMINI_API_KEY 입력 필요")

    if pexels_set:
        chk("Pexels API 키", True, "설정됨")
    else:
        warn("Pexels API 키", ".env에 PEXELS_API_KEY 입력 권장")

# 4. CapCut 경로
from dotenv import load_dotenv
import os
load_dotenv(env_path)

capcut_exe = Path(os.getenv("CAPCUT_EXE", ""))
draft_dir  = Path(os.getenv("CAPCUT_DRAFT_DIR", ""))
cache_dir  = Path(os.getenv("MOTION_BLUR_CACHE", ""))

chk("CapCut.exe", capcut_exe.exists(), str(capcut_exe))
chk("CapCut 초안 폴더", draft_dir.exists(), str(draft_dir))
chk("MotionBlur 캐시 폴더", cache_dir.exists(), str(cache_dir))

# 5. CapCutAPI
capcut_server = BASE / "CapCutAPI" / "capcut_server.py"
capcut_cfg    = BASE / "CapCutAPI" / "config.json"
chk("CapCutAPI/capcut_server.py", capcut_server.exists())
chk("CapCutAPI/config.json", capcut_cfg.exists())

# 6. CapCutAPI 서버 실행 여부
try:
    import requests as req
    api_base = os.getenv("CAPCUT_API_BASE", "http://localhost:9001")
    r = req.get(api_base, timeout=2)
    chk(f"CapCutAPI 서버 ({api_base})", True, "실행 중")
except Exception:
    warn("CapCutAPI 서버", "미실행 → cd CapCutAPI && python capcut_server.py")

# 7. 프로젝트 디렉토리
for d in ["assets", "scripts", "output"]:
    chk(f"디렉토리: {d}/", (BASE / d).exists())

# ── 결과 출력 ──────────────────────────────────────────────────
print()
print("=" * 58)
print("  캡컷 AI 영상 자동화 - 환경 점검 결과")
print("=" * 58)
for ok, msg in results:
    print(f"  {msg}")

errors = [m for ok, m in results if ok is False]
warns  = [m for ok, m in results if ok is None]

print("=" * 58)
if not errors:
    print(f"  >> 준비 완료! (경고 {len(warns)}개)")
    print()
    print("  [ 실행 순서 ]")
    print("  1) 터미널 A:  cd CapCutAPI && python capcut_server.py")
    print("  2) 터미널 B:  python main.py --topic \"영상 주제\"")
else:
    print(f"  >> 필수 항목 {len(errors)}개 미완료:")
    for m in errors:
        print(f"     {m}")
print("=" * 58)
print()

sys.exit(0 if not errors else 1)
