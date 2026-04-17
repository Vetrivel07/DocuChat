# src/services/query_service.py

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.config import get_settings
from src.llm.client import LLMClient
from src.prompts.grounded_prompt import PromptConfig, build_grounded_prompt
from src.retrieval.active_index import resolve_active_index
from src.retrieval.types import ActiveIndex
from src.retrieval.vector_retriever import RetrievedChunk, VectorRetriever
from src.retrieval.graph_retriever import GraphRetriever
from src.retrieval.hybrid_retriever import HybridRetriever

from src.retrieval.reranker import CrossEncoderReranker, RerankConfig
from src.eval.logger import EvalLogger, build_query_log_row

from src.ingestion.registry import load_manifest

_CIT_RE = re.compile(r"\[(\d{1,3})\]")

def _resolve_retrieval_mode(*, requested: Optional[str], manifest: Dict[str, Any], default_mode: str) -> str:
    mode = (requested or manifest.get("retrieval_mode") or default_mode or "vector").strip().lower()
    if mode not in {"vector", "hybrid"}:
        raise ValueError(f"Invalid retrieval_mode: {mode}")
    return mode

def _extract_citations(text: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for m in _CIT_RE.finditer(text or ""):
        cid = m.group(1)
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


@dataclass(frozen=True)
class QueryServiceConfig:
    top_k: int = 10
    max_context_chunks: int = 3
    history_turns: int = 5
    rerank_enabled: bool = False


class QueryService:
    def __init__(
        self,
        *,
        llm: LLMClient,
        retriever: VectorRetriever,
        graph_retriever: Optional[GraphRetriever] = None,
        hybrid_retriever: Optional[HybridRetriever] = None,
        logger: Optional[EvalLogger] = None,
        cfg: Optional[QueryServiceConfig] = None,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._graph_retriever = graph_retriever
        self._hybrid_retriever = hybrid_retriever
        self._logger = logger
        self._cfg = cfg or QueryServiceConfig()

    def run(
        self,
        *,
        collection_id: str,
        question: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        retrieval_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        s = get_settings()
        manifest = load_manifest(s.collections_dir, collection_id)

        effective_mode = _resolve_retrieval_mode(
            requested=retrieval_mode,
            manifest=manifest,
            default_mode=s.retrieval.default_mode,
        )

        # 1) Active index
        active: ActiveIndex = resolve_active_index(s, collection_id)

        # 2) Query handling
        rewritten = question

        # 3) Retrieval (FAISS)
        vector_rows: List[RetrievedChunk] = self._retriever.search(
            active=active,
            query_text=rewritten,
            top_k=self._cfg.top_k,
        )

        graph_rows: List[RetrievedChunk] = []
        if effective_mode == "hybrid":
            if self._graph_retriever is not None:
                graph_rows = self._graph_retriever.search(
                    collection_id=collection_id,
                    query_text=rewritten,
                    top_k=s.retrieval.graph_top_k,
                )

            if self._hybrid_retriever is not None:
                retrieved = self._hybrid_retriever.merge(
                    vector_rows=vector_rows,
                    graph_rows=graph_rows,
                    top_k=self._cfg.top_k,
                )
            else:
                retrieved = list(vector_rows)
        elif effective_mode == "vector":
            retrieved = list(vector_rows)
        else:
            raise ValueError(f"Unsupported retrieval_mode: {effective_mode}")

        retrieved_before = [
            {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "score": c.score}
            for c in retrieved
        ]

        # 4) Rerank (Stage 9)
        rerank_cfg = RerankConfig.from_env()
        reranked: Optional[List[RetrievedChunk]] = None
        final_for_context = list(retrieved)

        rerank_on = bool(self._cfg.rerank_enabled) and bool(rerank_cfg.enabled)
        if rerank_on and len(retrieved) > 1:
            reranker = CrossEncoderReranker(rerank_cfg)
            reranked = reranker.rerank(rewritten, retrieved)
            final_for_context = reranked[: max(int(rerank_cfg.top_n), 1)]

        reranked_slim = (
            [{"chunk_id": c.chunk_id, "doc_id": c.doc_id, "score": c.score} for c in reranked]
            if reranked is not None else None
        )

        final_ctx = final_for_context[: self._cfg.max_context_chunks]

        # 5) Prompt
        doc_name_by_id = {
            d.get("doc_id"): (d.get("file_name") or d.get("doc_id") or "unknown")
            for d in (manifest.get("docs") or [])
        }

        source_names = [doc_name_by_id.get(c.doc_id, c.doc_id) for c in final_ctx]

        prompt = build_grounded_prompt(
            question=rewritten,
            chunks=final_ctx,
            source_names=source_names,
            chat_history=chat_history or [],
            cfg=PromptConfig(max_context_chunks=self._cfg.max_context_chunks),
        )

        # 6) LLM
        answer_text = self._llm.generate(prompt)

        # 7) Sources payload
        sources = [
                    {
                        "source_idx": i + 1,  # aligns with [1], [2], ...
                        "source_name": source_names[i],
                        "chunk_id": c.chunk_id,
                        "doc_id": c.doc_id,
                        "page_num": c.page_num,
                        "start_char": c.start_char,
                        "end_char": c.end_char,
                        "score": c.score,
                        "text": c.text,  # needed for hover
                    }
                    for i, c in enumerate(final_ctx)
                ]

        # 8) Stage 7 logging (if logger provided)
        citations = _extract_citations(answer_text)
        if self._logger is not None:
            row = build_query_log_row(
                run_id=str(uuid.uuid4()),
                retrieval_mode=("vector_v2" if effective_mode == "vector" else "hybrid_v1"),
                collection_id=collection_id,
                embedder_id=active.embedder_id,
                embedder_dir=active.embedder_dir,
                top_k=self._cfg.top_k,
                max_context_chunks=self._cfg.max_context_chunks,
                original_query=question,
                rewritten_query=rewritten,
                retrieved_before_rerank=retrieved_before,
                reranked=reranked_slim,
                final_context=sources,
                answer_text=answer_text,
                citations=citations,
                extra={
                    "vector_retrieved": [
                        {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "score": c.score}
                        for c in vector_rows
                    ],
                    "graph_retrieved": [
                        {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "score": c.score}
                        for c in graph_rows
                    ],
                },
            )
            self._logger.log(row)

        return {
            "answer": answer_text,
            "sources": sources,
            "debug": {
                "original_query": question,
                "rewritten_query": rewritten,
                "embedder_id": active.embedder_id,
                "embedder_dir": active.embedder_dir,
                "top_k": self._cfg.top_k,
                "max_context_chunks": self._cfg.max_context_chunks,
                "rerank_enabled": rerank_on,
                "rerank_model": rerank_cfg.model_name if rerank_cfg.enabled else None,
                "rerank_top_n": rerank_cfg.top_n if rerank_cfg.enabled else None,
                "citations": citations,
                "retrieval_mode": effective_mode, 
            },
        }