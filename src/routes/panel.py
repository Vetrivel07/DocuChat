from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter

from src.config import get_settings
from src.ingestion.registry import load_manifest
from src.utils.atomic_io import read_json, iter_jsonl
from src.utils.fs import safe_name

router = APIRouter(tags=["panel"])


def _file_size_bytes(p: Path) -> int:
    try:
        return int(p.stat().st_size)
    except Exception:
        return 0


def _dir_size_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += int(p.stat().st_size)
            except Exception:
                pass
    return total


def _latest_job_for_collection(jobs_dir: Path, collection_id: str) -> Optional[Dict[str, Any]]:
    best = None
    best_created = ""
    if not jobs_dir.exists():
        return None

    for p in jobs_dir.glob("*.json"):
        if not p.is_file():
            continue
        try:
            obj = read_json(p)
            if obj.get("collection_id") != collection_id:
                continue
            created = str(obj.get("created_at") or "")
            if created >= best_created:
                best_created = created
                best = obj
        except Exception:
            continue

    return best


def _latest_embed_bench_for_collection(log_path: Path, collection_id: str, embedder_id: str) -> Optional[Dict[str, Any]]:
    if not log_path.exists():
        return None

    best = None
    for row in iter_jsonl(log_path):
        if row.get("collection_id") == collection_id and row.get("embedder_id") == embedder_id:
            best = row
    return best


def _read_graph_stats(graphs_dir: Path, collection_id: str) -> Optional[Dict[str, Any]]:
    p = graphs_dir / collection_id / "graph_stats.json"
    if not p.exists():
        return None
    try:
        return read_json(p)
    except Exception:
        return None


def _latest_eval_summary_for_mode(eval_runs_dir: Path, mode: str) -> Optional[Dict[str, Any]]:
    p = eval_runs_dir / mode / "summary.json"
    if not p.exists():
        return None
    try:
        return read_json(p)
    except Exception:
        return None


@router.get("/collections/{collection_id}/panel")
def collection_panel(collection_id: str):
    s = get_settings()

    manifest_path = s.collections_dir / f"{collection_id}.json"
    if not manifest_path.exists():
        return {
            "state": "no_collection",
            "collection_id": collection_id,
            "processing": None,
            "embedding": None,
            "index": None,
            "graph": None,
            "hybrid": None,
            "health": None,
            "show_eval_link": False,
        }

    manifest = load_manifest(s.collections_dir, collection_id)
    docs = manifest.get("docs", [])
    total_docs = len(docs)

    embedder_id = None
    if docs:
        emb_list = docs[0].get("embeddings") or []
        if emb_list:
            embedder_id = emb_list[0].get("embedder_id")

    embedder_dir = safe_name(embedder_id) if embedder_id else None
    retrieval_mode = str(manifest.get("retrieval_mode", "vector")).strip().lower()

    job = _latest_job_for_collection(s.jobs_dir, collection_id)

    processing = {
        "current_stage": None,
        "job_status": None,
        "retrieval_mode": retrieval_mode,
        "per_doc": [],
        "total_docs": total_docs,
    }

    if job:
        processing["current_stage"] = job.get("current_stage")
        processing["job_status"] = job.get("status")
        processing["per_doc"] = job.get("docs", [])

    embedding = None
    if embedder_id:
        bench = _latest_embed_bench_for_collection(s.logs_dir / "embed_bench.jsonl", collection_id, embedder_id)
        if bench:
            chunks_total = int(bench.get("chunks_total") or 0)
            chunks_skipped = int(bench.get("chunks_skipped") or 0)
            chunks_embedded = int(bench.get("chunks_embedded") or 0)

            avoidance_rate = (chunks_skipped / chunks_total * 100.0) if chunks_total > 0 else 0.0

            embed_s = float(bench.get("embed_s") or 0.0)
            avg_per_chunk = (embed_s / chunks_embedded) if chunks_embedded > 0 else 0.0
            embedding_time_saved_s = avg_per_chunk * chunks_skipped

            embedding = {
                "embedder_id": embedder_id,
                "embedding_avoidance_rate_pct": round(avoidance_rate, 2),
                "sqlite_hits": bench.get("sqlite_hits"),
                "chunks_total": chunks_total,
                "chunks_embedded": chunks_embedded,
                "chunks_skipped": chunks_skipped,
                "chunks_to_embed": bench.get("chunks_to_embed"),
                "rerun_wall_time_s": bench.get("wall_s"),
                "skip_check_s": bench.get("skip_check_s"),
                "embed_s": embed_s,
                "write_s": bench.get("write_s"),
                "embedding_time_saved_s_est": round(embedding_time_saved_s, 4),
                "cache_db_path": bench.get("cache_db_path"),
            }

    index_stats = None
    if embedder_dir:
        index_meta_path = s.indexes_dir / collection_id / embedder_dir / "index_meta.json"
        if index_meta_path.exists():
            index_meta = read_json(index_meta_path)
            index_stats = {
                "total_vectors": index_meta.get("vector_count"),
                "vector_dimension": index_meta.get("dim"),
                "metric_type": index_meta.get("metric"),
                "normalized": index_meta.get("normalized"),
                "indexed_docs_count": len(index_meta.get("doc_ids") or []),
                "doc_ids": index_meta.get("doc_ids") or [],
            }

    graph_stats = None
    if retrieval_mode == "hybrid":
        g = _read_graph_stats(s.graphs_dir, collection_id)
        if g:
            graph_stats = {
                "doc_nodes": g.get("doc_nodes", 0),
                "section_nodes": g.get("section_nodes", 0),
                "chunk_nodes": g.get("chunk_nodes", 0),
                "entity_nodes": g.get("entity_nodes", 0),
                "has_chunk_edges": g.get("has_chunk_edges", 0),
                "has_section_edges": g.get("has_section_edges", 0),
                "next_edges": g.get("next_edges", 0),
                "mentions_edges": g.get("mentions_edges", 0),
                "relates_to_edges": g.get("relates_to_edges", 0),
            }

    hybrid_stats = None
    if retrieval_mode == "hybrid":
        hybrid_summary = _latest_eval_summary_for_mode(s.storage_root / "eval" / "runs", "hybrid")
        if hybrid_summary:
            metrics = {m.get("name"): m for m in (hybrid_summary.get("metrics") or [])}
            hybrid_stats = {
                "graph_contribution_rate": (metrics.get("graph_contribution_rate") or {}).get("value"),
                "multihop_recall_at_10": (metrics.get("multihop_recall@10") or {}).get("value"),
                "citation_precision": (metrics.get("citation_precision") or {}).get("value"),
                "unsupported_claim_rate": (metrics.get("unsupported_claim_rate") or {}).get("value"),
                "matched_queries": hybrid_summary.get("matched_queries"),
            }

    health = {
        "cache_db_size_bytes": 0,
        "vector_file_size_bytes": 0,
        "last_job_runtime_s": None,
        "collection_storage_bytes": 0,
    }

    health["collection_storage_bytes"] = (
        _dir_size_bytes(s.raw_dir / collection_id)
        + _dir_size_bytes(s.processed_dir / collection_id)
        + _dir_size_bytes(s.chunks_dir / collection_id)
        + _dir_size_bytes(s.vectors_dir / collection_id)
        + _dir_size_bytes(s.indexes_dir / collection_id)
        + _dir_size_bytes(s.graphs_dir / collection_id)
    )

    if embedder_dir and docs:
        first_doc_id = docs[0].get("doc_id")
        if first_doc_id:
            vec_jsonl = s.vectors_dir / collection_id / embedder_dir / f"{first_doc_id}.jsonl"
            health["vector_file_size_bytes"] = _file_size_bytes(vec_jsonl)

        cache_db = s.vectors_dir / collection_id / embedder_dir / "embed_cache.sqlite"
        health["cache_db_size_bytes"] = _file_size_bytes(cache_db)

    if job:
        stages = job.get("stages") or {}
        ingest = stages.get("INGEST") or {}
        done_stage = stages.get("DONE") or {}
        index_stage = stages.get("INDEX") or {}
        graph_stage = stages.get("GRAPH") or {}

        t0 = ingest.get("started_at")
        t1 = done_stage.get("ended_at") or graph_stage.get("ended_at") or index_stage.get("ended_at") or job.get("created_at")

        health["last_job_runtime_s"] = None
        health["last_job_started_at"] = t0
        health["last_job_ended_at"] = t1

    return {
        "state": "ok",
        "collection_id": collection_id,
        "retrieval_mode": retrieval_mode,
        "processing": processing,
        "embedding": embedding,
        "index": index_stats,
        "graph": graph_stats,
        "hybrid": hybrid_stats,
        "health": health,
        "show_eval_link": True,
    }