"""ScoreForge REST API — Sprint 1 MVP.

Routes:
    GET  /health            → liveness check
    POST /convert           → upload sheet music, returns job_id (202)
    GET  /job/{id}          → poll job status + metadata
    GET  /job/{id}/result   → download completed MusicXML

Sprint 1 constraints (intentional):
    - In-memory job store (no DB, no Redis)
    - No auth, no billing
    - Single-page only (multi-page deferred to Sprint 2)
    - No validation/fix loop (raw extraction only)
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Add project root so core.* and models.* resolve regardless of cwd
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from core.extractor import extract_from_image
from core.musicxml_builder import build_musicxml

app = FastAPI(
    title="ScoreForge API",
    description="AI-powered sheet music to MusicXML converter",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Job store — plain dict, Sprint 1 only
# Replace with Redis + worker queue in Sprint 2.
# ---------------------------------------------------------------------------

PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"

_jobs: dict[str, dict] = {}

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "application/pdf",
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/convert", status_code=202)
async def convert(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Upload a sheet music image or PDF and start OMR conversion.

    Returns a job_id immediately (202 Accepted). Poll GET /job/{id} for status.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                "Accepted: image/png, image/jpeg, application/pdf"
            ),
        )

    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum 10 MB.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "id": job_id,
        "status": PENDING,
        "filename": file.filename or "upload",
        "measure_count": None,
        "part_count": None,
        "musicxml": None,
        "error": None,
    }

    # Persist upload to a temp file — the pipeline expects a filesystem path
    suffix = Path(file.filename or "upload.png").suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()

    background_tasks.add_task(_run_pipeline, job_id, tmp.name)
    return {"job_id": job_id, "status": PENDING}


@app.get("/job/{job_id}")
def get_job(job_id: str):
    """Return job status and metadata (excludes the MusicXML body)."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {k: v for k, v in job.items() if k != "musicxml"}


@app.get("/job/{job_id}/result")
def get_job_result(job_id: str):
    """Download the MusicXML output for a completed job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job['status']}', not 'completed'",
        )
    stem = Path(job["filename"]).stem
    return Response(
        content=job["musicxml"],
        media_type="application/vnd.recordare.musicxml+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.musicxml"'
        },
    )


# ---------------------------------------------------------------------------
# Background pipeline — runs in Starlette's background task thread
# ---------------------------------------------------------------------------


def _run_pipeline(job_id: str, tmp_path: str) -> None:
    """Execute the OMR pipeline for a single-page upload."""
    job = _jobs[job_id]
    job["status"] = RUNNING
    try:
        score, _model_info = extract_from_image(tmp_path)
        musicxml = build_musicxml(score)
        job["musicxml"] = musicxml
        job["measure_count"] = score.measure_count
        job["part_count"] = score.part_count
        job["status"] = COMPLETED
    except Exception as exc:
        job["status"] = FAILED
        job["error"] = str(exc)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Entrypoint for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=False)
