from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sentence_transformers import SentenceTransformer


@dataclass
class SentenceTransformersEmbedder:
    model_name: str
    normalize: bool
    embedder_id: str

    def __post_init__(self) -> None:
        self._model = SentenceTransformer(self.model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vecs = self._model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        # vecs is numpy array; convert to plain lists (JSON safe)
        return [v.tolist() for v in vecs]
