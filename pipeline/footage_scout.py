"""
Footage Scout: 대본 생성 전에 어떤 동물/주제의 영상이 실제로 존재하는지 확인.

"희망 검색(Search and Hope)" → "재고 우선(Footage-First)" 아키텍처 핵심 모듈.

흐름:
  1. Gemini로 주제에서 예상 동물 목록 추출
  2. Pexels + Wikimedia 에서 각 동물 영상 가용성 확인 (병렬)
  3. script_gen.py 에 가용 목록 전달 → 없는 동물은 대본에서 제외
"""

import sys
import time
import concurrent.futures
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GEMINI_API_KEY, PEXELS_API_KEY, PIXABAY_API_KEY

WIKIMEDIA_API    = "https://commons.wikimedia.org/w/api.php"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"


# ──────────────────────────────────────────────────────────────────
# 동물 목록 추출 (Gemini)
# ──────────────────────────────────────────────────────────────────

def extract_animals_from_topic(topic: str) -> list[str]:
    """
    Gemini로 주제에서 등장할 수 있는 동물/주인공 목록 추출.
    반환: ["wolf", "fox", "polar bear", ...] (영어 소문자)
    """
    if not GEMINI_API_KEY:
        return []
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=(
                f'주제: "{topic}"\n'
                "이 주제의 영상에 등장할 가능성 있는 동물이나 주요 피사체를 "
                "최대 10개 영어로만 나열하세요. "
                "형식: animal1, animal2, animal3 (쉼표 구분, 다른 설명 없이)\n"
                "동물이 없는 주제면 'none' 반환."
            ),
        )
        text = response.text.strip().lower()
        if text == "none" or not text:
            return []
        return [a.strip() for a in text.split(",") if a.strip() and a.strip() != "none"]
    except Exception as e:
        print(f"[Scout] 동물 추출 실패: {e}")
        return []


# ──────────────────────────────────────────────────────────────────
# 소스별 가용성 확인
# ──────────────────────────────────────────────────────────────────

def _pexels_has_video(animal: str) -> bool:
    if not PEXELS_API_KEY:
        return False
    try:
        resp = requests.get(
            PEXELS_VIDEO_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": animal, "orientation": "landscape",
                    "size": "large", "per_page": 5, "page": 1},
            timeout=8,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        # URL slug에 동물 이름이 있는 영상만 카운트
        animal_words = animal.lower().split()
        for v in videos:
            import re
            slug_m = re.search(r'/video/([^/?]+)', v.get("url", ""))
            if slug_m:
                slug = slug_m.group(1).replace('-', ' ').lower().split()
                if all(w in slug for w in animal_words):
                    return True
        return False
    except Exception:
        return False


def _pixabay_has_video(animal: str) -> bool:
    if not PIXABAY_API_KEY:
        return False
    try:
        resp = requests.get(
            PIXABAY_VIDEO_URL,
            params={"key": PIXABAY_API_KEY, "q": animal,
                    "video_type": "film", "per_page": 5},
            timeout=8,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        animal_words = animal.lower().split()
        for h in hits:
            tags = h.get("tags", "").lower()
            if all(w in tags for w in animal_words):
                return True
        return False
    except Exception:
        return False


def _wikimedia_has_video(animal: str) -> bool:
    try:
        resp = requests.get(
            WIKIMEDIA_API,
            params={
                "action": "query", "list": "search",
                "srsearch": f"{animal} filetype:video",
                "srnamespace": "6", "srlimit": "5", "format": "json",
            },
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        animal_words = animal.lower().split()
        for r in results:
            title = r.get("title", "").lower()
            if all(w in title for w in animal_words):
                return True
        return False
    except Exception:
        return False


def _check_animal(animal: str) -> tuple[str, bool]:
    """단일 동물 가용성 확인 (병렬 실행용)."""
    available = (
        _wikimedia_has_video(animal) or
        _pexels_has_video(animal) or
        _pixabay_has_video(animal)
    )
    status = "✅ 있음" if available else "❌ 없음"
    print(f"  [Scout] {animal}: {status}")
    return animal, available


# ──────────────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────────────

def scout_topic(topic: str) -> dict[str, bool]:
    """
    주제에서 등장할 동물을 추출하고 영상 가용성을 병렬 확인.

    반환: {"wolf": True, "snow_leopard": False, ...}
    빈 dict 반환 시 → 스카우트 실패, 대본은 제한 없이 생성
    """
    print(f"[Scout] '{topic}' 영상 재고 확인 중...")
    animals = extract_animals_from_topic(topic)
    if not animals:
        print("[Scout] 동물 없는 주제 또는 추출 실패 — 제한 없이 진행")
        return {}

    print(f"[Scout] 확인 대상: {animals}")
    availability: dict[str, bool] = {}

    # 최대 4스레드 병렬 실행으로 속도 최적화
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_check_animal, a): a for a in animals}
        for future in concurrent.futures.as_completed(futures):
            animal, available = future.result()
            availability[animal] = available

    available_list   = [a for a, v in availability.items() if v]
    unavailable_list = [a for a, v in availability.items() if not v]
    print(f"[Scout] 가용: {available_list}")
    if unavailable_list:
        print(f"[Scout] 미보유: {unavailable_list} → 대본에서 제외 권장")

    return availability
