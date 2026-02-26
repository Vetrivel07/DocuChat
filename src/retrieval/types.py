# src/retrieval/types.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ActiveIndex:
    collection_id: str
    embedder_id: str
    embedder_dir: str
    dim: int
    metric: str
    normalized: bool

    index_dir: Path
    faiss_path: Path
    meta_jsonl_path: Path
    index_meta_path: Path