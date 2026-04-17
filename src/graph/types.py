from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


NodeType = Literal["Document", "Section", "Chunk", "Entity"]
EdgeType = Literal["HAS_SECTION", "HAS_CHUNK", "NEXT", "MENTIONS", "RELATES_TO"]

EntityType = Literal[
    "PERSON",
    "ORG",
    "PRODUCT",
    "TOPIC",
    "SKILL",
    "POLICY_TERM",
    "DATE",
]

RelationType = Literal[
    "ASSOCIATED_WITH",
    "HAS_SKILL",
    "HAS_DATE",
    "RELATED_CONCEPT",
]


@dataclass(frozen=True)
class GraphNode:
    node_type: NodeType
    node_id: str
    collection_id: str
    properties: dict


@dataclass(frozen=True)
class GraphEdge:
    edge_type: EdgeType
    from_node_id: str
    to_node_id: str
    collection_id: str
    properties: dict


@dataclass(frozen=True)
class GraphArtifactPaths:
    build_manifest_path: str
    entity_mentions_path: str
    relations_path: str
    graph_stats_path: str


@dataclass(frozen=True)
class EntityMention:
    collection_id: str
    doc_id: str
    chunk_id: str
    entity_id: str
    entity_text: str
    entity_type: str
    confidence: float
    source_chunk_id: str


@dataclass(frozen=True)
class SemanticRelation:
    collection_id: str
    doc_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float
    source_chunk_id: str
    extractor_version: str


@dataclass(frozen=True)
class ExtractedEntity:
    entity_id: str
    entity_text: str
    canonical_name: str
    entity_type: str
    confidence: float


@dataclass(frozen=True)
class ExtractedRelation:
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float