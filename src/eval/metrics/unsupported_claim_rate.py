# src/eval/metrics/unsupported_claim_rate.py
from __future__ import annotations

from typing import Any, Dict, List

from src.eval.metrics.common import citation_chunk_ids_from_log_row, get_answer_text, is_abstained
from src.eval.metrics.schema import GoldRow, MetricSummary


def compute_unsupported_claim_rate(
    pairs: List[tuple[GoldRow, Dict[str, Any]]],
) -> tuple[MetricSummary, List[Dict[str, Any]]]:
    """
    Proxy UCR:
    - unanswerable + abstained  => 0 (correct behavior)
    - unanswerable + answered   => 1 (hallucinated)
    - answerable + no citations => 1 (ungrounded)
    - answerable + cited chunks within gold => 0 (supported)
    - answerable + cited chunks outside gold => 1 (unsupported)

    NOTE: when gold has no chunk IDs (our case), answerable queries
    with citations are treated as 0 (benefit of the doubt) since we
    cannot verify citation validity without gold chunk IDs.
    """
    per_query: List[Dict[str, Any]] = []
    vals: List[float] = []

    for gold, log_row in pairs:
        answer_text = get_answer_text(log_row)          # FIX: was log_row.get("answer_text")
        abstained = is_abstained(answer_text)
        cited = set(citation_chunk_ids_from_log_row(log_row))
        gold_set = set(gold.gold_chunk_ids)

        if not gold.answerable:
            # unanswerable: correct only if abstained
            unsupported = 0.0 if abstained else 1.0
        else:
            if not cited:
                # answerable but no citations = ungrounded
                unsupported = 1.0
            elif not gold_set:
                # answerable, has citations, but no gold chunk IDs to verify against
                # give benefit of the doubt — citations exist, can't verify
                unsupported = 0.0
            else:
                # answerable, has citations, has gold chunk IDs — check overlap
                unsupported = 0.0 if cited.issubset(gold_set) else 1.0

        vals.append(unsupported)
        per_query.append({
            "query": gold.query,
            "metric": "unsupported_claim_rate",
            "value": round(unsupported, 6),
            "abstained": abstained,
            "cited_count": len(cited),
            "proxy": True,
        })

    summary = MetricSummary(
        name="unsupported_claim_rate",
        value=(sum(vals) / len(vals)) if vals else None,
        count=len(vals),
        details={"proxy": True},
    )
    return summary, per_query