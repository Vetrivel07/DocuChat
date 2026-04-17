# src/eval/metrics/common.py
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from src.eval.metrics.schema import GoldRow


_WORD_RE = re.compile(r"\w+")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def tokenize(s: str) -> List[str]:
    return _WORD_RE.findall(normalize_text(s))


def exact_match(a: str, b: str) -> float:
    return 1.0 if normalize_text(a) == normalize_text(b) else 0.0


def token_f1(pred: str, gold: str) -> float:
    p = tokenize(pred)
    g = tokenize(gold)
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0

    p_counts: Dict[str, int] = {}
    g_counts: Dict[str, int] = {}
    for t in p:
        p_counts[t] = p_counts.get(t, 0) + 1
    for t in g:
        g_counts[t] = g_counts.get(t, 0) + 1

    common = 0
    for t, c in p_counts.items():
        common += min(c, g_counts.get(t, 0))

    if common == 0:
        return 0.0

    precision = common / len(p)
    recall    = common / len(g)
    return 2 * precision * recall / (precision + recall)


def is_abstained(answer_text: str) -> bool:
    return normalize_text(answer_text) == "not found in documents."


def get_answer_text(log_row: Dict[str, Any]) -> str:
    """Supports both 'answer_text' (logger schema) and 'answer' (API response schema)."""
    return str(log_row.get("answer_text") or log_row.get("answer") or "")


def citation_chunk_ids_from_log_row(log_row: Dict[str, Any]) -> List[str]:
    debug = log_row.get("debug") or {}
    citations = [str(x) for x in (debug.get("citations") or [])]
    if not citations:
        citations = [str(x) for x in (log_row.get("citations") or [])]

    ctx = log_row.get("sources") or log_row.get("final_context") or []
    idx_to_chunk: Dict[str, str] = {}
    for item in ctx:
        idx = item.get("source_idx")
        chunk_id = item.get("chunk_id")
        if idx is not None and chunk_id:
            idx_to_chunk[str(idx)] = str(chunk_id)

    out: List[str] = []
    for c in citations:
        cid = idx_to_chunk.get(c)
        if cid:
            out.append(cid)
    return out


def citation_source_names_from_log_row(log_row: Dict[str, Any]) -> List[str]:
    """Get source filenames that were actually cited in the answer."""
    debug = log_row.get("debug") or {}
    citations = [str(x) for x in (debug.get("citations") or [])]
    if not citations:
        citations = [str(x) for x in (log_row.get("citations") or [])]

    ctx = log_row.get("sources") or log_row.get("final_context") or []
    idx_to_name: Dict[str, str] = {}
    for item in ctx:
        idx = item.get("source_idx")
        name = item.get("source_name")
        if idx is not None and name:
            idx_to_name[str(idx)] = str(name)

    out: List[str] = []
    for c in citations:
        name = idx_to_name.get(c)
        if name:
            out.append(name)
    return out


def retrieved_source_names_from_log_row(log_row: Dict[str, Any]) -> List[str]:
    """Get all source filenames from retrieved chunks (sources[] in API response)."""
    rows = log_row.get("sources") or log_row.get("final_context") or []
    out: List[str] = []
    for r in rows:
        name = r.get("source_name")
        if name:
            out.append(str(name))
    return out


def retrieved_chunk_ids_from_log_row(log_row: Dict[str, Any]) -> List[str]:
    rows = log_row.get("retrieved_before_rerank") or []
    if rows:
        out: List[str] = []
        for r in rows:
            cid = r.get("chunk_id")
            if cid:
                out.append(str(cid))
        return out
    rows = log_row.get("sources") or []
    out = []
    for r in rows:
        cid = r.get("chunk_id")
        if cid:
            out.append(str(cid))
    return out


def final_context_chunk_ids_from_log_row(log_row: Dict[str, Any]) -> List[str]:
    rows = log_row.get("sources") or log_row.get("final_context") or []
    out: List[str] = []
    for r in rows:
        cid = r.get("chunk_id")
        if cid:
            out.append(str(cid))
    return out


def graph_retrieved_chunk_ids_from_log_row(log_row: Dict[str, Any]) -> List[str]:
    extra = log_row.get("extra") or {}
    rows  = extra.get("graph_retrieved") or []
    out: List[str] = []
    for r in rows:
        cid = r.get("chunk_id")
        if cid:
            out.append(str(cid))
    return out


def vector_retrieved_chunk_ids_from_log_row(log_row: Dict[str, Any]) -> List[str]:
    extra = log_row.get("extra") or {}
    rows  = extra.get("vector_retrieved") or []
    out: List[str] = []
    for r in rows:
        cid = r.get("chunk_id")
        if cid:
            out.append(str(cid))
    return out


def load_gold_rows(path: Path) -> List[GoldRow]:
    out: List[GoldRow] = []
    for row in read_jsonl(path):
        query = str(row.get("query") or "").strip()

        if "answerable" in row:
            answerable = bool(row["answerable"])
        else:
            answerable = row.get("expected_answer") is not None

        expected_answer = str(row.get("expected_answer") or "")

        if "relevant_chunk_ids" in row:
            gold_chunk_ids = [str(x) for x in (row["relevant_chunk_ids"] or [])]
        else:
            gold_chunk_ids = [str(x) for x in (row.get("gold_chunk_ids") or [])]

        # NEW: load source_ids from gold
        source_ids = [str(x) for x in (row.get("source_ids") or [])]

        multi_hop = bool(row.get("multi_hop", False))
        notes     = str(row.get("notes") or "")

        out.append(GoldRow(
            query=query,
            answerable=answerable,
            expected_answer=expected_answer,
            gold_chunk_ids=gold_chunk_ids,
            source_ids=source_ids,
            multi_hop=multi_hop,
            notes=notes,
        ))
    return out


def build_latest_log_map(
    log_rows: List[Dict[str, Any]],
    *,
    retrieval_mode: str,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in log_rows:
        if str(row.get("retrieval_mode") or "") != retrieval_mode:
            continue
        q = str(row.get("original_query") or "").strip()
        if not q:
            continue
        out[q] = row
    return out