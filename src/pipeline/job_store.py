from __future__ import annotations

from pathlib import Path
from typing import List
from uuid import uuid4

from src.models import DocState, JobState, StageState, iso_now
from src.pipeline.stages import STAGE_ORDER
from src.utils.atomic_io import atomic_write_json, read_json


class JobStore:
    def __init__(self, jobs_dir: Path):
        self.jobs_dir = jobs_dir

    def _path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def create_job(self, collection_id: str, file_names: List[str], mode: str) -> JobState:
        job_id = uuid4().hex
        stages = {s: StageState() for s in STAGE_ORDER}
        docs = [DocState(file_name=fn) for fn in file_names]

        job = JobState(
            job_id=job_id,
            collection_id=collection_id,
            mode=mode,  # "new" | "append"
            created_at=iso_now(),
            status="pending",
            current_stage="INGEST",
            stages=stages,
            docs=docs,
            errors=[],
        )
        self.write_job(job)
        return job

    def read_job(self, job_id: str) -> JobState:
        data = read_json(self._path(job_id))
        return JobState(**data)

    def write_job(self, job: JobState) -> None:
        atomic_write_json(self._path(job.job_id), job.model_dump())

    def stage_running(self, job: JobState, stage: str) -> None:
        job.status = "running"
        job.current_stage = stage
        st = job.stages[stage]
        st.status = "running"
        st.started_at = st.started_at or iso_now()
        self.write_job(job)

    def stage_done(self, job: JobState, stage: str) -> None:
        st = job.stages[stage]
        st.status = "done"
        st.ended_at = iso_now()
        self.write_job(job)

    def fail_job(self, job: JobState, stage: str, reason: str) -> None:
        job.status = "failed"
        job.current_stage = stage
        st = job.stages.get(stage)
        if st:
            st.status = "failed"
            st.ended_at = iso_now()
        job.errors.append({"stage": stage, "reason": reason, "ts": iso_now()})
        self.write_job(job)
