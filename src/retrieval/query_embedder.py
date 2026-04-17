from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from src.retrieval.embedder_id import ParsedEmbedderId


@dataclass
class QueryEmbedder:
    parsed: ParsedEmbedderId
    _model: Optional[SentenceTransformer] = None

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            # SentenceTransformers supports "BAAI/bge-m3"
            self._model = SentenceTransformer(self.parsed.model_name)
        return self._model

    def embed(self, text: str) -> np.ndarray:
        model = self._load()
        vec = model.encode([text], convert_to_numpy=True, normalize_embeddings=False)
        vec = vec.astype(np.float32, copy=False)

        if vec.shape != (1, self.parsed.dim):
            raise ValueError(f"Query embedding dim mismatch: got {vec.shape}, expected (1,{self.parsed.dim})")

        if self.parsed.normalize:
            # safe normalize
            n = np.linalg.norm(vec, axis=1, keepdims=True)
            n = np.maximum(n, 1e-12)
            vec = vec / n

        return vec