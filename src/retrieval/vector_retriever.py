# src/retrieval/vector_retriever.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import json
import numpy as np
import faiss  # type: ignore

from src.config import Settings
from src.retrieval.types import ActiveIndex
from src.retrieval.query_embedder import QueryEmbedder
from src.retrieval.embedder_id import parse_embedder_id


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id:        str
    doc_id:          str
    page_num:        Optional[int]
    start_char:      Optional[int]
    end_char:        Optional[int]
    score:           float
    text:            str
    # ── metadata fields (default-safe for old chunks) ─────────────────────────
    section_path:    List[str] = field(default_factory=list)
    section_context: str       = ""
    chunk_type:      str       = "semantic_text"
    token_count:     int       = 0
    index_this:      bool      = True


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _load_chunk_map(chunks_jsonl: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load chunk JSONL into: chunk_id → {text, section_path, section_context,
                                        chunk_type, token_count, index_this}
    Default-safe for old chunks missing new fields.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for row in _iter_jsonl(chunks_jsonl):
        cid = row.get("chunk_id")
        if not cid:
            continue
        out[str(cid)] = {
            "text":            str(row.get("text_clean") or row.get("text_original") or ""),
            "section_path":    row.get("section_path") or [],
            "section_context": str(row.get("section_context") or ""),
            "chunk_type":      str(row.get("chunk_type") or "semantic_text"),
            "token_count":     int(row.get("token_count") or 0),
            "index_this":      bool(row.get("index_this", True)),
        }
    return out


@dataclass
class VectorRetriever:
    s: Settings
    _faiss_cache: Dict[str, Any] = field(default_factory=dict)

    def _load_faiss(self, faiss_path: Path):
        key = str(faiss_path)
        idx = self._faiss_cache.get(key)
        if idx is None:
            idx = faiss.read_index(str(faiss_path))
            self._faiss_cache[key] = idx
        return idx

    def search(
        self,
        *,
        active:     ActiveIndex,
        query_text: str,
        top_k:      int,
    ) -> List[RetrievedChunk]:
        parsed = parse_embedder_id(active.embedder_id)
        qe     = QueryEmbedder(parsed)
        qvec   = qe.embed(query_text)
        return self.retrieve(active=active, query_vec=qvec, top_k=top_k)

    def retrieve(
        self,
        *,
        active:     ActiveIndex,
        query_vec:  np.ndarray,
        top_k:      int,
    ) -> List[RetrievedChunk]:
        if query_vec.dtype != np.float32:
            query_vec = query_vec.astype(np.float32)

        index   = self._load_faiss(active.faiss_path)
        D, I    = index.search(query_vec, int(top_k))
        ids     = I[0].tolist()
        dists   = D[0].tolist()

        meta_rows: List[Dict[str, Any]] = list(_iter_jsonl(active.meta_jsonl_path))

        need_doc_ids: set[str]            = set()
        picked_meta:  List[Dict[str, Any]] = []

        for idx in ids:
            if idx < 0 or idx >= len(meta_rows):
                picked_meta.append({})
                continue
            row = meta_rows[idx]
            picked_meta.append(row)
            did = row.get("doc_id")
            if did:
                need_doc_ids.add(str(did))

        doc_chunk_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for doc_id in need_doc_ids:
            p = self.s.chunks_dir / active.collection_id / f"{doc_id}.jsonl"
            doc_chunk_maps[doc_id] = _load_chunk_map(p) if p.exists() else {}

        out: List[RetrievedChunk] = []
        for pos, row in enumerate(picked_meta):
            if not row:
                continue

            chunk_id = str(row.get("chunk_id") or "")
            doc_id   = str(row.get("doc_id")   or "")
            if not chunk_id or not doc_id:
                continue

            page_num   = row.get("page_num")
            start_char = row.get("start_char")
            end_char   = row.get("end_char")

            # Prefer chunk JSONL (authoritative) over metadata.jsonl
            chunk_data       = doc_chunk_maps.get(doc_id, {}).get(chunk_id, {})
            text             = chunk_data.get("text", "")
            section_path     = chunk_data.get("section_path")     or row.get("section_path", [])
            section_context  = chunk_data.get("section_context")  or str(row.get("section_context") or "")
            chunk_type       = chunk_data.get("chunk_type")        or str(row.get("chunk_type") or "semantic_text")
            token_count      = chunk_data.get("token_count")       or int(row.get("token_count") or 0)
            index_this       = chunk_data.get("index_this",  True)

            out.append(
                RetrievedChunk(
                    chunk_id        = chunk_id,
                    doc_id          = doc_id,
                    page_num        = int(page_num)   if page_num   is not None else None,
                    start_char      = int(start_char) if start_char is not None else None,
                    end_char        = int(end_char)   if end_char   is not None else None,
                    score           = float(dists[pos]),
                    text            = text,
                    section_path    = section_path    if isinstance(section_path, list) else [],
                    section_context = section_context,
                    chunk_type      = chunk_type,
                    token_count     = token_count,
                    index_this      = index_this,
                )
            )
        return out