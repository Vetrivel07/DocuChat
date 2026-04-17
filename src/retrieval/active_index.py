from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import Settings
from src.ingestion.registry import load_manifest
from src.retrieval.types import ActiveIndex


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_embedder_id_from_manifest(manifest: Dict[str, Any]) -> Optional[str]:
    """
    Rule:
    - Prefer latest embedding entry in manifest (by created_at) across docs.
    - Fallback to first embeddings entry if timestamps missing.
    """
    best_id = None
    best_ts = ""
    for d in (manifest.get("docs") or []):
        for e in (d.get("embeddings") or []):
            eid = e.get("embedder_id")
            ts = str(e.get("created_at") or "")
            if eid and ts >= best_ts:
                best_ts = ts
                best_id = eid
    if best_id:
        return best_id

    # fallback: first doc first embedding
    docs = manifest.get("docs") or []
    if docs:
        emb = (docs[0].get("embeddings") or [])
        if emb and emb[0].get("embedder_id"):
            return emb[0]["embedder_id"]
    return None


def resolve_active_index(s: Settings, collection_id: str) -> ActiveIndex:
    """
    Deterministic chooser:
    1) Read collection manifest -> choose embedder_id (latest created_at).
    2) Read index_meta.json for that embedder (uses embedder_dir from index_meta).
    3) Validate required index artifacts exist.
    """
    # ---- manifest (source of truth for chosen embedder_id) ----
    manifest = load_manifest(s.collections_dir, collection_id)
    embedder_id = _pick_embedder_id_from_manifest(manifest)
    if not embedder_id:
        raise FileNotFoundError(f"No embedder_id found in manifest for collection_id={collection_id}")

    # ---- locate index_meta.json by scanning index folders ----
    index_base = s.indexes_dir / collection_id
    if not index_base.exists():
        raise FileNotFoundError(f"Missing indexes dir: {index_base}")

    chosen_index_meta_path: Optional[Path] = None
    for d in index_base.iterdir():
        if not d.is_dir():
            continue
        p = d / "index_meta.json"
        if not p.exists():
            continue
        try:
            meta = _read_json(p)
            if meta.get("embedder_id") == embedder_id:
                chosen_index_meta_path = p
                break
        except Exception:
            continue

    if not chosen_index_meta_path:
        raise FileNotFoundError(
            f"index_meta.json not found for embedder_id={embedder_id} in {index_base}"
        )

    index_meta = _read_json(chosen_index_meta_path)
    embedder_dir = str(index_meta.get("embedder_dir") or "").strip()
    if not embedder_dir:
        raise RuntimeError("index_meta.json missing embedder_dir")

    index_dir = s.indexes_dir / collection_id / embedder_dir
    faiss_path = index_dir / "vectors.faiss"
    meta_jsonl_path = index_dir / "metadata.jsonl"
    index_meta_path = index_dir / "index_meta.json"

    # ---- validate artifacts ----
    if not faiss_path.exists():
        raise FileNotFoundError(f"Missing FAISS index: {faiss_path}")
    if not meta_jsonl_path.exists():
        raise FileNotFoundError(f"Missing metadata.jsonl: {meta_jsonl_path}")
    if not index_meta_path.exists():
        raise FileNotFoundError(f"Missing index_meta.json: {index_meta_path}")

    dim = int(index_meta.get("dim") or 0)
    if dim <= 0:
        raise RuntimeError("index_meta.json invalid dim")

    metric = str(index_meta.get("metric") or "l2")
    normalized = bool(index_meta.get("normalized") or False)

    return ActiveIndex(
        collection_id=collection_id,
        embedder_id=embedder_id,
        embedder_dir=embedder_dir,
        dim=dim,
        metric=metric,
        normalized=normalized,
        index_dir=index_dir,
        faiss_path=faiss_path,
        meta_jsonl_path=meta_jsonl_path,
        index_meta_path=index_meta_path,
    )