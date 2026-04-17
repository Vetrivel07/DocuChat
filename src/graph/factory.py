from __future__ import annotations

from src.config import Settings
from src.graph.base import GraphStore
from src.graph.providers.neo4j_graph import Neo4jGraphStore


def get_graph_store(settings: Settings) -> GraphStore:
    provider = settings.graph.provider.strip().lower()

    if provider == "neo4j":
        return Neo4jGraphStore(settings.graph)

    raise ValueError(f"Unsupported graph provider: {settings.graph.provider}")
