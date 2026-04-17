from __future__ import annotations

from typing import Sequence

from neo4j import GraphDatabase

from src.config import GraphConfig
from src.graph.types import GraphEdge, GraphNode


class Neo4jGraphStore:
    def __init__(self, cfg: GraphConfig) -> None:
        self._cfg = cfg
        self._driver = GraphDatabase.driver(
            cfg.uri,
            auth=(cfg.user, cfg.password),
        )

    def ping(self) -> bool:
        with self._driver.session(database=self._cfg.database) as session:
            val = session.run("RETURN 1 AS ok").single()
            return bool(val and val["ok"] == 1)

    def ensure_schema(self) -> None:
        stmts = [
            "CREATE CONSTRAINT document_node_id IF NOT EXISTS FOR (n:Document) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT section_node_id IF NOT EXISTS FOR (n:Section) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT chunk_node_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.node_id IS UNIQUE",
            "CREATE CONSTRAINT entity_node_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.node_id IS UNIQUE",
            "CREATE INDEX document_doc_id IF NOT EXISTS FOR (n:Document) ON (n.doc_id)",
            "CREATE INDEX chunk_chunk_id IF NOT EXISTS FOR (n:Chunk) ON (n.chunk_id)",
            "CREATE INDEX entity_entity_id IF NOT EXISTS FOR (n:Entity) ON (n.entity_id)",
            "CREATE INDEX entity_canonical_name IF NOT EXISTS FOR (n:Entity) ON (n.canonical_name)",
        ]

        with self._driver.session(database=self._cfg.database) as session:
            for stmt in stmts:
                session.run(stmt).consume()

    def upsert_nodes(self, nodes: Sequence[GraphNode]) -> None:
        if not nodes:
            return

        query = """
        UNWIND $rows AS row
        CALL {
          WITH row
          CALL apoc.merge.node(
            [row.node_type],
            {node_id: row.node_id},
            {
              collection_id: row.collection_id
            },
            row.properties
          ) YIELD node
          SET node += row.properties
          SET node.collection_id = row.collection_id
          RETURN node
        }
        RETURN count(*) AS written
        """

        payload = [
            {
                "node_type": n.node_type,
                "node_id": n.node_id,
                "collection_id": n.collection_id,
                "properties": n.properties,
            }
            for n in nodes
        ]

        with self._driver.session(database=self._cfg.database) as session:
            session.run(query, rows=payload).consume()

    def upsert_edges(self, edges: Sequence[GraphEdge]) -> None:
        if not edges:
            return

        grouped: dict[str, list[GraphEdge]] = {}
        for e in edges:
            grouped.setdefault(e.edge_type, []).append(e)

        with self._driver.session(database=self._cfg.database) as session:
            for edge_type, group in grouped.items():
                query = f"""
                UNWIND $rows AS row
                MATCH (a {{node_id: row.from_node_id}})
                MATCH (b {{node_id: row.to_node_id}})
                MERGE (a)-[r:{edge_type}]->(b)
                SET r += row.properties
                SET r.collection_id = row.collection_id
                """
                payload = [
                    {
                        "from_node_id": e.from_node_id,
                        "to_node_id": e.to_node_id,
                        "collection_id": e.collection_id,
                        "properties": e.properties,
                    }
                    for e in group
                ]
                session.run(query, rows=payload).consume()

    def purge_collection(self, collection_id: str) -> None:
        with self._driver.session(database=self._cfg.database) as session:
            # delete chunks for this collection
            session.run(
                """
                MATCH (c:Chunk {collection_id: $collection_id})
                DETACH DELETE c
                """,
                collection_id=collection_id,
            ).consume()

            # delete documents for this collection
            session.run(
                """
                MATCH (d:Document {collection_id: $collection_id})
                DETACH DELETE d
                """,
                collection_id=collection_id,
            ).consume()

            # delete orphaned non-document/non-chunk nodes
            session.run(
                """
                MATCH (n)
                WHERE NOT n:Chunk AND NOT n:Document
                OPTIONAL MATCH (n)-[:FROM_CHUNK]->(c:Chunk)
                WITH n, count(c) AS refs
                WHERE refs = 0
                DETACH DELETE n
                """
            ).consume()

    def close(self) -> None:
        self._driver.close()
