# src/ingestion/registry.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from src.utils.atomic_io import atomic_write_json, read_json


def iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _manifest_path(collections_dir: Path, collection_id: str) -> Path:
    return collections_dir / f"{collection_id}.json"


def load_manifest(collections_dir: Path, collection_id: str) -> Dict[str, Any]:
    p = _manifest_path(collections_dir, collection_id)
    if not p.exists():
        return {"collection_id": collection_id, "created_at": iso_now(), "docs": []}
    return read_json(p)


def upsert_doc(
    manifest: Dict[str, Any],
    *,
    doc_id: str,
    sha256: str,
    file_name: str,
    file_type: str,
    file_size: int,
    raw_path: str,
    added_at: Optional[str] = None,
    status: str = "ingested",
) -> None:
    docs: List[Dict[str, Any]] = manifest.setdefault("docs", [])
    added_at = added_at or iso_now()

    # canonical: doc_id == sha256(file_bytes)
    new_doc = {
        "doc_id": doc_id,
        "sha256": sha256,
        "file_name": file_name,
        "file_type": file_type,
        "file_size": file_size,
        "raw_path": raw_path,
        "added_at": added_at,
        "status": status,
    }

    for i, d in enumerate(docs):
        if d.get("doc_id") == doc_id:
            docs[i] = {**d, **new_doc}
            return

    docs.append(new_doc)


def save_manifest(collections_dir: Path, collection_id: str, manifest: Dict[str, Any]) -> None:
    p = _manifest_path(collections_dir, collection_id)
    atomic_write_json(p, manifest)
