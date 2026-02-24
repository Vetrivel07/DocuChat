from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    embedder_id: str
    dim: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...
