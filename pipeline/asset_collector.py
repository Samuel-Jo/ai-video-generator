"""
Phase 2: Pexels API로 스톡 영상 수집 (Unsplash 이미지 폴백)
각 scene의 visual_description 키워드로 검색 → assets/ 저장

핵심 품질 보증:
1. 복합 동물명 추출 (snow leopard / polar bear / arctic hare 등)
2. URL slug + 태그 기반 1차 필터
3. Gemini Vision 썸네일 검증으로 "늑대 검색 → 개 영상" 차단
4. page 1 고정 + 랜덤 보조 페이지로 풍부한 후보 확보
"""

import re
import sys
import time
import random
import argparse
import json
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    PEXELS_API_KEY, UNSPLASH_API_KEY, ASSETS_DIR,
    VIDEO_WIDTH, VIDEO_HEIGHT, GEMINI_API_KEY,
)

PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
UNSPLASH_URL    = "https://api.unsplash.com/search/photos"

# ──────────────────────────────────────────────────────────────────
# 복합 동물 이름 목록
# 첫 단어만으로 동물을 특정할 수 없는 경우 (긴 것부터 매칭)
# ──────────────────────────────────────────────────────────────────
_COMPOUND_ANIMALS = sorted([
    "snow leopard", "polar bear", "arctic hare", "arctic fox",
    "snowy owl", "snowy egret", "grizzly bear", "gray wolf",
    "bald eagle", "great horned owl", "barn owl", "golden eagle",
    "killer whale", "blue whale", "humpback whale", "sperm whale",
    "sea otter", "sea lion", "mountain lion", "mountain goat",
    "white wolf", "black bear", "red fox", "red deer",
    "brown bear", "black wolf", "spotted hyena",
], key=len, reverse=True)  # 긴 것부터 매칭해야 "snow leopard" > "snow" 우선

# 풍경/배경 키워드 → 동물 없는 장면, Gemini 검증 불필요
_SCENE_WORDS = {
    "snow", "snowy", "winter", "landscape", "forest", "mountain",
    "sunset", "sunrise", "various", "beautiful", "nature", "scenic",
    "sky", "clouds", "ocean", "sea", "river", "lake", "field",
    "aerial", "timelapse", "city", "urban", "mountain",
}

# Gemini 클라이언트 (lazy init)
_gemini_client = None


# ──────────────────────────────────────────────────────────────────
# 헬퍼 함수
# ──────────────────────────────────────────────────────────────────

def _get_gemini():
    """Gemini 클라이언트 싱글턴."""
    global _gemini_client
    if _gemini_client is None and GEMINI_API_KEY:
        from google import genai as _genai
        _gemini_client = _genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _extract_subject(keyword: str) -> str:
    """
    키워드에서 동물/주인공 이름 추출.
    복합 동물명(snow leopard, polar bear …) 우선 매칭.
    """
    kw_lower = keyword.lower().strip()
    for compound in _COMPOUND_ANIMALS:
        if kw_lower.startswith(compound):
            return compound
    return kw_lower.split()[0]


def _score_video(video: dict, keyword: str) -> int:
    """
    URL slug(3점) + 태그(1점) 합산 관련성 점수.
    slug 예: /video/wolf-running-in-snow-12345/ → "wolf running in snow"
    """
    words = keyword.lower().split()
    score = 0
    slug_match = re.search(r'/video/([^/?]+)', video.get("url", ""))
    if slug_match:
        slug = slug_match.group(1).replace('-', ' ').lower()
        for w in words:
            if w in slug.split():  # 단어 경계 매칭
                score += 3
    tags = [t["title"].lower() for t in video.get("tags", [])]
    for w in words:
        if any(w == tag or w in tag.split() for tag in tags):
            score += 1
    return score


def _is_subject_present(video: dict, subject: str) -> bool:
    """
    주인공(subject)이 URL slug 또는 태그에 있어야 통과.
    복합어(snow leopard)의 경우 ALL 단어가 있어야 함.
    단어 경계 매칭 사용 (snow ≠ snowy, snowy landscape).
    """
    subject_words = subject.lower().split()

    slug_match = re.search(r'/video/([^/?]+)', video.get("url", ""))
    if slug_match:
        slug_words = slug_match.group(1).replace('-', ' ').lower().split()
        if all(w in slug_words for w in subject_words):
            return True

    tags_flat = " ".join(t["title"].lower() for t in video.get("tags", []))
    tag_words  = tags_flat.split()
    if all(w in tag_words for w in subject_words):
        return True

    return False


def _verify_thumbnail(thumbnail_url: str, subject: str) -> bool:
    """
    Gemini Vision으로 썸네일에 해당 동물이 실제 등장하는지 검증.
    '늑대 검색 → 개 영상' 같은 미묘한 불일치를 잡아냄.
    """
    client = _get_gemini()
    if client is None or not thumbnail_url:
        return True  # Gemini 없으면 통과
    try:
        from google.genai import types
        img_bytes = requests.get(thumbnail_url, timeout=8).content
        if not img_bytes:
            return True
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                (
                    f"You are a stock video quality checker. "
                    f"Does this thumbnail image mainly show a {subject}? "
                    f"Answer ONLY 'yes' or 'no'."
                ),
            ],
        )
        passed = response.text.strip().lower().startswith("yes")
        print(f"  [Gemini Vision] '{subject}': {'통과 ✅' if passed else '거부 ❌'}")
        return passed
    except Exception as e:
        print(f"  [Gemini Vision] 오류 (통과 처리): {e}")
        return True  # 오류 시 차단하지 않음


def _best_hd_file(video: dict) -> dict | None:
    """video_files 중 width >= 1280 인 가장 해상도 높은 파일 반환."""
    files = sorted(
        video.get("video_files", []),
        key=lambda f: (f.get("width", 0), f.get("height", 0)),
        reverse=True,
    )
    for vf in files:
        if vf.get("width", 0) >= 1280:
            return vf
    return None


def _pexels_search(query: str, page: int = 1, per_page: int = 15) -> list:
    """Pexels 영상 검색 (단일 페이지)."""
    if not PEXELS_API_KEY:
        return []
    try:
        resp = requests.get(
            PEXELS_VIDEO_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={
                "query":       query,
                "orientation": "landscape",
                "size":        "large",
                "per_page":    per_page,
                "page":        page,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("videos", [])
    except Exception as e:
        print(f"  [Pexels] '{query}' p{page} 오류: {e}")
        return []


def _select_best(
    videos: list,
    query: str,
    subject: str,
    used_ids: set,
    use_gemini: bool,
) -> dict | None:
    """
    후보 영상 중 최적 선택:
    1) slug/태그 필터 (1차)
    2) 점수 내림차순 정렬
    3) Gemini Vision 검증 (use_gemini=True 이고 동물 장면인 경우)
    slug 필터 통과 결과가 없으면 전체를 대상으로 Gemini 검증 (모든 후보 재검토)
    """
    is_animal = subject not in _SCENE_WORDS
    relevant   = [v for v in videos if _is_subject_present(v, subject)]
    fallback_mode = len(relevant) == 0

    if fallback_mode:
        # slug 필터가 모두 거른 경우 → Gemini가 전체를 검증
        print(f"  [선택] slug 필터 결과 0개 → Gemini로 전체 {len(videos)}개 검증")
        relevant = videos

    scored      = sorted(relevant, key=lambda v: _score_video(v, query), reverse=True)
    max_gemini  = 5 if fallback_mode else 3
    gemini_used = 0

    for video in scored:
        if video["id"] in used_ids:
            continue

        # Gemini Vision 검증 (동물 장면, 예산 내)
        if use_gemini and is_animal and gemini_used < max_gemini:
            thumbnail = video.get("image", "")
            if thumbnail:
                gemini_used += 1
                if not _verify_thumbnail(thumbnail, subject):
                    continue  # Gemini 거부 → 다음 후보

        return video

    return None


# ──────────────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────────────

def collect_assets(scenes: list) -> dict:
    """
    scenes 리스트를 받아 각 scene에 맞는 영상/이미지를 수집.
    반환값: {scene_id: Path} 딕셔너리
    """
    results         = {}
    used_video_ids: set = set()  # 전체 장면 걸친 중복 방지

    for scene in scenes:
        sid      = scene["scene_id"]
        keyword  = scene["visual_description"]
        fallbacks = scene.get("search_fallbacks", [])
        print(f"[asset_collector] scene {sid}: '{keyword}' 검색 중...")

        asset_path = _fetch_video(sid, keyword, fallbacks, used_video_ids)
        if asset_path is None:
            print(f"  → 영상 없음, Pexels 이미지로 폴백")
            asset_path = _fetch_photo_pexels(sid, keyword)
        if asset_path is None and UNSPLASH_API_KEY:
            print(f"  → Pexels 이미지 없음, Unsplash로 폴백")
            asset_path = _fetch_photo_unsplash(sid, keyword)
        if asset_path is None:
            print(f"  ⚠️ scene {sid}: 에셋 수집 실패")
        else:
            print(f"  ✅ {asset_path.name}")

        results[sid] = asset_path
        time.sleep(0.3)

    return results


def _fetch_video(
    scene_id:  int,
    keyword:   str,
    fallbacks: list = None,
    used_ids:  set  = None,
) -> Path | None:
    if not PEXELS_API_KEY:
        return None
    if used_ids is None:
        used_ids = set()

    subject    = _extract_subject(keyword)   # 복합 동물명 지원
    queries    = [keyword] + (fallbacks or [])
    use_gemini = subject not in _SCENE_WORDS  # 풍경 장면은 Gemini 불필요

    for query in queries:
        query_subject = _extract_subject(query)

        # ── page 1(최상위 결과) 항상 포함 + 랜덤 보조 페이지로 다양성 확보 ──
        p1_videos    = _pexels_search(query, page=1,                  per_page=15)
        extra_page   = random.randint(2, 4)
        extra_videos = _pexels_search(query, page=extra_page,         per_page=10)

        # 중복 제거 후 합산
        seen_ids   = set()
        all_videos = []
        for v in p1_videos + extra_videos:
            if v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                all_videos.append(v)

        if not all_videos:
            print(f"  [Pexels] '{query}' 결과 없음, 다음 키워드...")
            continue

        print(
            f"  [Pexels] '{query}' {len(all_videos)}개 후보, "
            f"주인공: '{query_subject}'"
        )

        best = _select_best(all_videos, query, query_subject, used_ids, use_gemini)
        if best is None:
            print(f"  → '{query}': 유효한 영상 없음, 다음 키워드...")
            time.sleep(0.3)
            continue

        vf = _best_hd_file(best)
        if vf:
            safe_q = query.replace(' ', '_')[:20]
            out    = ASSETS_DIR / f"{scene_id}_{safe_q}.mp4"
            if _download(vf["link"], out):
                used_ids.add(best["id"])
                return out
        time.sleep(0.2)

    # ── 최후 수단: 필터·검증 완전 해제, primary 키워드 page 1 ──────
    print(f"  ⚠️ 모든 키워드 실패 → 필터 해제 최후 시도 ('{keyword}')")
    for v in _pexels_search(keyword, page=1, per_page=5):
        if v["id"] not in used_ids:
            vf = _best_hd_file(v)
            if vf:
                out = ASSETS_DIR / f"{scene_id}_{keyword.replace(' ', '_')[:20]}.mp4"
                if _download(vf["link"], out):
                    used_ids.add(v["id"])
                    return out

    return None


def _fetch_photo_pexels(scene_id: int, keyword: str) -> Path | None:
    if not PEXELS_API_KEY:
        return None
    try:
        resp = requests.get(
            PEXELS_PHOTO_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": keyword, "orientation": "landscape",
                    "size": "large", "per_page": 3},
            timeout=15,
        )
        resp.raise_for_status()
        for photo in resp.json().get("photos", []):
            url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
            if url:
                out = ASSETS_DIR / f"{scene_id}_{keyword.replace(' ', '_')[:20]}.jpg"
                if _download(url, out):
                    return out
    except Exception as e:
        print(f"  [Pexels photo] 오류: {e}")
    return None


def _fetch_photo_unsplash(scene_id: int, keyword: str) -> Path | None:
    try:
        resp = requests.get(
            UNSPLASH_URL,
            params={"query": keyword, "orientation": "landscape",
                    "per_page": 3, "client_id": UNSPLASH_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        for photo in resp.json().get("results", []):
            url = photo.get("urls", {}).get("regular")
            if url:
                out = ASSETS_DIR / f"{scene_id}_{keyword.replace(' ', '_')[:20]}.jpg"
                if _download(url, out):
                    return out
    except Exception as e:
        print(f"  [Unsplash] 오류: {e}")
    return None


def _download(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"  [download] 실패 {url[:60]}...: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="에셋 수집기 단위 테스트")
    parser.add_argument("--script", required=True, help="scripts/*.json 경로")
    args = parser.parse_args()

    with open(args.script, encoding="utf-8") as f:
        script = json.load(f)

    results = collect_assets(script["scenes"])
    print("\n=== 수집 결과 ===")
    for sid, path in results.items():
        status = str(path) if path else "❌ 실패"
        print(f"  scene {sid}: {status}")
