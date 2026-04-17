from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from src.config import get_settings
from src.pipeline.job_store import JobStore
from src.pipeline.runner import PipelineRunner
from src.ingestion.registry import load_manifest, save_manifest, set_retrieval_mode

router = APIRouter(tags=["uploads"])


@router.post("/uploads")
async def uploads(
    background: BackgroundTasks,
    files: List[UploadFile] = File(...),
    collection_id: Optional[str] = Form(default=None),  # append if present
    retrieval_mode: Optional[str] = Form(default=None),
):
    s = get_settings()

    col_id = collection_id or uuid4().hex
    raw_dir = s.raw_dir / col_id
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(s.collections_dir, col_id)

    # set mode only when creating a new workspace
    # append must keep existing mode
    if not collection_id:
        set_retrieval_mode(manifest, retrieval_mode or s.retrieval.default_mode)
        save_manifest(s.collections_dir, col_id, manifest)

    file_names: List[str] = []
    for f in files:
        file_names.append(f.filename)
        (raw_dir / f.filename).write_bytes(await f.read())

    mode = "append" if collection_id else "new"
    store = JobStore(s.jobs_dir)
    job = store.create_job(collection_id=col_id, file_names=file_names, mode=mode)

    runner = PipelineRunner(store)
    background.add_task(runner.run, job.job_id)

    return {"job_id": job.job_id, "collection_id": col_id}
