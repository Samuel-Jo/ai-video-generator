"""
캡컷 AI 영상 자동화 - FastAPI 웹 서버
실행: python server.py
"""

import io
import os
import sys
import uuid
import threading
from datetime import datetime
from pathlib import Path
from enum import Enum

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline.script_gen import generate_script, save_script
from pipeline.asset_collector import collect_assets
from pipeline.ffmpeg_renderer import render as ffmpeg_render
from pipeline.tts_gen import generate_all as tts_generate_all
from pipeline.r2_storage import upload_video, is_configured as r2_configured
from config import OUTPUT_DIR

app = FastAPI(title="캡컷 AI 영상 자동화", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Job 상태 관리 (메모리 내) ─────────────────────────────────────────────
class Status(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    ERROR     = "error"

jobs: dict[str, dict] = {}   # job_id → {status, progress, message, output_file}


class GenerateRequest(BaseModel):
    topic: str
    duration: int = 180


# ── API 엔드포인트 ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic이 비어 있습니다.")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": Status.PENDING,
        "progress": 0,
        "message": "대기 중...",
        "topic": req.topic,
        "output_file": None,
        "download_url": None,
        "created_at": datetime.now().isoformat(),
    }

    thread = threading.Thread(target=_run_pipeline, args=(job_id, req.topic, req.duration), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": Status.PENDING}


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job을 찾을 수 없습니다.")
    return job


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job을 찾을 수 없습니다.")
    if job["status"] != Status.DONE:
        raise HTTPException(status_code=400, detail=f"아직 완료되지 않았습니다. (status: {job['status']})")

    # R2에 업로드된 경우 presigned URL로 리다이렉트
    if job.get("download_url"):
        return RedirectResponse(url=job["download_url"])

    # 로컬 파일 폴백
    out = Path(job["output_file"])
    if not out.exists():
        raise HTTPException(status_code=404, detail="파일이 존재하지 않습니다.")
    return FileResponse(path=str(out), media_type="video/mp4", filename=out.name)


@app.get("/api/jobs")
async def list_jobs():
    return [
        {"job_id": jid, **{k: v for k, v in info.items() if k != "output_file"}}
        for jid, info in sorted(jobs.items(), key=lambda x: x[1]["created_at"], reverse=True)
    ]


# ── 파이프라인 백그라운드 실행 ────────────────────────────────────────────

def _update(job_id: str, status: Status, progress: int, message: str):
    jobs[job_id].update({"status": status, "progress": progress, "message": message})
    print(f"[job:{job_id}] ({progress}%) {message}")


def _run_pipeline(job_id: str, topic: str, duration: int):
    try:
        # Phase 1: 대본 생성
        _update(job_id, Status.RUNNING, 5, "대본 생성 중...")
        script = generate_script(topic, duration)
        save_script(script, topic)
        _update(job_id, Status.RUNNING, 25, f"대본 완료: {script['title']}")

        # Phase 2: 에셋 수집
        _update(job_id, Status.RUNNING, 30, "영상 에셋 수집 중...")
        asset_paths = collect_assets(script["scenes"])
        collected = sum(1 for v in asset_paths.values() if v is not None)
        _update(job_id, Status.RUNNING, 60, f"에셋 수집 완료: {collected}/{len(script['scenes'])}개")

        if collected == 0:
            raise RuntimeError("Pexels API 키를 확인하세요. 에셋 수집에 실패했습니다.")

        # Phase 3: 나레이션 생성
        _update(job_id, Status.RUNNING, 62, "나레이션 생성 중...")
        from config import ASSETS_DIR
        audio_paths = tts_generate_all(script["scenes"], ASSETS_DIR)
        narrated = len(audio_paths)
        _update(job_id, Status.RUNNING, 65, f"나레이션 완료: {narrated}/{len(script['scenes'])}개")

        # Phase 4: 렌더링
        _update(job_id, Status.RUNNING, 67, "영상 렌더링 중... (수 분 소요)")
        output_file = ffmpeg_render(script, asset_paths, audio_paths)
        _update(job_id, Status.RUNNING, 98, "렌더링 완료, 마무리 중...")

        jobs[job_id]["output_file"] = str(output_file)

        # R2 업로드 (설정된 경우)
        if r2_configured():
            _update(job_id, Status.RUNNING, 99, "R2에 업로드 중...")
            r2_key = f"videos/{job_id}/{output_file.name}"
            download_url = upload_video(output_file, r2_key)
            jobs[job_id]["download_url"] = download_url

        _update(job_id, Status.DONE, 100, f"완료: {output_file.name}")

    except Exception as e:
        _update(job_id, Status.ERROR, 0, f"오류: {e}")


# ── 서버 실행 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print("=" * 50)
    print("  AI 영상 자동화 서버 시작")
    print(f"  로컬: http://localhost:{port}")
    print("=" * 50)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
