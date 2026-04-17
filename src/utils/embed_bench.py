from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class EmbedBench:
    version: str
    collection_id: str
    embedder_id: str
    log_path: Path
    run_mode: str = "unknown"

    started_at_ts: str | None = None  # optional: if you want iso timestamp
    _t0: float = field(default_factory=time.perf_counter, init=False)
    _data: Dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._data.update(
            {
                "version": self.version,
                "collection_id": self.collection_id,
                "embedder_id": self.embedder_id,
                "run_mode": self.run_mode,
                # timers (accumulated)
                "wall_s": 0.0,
                "skip_check_s": 0.0,
                "embed_s": 0.0,
                "write_s": 0.0,
                # counts
                "chunks_total": 0,
                "chunks_skipped": 0,
                "chunks_embedded": 0,
                "batches": 0,
                "avg_batch_size": 0.0,
                "vectors_written": 0,
                "dim_expected": None,
                "dim_mismatch_count": 0,
                "nan_inf_count": 0,
                # IO proof
                "vectors_jsonl_bytes_read": 0,
                # v2 fields (keep null in v1)
                "sqlite_hits": None,
                "sqlite_query_s": None,
                # api fields (keep null unless you use api backend)
                "api_requests": None,
                "api_retries": None,
                "api_429": None,
            }
        )

    def add(self, key: str, value: Any) -> None:
        # numeric accumulates; otherwise overwrite
        cur = self._data.get(key)
        if isinstance(cur, (int, float)) and isinstance(value, (int, float)):
            self._data[key] = cur + value
        else:
            self._data[key] = value

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def timer_end(self, start_t: float, key: str) -> None:
        self.add(key, time.perf_counter() - start_t)

    _finished: bool = field(default=False, init=False)

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True

        self._data["wall_s"] = time.perf_counter() - self._t0
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        line = json.dumps(self._data, ensure_ascii=False)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())