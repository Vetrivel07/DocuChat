from __future__ import annotations

from typing import Any, List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["query"])


class QueryIn(BaseModel):
    collection_id: str
    question: str


@router.post("/query")
def query(inp: QueryIn):
    return {
        "answer": "Stub: Stage 9 will implement hybrid retrieval + grounded generation.",
        "sources": [],  # list[ {source_name/doc_id/page_num/score...} ]
    }
