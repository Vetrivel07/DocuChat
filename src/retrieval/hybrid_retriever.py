from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from src.retrieval.vector_retriever import RetrievedChunk


@dataclass
class HybridRetriever:
    vector_weight: float = 0.65
    graph_weight: float = 0.35

    @staticmethod
    def _normalize_vector_scores(rows: List[RetrievedChunk]) -> Dict[str, float]:
        """
        Vector score is L2 distance in current system.
        Lower is better.
        Convert to similarity-like score in [0,1].
        """
        out: Dict[str, float] = {}
        for r in rows:
            out[r.chunk_id] = 1.0 / (1.0 + max(float(r.score), 0.0))
        return out

    @staticmethod
    def _normalize_graph_scores(rows: List[RetrievedChunk]) -> Dict[str, float]:
        """
        Graph score is entity hit count.
        Higher is better.
        """
        if not rows:
            return {}
        max_score = max(max(float(r.score), 0.0) for r in rows)
        if max_score <= 0:
            return {r.chunk_id: 0.0 for r in rows}
        return {r.chunk_id: max(float(r.score), 0.0) / max_score for r in rows}

    def merge(
        self,
        *,
        vector_rows: List[RetrievedChunk],
        graph_rows: List[RetrievedChunk],
        top_k: int,
    ) -> List[RetrievedChunk]:
        v_map = self._normalize_vector_scores(vector_rows)
        g_map = self._normalize_graph_scores(graph_rows)

        by_chunk: Dict[str, RetrievedChunk] = {}

        for row in vector_rows:
            by_chunk[row.chunk_id] = row

        for row in graph_rows:
            if row.chunk_id not in by_chunk:
                by_chunk[row.chunk_id] = row

        scored: list[tuple[float, RetrievedChunk]] = []
        for chunk_id, row in by_chunk.items():
            v = v_map.get(chunk_id, 0.0)
            g = g_map.get(chunk_id, 0.0)
            hybrid_score = (self.vector_weight * v) + (self.graph_weight * g)

            scored.append(
                (
                    hybrid_score,
                    RetrievedChunk(
                        chunk_id=row.chunk_id,
                        doc_id=row.doc_id,
                        page_num=row.page_num,
                        start_char=row.start_char,
                        end_char=row.end_char,
                        score=hybrid_score,   # final hybrid score
                        text=row.text,
                    ),
                )
            )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [row for _, row in scored[: max(1, int(top_k))]]