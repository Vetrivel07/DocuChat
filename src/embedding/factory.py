from __future__ import annotations

from src.config import Settings
from src.embedding.base import Embedder
from src.embedding.local_sentence_transformers import SentenceTransformersEmbedder


def _norm_flag(normalize: bool) -> str:
    return "norm1" if normalize else "norm0"


def build_embedder_id(
    *,
    provider: str,
    model_name: str,
    dim: int,
    normalize: bool,
    cleaner_version: str,
    chunker_version: str,
) -> str:
    # stable, versioned identity; update components only when behavior changes
    return f"{provider}|{model_name}|d{dim}|{_norm_flag(normalize)}|clean{cleaner_version}|chunk{chunker_version}"


def get_embedder(settings: Settings) -> Embedder:
    # Stage 6: real local BGE via SentenceTransformers
    if settings.embedding.provider != "local":
        raise ValueError(f"Unsupported embedding provider: {settings.embedding.provider}")

    # Create a temporary model to discover dim, then build embedder_id deterministically
    temp = SentenceTransformersEmbedder(
        model_name=settings.embedding.model_name,
        normalize=settings.embedding.normalize,
        embedder_id="temp",
    )

    embedder_id = build_embedder_id(
        provider="local",
        model_name=settings.embedding.model_name,
        dim=temp.dim,
        normalize=settings.embedding.normalize,
        cleaner_version=settings.versions.cleaner,
        chunker_version=settings.versions.chunker,
    )

    # Recreate with final embedder_id (clean)
    return SentenceTransformersEmbedder(
        model_name=settings.embedding.model_name,
        normalize=settings.embedding.normalize,
        embedder_id=embedder_id,
    )
