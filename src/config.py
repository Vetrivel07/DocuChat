from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> None:
    """
    Minimal .env loader (no extra dependency).
    - Ignores blank lines and comments (# ...)
    - Supports KEY=VALUE (VALUE may be quoted)
    - Does NOT override already-set environment variables
    """
    if not dotenv_path.exists():
        return

    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")

        if not k:
            continue
        if k in os.environ:
            continue

        os.environ[k] = v


def _env_str(key: str, default: str) -> str:
    v = os.environ.get(key)
    return default if v is None or v == "" else str(v)


def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key)
    try:
        return int(v) if v is not None and v != "" else default
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    v = os.environ.get(key)
    try:
        return float(v) if v is not None and v != "" else default
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Versions:
    extractor: str = "v1"
    cleaner: str = "v1"
    chunker: str = "v1"
    indexer: str = "faiss-v1"
    graph: str = "neo4j-v1"


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "local"
    model_name: str = "BAAI/bge-m3"
    normalize: bool = False


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 10
    max_context_chunks: int = 3
    history_turns: int = 5
    rerank_enabled: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    openai_api_key: str = ""  # required when provider=openai


@dataclass(frozen=True)
class Settings:
    project_root: Path
    storage_root: Path

    versions: Versions = Versions()
    embedding: EmbeddingConfig = EmbeddingConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    llm: LlmConfig = LlmConfig()

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
    def logs_dir(self) -> Path: return self.storage_root / "logs"

    @property
    def query_log_path(self) -> Path: return self.logs_dir / "query_log.jsonl"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[1]

    # load .env once (project root)
    _load_dotenv(project_root / ".env")

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

    retrieval = RetrievalConfig(
        top_k=_env_int("TOP_K", 10),
        max_context_chunks=_env_int("MAX_CONTEXT_CHUNKS", 3),
        history_turns=_env_int("HISTORY_TURNS", 5),
        rerank_enabled=_env_bool("RERANK_ENABLED", False),
        rerank_model=_env_str("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
    )

    llm = LlmConfig(
        provider=_env_str("LLM_PROVIDER", "openai"),
        model=_env_str("LLM_MODEL", "gpt-4o-mini"),
        temperature=_env_float("LLM_TEMPERATURE", 0.0),
        openai_api_key=_env_str("OPENAI_API_KEY", ""),
    )

    return Settings(
        project_root=project_root,
        storage_root=storage_root,
        versions=Versions(),
        embedding=EmbeddingConfig(),
        retrieval=retrieval,
        llm=llm,
    )