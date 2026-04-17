from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class DocumentNodeModel(BaseModel):
    node_id: str
    collection_id: str
    doc_id: str
    file_name: str
    file_type: str
    raw_path: Optional[str] = None


class SectionNodeModel(BaseModel):
    node_id: str
    collection_id: str
    doc_id: str
    section_name: str
    order_index: int = 0


class ChunkNodeModel(BaseModel):
    node_id: str
    collection_id: str
    doc_id: str
    chunk_id: str
    page_num: Optional[int] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    text_clean: str = ""


class EntityNodeModel(BaseModel):
    node_id: str
    collection_id: str
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)


class EntityMentionModel(BaseModel):
    collection_id: str
    doc_id: str
    chunk_id: str
    entity_id: str
    entity_text: str
    canonical_name: str
    entity_type: str
    confidence: float
    source_chunk_id: str


class SemanticRelationModel(BaseModel):
    collection_id: str
    doc_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float
    source_chunk_id: str
    extractor_version: str


class GraphBuildManifestModel(BaseModel):
    collection_id: str
    graph_version: str
    provider: str
    database: str
    docs_count: int
    chunks_count: int
    entities_count: int
    relations_count: int


class GraphStatsModel(BaseModel):
    collection_id: str
    doc_nodes: int = 0
    section_nodes: int = 0
    chunk_nodes: int = 0
    entity_nodes: int = 0
    has_chunk_edges: int = 0
    has_section_edges: int = 0
    next_edges: int = 0
    mentions_edges: int = 0
    relates_to_edges: int = 0