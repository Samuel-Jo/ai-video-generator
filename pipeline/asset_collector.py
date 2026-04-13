"""
Phase 2: 스톡 영상 수집 — Pexels → Pixabay → 서식지 폴백 3단계

검색 순서:
  1) Pexels   (page 1 + 랜덤 보조 페이지, slug/Gemini 필터)
  2) Pixabay  (야생동물 전문, PIXABAY_API_KEY 있을 때)
  3) 서식지 폴백  (동물 못 찾으면 해당 동물의 서식지 영상 — 사람 등장 방지)
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
    GEMINI_API_KEY, PIXABAY_API_KEY,
)

PEXELS_VIDEO_URL  = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL  = "https://api.pexels.com/v1/search"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
WIKIMEDIA_API     = "https://commons.wikimedia.org/w/api.php"
UNSPLASH_URL      = "https://api.unsplash.com/search/photos"

# ──────────────────────────────────────────────────────────────────
# 복합 동물 이름 (첫 단어만으로 동물을 특정할 수 없는 경우)
# ──────────────────────────────────────────────────────────────────
_COMPOUND_ANIMALS = sorted([
    "snow leopard", "polar bear", "arctic hare", "arctic fox",
    "snowy owl", "snowy egret", "grizzly bear", "gray wolf",
    "bald eagle", "great horned owl", "barn owl", "golden eagle",
    "killer whale", "blue whale", "humpback whale",
    "sea otter", "sea lion", "mountain lion", "mountain goat",
    "white wolf", "black bear", "red fox", "red deer",
    "brown bear", "black wolf", "spotted hyena",
    "wild boar", "wild cat",
], key=len, reverse=True)

# 풍경/배경 전용 장면 (Gemini 검증·동물 필터 불필요)
_SCENE_WORDS = {
    "snow", "snowy", "winter", "landscape", "forest", "mountain",
    "sunset", "sunrise", "various", "beautiful", "nature", "scenic",
    "sky", "clouds", "ocean", "sea", "river", "lake", "field",
    "aerial", "timelapse", "city", "urban",
}

# 행동/수식 단어 (서식지 추출 시 제거)
_ACTION_WORDS = frozenset({
    "running", "walking", "hopping", "flying", "swimming", "hunting",
    "camouflage", "pack", "herd", "hiding", "jumping", "crawling",
    "stalking", "prowling", "sleeping", "eating", "playing",
    "various", "beautiful", "group", "alone",
})

# 동물별 기본 서식지 키워드 (최후 수단 폴백용)
_ANIMAL_HABITATS = {
    "wolf":         "winter forest snow wilderness",
    "fox":          "forest snow meadow",
    "polar bear":   "arctic ice snow ocean",
    "snow leopard": "rocky mountain snow high altitude",
    "reindeer":     "snowy tundra forest",
    "arctic hare":  "snowy tundra white landscape",
    "snowy owl":    "snowy field winter open sky",
    "weasel":       "forest floor snow leaves",
    "stoat":        "forest snow nature",
    "ermine":       "snowy ground nature",
    "arctic fox":   "arctic tundra snow ice",
    "lynx":         "pine forest snow winter",
    "wolverine":    "taiga forest snow",
    "musk ox":      "arctic tundra snow herd",
    "moose":        "forest lake snow winter",
    "elk":          "forest meadow snow",
}

# Gemini 클라이언트 (lazy init)
_gemini_client = None


# ══════════════════════════════════════════════════════════════════
# 내부 헬퍼
# ══════════════════════════════════════════════════════════════════

def _get_gemini():
    global _gemini_client
    if _gemini_client is None and GEMINI_API_KEY:
        try:
            from google import genai as _g
            _gemini_client = _g.Client(api_key=GEMINI_API_KEY)
            print("[Gemini Vision] 초기화 성공 ✅")
        except Exception as e:
            print(f"[Gemini Vision] 초기화 실패 — 검증 비활성화: {e}")
    return _gemini_client


def _extract_subject(keyword: str) -> str:
    """복합 동물명 우선 추출 (snow leopard, polar bear …)."""
    kw = keyword.lower().strip()
    for compound in _COMPOUND_ANIMALS:
        if kw.startswith(compound):
            return compound
    return kw.split()[0]


def _get_habitat_fallback(keyword: str, subject: str) -> str:
    """
    동물 이름·행동 단어를 제거한 서식지 키워드 반환.
    사전 등록 동물은 정확한 서식지 키워드 우선 사용.
    """
    # 사전 등록 서식지
    if subject in _ANIMAL_HABITATS:
        return _ANIMAL_HABITATS[subject]

    # 자동 추출: 동물 이름 + 행동 단어 제거
    subject_words = set(subject.lower().split())
    remaining = [
        w for w in keyword.lower().split()
        if w not in subject_words and w not in _ACTION_WORDS
    ]
    return (" ".join(remaining[:3]) + " nature landscape").strip() if remaining \
        else "nature wildlife landscape"


def _score_video(video: dict, keyword: str) -> int:
    """URL slug(3점) + 태그(1점). 단어 경계 매칭."""
    words = keyword.lower().split()
    score = 0
    # Pexels: /video/wolf-..., Pixabay: /videos/wolf-...
    slug_match = re.search(r'/videos?/([^/?]+)', video.get("url", ""))
    if slug_match:
        slug_words = slug_match.group(1).replace('-', ' ').lower().split()
        for w in words:
            if w in slug_words:
                score += 3
    tags = [t["title"].lower() for t in video.get("tags", [])]
    tag_words = " ".join(tags).split()
    for w in words:
        if w in tag_words:
            score += 1
    return score


def _is_subject_present(video: dict, subject: str) -> bool:
    """
    주인공 단어가 URL slug·태그에 모두 존재해야 통과.
    단어 경계 매칭 (snow ≠ snowy).
    """
    subject_words = subject.lower().split()

    slug_match = re.search(r'/videos?/([^/?]+)', video.get("url", ""))
    if slug_match:
        slug_words = slug_match.group(1).replace('-', ' ').lower().split()
        if all(w in slug_words for w in subject_words):
            return True

    tags = [t["title"].lower() for t in video.get("tags", [])]
    tag_words = " ".join(tags).split()
    return all(w in tag_words for w in subject_words)


def _verify_thumbnail(thumbnail_url: str, subject: str) -> bool:
    """
    Gemini Vision으로 썸네일에 해당 동물이 실제 등장하는지 검증.
    slug/태그로 잡지 못한 미묘한 불일치(늑대→개 등) 차단.
    """
    client = _get_gemini()
    if client is None:
        print(f"  [Gemini Vision] ⚠️ 비활성화 — '{subject}' 검증 생략")
        return True
    if not thumbnail_url:
        return True
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
        return True


def _best_hd_file(video: dict) -> dict | None:
    """최고 해상도 파일 반환. HD(≥1280) 우선, 없으면 ≥640 허용 (Wikimedia 등)."""
    files = sorted(
        video.get("video_files", []),
        key=lambda f: (f.get("width", 0), f.get("height", 0)),
        reverse=True,
    )
    for vf in files:
        if vf.get("width", 0) >= 1280:
            return vf
    # HD 없으면 640p 이상 허용 (Wikimedia 다큐 영상 등)
    for vf in files:
        if vf.get("width", 0) >= 640:
            return vf
    return None


# ══════════════════════════════════════════════════════════════════
# 검색 소스별 함수
# ══════════════════════════════════════════════════════════════════

def _pexels_search(query: str, page: int = 1, per_page: int = 15) -> list:
    if not PEXELS_API_KEY:
        return []
    try:
        resp = requests.get(
            PEXELS_VIDEO_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": "landscape",
                    "size": "large", "per_page": per_page, "page": page},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("videos", [])
    except Exception as e:
        print(f"  [Pexels] '{query}' p{page} 오류: {e}")
        return []


def _pixabay_search(query: str, per_page: int = 15) -> list:
    """Pixabay 영상 검색 (야생동물 전문 소스)."""
    if not PIXABAY_API_KEY:
        return []
    try:
        resp = requests.get(
            PIXABAY_VIDEO_URL,
            params={
                "key":        PIXABAY_API_KEY,
                "q":          query,
                "video_type": "film",
                "per_page":   per_page,
                "safesearch": "true",
                "order":      "relevant",
            },
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        return [_pixabay_to_internal(h) for h in hits]
    except Exception as e:
        print(f"  [Pixabay] '{query}' 오류: {e}")
        return []


def _wikimedia_search(query: str, max_results: int = 8) -> list:
    """
    Wikimedia Commons에서 실제 야생동물 영상 검색.
    API 키 불필요, CC 라이선스, 실제 다큐 영상 보유.
    """
    try:
        # generator=search 로 파일 목록 + videoinfo 한 번에 조회
        resp = requests.get(
            WIKIMEDIA_API,
            params={
                "action":    "query",
                "generator": "search",
                "gsrsearch": f"{query} filetype:video",
                "gsrnamespace": "6",
                "gsrlimit":  str(max_results),
                "prop":      "videoinfo",
                "viprop":    "url|dimensions|mime|thumburl",
                "viurlwidth": "1280",
                "format":    "json",
            },
            timeout=12,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
    except Exception as e:
        print(f"  [Wikimedia] '{query}' 오류: {e}")
        return []

    results = []
    for page in pages.values():
        title = page.get("title", "")
        vi    = (page.get("videoinfo") or [{}])[0]
        url   = vi.get("url", "")
        mime  = vi.get("mime", "")
        w     = vi.get("width", 0)
        h     = vi.get("height", 0)

        # 동영상 파일만 (ogg/webm/mp4), 너무 작은 건 제외
        if not url or "video" not in mime or w < 320:
            continue

        # 파일명에서 태그 추출 (File:Wolf_running_snow.webm → [wolf, running, snow])
        name_tags = re.sub(r'\.(webm|ogv|ogg|mp4)$', '', title, flags=re.I)
        name_tags = re.sub(r'^File:', '', name_tags)
        tags = [{"title": t.strip().lower()} for t in
                re.split(r'[_\-\s]+', name_tags) if t.strip()]

        results.append({
            "id":          f"wiki_{page['pageid']}",
            "url":         f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
            "image":       vi.get("thumburl", ""),
            "tags":        tags,
            "video_files": [{"link": url, "width": w, "height": h}],
        })

    if results:
        print(f"  [Wikimedia] '{query}' {len(results)}개 야생동물 영상 발견")
    return results


def _pixabay_to_internal(hit: dict) -> dict:
    """Pixabay 응답을 내부 video dict 형식으로 통일."""
    tags = [{"title": t.strip()} for t in hit.get("tags", "").split(",") if t.strip()]
    files = []
    for size in ("large", "medium", "small"):
        s = hit.get("videos", {}).get(size, {})
        if s.get("url") and s.get("width", 0) >= 640:
            files.append({"link": s["url"], "width": s.get("width", 0),
                          "height": s.get("height", 0)})
    return {
        "id":          f"pixabay_{hit['id']}",
        "url":         hit.get("pageURL", ""),
        "image":       hit.get("webformatURL", ""),
        "tags":        tags,
        "video_files": files,
    }


def _gather_candidates(query: str, source: str) -> list:
    """
    검색 소스에 따라 후보 영상 수집.
    source: "pexels" | "pixabay"
    """
    if source == "pixabay":
        return _pixabay_search(query, per_page=20)

    # Pexels: page 1 항상 + 랜덤 보조 페이지
    p1   = _pexels_search(query, page=1,               per_page=15)
    p_ex = _pexels_search(query, page=random.randint(2, 4), per_page=10)
    seen, merged = set(), []
    for v in p1 + p_ex:
        if v["id"] not in seen:
            seen.add(v["id"])
            merged.append(v)
    return merged


def _select_best(videos: list, query: str, subject: str,
                 used_ids: set, use_gemini: bool) -> dict | None:
    """
    후보 중 최적 영상 선택:
      1) slug/태그 필터 → relevant
      2) relevant 없으면 전체를 Gemini로 검증 (fallback_mode)
      3) 점수 정렬 → Gemini Vision 최종 검증 → 다운로드
    """
    is_animal    = subject not in _SCENE_WORDS
    relevant     = [v for v in videos if _is_subject_present(v, subject)]
    fallback_mode = len(relevant) == 0

    if fallback_mode:
        print(f"  [선택] slug 필터 0개 → Gemini로 전체 {len(videos)}개 재검토")
        relevant = videos

    scored      = sorted(relevant, key=lambda v: _score_video(v, query), reverse=True)
    max_gemini  = 6 if fallback_mode else 3
    gemini_used = 0

    for video in scored:
        if video["id"] in used_ids:
            continue
        if use_gemini and is_animal and gemini_used < max_gemini:
            thumb = video.get("image", "")
            if thumb:
                gemini_used += 1
                if not _verify_thumbnail(thumb, subject):
                    continue
        return video

    return None


# ══════════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════════

def collect_assets(scenes: list) -> dict:
    """
    scenes 리스트 → 각 scene에 맞는 영상/이미지 수집.
    반환: {scene_id: Path}
    """
    results        = {}
    used_video_ids: set = set()

    for scene in scenes:
        sid             = scene["scene_id"]
        keyword         = scene["visual_description"]
        fallbacks       = scene.get("search_fallbacks", [])
        habitat_hint    = scene.get("habitat_fallback", "")   # Layer 3 필드
        print(f"[asset_collector] scene {sid}: '{keyword}' 검색 중...")

        asset_path = _fetch_video(sid, keyword, fallbacks, used_video_ids, habitat_hint)

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
    scene_id:      int,
    keyword:       str,
    fallbacks:     list = None,
    used_ids:      set  = None,
    habitat_hint:  str  = "",
) -> Path | None:
    if not PEXELS_API_KEY and not PIXABAY_API_KEY:
        return None
    if used_ids is None:
        used_ids = set()

    subject    = _extract_subject(keyword)
    queries    = [keyword] + (fallbacks or [])
    use_gemini = subject not in _SCENE_WORDS

    # ── 1단계: Pexels ────────────────────────────────────────────
    for query in queries:
        q_subject = _extract_subject(query)
        candidates = _gather_candidates(query, "pexels")
        if not candidates:
            print(f"  [Pexels] '{query}' 결과 없음")
            continue

        print(f"  [Pexels] '{query}' {len(candidates)}개, 주인공: '{q_subject}'")
        best = _select_best(candidates, query, q_subject, used_ids, use_gemini)
        if best:
            out = _download_video(best, scene_id, query, used_ids)
            if out:
                return out
        time.sleep(0.3)

    # ── 2단계: Pixabay (야생동물 전문 소스) ─────────────────────
    if PIXABAY_API_KEY:
        for query in queries:
            q_subject  = _extract_subject(query)
            candidates = _gather_candidates(query, "pixabay")
            if not candidates:
                continue

            print(f"  [Pixabay] '{query}' {len(candidates)}개, 주인공: '{q_subject}'")
            best = _select_best(candidates, query, q_subject, used_ids, use_gemini)
            if best:
                out = _download_video(best, scene_id, query, used_ids)
                if out:
                    return out
            time.sleep(0.3)
    else:
        print(f"  [Pixabay] API 키 없음 (pixabay.com/api/ 에서 무료 발급 권장)")

    # ── 2.5단계: Wikimedia Commons (실제 야생동물 다큐 영상) ────
    for query in queries:
        q_subject  = _extract_subject(query)
        candidates = _wikimedia_search(query)
        if not candidates:
            continue

        print(f"  [Wikimedia] '{query}' {len(candidates)}개, 주인공: '{q_subject}'")
        best = _select_best(candidates, query, q_subject, used_ids, use_gemini)
        if best:
            out = _download_video(best, scene_id, query, used_ids)
            if out:
                return out
        time.sleep(0.5)

    # ── 3단계: 서식지 폴백 — _select_best() 거쳐 최적 선택 ─────
    habitat_query = (
        habitat_hint.strip()
        or _get_habitat_fallback(keyword, subject)
    )
    print(f"  ⚠️ 동물 영상 없음 → 서식지 대체: '{habitat_query}'")

    for source in ("pexels", "pixabay", "wikimedia"):
        if source == "pixabay" and not PIXABAY_API_KEY:
            continue
        candidates = (
            _wikimedia_search(habitat_query)
            if source == "wikimedia"
            else _gather_candidates(habitat_query, source)
        )
        if not candidates:
            continue
        # 서식지 장면은 동물 주인공 필터 불필요, Gemini 검증도 생략
        best = _select_best(candidates, habitat_query,
                            habitat_query.split()[0], used_ids, use_gemini=False)
        if best:
            out = _download_video(best, scene_id, habitat_query, used_ids)
            if out:
                return out
        time.sleep(0.3)

    return None


def _download_video(video: dict, scene_id: int, query: str, used_ids: set) -> Path | None:
    """영상 파일 선택·다운로드·ID 등록."""
    vf = _best_hd_file(video)
    if vf:
        safe_q = query.replace(' ', '_')[:20]
        out    = ASSETS_DIR / f"{scene_id}_{safe_q}.mp4"
        if _download(vf["link"], out):
            used_ids.add(video["id"])
            return out
    return None


# ══════════════════════════════════════════════════════════════════
# 이미지 폴백
# ══════════════════════════════════════════════════════════════════

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
        print(f"  [download] 실패 {url[:60]}…: {e}")
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
        print(f"  scene {sid}: {str(path) if path else '❌ 실패'}")
