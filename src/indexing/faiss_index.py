# src/indexing/faiss_index.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4

import numpy as np
import faiss

from src.utils.atomic_io import atomic_write_json, atomic_write_jsonl, iter_jsonl, atomic_replace_dir


@dataclass(frozen=True)
class IndexResult:
    vector_count: int
    doc_ids:      List[str]
    dim:          int
    embedder_id:  str
    metric:       str
    normalized:   bool


def _safe_dir_name(embedder_dir: str) -> str:
    out = []
    for ch in embedder_dir:
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")


def _row_sort_key(r: Dict[str, Any]) -> Tuple[int, int, int, str]:
    return (
        int(r.get("page_num", 0)),
        int(r.get("start_char", 0)),
        int(r.get("end_char", 0)),
        str(r.get("chunk_id", "")),
    )


def build_faiss_for_collection(
    *,
    collection_id: str,
    vectors_dir:   Path,
    indexes_dir:   Path,
    embedder_id:   str,
    embedder_dir:  str,
    dim:           int,
    metric:        str,
    normalized:    bool,
) -> IndexResult:
    src_dir = vectors_dir / collection_id / embedder_dir
    if not src_dir.exists():
        return IndexResult(0, [], dim, embedder_id, metric, normalized)

    doc_files = sorted(
        [p for p in src_dir.glob("*.jsonl") if p.is_file()],
        key=lambda p: p.stem,
    )

    metas:        List[Dict[str, Any]] = []
    vecs:         List[np.ndarray]     = []
    used_doc_ids: List[str]            = []

    for p in doc_files:
        doc_id = p.stem
        rows:  List[Dict[str, Any]] = []

        for r in iter_jsonl(p):
            if r.get("embedder_id") != embedder_id:
                continue
            v = r.get("vector")
            if not isinstance(v, list) or len(v) != dim:
                continue
            rows.append(r)

        rows.sort(key=_row_sort_key)
        if not rows:
            continue

        used_doc_ids.append(doc_id)

        for r in rows:
            vecs.append(np.asarray(r["vector"], dtype=np.float32))
            metas.append(
                {
                    "chunk_id":        r["chunk_id"],
                    "doc_id":          r["doc_id"],
                    "page_num":        int(r.get("page_num", 0)),
                    "start_char":      int(r.get("start_char", 0)),
                    "end_char":        int(r.get("end_char", 0)),
                    # ── new fields (backwards-compatible defaults) ──────────
                    "section_path":    r.get("section_path", []),
                    "section_context": r.get("section_context", ""),
                    "chunk_type":      r.get("chunk_type", "semantic_text"),
                    "token_count":     int(r.get("token_count", 0)),
                    "index_this":      bool(r.get("index_this", True)),
                }
            )

    if not vecs:
        return IndexResult(0, [], dim, embedder_id, metric, normalized)

    X = np.stack(vecs, axis=0)

    if metric == "ip":
        index = faiss.IndexFlatIP(dim)
    elif metric == "l2":
        index = faiss.IndexFlatL2(dim)
    else:
        raise ValueError("INDEX_METRIC_INVALID")

    index.add(X)

    final_dir = indexes_dir / collection_id / embedder_dir
    tmp_dir   = final_dir.parent / f"tmp_{uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(tmp_dir / "vectors.faiss"))
    atomic_write_jsonl(tmp_dir / "metadata.jsonl", metas)
    atomic_write_json(
        tmp_dir / "index_meta.json",
        {
            "collection_id": collection_id,
            "embedder_id":   embedder_id,
            "embedder_dir":  embedder_dir,
            "dim":           dim,
            "metric":        metric,
            "normalized":    bool(normalized),
            "vector_count":  int(index.ntotal),
            "doc_ids":       used_doc_ids,
        },
    )

    atomic_replace_dir(tmp_dir, final_dir)

    return IndexResult(int(index.ntotal), used_doc_ids, dim, embedder_id, metric, normalized)