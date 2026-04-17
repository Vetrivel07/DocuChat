from __future__ import annotations

from dataclasses import asdict

from neo4j import Driver

from src.graph.models import GraphBuildManifestModel, GraphStatsModel
from src.graph.types import EntityMention, SemanticRelation
from src.utils.atomic_io import atomic_write_json, atomic_write_jsonl


def _entity_mentions_from_graph(driver: Driver, collection_id: str) -> list[EntityMention]:
    query = """
    MATCH (e)-[:FROM_CHUNK]->(c:Chunk)
    WHERE c.collection_id = $collection_id AND c.chunk_id IS NOT NULL
    WITH e, c,
         [lbl IN labels(e) WHERE lbl <> '__KGBuilder__' AND lbl <> '__Entity__'][0] AS entity_type,
         [k IN keys(e) WHERE k <> '__tmp_internal_id' AND k <> 'embedding'][0] AS first_key
    RETURN DISTINCT
        c.doc_id AS doc_id,
        c.chunk_id AS chunk_id,
        coalesce(e.uuid, e.id, toString(id(e))) AS entity_id,
        coalesce(e.name, e.title, e.description,
                 e[first_key], toString(id(e))) AS entity_text,
        entity_type
    ORDER BY doc_id, chunk_id, entity_text
    """
    out: list[EntityMention] = []
    with driver.session() as session:
        for row in session.run(query, collection_id=collection_id):
            entity_text = str(row["entity_text"] or "").strip()
            if not entity_text:
                continue
            out.append(
                EntityMention(
                    collection_id=collection_id,
                    doc_id=str(row["doc_id"]),
                    chunk_id=str(row["chunk_id"]),
                    entity_id=str(row["entity_id"]),
                    entity_text=str(row["entity_text"]),
                    entity_type=str(row["entity_type"] or "Entity"),
                    confidence=1.0,
                    source_chunk_id=str(row["chunk_id"]),
                )
            )
    return out


def _relations_from_graph(driver: Driver, collection_id: str) -> list[SemanticRelation]:
    query = """
    MATCH (a)-[r]->(b)
    MATCH (a)-[:FROM_CHUNK]->(c:Chunk)
    WHERE c.collection_id = $collection_id
      AND c.chunk_id IS NOT NULL
      AND type(r) <> 'FROM_CHUNK'
    RETURN DISTINCT
        c.doc_id AS doc_id,
        c.chunk_id AS source_chunk_id,
        coalesce(a.uuid, a.id, toString(id(a))) AS source_entity_id,
        coalesce(b.uuid, b.id, toString(id(b))) AS target_entity_id,
        type(r) AS relation_type
    ORDER BY doc_id, source_chunk_id, relation_type
    """
    out: list[SemanticRelation] = []
    with driver.session() as session:
        for row in session.run(query, collection_id=collection_id):
            out.append(
                SemanticRelation(
                    collection_id=collection_id,
                    doc_id=str(row["doc_id"]),
                    source_entity_id=str(row["source_entity_id"]),
                    target_entity_id=str(row["target_entity_id"]),
                    relation_type=str(row["relation_type"]),
                    confidence=1.0,
                    source_chunk_id=str(row["source_chunk_id"]),
                    extractor_version="neo4j_graphrag_v1",
                )
            )
    return out


def _graph_stats(driver: Driver, collection_id: str) -> GraphStatsModel:
    stats = GraphStatsModel(collection_id=collection_id)

    with driver.session() as session:
        stats.chunk_nodes = int(
            session.run(
                "MATCH (c:Chunk {collection_id:$collection_id}) RETURN count(c) AS n",
                collection_id=collection_id,
            ).single()["n"]
        )
        stats.doc_nodes = int(
            session.run(
                "MATCH (d:Document {collection_id:$collection_id}) RETURN count(d) AS n",
                collection_id=collection_id,
            ).single()["n"]
        )
        stats.has_chunk_edges = int(
            session.run(
                """
                MATCH (:Document {collection_id:$collection_id})-[r:HAS_CHUNK]->(:Chunk {collection_id:$collection_id})
                RETURN count(r) AS n
                """,
                collection_id=collection_id,
            ).single()["n"]
        )
        stats.next_edges = int(
            session.run(
                """
                MATCH (:Chunk {collection_id:$collection_id})-[r:NEXT]->(:Chunk {collection_id:$collection_id})
                RETURN count(r) AS n
                """,
                collection_id=collection_id,
            ).single()["n"]
        )
        stats.mentions_edges = int(
            session.run(
                """
                MATCH ()-[r:FROM_CHUNK]->(:Chunk {collection_id:$collection_id})
                RETURN count(r) AS n
                """,
                collection_id=collection_id,
            ).single()["n"]
        )
        stats.relates_to_edges = int(
            session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE type(r) <> 'FROM_CHUNK'
                  AND (a.collection_id = $collection_id
                       OR b.collection_id = $collection_id)
                RETURN count(r) AS n
                """,
                collection_id=collection_id,
            ).single()["n"]
        )

    return stats


def write_graph_artifacts(
    *,
    driver: Driver,
    collection_id: str,
    graphs_dir,
    provider: str,
    database: str,
) -> None:
    out_dir = graphs_dir / collection_id
    out_dir.mkdir(parents=True, exist_ok=True)

    mentions = _entity_mentions_from_graph(driver, collection_id)
    relations = _relations_from_graph(driver, collection_id)
    stats = _graph_stats(driver, collection_id)

    manifest = GraphBuildManifestModel(
        collection_id=collection_id,
        graph_version="neo4j-graphrag-v1",
        provider=provider,
        database=database,
        docs_count=stats.doc_nodes,
        chunks_count=stats.chunk_nodes,
        entities_count=len(mentions),
        relations_count=len(relations),
    )

    atomic_write_jsonl(out_dir / "entity_mentions.jsonl", [asdict(x) for x in mentions])
    atomic_write_jsonl(out_dir / "relations.jsonl", [asdict(x) for x in relations])
    atomic_write_json(out_dir / "graph_stats.json", stats.model_dump())
    atomic_write_json(out_dir / "build_manifest.json", manifest.model_dump())