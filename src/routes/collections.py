from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.config import get_settings
from src.ingestion.registry import load_manifest

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
    Stage-1 vanish: filesystem cleanup only.
    Later stages will also remove: processed/chunks/indexes/neo4j/chat_history/manifest.
    """
    s = get_settings()

    targets = [
        s.raw_dir / collection_id,
        s.processed_dir / collection_id,
        s.chunks_dir / collection_id,
        s.indexes_dir / collection_id,
        s.chat_history_dir / f"{collection_id}.json",
        s.collections_dir / f"{collection_id}.json",
    ]

    # delete files/dirs best-effort
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

    return {"ok": True}

@router.get("/collections/{collection_id}/panel")
def collection_panel(collection_id: str):
    s = get_settings()

    # 1) manifest
    try:
        m = load_manifest(s.collections_dir, collection_id)
    except Exception:
        return {"state": "no_collection"}

    docs = m.get("docs", [])
    total_docs = len(docs)

    # pick embedder info (first doc, first embedding) if exists
    embedder_id = None
    embedder_dir = None
    try:
        if docs and docs[0].get("embeddings"):
            embedder_id = docs[0]["embeddings"][0].get("embedder_id")
            # folder name is stored in index_meta usually; but we can derive from embedder_id:
            # your pipeline uses: local_BAAI_bge-m3_d1024_norm0_cleanv1_chunkv1
            # safest minimal approach: scan indexes dir if it exists
    except Exception:
        pass

    # 2) latest job for this collection (scan jobs dir, choose max created_at)
    latest_job: Optional[Dict[str, Any]] = None
    for p in s.jobs_dir.glob("*.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            if j.get("collection_id") != collection_id:
                continue
            if latest_job is None or (j.get("created_at", "") > latest_job.get("created_at", "")):
                latest_job = j
        except Exception:
            continue

    current_stage = (latest_job or {}).get("current_stage")
    job_status = (latest_job or {}).get("status")

    # 3) find embedder_dir (don’t guess; discover from index folder if present)
    index_base = s.indexes_dir / collection_id
    if index_base.exists():
        # choose first embedder folder (or match embedder_id if you later want)
        for d in index_base.iterdir():
            if d.is_dir():
                embedder_dir = d.name
                break

    # 4) index stats
    index_meta = {}
    if embedder_dir:
        p_meta = s.indexes_dir / collection_id / embedder_dir / "index_meta.json"
        if p_meta.exists():
            try:
                index_meta = json.loads(p_meta.read_text(encoding="utf-8"))
            except Exception:
                index_meta = {}

    # 5) embed bench: latest line for this collection (+ embedder if known)
    bench: Optional[Dict[str, Any]] = None
    log_path = s.logs_dir / "embed_bench.jsonl"
    if log_path.exists():
        try:
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("collection_id") != collection_id:
                    continue
                if embedder_id and obj.get("embedder_id") != embedder_id:
                    continue
                bench = obj  # keep last match
        except Exception:
            bench = None

    # compute embedding metrics (only if bench exists)
    embedding = {}
    if bench:
        chunks_total = int(bench.get("chunks_total") or 0)
        chunks_skipped = int(bench.get("chunks_skipped") or 0)
        chunks_embedded = int(bench.get("chunks_embedded") or 0)
        sqlite_hits = bench.get("sqlite_hits")

        avoidance = 0.0
        if chunks_total > 0:
            avoidance = (chunks_skipped / chunks_total) * 100.0

        # minimal estimate: time saved ≈ avg embed time per embedded chunk * skipped
        embed_s = float(bench.get("embed_s") or 0.0)
        per_chunk = (embed_s / max(chunks_embedded, 1))
        time_saved_est = per_chunk * chunks_skipped

        embedding = {
            "embedding_avoidance_rate_pct": round(avoidance, 2),
            "sqlite_hits": sqlite_hits,
            "chunks_embedded": chunks_embedded,
            "chunks_skipped": chunks_skipped,
            "rerun_wall_time_s": round(float(bench.get("wall_s") or 0.0), 3),
            "embedding_time_saved_s_est": round(time_saved_est, 3),
        }
    else:
        embedding = {
            "embedding_avoidance_rate_pct": None,
            "sqlite_hits": None,
            "chunks_embedded": None,
            "chunks_skipped": None,
            "rerun_wall_time_s": None,
            "embedding_time_saved_s_est": None,
        }

    # 6) system health sizes
    def size_bytes(path: Path) -> int:
        try:
            return path.stat().st_size
        except Exception:
            return 0

    cache_db_size = 0
    vector_file_size = 0
    if embedder_dir:
        cache_path = s.vectors_dir / collection_id / embedder_dir / "embed_cache.sqlite"
        cache_db_size = size_bytes(cache_path)

        # sum all vector jsonl files under that embedder dir
        vec_dir = s.vectors_dir / collection_id / embedder_dir
        if vec_dir.exists():
            for fp in vec_dir.glob("*.jsonl"):
                vector_file_size += size_bytes(fp)

    # total collection storage bytes (raw+processed+chunks+vectors+indexes)
    total_storage = 0
    for base in [s.raw_dir, s.processed_dir, s.chunks_dir, s.vectors_dir, s.indexes_dir]:
        root = base / collection_id
        if not root.exists():
            continue
        for fp in root.rglob("*"):
            if fp.is_file():
                total_storage += size_bytes(fp)

    return {
        "state": "ok",
        "processing": {
            "current_stage": current_stage,
            "job_status": job_status,
            "total_docs": total_docs,
        },
        "embedding": embedding,
        "index": {
            "total_vectors": index_meta.get("vector_count"),
            "vector_dimension": index_meta.get("dim"),
            "metric_type": index_meta.get("metric"),
            "indexed_docs_count": len(index_meta.get("doc_ids", []) or []),
        },
        "health": {
            "cache_db_size_bytes": cache_db_size,
            "vector_file_size_bytes": vector_file_size,
            "collection_storage_bytes": total_storage,
        },
    }