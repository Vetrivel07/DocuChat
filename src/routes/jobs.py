from __future__ import annotations

from fastapi import APIRouter

from src.config import get_settings
from src.pipeline.job_store import JobStore

router = APIRouter(tags=["jobs"])

# Map enum stages -> UI keys in your JS (STAGE_LABELS)
STAGE_TO_UI = {
    "INGEST": "ingestion",
    "EXTRACT": "extraction",
    "CLEAN": "cleaning",
    "CHUNK": "chunking",
    "EMBED": "embeddings",
    "INDEX": "indexing",
    "GRAPH": "graph",
    "DONE": "ready",
}


@router.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    s = get_settings()
    store = JobStore(s.jobs_dir)
    job = store.read_job(job_id)

    stage_enum = job.current_stage or "INGEST"
    ui_stage = STAGE_TO_UI.get(stage_enum, "ingestion")

    stage_state = "running"
    if stage_enum in job.stages:
        stage_state = job.stages[stage_enum].status

    message = ""
    if job.status == "failed" and job.errors:
        message = job.errors[-1].get("reason", "Job failed")

    state = job.status
    if job.status == "done":
        state = "ready"

    return {
        "state": state,                       # "pending|running|failed|ready"
        "collection_id": job.collection_id,
        "current_stage": ui_stage,            # matches your STAGE_LABELS keys
        "stage_state": stage_state,
        "message": message,
        "done_stages": [],                    # optional (kept for compatibility)
        "source_names": [d.file_name for d in job.docs],
    }
