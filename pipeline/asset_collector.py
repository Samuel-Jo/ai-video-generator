"""
Phase 2: Pexels API로 스톡 영상 수집 (Unsplash 이미지 폴백)
각 scene의 visual_description 키워드로 검색 → assets/ 저장
"""

import sys
import time
import argparse
import json
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PEXELS_API_KEY, UNSPLASH_API_KEY, ASSETS_DIR, VIDEO_WIDTH, VIDEO_HEIGHT

PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
UNSPLASH_URL = "https://api.unsplash.com/search/photos"


def collect_assets(scenes: list) -> dict:
    """
    scenes 리스트를 받아 각 scene에 맞는 영상/이미지를 수집한다.
    반환값: {scene_id: Path} 딕셔너리
    """
    results = {}
    for scene in scenes:
        sid = scene["scene_id"]
        keyword = scene["visual_description"]
        print(f"[asset_collector] scene {sid}: '{keyword}' 검색 중...")

        asset_path = _fetch_video(sid, keyword)
        if asset_path is None:
            print(f"  → 영상 없음, Pexels 이미지로 폴백")
            asset_path = _fetch_photo_pexels(sid, keyword)
        if asset_path is None and UNSPLASH_API_KEY:
            print(f"  → Pexels 이미지 없음, Unsplash로 폴백")
            asset_path = _fetch_photo_unsplash(sid, keyword)
        if asset_path is None:
            print(f"  ⚠️ scene {sid}: 에셋 수집 실패 (수동으로 assets/{sid}_*.mp4 를 배치하세요)")
        else:
            print(f"  ✅ {asset_path.name}")
        results[sid] = asset_path
        time.sleep(0.3)  # API 레이트 리밋 방지

    return results


def _fetch_video(scene_id: int, keyword: str) -> Path | None:
    if not PEXELS_API_KEY:
        return None

    params = {
        "query": keyword,
        "orientation": "landscape",
        "size": "large",
        "per_page": 5,
    }
    headers = {"Authorization": PEXELS_API_KEY}

    try:
        resp = requests.get(PEXELS_VIDEO_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
    except Exception as e:
        print(f"  [Pexels video] 오류: {e}")
        return None

    for video in videos:
        # HD 파일 우선, 그 다음 SD
        files = sorted(
            video.get("video_files", []),
            key=lambda f: (f.get("width", 0), f.get("height", 0)),
            reverse=True,
        )
        for vf in files:
            if vf.get("width", 0) >= 1280:
                out = ASSETS_DIR / f"{scene_id}_{keyword.replace(' ', '_')[:20]}.mp4"
                if _download(vf["link"], out):
                    return out

    return None


def _fetch_photo_pexels(scene_id: int, keyword: str) -> Path | None:
    if not PEXELS_API_KEY:
        return None

    params = {
        "query": keyword,
        "orientation": "landscape",
        "size": "large",
        "per_page": 3,
    }
    headers = {"Authorization": PEXELS_API_KEY}

    try:
        resp = requests.get(PEXELS_PHOTO_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
    except Exception as e:
        print(f"  [Pexels photo] 오류: {e}")
        return None

    for photo in photos:
        url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
        if url:
            out = ASSETS_DIR / f"{scene_id}_{keyword.replace(' ', '_')[:20]}.jpg"
            if _download(url, out):
                return out

    return None


def _fetch_photo_unsplash(scene_id: int, keyword: str) -> Path | None:
    params = {
        "query": keyword,
        "orientation": "landscape",
        "per_page": 3,
        "client_id": UNSPLASH_API_KEY,
    }

    try:
        resp = requests.get(UNSPLASH_URL, params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        print(f"  [Unsplash] 오류: {e}")
        return None

    for photo in results:
        url = photo.get("urls", {}).get("regular")
        if url:
            out = ASSETS_DIR / f"{scene_id}_{keyword.replace(' ', '_')[:20]}.jpg"
            if _download(url, out):
                return out

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
