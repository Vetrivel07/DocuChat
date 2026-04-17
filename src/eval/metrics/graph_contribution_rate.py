# src\eval\metrics\graph_contribution_rate.py
from __future__ import annotations

from typing import Any, Dict, List

from src.eval.metrics.common import (
    final_context_chunk_ids_from_log_row,
    graph_retrieved_chunk_ids_from_log_row,
)
from src.eval.metrics.schema import MetricSummary


def compute_graph_contribution_rate(
    pairs: List[tuple[Any, Dict[str, Any]]],
) -> tuple[MetricSummary, List[Dict[str, Any]]]:
    """
    Definition used here:
    - For each hybrid query:
        graph_contribution_rate =
            (# final-context chunk_ids that also appear in graph_retrieved)
            / (# final-context chunk_ids)

    Interpretation:
    - 0.0  => final answer context came only from vector side
    - 1.0  => final answer context came fully from graph-supported retrieval
    """
    per_query: List[Dict[str, Any]] = []
    vals: List[float] = []

    for gold, log_row in pairs:
        retrieval_mode = str(log_row.get("retrieval_mode") or "")
        if not retrieval_mode.startswith("hybrid"):
            per_query.append(
                {
                    "query": getattr(gold, "query", ""),
                    "metric": "graph_contribution_rate",
                    "value": None,
                    "reason": "not_hybrid",
                }
            )
            continue

        final_ids = final_context_chunk_ids_from_log_row(log_row)
        graph_ids = set(graph_retrieved_chunk_ids_from_log_row(log_row))

        if not final_ids:
            per_query.append(
                {
                    "query": getattr(gold, "query", ""),
                    "metric": "graph_contribution_rate",
                    "value": 0.0,
                    "final_context_count": 0,
                    "graph_supported_count": 0,
                }
            )
            vals.append(0.0)
            continue

        graph_supported_count = sum(1 for cid in final_ids if cid in graph_ids)
        val = graph_supported_count / len(final_ids)
        vals.append(val)

        per_query.append(
            {
                "query": getattr(gold, "query", ""),
                "metric": "graph_contribution_rate",
                "value": round(val, 6),
                "final_context_count": len(final_ids),
                "graph_supported_count": graph_supported_count,
            }
        )

    summary = MetricSummary(
        name="graph_contribution_rate",
        value=(sum(vals) / len(vals)) if vals else None,
        count=len(vals),
        details={"applies_to": "hybrid_queries_only"},
    )
    return summary, per_query