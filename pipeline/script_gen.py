"""
Phase 1: Gemini API를 이용한 유튜브 영상 대본 자동 생성
입력: 주제 문자열
출력: 장면별 구조화된 JSON (scripts/ 폴더에 저장)
"""

import json
import re
import sys
import argparse
from pathlib import Path

from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GEMINI_API_KEY, SCRIPTS_DIR

SYSTEM_PROMPT = """\
당신은 유튜브 영상 제작 전문 작가입니다.
사용자가 주제를 입력하면 16:9 유튜브 영상용 대본을 JSON 형식으로 작성합니다.

출력 형식 (반드시 아래 JSON 구조만 출력, 마크다운 코드블록 없이):
{
  "title": "영상 제목 (50자 이내)",
  "description": "영상 설명 (유튜브 설명란용, 200자 이내)",
  "duration_sec": 180,
  "scenes": [
    {
      "scene_id": 1,
      "narration": "나레이션 텍스트 (자연스러운 한국어)",
      "duration_sec": 20,
      "visual_description": "영문 Pexels 검색 키워드 (3단어 이내, 예: technology future AI)",
      "subtitle": "화면 하단에 표시할 자막 (30자 이내 핵심 문장)"
    }
  ]
}

규칙:
- scenes 배열의 duration_sec 합계 = duration_sec (오차 +-10초 허용)
- visual_description은 반드시 영문, Pexels에서 검색 가능한 구체적 키워드
- 장면은 8~12개 사이로 구성
- narration은 각 장면당 읽는 데 duration_sec 초가 걸리는 분량
"""

FEW_SHOT = """\
예시 입력: "2026년 전기차 시장 전망"
예시 출력:
{
  "title": "2026년 전기차 시장 완벽 정리 | 테슬라부터 현대까지",
  "description": "2026년 전기차 시장의 핵심 트렌드와 주요 제조사별 전략을 분석합니다.",
  "duration_sec": 180,
  "scenes": [
    {
      "scene_id": 1,
      "narration": "2026년, 전기차는 더 이상 미래의 이야기가 아닙니다. 전 세계 자동차 판매량의 30%를 넘어선 전기차 시장의 현재를 살펴봅니다.",
      "duration_sec": 20,
      "visual_description": "electric car future highway",
      "subtitle": "전기차 점유율 30% 돌파"
    }
  ]
}
"""


def generate_script(topic: str, duration_sec: int = 180) -> dict:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = (
        f"{FEW_SHOT}\n\n"
        f"주제: \"{topic}\"\n"
        f"목표 시간: {duration_sec}초\n\n"
        "위 주제로 JSON 대본을 작성해주세요."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
        ),
    )

    raw = response.text.strip()
    # 마크다운 코드블록 제거
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    script = json.loads(raw)
    _validate(script)
    return script


def _validate(script: dict):
    required = {"title", "description", "duration_sec", "scenes"}
    missing = required - script.keys()
    if missing:
        raise ValueError(f"생성된 JSON에 필드 누락: {missing}")
    if not isinstance(script["scenes"], list) or len(script["scenes"]) == 0:
        raise ValueError("scenes 배열이 비어 있습니다.")
    for scene in script["scenes"]:
        for field in ("scene_id", "narration", "duration_sec", "visual_description", "subtitle"):
            if field not in scene:
                raise ValueError(f"scene {scene.get('scene_id', '?')}에 '{field}' 필드 누락")


def save_script(script: dict, topic: str) -> Path:
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", topic)[:50]
    out_path = SCRIPTS_DIR / f"{safe_name}.json"
    out_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[script_gen] 대본 저장: {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini API 대본 생성기")
    parser.add_argument("--topic", required=True, help="영상 주제")
    parser.add_argument("--duration", type=int, default=180, help="목표 시간(초)")
    args = parser.parse_args()

    script = generate_script(args.topic, args.duration)
    path = save_script(script, args.topic)
    print(json.dumps(script, ensure_ascii=False, indent=2))
