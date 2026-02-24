from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Versions:
    extractor: str = "v1"
    cleaner: str = "v1"
    chunker: str = "v1"
    indexer: str = "faiss-v1"
    graph: str = "neo4j-v1"


@dataclass(frozen=True)
class EmbeddingConfig:
    # Stage 6: real embeddings, swappable by config + factory
    provider: str = "local"
    # BGE-M3 (SentenceTransformers compatible). You can change this later easily.
    model_name: str = "BAAI/bge-m3"
    normalize: bool = False  # keep optional; set True only if you want normalized vectors


@dataclass(frozen=True)
class Settings:
    project_root: Path
    storage_root: Path
    versions: Versions = Versions()
    embedding: EmbeddingConfig = EmbeddingConfig()

    @property
    def raw_dir(self) -> Path: return self.storage_root / "raw"

    @property
    def processed_dir(self) -> Path: return self.storage_root / "processed"

    @property
    def chunks_dir(self) -> Path: return self.storage_root / "chunks"

    @property
    def vectors_dir(self) -> Path: return self.storage_root / "vectors"

    @property
    def indexes_dir(self) -> Path: return self.storage_root / "indexes"

    @property
    def collections_dir(self) -> Path: return self.storage_root / "collections"

    @property
    def jobs_dir(self) -> Path: return self.storage_root / "jobs"

    @property
    def chat_history_dir(self) -> Path: return self.storage_root / "chat_history"

    @property
    def logs_dir(self) -> Path:
        return self.storage_root / "logs"


def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[1]
    storage_root = project_root / "storage"
    storage_root.mkdir(parents=True, exist_ok=True)

    for d in [
        storage_root / "raw",
        storage_root / "processed",
        storage_root / "chunks",
        storage_root / "vectors",
        storage_root / "indexes",
        storage_root / "collections",
        storage_root / "jobs",
        storage_root / "chat_history",
        storage_root / "logs",

    ]:
        d.mkdir(parents=True, exist_ok=True)

    return Settings(project_root=project_root, storage_root=storage_root)
