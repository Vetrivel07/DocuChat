from __future__ import annotations

from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.llm import OpenAILLM

from src.config import GraphConfig


def build_graph_llm(cfg: GraphConfig) -> OpenAILLM:
    provider = (cfg.llm_provider or "").strip().lower()
    if provider != "openai":
        raise ValueError(f"Unsupported GRAPH_LLM_PROVIDER: {cfg.llm_provider}")

    return OpenAILLM(
        model_name=cfg.llm_model,
        model_params={
            "temperature": float(cfg.llm_temperature),
            "response_format": {"type": "json_object"},
        },
    )


def build_graph_embedder(cfg: GraphConfig) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=cfg.embedding_model)