import argparse
import json
import time
import requests
from pathlib import Path
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description="Auto-run gold queries through DocuChat API.")
    parser.add_argument("--mode", type=str, required=True, choices=["vector_v2", "hybrid_v1"],
                        help="Retrieval mode to use.")
    parser.add_argument("--collection-id", type=str, required=True,
                        help="Collection ID of your uploaded documents.")
    parser.add_argument("--gold-path", type=str,
                        default="storage/eval/gold/baseline_gold.jsonl",
                        help="Path to gold dataset JSONL.")
    parser.add_argument("--api-url", type=str,
                        default="http://127.0.0.1:8080",
                        help="Base URL of your DocuChat API.")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Delay in seconds between queries.")
    parser.add_argument("--output-log", type=str,
                        default="storage/logs/query_log.jsonl",
                        help="Path to save query log JSONL.")
    return parser.parse_args()


def load_gold(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_query(api_url: str, collection_id: str, question: str, mode: str) -> dict:
    """Send a single query to the DocuChat /query endpoint."""
    url = f"{api_url}/query"

    # Map eval mode names to what your API accepts
    # vector_v2 -> "vector", hybrid_v1 -> "hybrid"
    api_mode = "vector" if mode == "vector_v2" else "hybrid"

    payload = {
        "collection_id": collection_id,
        "question": question,          # your route uses 'question' not 'query'
        "retrieval_mode": api_mode,
    }
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def main():
    args = parse_args()

    gold_path = Path(args.gold_path)
    output_log = Path(args.output_log)
    output_log.parent.mkdir(parents=True, exist_ok=True)

    gold_rows = load_gold(str(gold_path))

    print(f"\n{'='*60}")
    print(f"DocuChat Auto Query Runner")
    print(f"{'='*60}")
    print(f"Mode          : {args.mode}")
    print(f"Collection ID : {args.collection_id}")
    print(f"Total queries : {len(gold_rows)}")
    print(f"API URL       : {args.api_url}")
    print(f"Output log    : {output_log}")
    print(f"Delay between : {args.delay}s")
    print(f"Est. time     : ~{int(len(gold_rows) * args.delay / 60)} min")
    print(f"{'='*60}\n")

    results = []
    failed = []

    for i, gold in enumerate(gold_rows, 1):
        query_id = gold.get("query_id", f"q{i}")
        question = gold["query"]

        print(f"[{i:>3}/{len(gold_rows)}] {query_id} | {question[:65]}...")

        try:
            result = run_query(
                api_url=args.api_url,
                collection_id=args.collection_id,
                question=question,
                mode=args.mode,
            )

            # Enrich result with gold metadata for eval script matching
            result["original_query"] = question
            result["rewritten_query"] = question
            result["retrieval_mode"] = args.mode
            result["collection_id"] = args.collection_id
            result["gold_query_id"] = query_id
            result["gold_is_answerable"] = gold.get("is_answerable")
            result["gold_chunk_ids"] = gold.get("relevant_chunk_ids", [])
            result["run_timestamp"] = datetime.utcnow().isoformat()

            results.append(result)

            answer_preview = str(result.get("answer_text", "")).strip()[:80]
            print(f"         ✅  {answer_preview}...")

        except requests.exceptions.HTTPError as e:
            msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            print(f"         ❌  {msg}")
            failed.append({"query_id": query_id, "query": question, "error": msg})

        except Exception as e:
            print(f"         ❌  {type(e).__name__}: {e}")
            failed.append({"query_id": query_id, "query": question, "error": str(e)})

        if i < len(gold_rows):
            time.sleep(args.delay)

    # Write results to query log
    with open(output_log, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # Save failed list separately
    if failed:
        failed_path = output_log.parent / f"failed_{args.mode}.json"
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(failed, f, indent=2)

    print(f"\n{'='*60}")
    print(f"DONE!")
    print(f"Successful : {len(results)}")
    print(f"Failed     : {len(failed)}")
    print(f"Log saved  : {output_log}")
    print(f"{'='*60}")

    if failed:
        print(f"\n⚠️  {len(failed)} failed queries saved to: {output_log.parent}/failed_{args.mode}.json")

    print(f"\n✅ Next step — run evaluation:")
    print(f"   python -m scripts.run_eval --retrieval-mode {args.mode} --gold-path {args.gold_path} --query-log-path {output_log}")


if __name__ == "__main__":
    main()