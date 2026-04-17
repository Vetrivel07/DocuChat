from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedEmbedderId:
    provider: str
    model_name: str
    dim: int
    normalize: bool


def parse_embedder_id(embedder_id: str) -> ParsedEmbedderId:
    """
    Expected format (your current outputs):
      local|BAAI/bge-m3|d1024|norm0|cleanv1|chunkv1
    """
    parts = (embedder_id or "").split("|")
    if len(parts) < 4:
        raise ValueError(f"Invalid embedder_id: {embedder_id}")

    provider = parts[0].strip()
    model_name = parts[1].strip()

    dim_part = parts[2].strip()
    if not dim_part.startswith("d"):
        raise ValueError(f"Invalid embedder_id dim token: {embedder_id}")
    dim = int(dim_part[1:])

    norm_part = parts[3].strip()
    if not norm_part.startswith("norm"):
        raise ValueError(f"Invalid embedder_id norm token: {embedder_id}")
    normalize = norm_part == "norm1"

    return ParsedEmbedderId(
        provider=provider,
        model_name=model_name,
        dim=dim,
        normalize=normalize,
    )