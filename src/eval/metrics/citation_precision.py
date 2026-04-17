# src/eval/metrics/citation_precision.py
from __future__ import annotations

from typing import Any, Dict, List

from src.eval.metrics.common import citation_source_names_from_log_row
from src.eval.metrics.schema import GoldRow, MetricSummary
from src.eval.metrics.source_mapping import gold_source_ids_to_filenames


def compute_citation_precision(
    pairs: List[tuple[GoldRow, Dict[str, Any]]],
) -> tuple[MetricSummary, List[Dict[str, Any]]]:
    """
    Source-level Citation Precision.
    Of the sources cited in the answer, how many were expected sources?
    Uses gold source_ids mapped to filenames for matching.
    """
    per_query: List[Dict[str, Any]] = []
    vals: List[float] = []

    for gold, log_row in pairs:
        cited_names = citation_source_names_from_log_row(log_row)
        cited_set = set(cited_names)
        gold_sources = gold_source_ids_to_filenames(gold.source_ids)

        if not cited_names:
            # No citations at all — 0 precision
            val = 0.0
        elif not gold_sources:
            # No gold sources to verify — skip
            per_query.append({
                "query": gold.query,
                "metric": "citation_precision",
                "value": None,
                "reason": "no_gold_sources",
            })
            continue
        else:
            correct = len(cited_set.intersection(gold_sources))
            val = correct / len(cited_set)

        vals.append(val)
        per_query.append({
            "query": gold.query,
            "metric": "citation_precision",
            "value": round(val, 6),
            "cited_sources": list(cited_set),
            "gold_sources": list(gold_sources),
        })

    summary = MetricSummary(
        name="citation_precision",
        value=(sum(vals) / len(vals)) if vals else None,
        count=len(vals),
        details={"matching": "source_level"},
    )
    return summary, per_query