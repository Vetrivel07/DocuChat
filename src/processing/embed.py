# src/processing/embed.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple
import hashlib
import json
import math
import os
import time

import numpy as np

from src.embedding.base import Embedder
from src.utils.atomic_io import iter_jsonl, atomic_replace_jsonl
from src.models import iso_now
from src.utils.embed_bench import EmbedBench

from src.utils.embed_cache import (
    CacheDb,
    lookup_existing_vectors,       # checks vector_store
    fetch_vectors,                 # loads vectors from vector_store
    upsert_vectors,                # inserts into vector_store (INSERT OR IGNORE)
    lookup_existing_doc_chunks,    # checks doc_vectors for this doc/embedder
    insert_doc_vectors,            # inserts into doc_vectors (INSERT OR IGNORE)
)


@dataclass
class EmbedBatching:
    max_batch_size: int = 64
    max_batch_chars: int = 80_000  # char budget


# ----------------------------
# Helpers
# ----------------------------
def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _embed_signature(embedder_id: str) -> str:
    # embedder_id already includes model + dim + norm + versions
    return _sha256_hex(embedder_id)


def _cache_key(*, embedder_id: str, text_clean: str) -> str:
    """
    Content-based key (NO doc_id/chunk_id):
      cache_key = sha256( sha256(embedder_id) + "|" + sha256(text_clean) )
    """
    sig = _embed_signature(embedder_id)
    fp = _sha256_hex(text_clean)  # use exact stored text_clean (no extra normalization)
    return _sha256_hex(f"{sig}|{fp}")


def _make_batches(items: List[Dict[str, Any]], cfg: EmbedBatching) -> Iterable[List[Dict[str, Any]]]:
    batch: List[Dict[str, Any]] = []
    chars = 0

    for it in items:
        t = it.get("text_clean") or ""
        tlen = len(t)

        if batch and (len(batch) >= cfg.max_batch_size or (chars + tlen) > cfg.max_batch_chars):
            yield batch
            batch = []
            chars = 0

        batch.append(it)
        chars += tlen

    if batch:
        yield batch


def _append_jsonl_durable(path: Path, rows: List[Dict[str, Any]]) -> None:
    """
    Append rows to JSONL with flush+fsync to reduce crash window.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _validate_vec(v: List[float], dim: int) -> tuple[bool, int]:
    """
    Returns (ok, nan_inf_count_for_this_vec).
    """
    if len(v) != dim:
        return False, 0
    bad = 0
    for x in v:
        if x is None or not isinstance(x, (int, float)) or math.isnan(x) or math.isinf(x):
            bad += 1
    return bad == 0, bad


# ============================================================
# v1 (KEEP AS-IS): JSONL scan by chunk_id + merge/replace
# ============================================================
def _existing_chunk_ids(vectors_path: Path, *, bench: EmbedBench | None = None) -> Set[str]:
    if not vectors_path.exists():
        return set()

    # IO proof for v1
    if bench:
        bench.add("vectors_jsonl_bytes_read", vectors_path.stat().st_size)

    out: Set[str] = set()
    for row in iter_jsonl(vectors_path):
        cid = row.get("chunk_id")
        if cid:
            out.add(cid)
    return out


def _iter_missing_chunks_v1(
    chunks_path: Path,
    existing: Set[str],
    *,
    bench: EmbedBench | None = None,
) -> List[Dict[str, Any]]:
    missing: List[Dict[str, Any]] = []
    total = 0
    skipped = 0
    for ch in iter_jsonl(chunks_path):
        cid = ch.get("chunk_id")
        if not cid:
            continue
        text = (ch.get("text_clean") or "").strip()
        if not text:
            skipped += 1
            continue
        total += 1
        if cid in existing:
            skipped += 1
            continue

        missing.append(ch)

    if bench:
        bench.set("chunks_total", total)
        bench.set("chunks_skipped", skipped)
        bench.set("chunks_to_embed", len(missing))
    return missing


def embed_doc_chunks(
    *,
    embedder: Embedder,
    chunks_path: Path,
    vectors_path: Path,
    batching: EmbedBatching = EmbedBatching(),
    bench: EmbedBench | None = None,
) -> Tuple[int, int]:
    """
    v1: scan vectors jsonl to decide skip; merge+replace.
    Returns: (num_new_vectors_written, total_vectors_after_merge)
    """
    t_skip = time.perf_counter()
    existing = _existing_chunk_ids(vectors_path, bench=bench)
    if bench:
        bench.timer_end(t_skip, "skip_check_s")

    missing_chunks = _iter_missing_chunks_v1(chunks_path, existing, bench=bench)
    if not missing_chunks:
        return 0, len(existing)

    new_rows: List[Dict[str, Any]] = []
    t_embed = time.perf_counter()
    batches = 0
    total_batch = 0

    bench and bench.set("dim_expected", embedder.dim)

    for batch in _make_batches(missing_chunks, batching):
        batches += 1
        total_batch += len(batch)

        texts = [b["text_clean"] for b in batch]
        vecs = embedder.embed_texts(texts)
        if len(vecs) != len(batch):
            raise ValueError("EMBEDDING_SIZE_MISMATCH")

        ts = iso_now()
        for b, v in zip(batch, vecs):
            ok, bad = _validate_vec(v, embedder.dim)
            if not ok:
                bench and bench.add("dim_mismatch_count", 1)
                raise ValueError("DIM_MISMATCH")
            if bad:
                bench and bench.add("nan_inf_count", bad)

            new_rows.append(
                {
                    "chunk_id": b["chunk_id"],
                    "doc_id": b["doc_id"],
                    "page_num": b.get("page_num"),
                    "start_char": b.get("start_char"),
                    "end_char": b.get("end_char"),
                    "vector": v,
                    "dim": embedder.dim,
                    "embedder_id": embedder.embedder_id,
                    "embedded_at": ts,
                }
            )

    if bench:
        bench.timer_end(t_embed, "embed_s")
        bench.set("batches", batches)
        bench.set("avg_batch_size", (total_batch / batches) if batches else 0.0)
        bench.set("chunks_embedded", len(new_rows))
        bench.add("vectors_written", len(new_rows))

    # merge+replace
    t_write = time.perf_counter()

    new_ids = {r["chunk_id"] for r in new_rows}
    merged_rows: List[Dict[str, Any]] = []

    if vectors_path.exists():
        for r in iter_jsonl(vectors_path):
            cid = r.get("chunk_id")
            if cid and cid in new_ids:
                continue
            merged_rows.append(r)

    merged_rows.extend(new_rows)
    atomic_replace_jsonl(vectors_path, merged_rows)

    if bench:
        bench.timer_end(t_write, "write_s")

    total_after = len({r.get("chunk_id") for r in merged_rows if r.get("chunk_id")})
    return len(new_rows), total_after


# ============================================================
# v2 (CONTENT DEDUP): SQLite vector_store + doc_vectors idempotency
# ============================================================
def embed_doc_chunks_sqlite(
    *,
    embedder: Embedder,
    chunks_path: Path,
    vectors_path: Path,
    cache_db_path: Path,
    batching: EmbedBatching = EmbedBatching(),
    bench: EmbedBench | None = None,
) -> Tuple[int, int]:
    """
    v2 guarantees:
      - skip decision uses SQLite only (no vectors JSONL scan)
      - content-based reuse across docs via vector_store
      - per-doc vectors JSONL still appended for FAISS
      - idempotent per-doc append via doc_vectors table
      - crash-safe commit order per batch:
          (1) append JSONL durable
          (2) insert into SQLite (INSERT OR IGNORE)
    Returns: (num_new_vectors_written, total_vectors_for_this_doc)
    """
    bench and bench.set("dim_expected", embedder.dim)

    # Open DB once per doc run (file persists at cache_db_path)
    t_sql0 = time.perf_counter()
    con = CacheDb(cache_db_path).connect()
    bench and bench.add("sqlite_query_s", time.perf_counter() - t_sql0)

    try:
        # 1) Load VALID chunks + compute content keys
        chunks: List[Dict[str, Any]] = []
        valid_total = 0

        for ch in iter_jsonl(chunks_path):
            cid = ch.get("chunk_id")
            doc_id = ch.get("doc_id")
            text = (ch.get("text_clean") or "").strip()
            if not cid or not doc_id or not text:
                continue

            ch["_cache_key"] = _cache_key(embedder_id=embedder.embedder_id, text_clean=text)
            chunks.append(ch)
            valid_total += 1

        bench and bench.set("chunks_total", valid_total)

        if not chunks:
            bench and bench.set("sqlite_hits", 0)
            bench and bench.set("chunks_skipped", 0)
            bench and bench.set("chunks_to_embed", 0)
            bench and bench.set("chunks_embedded", 0)
            bench and bench.add("vectors_written", 0)
            bench and bench.set("vectors_jsonl_bytes_read", 0)
            return 0, 0

        doc_id = str(chunks[0]["doc_id"])
        chunk_ids = [str(ch["chunk_id"]) for ch in chunks]

        # Step A: idempotency for THIS doc (already appended?)
        t_doc = time.perf_counter()
        already_written = lookup_existing_doc_chunks(
            con,
            doc_id=doc_id,
            embedder_id=embedder.embedder_id,
            chunk_ids=chunk_ids,
        )
        bench and bench.add("sqlite_query_s", time.perf_counter() - t_doc)

        already_count = len(already_written)

        pending = [ch for ch in chunks if str(ch["chunk_id"]) not in already_written]

        # If nothing pending, rerun should be FAST and still return total vectors for doc.
        if not pending:
            bench and bench.set("sqlite_hits", 0)
            bench and bench.set("chunks_skipped", already_count)
            bench and bench.set("chunks_to_embed", 0)
            bench and bench.set("chunks_embedded", 0)
            bench and bench.add("vectors_written", 0)
            bench and bench.set("vectors_jsonl_bytes_read", 0)
            return 0, already_count

        # Step B: content reuse via vector_store for pending only
        pending_keys = [str(ch["_cache_key"]) for ch in pending]

        t_sql = time.perf_counter()
        existing_keys = lookup_existing_vectors(con, pending_keys)
        dt_sql = time.perf_counter() - t_sql

        if bench:
            bench.add("sqlite_query_s", dt_sql)
            bench.add("skip_check_s", dt_sql)
            bench.set("sqlite_hits", len(existing_keys))

        hit_chunks = [ch for ch in pending if str(ch["_cache_key"]) in existing_keys]
        miss_chunks = [ch for ch in pending if str(ch["_cache_key"]) not in existing_keys]

        # if bench and fallback_miss_chunks:
        #     bench.set("chunks_to_embed", len(miss_chunks))


        # Step C: HIT PATH (reuse vectors from vector_store; append JSONL; mark doc_vectors)
        rows_hit: List[Dict[str, Any]] = []
        doc_rows_hit: List[tuple[str, str, str, str, str, int, str]] = []

        if hit_chunks:
            t_sqlh = time.perf_counter()
            vec_map = fetch_vectors(con, [str(ch["_cache_key"]) for ch in hit_chunks])  # {ck: (dim, vec_list)}
            bench and bench.add("sqlite_query_s", time.perf_counter() - t_sqlh)
            ts = iso_now()
            materialized_hit_chunks: List[Dict[str, Any]] = []
            fallback_miss_chunks: List[Dict[str, Any]] = []

            for ch in hit_chunks:
                ck = str(ch["_cache_key"])
                got = vec_map.get(ck)
                if not got:
                    # key existed in membership check, but vector missing -> treat as MISS
                    fallback_miss_chunks.append(ch)
                    continue

                dim, vec = got
                if int(dim) != int(embedder.dim):
                    # dimension mismatch -> treat as MISS
                    fallback_miss_chunks.append(ch)
                    continue

                materialized_hit_chunks.append(ch)

                rows_hit.append(
                    {
                        "chunk_id": ch["chunk_id"],
                        "doc_id": ch["doc_id"],
                        "page_num": ch.get("page_num"),
                        "start_char": ch.get("start_char"),
                        "end_char": ch.get("end_char"),
                        "vector": vec,
                        "dim": embedder.dim,
                        "embedder_id": embedder.embedder_id,
                        "cache_key": ck,
                        "embedded_at": ts,
                    }
                )
                doc_rows_hit.append(
                    (
                        str(ch["doc_id"]),
                        str(ch["chunk_id"]),
                        embedder.embedder_id,
                        ck,
                        str(vectors_path),
                        int(embedder.dim),
                        ts,
                    )
                )

            # write+mark only the materialized hits (unchanged)
            if rows_hit:
                t_w = time.perf_counter()
                _append_jsonl_durable(vectors_path, rows_hit)
                bench and bench.timer_end(t_w, "write_s")

                t_m = time.perf_counter()
                insert_doc_vectors(con, doc_rows_hit)
                bench and bench.add("sqlite_query_s", time.perf_counter() - t_m)

            # IMPORTANT: add fallback misses back into miss_chunks so they get embedded
            if fallback_miss_chunks:
                miss_chunks.extend(fallback_miss_chunks)
        

        if bench:
            bench.set("chunks_to_embed", len(miss_chunks))
            bench.set("chunks_skipped", already_count + len(rows_hit))
            bench.set("sqlite_hits", len(rows_hit))  # optional but recommended

        # If no misses, we're done (0 embedding calls). Total vectors for doc = already + new appended hits.
        if not miss_chunks:
            total_for_doc = already_count + len(rows_hit)
            if bench:
                bench.set("chunks_embedded", 0)
                bench.add("vectors_written", len(rows_hit))
                bench.set("vectors_jsonl_bytes_read", 0)
            return 0, total_for_doc

        # Step D: MISS PATH (embed; append JSONL; upsert vector_store; mark doc_vectors)
        new_rows_written = 0
        t_embed = time.perf_counter()
        batches = 0
        total_batch = 0

        for batch in _make_batches(miss_chunks, batching):
            batches += 1
            total_batch += len(batch)

            texts = [b["text_clean"] for b in batch]
            vecs = embedder.embed_texts(texts)
            if len(vecs) != len(batch):
                raise ValueError("EMBEDDING_SIZE_MISMATCH")

            ts = iso_now()

            rows_out: List[Dict[str, Any]] = []
            store_rows: List[tuple[str, int, bytes, str]] = []
            doc_rows_miss: List[tuple[str, str, str, str, str, int, str]] = []

            for b, v in zip(batch, vecs):
                ok, bad = _validate_vec(v, embedder.dim)
                if not ok:
                    bench and bench.add("dim_mismatch_count", 1)
                    raise ValueError("DIM_MISMATCH")
                if bad:
                    bench and bench.add("nan_inf_count", bad)

                ck = str(b["_cache_key"])

                rows_out.append(
                    {
                        "chunk_id": b["chunk_id"],
                        "doc_id": b["doc_id"],
                        "page_num": b.get("page_num"),
                        "start_char": b.get("start_char"),
                        "end_char": b.get("end_char"),
                        "vector": v,
                        "dim": embedder.dim,
                        "embedder_id": embedder.embedder_id,
                        "cache_key": ck,
                        "embedded_at": ts,
                    }
                )

                blob = np.asarray(v, dtype=np.float32).tobytes()
                store_rows.append((ck, int(embedder.dim), blob, ts))

                doc_rows_miss.append(
                    (
                        str(b["doc_id"]),
                        str(b["chunk_id"]),
                        embedder.embedder_id,
                        ck,
                        str(vectors_path),
                        int(embedder.dim),
                        ts,
                    )
                )

            # (1) write JSONL durable
            t_w = time.perf_counter()
            _append_jsonl_durable(vectors_path, rows_out)
            bench and bench.timer_end(t_w, "write_s")

            # (2) sqlite inserts (idempotent)
            t_s = time.perf_counter()
            upsert_vectors(con, store_rows)
            insert_doc_vectors(con, doc_rows_miss)
            bench and bench.add("sqlite_query_s", time.perf_counter() - t_s)

            new_rows_written += len(rows_out)

        if bench:
            bench.timer_end(t_embed, "embed_s")
            bench.set("batches", batches)
            bench.set("avg_batch_size", (total_batch / batches) if batches else 0.0)
            bench.set("chunks_embedded", new_rows_written)
            bench.add("vectors_written", new_rows_written + len(rows_hit))
            bench.set("vectors_jsonl_bytes_read", 0)

        total_for_doc = already_count + len(rows_hit) + new_rows_written
        return new_rows_written, total_for_doc

    finally:
        con.close()
