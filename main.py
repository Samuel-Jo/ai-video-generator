"""
캡컷 AI 영상 자동화 파이프라인 - 통합 실행기

사용법:
  python main.py --topic "영상 주제"              # 기본 (ffmpeg 자동 렌더링)
  python main.py --topic "주제" --duration 120
  python main.py --script scripts/기존대본.json   # 대본 재활용
  python main.py --topic "주제" --skip-assets     # 이미 assets/ 있을 때
  python main.py --topic "주제" --capcut-mode     # CapCut GUI 캐시 추출 방식
"""

import argparse
import json
import sys
import io
from pathlib import Path

# 실시간 출력 + UTF-8 인코딩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from pipeline.script_gen import generate_script, save_script
from pipeline.asset_collector import collect_assets
from pipeline.ffmpeg_renderer import render as ffmpeg_render


def main():
    parser = argparse.ArgumentParser(
        description="캡컷 AI 영상 자동화 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py --topic "2026년 AI 기술 트렌드"
  python main.py --script scripts/2026년_AI_기술_트렌드.json --skip-assets
  python main.py --topic "전기차 시장 분석" --duration 120
        """,
    )
    parser.add_argument("--topic", help="영상 주제 (신규 대본 생성 시)")
    parser.add_argument("--duration", type=int, default=180, help="목표 시간(초, 기본: 180)")
    parser.add_argument("--script", help="기존 대본 JSON 경로 (재활용)")
    parser.add_argument("--skip-assets", action="store_true", help="에셋 수집 건너뜀 (assets/ 재사용)")
    parser.add_argument("--capcut-mode", action="store_true", help="CapCut GUI 캐시 추출 방식 사용")
    args = parser.parse_args()

    if not args.topic and not args.script:
        parser.error("--topic 또는 --script 중 하나를 지정하세요.")

    print()
    print("=" * 60)
    print("  캡컷 AI 영상 자동화 파이프라인")
    print("=" * 60)

    # ── Phase 1: 대본 생성 또는 로드 ──────────────────────────
    if args.script:
        script_path = Path(args.script)
        with open(script_path, encoding="utf-8") as f:
            script = json.load(f)
        print(f"\n[1/3] 대본 로드: {script_path.name}")
    else:
        print(f"\n[1/3] 대본 생성 중... (주제: {args.topic})")
        script = generate_script(args.topic, args.duration)
        script_path = save_script(script, args.topic)

    print(f"  제목: {script['title']}")
    print(f"  장면: {len(script['scenes'])}개 / {script['duration_sec']}초")

    # ── Phase 2: 에셋 수집 ────────────────────────────────────
    asset_paths = {}
    if args.skip_assets:
        print("\n[2/3] 에셋 재사용 (--skip-assets)")
        from config import ASSETS_DIR
        for scene in script["scenes"]:
            sid = scene["scene_id"]
            matches = list(ASSETS_DIR.glob(f"{sid}_*"))
            asset_paths[sid] = matches[0] if matches else None
    else:
        print("\n[2/3] 에셋 수집 중... (Pexels API)")
        asset_paths = collect_assets(script["scenes"])

    collected = sum(1 for v in asset_paths.values() if v is not None)
    print(f"  수집 완료: {collected}/{len(script['scenes'])}개")

    if collected == 0:
        print("\n[ERR] 에셋이 없습니다. Pexels API 키(.env)를 확인하거나 assets/에 파일을 직접 배치하세요.")
        sys.exit(1)

    # ── Phase 3: 렌더링 ───────────────────────────────────────
    if args.capcut_mode:
        # CapCut GUI 방식 (반자동 - 사용자 GUI 조작 필요)
        from pipeline.capcut_draft import build_capcut_draft, check_server
        from pipeline.cache_extractor import launch_capcut, wait_for_user_and_extract

        print("\n[3/3] CapCut 초안 생성 + 캐시 추출")
        if check_server():
            draft_id = build_capcut_draft(script, asset_paths)
            print(f"  초안 ID: {draft_id}")
        else:
            print("  [WARN] CapCutAPI 서버 미실행 - 초안 자동 생성 건너뜀")

        launch_capcut()
        output_file = wait_for_user_and_extract(script["title"])
    else:
        # ffmpeg 직접 렌더링 (완전 자동, 기본값)
        print("\n[3/3] ffmpeg 렌더링 중... (자동)")
        output_file = ffmpeg_render(script, asset_paths)

    print()
    print("=" * 60)
    print(f"  [완료] {output_file.name}")
    print(f"  경로: {output_file}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
