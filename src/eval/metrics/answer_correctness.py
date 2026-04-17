# src/eval/metrics/answer_correctness.py
from __future__ import annotations

from typing import Any, Dict, List

from src.eval.metrics.common import exact_match, get_answer_text, token_f1
from src.eval.metrics.schema import GoldRow, MetricSummary


def compute_answer_correctness(
    pairs: List[tuple[GoldRow, Dict[str, Any]]],
) -> tuple[MetricSummary, List[Dict[str, Any]], MetricSummary]:
    per_query: List[Dict[str, Any]] = []
    em_vals: List[float] = []
    f1_vals: List[float] = []

    for gold, log_row in pairs:
        if not gold.expected_answer:
            per_query.append({
                "query": gold.query,
                "metric": "answer_correctness",
                "exact_match": None,
                "token_f1": None,
            })
            continue

        pred = get_answer_text(log_row)              
        em = exact_match(pred, gold.expected_answer)
        f1 = token_f1(pred, gold.expected_answer)

        em_vals.append(em)
        f1_vals.append(f1)

        per_query.append({
            "query": gold.query,
            "metric": "answer_correctness",
            "exact_match": round(em, 6),
            "token_f1": round(f1, 6),
        })

    em_summary = MetricSummary(
        name="answer_correctness_em",
        value=(sum(em_vals) / len(em_vals)) if em_vals else None,
        count=len(em_vals),
        details={},
    )
    f1_summary = MetricSummary(
        name="answer_correctness_f1",
        value=(sum(f1_vals) / len(f1_vals)) if f1_vals else None,
        count=len(f1_vals),
        details={},
    )
    return em_summary, per_query, f1_summary