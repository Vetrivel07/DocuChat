# src/eval/metrics/abstention_accuracy.py
from __future__ import annotations

from typing import Any, Dict, List

from src.eval.metrics.common import get_answer_text, is_abstained
from src.eval.metrics.schema import GoldRow, MetricSummary


def compute_abstention_accuracy(
    pairs: List[tuple[GoldRow, Dict[str, Any]]],
) -> tuple[MetricSummary, List[Dict[str, Any]]]:
    per_query: List[Dict[str, Any]] = []
    vals: List[float] = []

    for gold, log_row in pairs:
        answer_text = get_answer_text(log_row)      
        predicted_abstain = is_abstained(answer_text)
        should_abstain = not gold.answerable
        val = 1.0 if predicted_abstain == should_abstain else 0.0
        vals.append(val)

        per_query.append({
            "query": gold.query,
            "metric": "abstention_accuracy",
            "value": round(val, 6),
            "predicted_abstain": predicted_abstain,
            "should_abstain": should_abstain,
        })

    summary = MetricSummary(
        name="abstention_accuracy",
        value=(sum(vals) / len(vals)) if vals else None,
        count=len(vals),
        details={},
    )
    return summary, per_query