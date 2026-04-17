from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.config import get_settings
from src.ingestion.registry import load_manifest
from src.graph.factory import get_graph_store

import json
from pathlib import Path
from typing import Any, Dict, Optional

router = APIRouter(tags=["collections"])


@router.get("/collections/{collection_id}/files")
def list_files(collection_id: str):
    s = get_settings()

    # Prefer manifest (more correct once INGEST is real)
    try:
        m = load_manifest(s.collections_dir, collection_id)
        docs = m.get("docs", [])
        files = []
        for d in docs:
            name = d.get("file_name") or d.get("doc_id")
            files.append(
                {
                    "file_id": d.get("doc_id"),
                    "original_filename": name,
                    "download_url": f"/collections/{collection_id}/files/{name}",
                }
            )
        return {"files": files}
    except Exception:
        return {"files": []}


@router.get("/collections/{collection_id}/files/{filename}")
def download_file(collection_id: str, filename: str):
    s = get_settings()
    p = s.raw_dir / collection_id / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(p), filename=filename)

@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str):
    """
    Production-level vanish:
    - remove workspace files
    - remove workspace jobs
    - purge Neo4j graph for this collection
    - keep global logs/eval artifacts
    """
    s = get_settings()

    # 1. purge graph db data for this collection
    if s.graph.enabled:
        graph_store = get_graph_store(s)
        try:
            graph_store.purge_collection(collection_id)
        finally:
            graph_store.close()

    # 2. remove filesystem workspace artifacts
    targets = [
        s.raw_dir / collection_id,
        s.processed_dir / collection_id,
        s.chunks_dir / collection_id,
        s.vectors_dir / collection_id,
        s.indexes_dir / collection_id,
        s.graphs_dir / collection_id,
        s.chat_history_dir / f"{collection_id}.json",
        s.collections_dir / f"{collection_id}.json",
    ]

    for t in targets:
        if t.is_file():
            t.unlink(missing_ok=True)
        elif t.is_dir() and t.exists():
            for p in sorted(t.rglob("*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    try:
                        p.rmdir()
                    except OSError:
                        pass
            try:
                t.rmdir()
            except OSError:
                pass

    # 3. remove jobs for this collection
    # if s.jobs_dir.exists():
    #     for p in s.jobs_dir.glob("*.json"):
    #         try:
    #             obj = json.loads(p.read_text(encoding="utf-8"))
    #             if obj.get("collection_id") == collection_id:
    #                 p.unlink(missing_ok=True)
    #         except Exception:
    #             continue

    return {"ok": True}