from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from src.eval.metrics.common import read_jsonl, write_csv, write_json


def _read_json(path: Path) -> Dict[str, Any]:
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare vector vs hybrid evaluation results.")
    parser.add_argument(
        "--vector-summary",
        type=str,
        default="storage/eval/runs/vector/summary.json",
        help="Path to vector summary.json",
    )
    parser.add_argument(
        "--hybrid-summary",
        type=str,
        default="storage/eval/runs/hybrid/summary.json",
        help="Path to hybrid summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="storage/eval/comparison",
        help="Output directory for comparison files",
    )
    return parser.parse_args()


def _metrics_map(summary_obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in summary_obj.get("metrics") or []:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        out[name] = row
    return out


def _safe_delta(vector_value: Any, hybrid_value: Any) -> Any:
    if vector_value is None or hybrid_value is None:
        return None
    try:
        return float(hybrid_value) - float(vector_value)
    except Exception:
        return None


def _safe_pct_delta(vector_value: Any, hybrid_value: Any) -> Any:
    if vector_value is None or hybrid_value is None:
        return None
    try:
        v = float(vector_value)
        h = float(hybrid_value)
        if v == 0:
            return None
        return ((h - v) / v) * 100.0
    except Exception:
        return None


def main() -> None:
    args = _parse_args()

    vector_summary_path = Path(args.vector_summary)
    hybrid_summary_path = Path(args.hybrid_summary)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not vector_summary_path.exists():
        raise FileNotFoundError(f"Missing vector summary: {vector_summary_path}")

    if not hybrid_summary_path.exists():
        raise FileNotFoundError(f"Missing hybrid summary: {hybrid_summary_path}")

    vector_summary = _read_json(vector_summary_path)
    hybrid_summary = _read_json(hybrid_summary_path)

    vector_metrics = _metrics_map(vector_summary)
    hybrid_metrics = _metrics_map(hybrid_summary)

    all_metric_names = sorted(set(vector_metrics.keys()) | set(hybrid_metrics.keys()))

    comparison_rows: List[Dict[str, Any]] = []
    improved_metrics: List[str] = []
    declined_metrics: List[str] = []
    unchanged_metrics: List[str] = []

    for name in all_metric_names:
        v_row = vector_metrics.get(name, {})
        h_row = hybrid_metrics.get(name, {})

        v_val = v_row.get("value")
        h_val = h_row.get("value")

        delta = _safe_delta(v_val, h_val)
        pct_delta = _safe_pct_delta(v_val, h_val)

        if delta is None:
            trend = "n/a"
        elif delta > 0:
            trend = "improved"
            improved_metrics.append(name)
        elif delta < 0:
            trend = "declined"
            declined_metrics.append(name)
        else:
            trend = "unchanged"
            unchanged_metrics.append(name)

        comparison_rows.append(
            {
                "metric": name,
                "vector_value": v_val,
                "hybrid_value": h_val,
                "delta": delta,
                "pct_delta": pct_delta,
                "trend": trend,
                "vector_count": v_row.get("count"),
                "hybrid_count": h_row.get("count"),
            }
        )

    comparison_summary = {
        "vector_summary_path": str(vector_summary_path),
        "hybrid_summary_path": str(hybrid_summary_path),
        "vector_retrieval_mode": vector_summary.get("retrieval_mode"),
        "hybrid_retrieval_mode": hybrid_summary.get("retrieval_mode"),
        "vector_matched_queries": vector_summary.get("matched_queries"),
        "hybrid_matched_queries": hybrid_summary.get("matched_queries"),
        "metrics_compared": len(comparison_rows),
        "improved_metrics": improved_metrics,
        "declined_metrics": declined_metrics,
        "unchanged_metrics": unchanged_metrics,
        "comparison_rows": comparison_rows,
    }

    write_json(output_dir / "vector_vs_hybrid.json", comparison_summary)
    write_csv(output_dir / "vector_vs_hybrid.csv", comparison_rows)

    print("Comparison completed.")
    print(f"Output written to: {output_dir}")


if __name__ == "__main__":
    main()