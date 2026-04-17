# scripts/run_eval.py

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from src.eval.metrics.common import (
    build_latest_log_map,
    load_gold_rows,
    read_jsonl,
    write_csv,
    write_json,
    write_jsonl,
)
from src.eval.metrics.recall_at_k import compute_recall_at_k
from src.eval.metrics.citation_precision import compute_citation_precision
from src.eval.metrics.abstention_accuracy import compute_abstention_accuracy
from src.eval.metrics.unsupported_claim_rate import compute_unsupported_claim_rate
from src.eval.metrics.answer_correctness import compute_answer_correctness
from src.eval.metrics.graph_contribution_rate import compute_graph_contribution_rate
from src.eval.metrics.multihop_recall_at_k import compute_multihop_recall_at_k


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DocuChat evaluation.")
    parser.add_argument(
        "--retrieval-mode",
        type=str,
        default="vector_v2",
        choices=["vector_v2", "hybrid_v1"],
        help="Retrieval mode to evaluate.",
    )
    parser.add_argument(
        "--gold-path",
        type=str,
        default="storage/eval/gold/baseline_gold.jsonl",
        help="Path to gold dataset JSONL.",
    )
    parser.add_argument(
        "--query-log-path",
        type=str,
        default="storage/logs/query_log.jsonl",
        help="Path to runtime query log JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Optional explicit output directory. If omitted, uses storage/eval/runs/<mode_name>/",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=10,
        help="Top-k cutoff for recall metrics.",
    )
    return parser.parse_args()


def _mode_dir_name(retrieval_mode: str) -> str:
    if retrieval_mode == "vector_v2":
        return "vector"
    if retrieval_mode == "hybrid_v1":
        return "hybrid"
    return retrieval_mode


def main() -> None:
    args = _parse_args()

    retrieval_mode = args.retrieval_mode
    gold_path = Path(args.gold_path)
    query_log_path = Path(args.query_log_path)

    mode_dir_name = _mode_dir_name(retrieval_mode)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir.strip()
        else Path("storage/eval/runs") / mode_dir_name
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    gold_rows = load_gold_rows(gold_path)
    log_rows = read_jsonl(query_log_path)
    latest_log_map = build_latest_log_map(log_rows, retrieval_mode=retrieval_mode)

    pairs: List[tuple[Any, Dict[str, Any]]] = []
    missing_queries: List[str] = []

    for gold in gold_rows:
        row = latest_log_map.get(gold.query)
        if row is None:
            missing_queries.append(gold.query)
            continue
        pairs.append((gold, row))

    summaries = []
    per_query_rows: List[Dict[str, Any]] = []

    # 1. recall@k
    recall_summary, recall_per_query = compute_recall_at_k(pairs, k=args.k)
    summaries.append(recall_summary)
    per_query_rows.extend(recall_per_query)

    # 2. citation precision
    cp_summary, cp_per_query = compute_citation_precision(pairs)
    summaries.append(cp_summary)
    per_query_rows.extend(cp_per_query)

    # 3. abstention accuracy
    aa_summary, aa_per_query = compute_abstention_accuracy(pairs)
    summaries.append(aa_summary)
    per_query_rows.extend(aa_per_query)

    # 4. unsupported claim rate
    ucr_summary, ucr_per_query = compute_unsupported_claim_rate(pairs)
    summaries.append(ucr_summary)
    per_query_rows.extend(ucr_per_query)

    # 5. answer correctness
    em_summary, ac_per_query, f1_summary = compute_answer_correctness(pairs)
    summaries.append(em_summary)
    summaries.append(f1_summary)
    per_query_rows.extend(ac_per_query)

    # 6. graph contribution rate
    gcr_summary, gcr_per_query = compute_graph_contribution_rate(pairs)
    summaries.append(gcr_summary)
    per_query_rows.extend(gcr_per_query)

    # 7. multihop recall@k
    mhr_summary, mhr_per_query = compute_multihop_recall_at_k(pairs, k=args.k)
    summaries.append(mhr_summary)
    per_query_rows.extend(mhr_per_query)

    summary_obj = {
        "retrieval_mode": retrieval_mode,
        "gold_path": str(gold_path),
        "query_log_path": str(query_log_path),
        "matched_queries": len(pairs),
        "missing_queries": missing_queries,
        "metrics": [
            {
                "name": s.name,
                "value": s.value,
                "count": s.count,
                "details": s.details,
            }
            for s in summaries
        ],
    }

    metrics_csv_rows = [
        {
            "metric": s.name,
            "value": s.value,
            "count": s.count,
        }
        for s in summaries
    ]

    write_json(output_dir / "summary.json", summary_obj)
    write_jsonl(output_dir / "per_query.jsonl", per_query_rows)
    write_csv(output_dir / "metrics.csv", metrics_csv_rows)

    dashboard_latest = {
        "summary": summary_obj,
        "per_query_count": len(per_query_rows),
    }
    write_json(Path("storage/eval/dashboard/latest.json"), dashboard_latest)

    print(f"Evaluation completed for mode={retrieval_mode}")
    print(f"Output written to: {output_dir}")


if __name__ == "__main__":
    main()