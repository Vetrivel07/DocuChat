# src/models.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


JobStatus = Literal["pending", "running", "done", "failed"]
StageStatus = Literal["pending", "running", "done", "failed"]
DocStatus = Literal["pending", "running", "done", "failed"]


def iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class StageState(BaseModel):
    status: StageStatus = "pending"
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class DocCounts(BaseModel):
    pages: int = 0
    chunks: int = 0
    vectors: int = 0


class DocState(BaseModel):
    doc_id: Optional[str] = None
    file_name: str
    status: DocStatus = "pending"
    fail_reason: Optional[str] = None
    counts: DocCounts = Field(default_factory=DocCounts)


class JobState(BaseModel):
    job_id: str
    collection_id: str
    mode: Literal["new", "append"] = "new"
    created_at: str

    status: JobStatus = "pending"
    current_stage: str = "INGEST"

    stages: Dict[str, StageState]
    docs: List[DocState] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
