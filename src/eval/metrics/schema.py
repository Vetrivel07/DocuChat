# src/eval/metrics/schema.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GoldRow:
    query: str
    answerable: bool
    expected_answer: str = ""
    gold_chunk_ids: List[str] = field(default_factory=list)
    source_ids: List[str] = field(default_factory=list)   # NEW: e.g. ["source_1", "source_2"]
    multi_hop: bool = False
    notes: str = ""


@dataclass(frozen=True)
class RetrievedItem:
    chunk_id: str
    doc_id: str
    score: float


@dataclass(frozen=True)
class FinalContextItem:
    source_idx: int
    source_name: str
    chunk_id: str
    doc_id: str
    page_num: Optional[int]
    start_char: Optional[int]
    end_char: Optional[int]
    score: float
    text: str


@dataclass(frozen=True)
class QueryLogRow:
    run_id: str
    retrieval_mode: str
    collection_id: str
    embedder_id: str
    embedder_dir: str
    top_k: int
    max_context_chunks: int
    original_query: str
    rewritten_query: str
    retrieved_before_rerank: List[Dict[str, Any]]
    reranked: Optional[List[Dict[str, Any]]]
    final_context: List[Dict[str, Any]]
    answer_text: str
    citations: List[str]
    is_answerable: Optional[bool] = None
    gold_chunk_ids: Optional[List[str]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricSummary:
    name: str
    value: Optional[float]
    count: int
    details: Dict[str, Any] = field(default_factory=dict)