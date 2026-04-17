# src\eval\logger.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EvalLogger:
    """
    Append-only JSONL logger for evaluation.

    Runtime logs only. Metric computation stays outside runtime (scripts/).
    """
    log_path: Path

    def log(self, row: Dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # append safely (fsync)
        line = json.dumps(row, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())


def build_query_log_row(
    *,
    run_id: str,
    retrieval_mode: str,          # "vector_v2" for now
    collection_id: str,
    embedder_id: str,
    embedder_dir: str,
    top_k: int,
    max_context_chunks: int,
    original_query: str,
    rewritten_query: str,
    retrieved_before_rerank: list[dict],
    reranked: Optional[list[dict]],
    final_context: list[dict],
    answer_text: str,
    citations: Optional[list[str]] = None,
    is_answerable: Optional[bool] = None,
    gold_chunk_ids: Optional[list[str]] = None,
    extra: Optional[dict] = None,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "retrieval_mode": retrieval_mode,
        "collection_id": collection_id,
        "embedder_id": embedder_id,
        "embedder_dir": embedder_dir,
        "top_k": top_k,
        "max_context_chunks": max_context_chunks,
        "original_query": original_query,
        "rewritten_query": rewritten_query,
        "retrieved_before_rerank": retrieved_before_rerank,
        "reranked": reranked,
        "final_context": final_context,
        "answer_text": answer_text,
        "citations": citations,
        "is_answerable": is_answerable,
        "gold_chunk_ids": gold_chunk_ids,
        "extra": extra or {},
    }