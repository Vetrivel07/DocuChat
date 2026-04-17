# src/eval/metrics/multihop_recall_at_k.py
from __future__ import annotations

from typing import Any, Dict, List

from src.eval.metrics.common import retrieved_source_names_from_log_row
from src.eval.metrics.schema import GoldRow, MetricSummary
from src.eval.metrics.source_mapping import gold_source_ids_to_filenames


def compute_multihop_recall_at_k(
    pairs: List[tuple[GoldRow, Dict[str, Any]]],
    *,
    k: int = 10,
) -> tuple[MetricSummary, List[Dict[str, Any]]]:
    """
    Source-level Multi-hop Recall@k.
    Only evaluated on gold rows marked multi_hop=True.
    Checks whether all expected source documents were retrieved.
    """
    per_query: List[Dict[str, Any]] = []
    vals: List[float] = []

    for gold, log_row in pairs:
        if not bool(getattr(gold, "multi_hop", False)):
            per_query.append({
                "query": gold.query,
                "metric": f"multihop_recall@{k}",
                "value": None,
                "reason": "not_multihop_gold",
            })
            continue

        gold_sources = gold_source_ids_to_filenames(gold.source_ids)
        retrieved_names = retrieved_source_names_from_log_row(log_row)[:k]
        retrieved_set = set(retrieved_names)

        if not gold_sources:
            per_query.append({
                "query": gold.query,
                "metric": f"multihop_recall@{k}",
                "value": None,
                "reason": "no_gold_sources",
            })
            continue

        hits = len(gold_sources.intersection(retrieved_set))
        val = hits / len(gold_sources)
        vals.append(val)

        per_query.append({
            "query": gold.query,
            "metric": f"multihop_recall@{k}",
            "value": round(val, 6),
            "gold_sources": list(gold_sources),
            "retrieved_sources": list(retrieved_set),
            "hits": hits,
        })

    summary = MetricSummary(
        name=f"multihop_recall@{k}",
        value=(sum(vals) / len(vals)) if vals else None,
        count=len(vals),
        details={"k": k, "matching": "source_level", "applies_to": "multi_hop_gold_only"},
    )
    return summary, per_query