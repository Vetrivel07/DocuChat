# src/retrieval/reranker.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Sequence

from sentence_transformers import CrossEncoder

from src.retrieval.vector_retriever import RetrievedChunk


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


@dataclass(frozen=True)
class RerankConfig:
    enabled: bool = True
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_n: int = 5  # how many to keep after rerank (before final context cut)

    @staticmethod
    def from_env() -> "RerankConfig":
        return RerankConfig(
            enabled=_env_bool("RERANK_ENABLED", True),
            model_name=os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            top_n=_env_int("RERANK_TOP_N", 5),
        )


class CrossEncoderReranker:
    """
    Cross-encoder reranker:
    scores (query, chunk_text) pairs and reorders candidates by relevance.

    Keeps your system swap-friendly:
    - config from env
    - model load is lazy
    """

    def __init__(self, cfg: RerankConfig) -> None:
        self._cfg = cfg
        self._model: Optional[CrossEncoder] = None

    def _get_model(self) -> CrossEncoder:
        if self._model is None:
            self._model = CrossEncoder(self._cfg.model_name)
        return self._model

    @staticmethod
    def _chunk_text(c: RetrievedChunk) -> str:
        # Be tolerant to your evolving RetrievedChunk schema.
        txt = getattr(c, "text_clean", None) or getattr(c, "text", None)
        if not txt:
            # If this happens, fix VectorRetriever to attach text_clean.
            raise ValueError("RetrievedChunk missing text_clean/text required for reranking.")
        return str(txt)

    def rerank(self, query: str, candidates: Sequence[RetrievedChunk]) -> List[RetrievedChunk]:
        if not candidates:
            return []

        model = self._get_model()

        pairs = [(query, self._chunk_text(c)) for c in candidates]
        scores = model.predict(pairs)

        # Stable sort: primary = rerank score desc, secondary = original faiss score asc/desc not guaranteed;
        # keep original order as final tie-breaker by enumerating.
        indexed = list(enumerate(candidates))
        ranked = sorted(
            zip(indexed, scores),
            key=lambda x: (-float(x[1]), x[0][0]),  # score desc, original index asc
        )

        reranked = [pair[0][1] for pair in ranked]
        return reranked[: max(int(self._cfg.top_n), 1)]