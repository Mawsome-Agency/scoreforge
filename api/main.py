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
from core.api import get_provider_roster

app = FastAPI(
    title="ScoreForge API",
    description="AI-powered sheet music to MusicXML converter",
    version="0.2.0",
)

# ---------------------------------------------------------------------------
# Job store — in-memory (dev) or SQLite (production)
# Configured via JOB_STORE_TYPE environment variable (default: memory)
# ---------------------------------------------------------------------------
from api.job_store import JobStore

PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"

# Initialize job store based on environment
_job_store_type = os.getenv("JOB_STORE_TYPE", "memory")
_job_store_path = os.getenv("JOB_STORE_PATH", "data/jobs.db")
_jobs = JobStore(store_type=_job_store_type, db_path=_job_store_path)

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
    return {"status": "ok", "version": "0.2.0"}


@app.get("/providers")
def providers():
    """Return all configured round-robin providers and their status."""
    return {"providers": get_provider_roster()}


@app.post("/convert", status_code=202)
async def convert(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    upload_source: Optional[str] = None,
):
    """Upload a sheet music image or PDF and start OMR conversion.

    Returns a job_id immediately (202 Accepted). Poll GET /job/{id} for status.

    Query parameters:
        upload_source: Optional identifier for who uploaded (e.g., "matt", "test-agent")
                      Agents will have (agent) suffix auto-appended if not present.
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

    # Process upload_source - default to anonymous, append (agent) suffix for agents
    if upload_source:
        # Auto-append (agent) suffix if not present
        if "agent" in upload_source.lower() and not upload_source.endswith("(agent)"):
            upload_source = f"{upload_source} (agent)"
    else:
        upload_source = "anonymous"

    _jobs.set(job_id, {
        "id": job_id,
        "status": PENDING,
        "filename": file.filename or "upload",
        "measure_count": None,
        "part_count": None,
        "musicxml": None,
        "error": None,
        "model_provider": None,
        "model_name": None,
        "upload_source": upload_source,
    })

    # Persist upload to a temp file — pipeline expects a filesystem path
    suffix = Path(file.filename or "upload.png").suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()

    background_tasks.add_task(_run_pipeline, job_id, tmp.name)
    return {"job_id": job_id, "status": PENDING}


@app.get("/job/{job_id}")
def get_job(job_id: str):
    """Return job status and metadata (excludes MusicXML body)."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {k: v for k, v in job.items() if k != "musicxml"}


@app.get("/job/{job_id}/result")
def get_job_result(job_id: str):
    """Download MusicXML output for a completed job."""
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


@app.get("/runs")
def get_runs(
    status: Optional[str] = None,
    model_provider: Optional[str] = None,
    upload_source: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
):
    """List all runs with summary statistics and optional filtering.

    Query parameters:
        status: Filter by job status (pending, running, completed, failed)
        model_provider: Filter by model provider (e.g., "anthropic", "ollama:qwen3-vl:235b-instruct")
        upload_source: Filter by upload source (partial match, case-insensitive)
        limit: Maximum number of results to return
        offset: Number of results to skip (for pagination)

    Returns:
        {
            "stats": {summary statistics},
            "runs": [list of job objects without musicxml body]
        }
    """
    # Get filtered list of runs
    runs = _jobs.list_filtered(
        status=status,
        model_provider=model_provider,
        upload_source=upload_source,
        limit=limit,
        offset=offset,
    )

    # Remove musicxml from each run (too large for list view)
    for run in runs:
        run.pop("musicxml", None)

    # Get summary stats
    stats = _jobs.get_stats()

    return {
        "stats": stats,
        "runs": runs,
    }


# ---------------------------------------------------------------------------
# Background pipeline — runs in Starlette's background task thread
# ---------------------------------------------------------------------------


def _run_pipeline(job_id: str, tmp_path: str) -> None:
    """Execute OMR pipeline for a single-page upload."""
    job = _jobs.get(job_id)
    if not job:
        return

    job["status"] = RUNNING
    _jobs.set(job_id, job)

    try:
        score, model_info = extract_from_image(tmp_path)
        musicxml = build_musicxml(score)

        # Calculate duration and set completion timestamp
        completed_at = datetime.now(timezone.utc).isoformat()
        created_at = datetime.fromisoformat(job["created_at"])
        duration_seconds = int((datetime.fromisoformat(completed_at) - created_at).total_seconds())

        job["musicxml"] = musicxml
        job["measure_count"] = score.measure_count
        job["part_count"] = score.part_count
        job["model_provider"] = model_info.get("provider")
        job["model_name"] = model_info.get("model")
        job["status"] = COMPLETED
        job["completed_at"] = completed_at
        job["duration_seconds"] = duration_seconds
        _jobs.set(job_id, job)
    except Exception as exc:
        # Calculate duration even for failed jobs
        completed_at = datetime.now(timezone.utc).isoformat()
        created_at = datetime.fromisoformat(job["created_at"])
        duration_seconds = int((datetime.fromisoformat(completed_at) - created_at).total_seconds())

        job["status"] = FAILED
        job["error"] = str(exc)
        job["completed_at"] = completed_at
        job["duration_seconds"] = duration_seconds
        _jobs.set(job_id, job)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Entrypoint for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=False)
