"""
Edge TTS 나레이션 생성
- edge-tts 라이브러리 사용 (Microsoft Edge TTS, 무료)
- 기본 음성: ko-KR-HyunsuNeural (한국어 남성)
"""
import asyncio
import os
from pathlib import Path

TTS_VOICE = os.getenv("TTS_VOICE", "ko-KR-HyunsuNeural")


async def _generate_async(text: str, output_path: str, voice: str):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_narration(text: str, output_path: Path, voice: str = None) -> Path:
    """단일 장면 나레이션 생성. 반환: 저장된 mp3 경로"""
    voice = voice or TTS_VOICE
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_generate_async(text, str(output_path), voice))
    finally:
        loop.close()
    return output_path


def generate_all(scenes: list, output_dir: Path, voice: str = None) -> dict:
    """
    모든 장면의 나레이션 생성.
    반환: {scene_id: audio_path}  (실패 장면은 포함 안 됨)
    """
    voice = voice or TTS_VOICE
    audio_paths = {}
    for scene in scenes:
        sid = scene["scene_id"]
        text = scene.get("narration", "").strip()
        if not text:
            continue
        out = output_dir / f"narration_{sid:03d}.mp3"
        try:
            generate_narration(text, out, voice)
            audio_paths[sid] = out
            print(f"  [TTS scene {sid}] {len(text)}자 → {out.name}")
        except Exception as e:
            print(f"  [TTS scene {sid}] 실패: {e}")
    return audio_paths
