"""
CapCut GUI 없이 ffmpeg로 직접 영상 렌더링
- CapCut 내장 ffmpeg 사용 (별도 설치 불필요)
- 각 scene 클립 트리밍 + 자막 오버레이 + 최종 연결
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS

# CapCut 내장 ffmpeg (버전 경로는 glob으로 자동 탐색)
def _find_ffmpeg() -> str:
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "Apps"
    if base.exists():
        for candidate in sorted(base.iterdir(), reverse=True):
            exe = candidate / "ffmpeg.exe"
            if exe.exists():
                return str(exe)
    for fallback in ["ffmpeg", "ffmpeg.exe"]:
        if shutil.which(fallback):
            return fallback
    raise FileNotFoundError("ffmpeg를 찾을 수 없습니다.")


def _find_encoder(ffmpeg: str) -> tuple[str, list[str]]:
    """
    사용 가능한 H264 인코더 자동 선택.
    화질 우선 순서: nvenc → amf → qsv → mf → mpeg4
    반환: (encoder_name, quality_flags)
    """
    result = subprocess.run(
        [ffmpeg, "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    available = (result.stdout + result.stderr).decode("utf-8", errors="replace")

    candidates = [
        # (encoder, quality_flags)  ← 비트레이트 대신 품질 기반 인코딩
        ("h264_nvenc", ["-preset", "p4", "-cq", "20", "-bf", "2"]),
        ("h264_amf",   ["-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"]),
        ("h264_qsv",   ["-preset", "medium", "-global_quality", "20", "-look_ahead", "1"]),
        ("h264_mf",    ["-b:v", "8000k"]),
        ("mpeg4",      ["-q:v", "3"]),
    ]
    for enc, flags in candidates:
        if enc in available:
            return enc, flags
    return "mpeg4", ["-q:v", "3"]


_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
    r"C:\Windows\Fonts\batang.ttc",
]

def _find_font() -> str:
    for f in _FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return ""


def _get_duration(ffmpeg: str, path: Path) -> float:
    """소스 클립의 실제 재생 시간(초) 반환"""
    result = subprocess.run(
        [ffmpeg, "-i", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    out = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
    if m:
        h, m2, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
        return h * 3600 + m2 * 60 + s
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────

def render(script: dict, asset_paths: dict, audio_paths: dict = None) -> Path:
    ffmpeg          = _find_ffmpeg()
    font            = _find_font()
    encoder, e_flags = _find_encoder(ffmpeg)
    audio_paths     = audio_paths or {}

    print(f"[renderer] ffmpeg:  {Path(ffmpeg).name}")
    print(f"[renderer] encoder: {encoder}")
    print(f"[renderer] font:    {Path(font).name if font else '(기본)'}")
    print(f"[renderer] 나레이션: {len(audio_paths)}개 장면")

    with tempfile.TemporaryDirectory(prefix="capcut_render_") as tmp_dir:
        tmp = Path(tmp_dir)
        clip_list = []

        for scene in script["scenes"]:
            sid      = scene["scene_id"]
            dur      = float(scene["duration_sec"])
            subtitle = scene.get("subtitle", "")
            asset    = asset_paths.get(sid)
            audio    = audio_paths.get(sid)

            if asset is None or not asset.exists():
                print(f"  [scene {sid}] 에셋 없음 → 건너뜀")
                continue

            out_clip = tmp / f"scene_{sid:03d}.mp4"
            _process_clip(ffmpeg, encoder, e_flags, asset, out_clip, dur, subtitle, font, audio)
            clip_list.append(out_clip)
            print(f"  [scene {sid}] {asset.name} → {dur}s {'(나레이션O)' if audio else '(나레이션X)'}")

        if not clip_list:
            raise RuntimeError("처리된 클립이 없습니다.")

        # concat list (경로 슬래시 통일)
        concat_file = tmp / "concat.txt"
        lines = [f"file '{str(p).replace(chr(92), '/')}'" for p in clip_list]
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        safe_title = re.sub(r'[\\/:*?"<>|]', "_", script["title"])[:40]
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path   = OUTPUT_DIR / f"{safe_title}_{timestamp}.mp4"

        print(f"[renderer] 연결 중... ({len(clip_list)}개 클립)")
        _concat(ffmpeg, concat_file, out_path)

    print(f"[renderer] 완료: {out_path}")
    return out_path


# ── 내부 처리 ─────────────────────────────────────────────────────────────

def _make_subtitle_png(text: str, font_path: str, out: Path):
    """Pillow로 자막 오버레이 PNG (투명 배경, 하단 중앙)"""
    img  = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = 56
    try:
        pil_font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        pil_font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=pil_font)
    tw   = bbox[2] - bbox[0]
    th   = bbox[3] - bbox[1]
    x    = (VIDEO_WIDTH - tw) // 2
    y    = VIDEO_HEIGHT - th - 70

    pad = 14
    draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0, 170))
    for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
        draw.text((x + dx, y + dy), text, font=pil_font, fill=(0, 0, 0, 255))
    draw.text((x, y), text, font=pil_font, fill=(255, 255, 255, 255))

    img.save(str(out), "PNG")


def _process_clip(
    ffmpeg: str,
    encoder: str,
    enc_flags: list,
    src: Path,
    dst: Path,
    duration: float,
    subtitle: str,
    font: str,
    audio: Path = None,
):
    """단일 클립: 루프·트리밍 + 1080p 스케일 + 자막 overlay + 나레이션 → CFR 인코딩

    - 오디오 있으면: TTS 실제 길이를 duration으로 사용 (길이 일치)
    - 오디오 없으면: anullsrc 무음 추가 (concat 호환성 유지)
    - 모든 클립이 video+aac 구조 → concat -c copy 가능
    """
    is_image = src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")

    has_audio = audio is not None and audio.exists()

    # TTS 실제 길이를 클립 길이로 사용 (나레이션-영상 싱크)
    if has_audio:
        tts_dur = _get_duration(ffmpeg, audio)
        if tts_dur > 0:
            duration = tts_dur

    if not is_image:
        src_dur = _get_duration(ffmpeg, src)
        need_loop = src_dur > 0 and src_dur < duration
    else:
        need_loop = False

    scale = (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
        ":force_original_aspect_ratio=decrease"
        ":flags=lanczos,"
        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={VIDEO_FPS}"
    )

    loop_flag  = ["-stream_loop", "-1"] if need_loop else []
    video_loop = ["-loop", "1"] if is_image else loop_flag

    if has_audio:
        # 실제 나레이션 오디오 사용
        audio_inputs = ["-i", str(audio)]
        # filter_complex에서 오디오 index
        audio_idx = 2 if subtitle else 1
        audio_map   = ["-map", f"{audio_idx}:a"]
        audio_codec = ["-c:a", "aac", "-b:a", "128k"]
    else:
        # 무음(anullsrc) 추가 → concat 스트림 구조 통일
        audio_inputs = ["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo"]
        audio_idx = 2 if subtitle else 1
        audio_map   = ["-map", f"{audio_idx}:a"]
        audio_codec = ["-c:a", "aac", "-b:a", "64k"]

    if subtitle:
        sub_png = dst.parent / f"{dst.stem}_sub.png"
        _make_subtitle_png(subtitle, font, sub_png)

        filter_complex = (
            f"[0:v]{scale}[bg];"
            f"[1:v]loop=loop=-1:size=1:start=0[sub];"
            f"[bg][sub]overlay=0:0:shortest=1[vout]"
        )
        cmd = (
            [ffmpeg, "-y"]
            + video_loop
            + ["-i", str(src)]
            + ["-loop", "1", "-i", str(sub_png)]
            + audio_inputs
            + ["-t", str(duration)]
            + ["-filter_complex", filter_complex]
            + ["-map", "[vout]"] + audio_map
            + ["-c:v", encoder] + enc_flags
            + audio_codec
            + ["-movflags", "+faststart", str(dst)]
        )
    else:
        cmd = (
            [ffmpeg, "-y"]
            + video_loop
            + ["-i", str(src)]
            + audio_inputs
            + ["-t", str(duration), "-vf", scale]
            + ["-map", "0:v"] + audio_map
            + ["-c:v", encoder] + enc_flags
            + audio_codec
            + ["-movflags", "+faststart", str(dst)]
        )

    _run(cmd)


def _concat(ffmpeg: str, concat_file: Path, out: Path):
    """
    concat demuxer + stream copy (재인코딩 없음 → 화질 유지).
    클립이 모두 동일 codec·해상도·fps로 인코딩되어 있으므로 copy 가능.
    """
    cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",              # 재인코딩 없이 스트림 복사
        "-movflags", "+faststart",
        str(out),
    ]
    _run(cmd)


def _run(cmd: list):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")[-1000:]
        raise RuntimeError(f"ffmpeg 오류:\n{err}")
