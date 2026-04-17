from __future__ import annotations

import asyncio
from collections import defaultdict

from neo4j import GraphDatabase
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline

from src.config import Settings
from src.graph.artifacts import write_graph_artifacts
from src.graph.chunk_source import SourceChunk, load_collection_chunks
from src.graph.factory import get_graph_store
from src.graph.llm_adapter import build_graph_embedder, build_graph_llm
from src.graph.types import GraphEdge, GraphNode


class GraphBuilder:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._cfg = settings.graph

    def build(self, collection_id: str) -> None:
        if not self._cfg.enabled or not self._cfg.build_enabled:
            return

        chunks = load_collection_chunks(self._s, collection_id)
        if not chunks:
            return

        store = get_graph_store(self._s)
        store.ensure_schema()

        driver = GraphDatabase.driver(
            self._cfg.uri,
            auth=(self._cfg.user, self._cfg.password),
        )

        try:
            self._run_kg_pipeline(driver, chunks)
            self._stamp_chunk_metadata(driver, chunks)
            self._upsert_document_node(store, chunks)
            self._link_documents_to_chunks_cypher(driver, chunks)
            self._link_chunk_adjacency(driver, chunks)

            write_graph_artifacts(
                driver=driver,
                collection_id=collection_id,
                graphs_dir=self._s.graphs_dir,
                provider=self._cfg.provider,
                database=self._cfg.database,
            )
        finally:
            driver.close()
            store.close()

    def _run_kg_pipeline(self, driver, chunks: list[SourceChunk]) -> None:
        llm = build_graph_llm(self._cfg)
        embedder = build_graph_embedder(self._cfg)

        kg_builder = SimpleKGPipeline(
            llm=llm,
            driver=driver,
            embedder=embedder,
            schema=self._cfg.schema_mode,
            on_error="IGNORE",
            from_pdf=False,
        )

        async def _run_all():
            for chunk in chunks:
                await kg_builder.run_async(text=chunk.text_clean)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside a running event loop (FastAPI/uvicorn)
            # Run in a separate thread to avoid blocking
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run_all())
                future.result()
        else:
            # No running event loop — safe to use asyncio.run directly
            asyncio.run(_run_all())

    def _upsert_document_and_chunk_shells(self, store, chunks: list[SourceChunk]) -> None:
        """doc_seen: set[str] = set()
        nodes: list[GraphNode] = []

        for ch in chunks:
            doc_node_id = f"doc::{ch.collection_id}::{ch.doc_id}"
            chunk_node_id = f"chunk::{ch.collection_id}::{ch.chunk_id}"

            if ch.doc_id not in doc_seen:
                doc_seen.add(ch.doc_id)
                nodes.append(
                    GraphNode(
                        node_type="Document",
                        node_id=doc_node_id,
                        collection_id=ch.collection_id,
                        properties={
                            "doc_id": ch.doc_id,
                            "file_name": ch.file_name,
                            "file_type": ch.file_type,
                        },
                    )
                )

            nodes.append(
                GraphNode(
                    node_type="Chunk",
                    node_id=chunk_node_id,
                    collection_id=ch.collection_id,
                    properties={
                        "chunk_id": ch.chunk_id,
                        "doc_id": ch.doc_id,
                        "page_num": ch.page_num,
                        "start_char": ch.start_char,
                        "end_char": ch.end_char,
                        "text_clean": ch.text_clean,
                    },
                )
            )

        store.upsert_nodes(nodes)
"""
    def _upsert_document_node(self, store, chunks: list[SourceChunk]) -> None:
        doc_seen: set[str] = set()
        nodes: list[GraphNode] = []

        for ch in chunks:
            if ch.doc_id in doc_seen:
                continue
            doc_seen.add(ch.doc_id)
            doc_node_id = f"doc::{ch.collection_id}::{ch.doc_id}"
            nodes.append(
                GraphNode(
                    node_type="Document",
                    node_id=doc_node_id,
                    collection_id=ch.collection_id,
                    properties={
                        "doc_id": ch.doc_id,
                        "file_name": ch.file_name,
                        "file_type": ch.file_type,
                    },
                )
            )

        store.upsert_nodes(nodes)

    def _link_documents_to_chunks(self, store, chunks: list[SourceChunk]) -> None:
        """edges: list[GraphEdge] = []
        for ch in chunks:
            edges.append(
                GraphEdge(
                    edge_type="HAS_CHUNK",
                    from_node_id=f"doc::{ch.collection_id}::{ch.doc_id}",
                    to_node_id=f"chunk::{ch.collection_id}::{ch.chunk_id}",
                    collection_id=ch.collection_id,
                    properties={"doc_id": ch.doc_id, "chunk_id": ch.chunk_id},
                )
            )
        store.upsert_edges(edges)"""
        pass

    def _link_documents_to_chunks_cypher(self, driver, chunks: list[SourceChunk]) -> None:
        query = """
        MATCH (d:Document {node_id: $doc_node_id})
        MATCH (c:Chunk {chunk_id: $chunk_id, collection_id: $collection_id})
        MERGE (d)-[:HAS_CHUNK {doc_id: $doc_id, chunk_id: $chunk_id}]->(c)
        """
        with driver.session(database=self._cfg.database) as session:
            for ch in chunks:
                session.run(
                    query,
                    doc_node_id=f"doc::{ch.collection_id}::{ch.doc_id}",
                    chunk_id=ch.chunk_id,
                    collection_id=ch.collection_id,
                    doc_id=ch.doc_id,
                ).consume()

    def _link_chunk_adjacency(self, driver, chunks: list[SourceChunk]) -> None:
        grouped: dict[str, list[SourceChunk]] = defaultdict(list)
        for ch in chunks:
            grouped[ch.doc_id].append(ch)

        query = """
        MATCH (a:Chunk {chunk_id: $from_chunk_id, collection_id: $collection_id})
        MATCH (b:Chunk {chunk_id: $to_chunk_id, collection_id: $collection_id})
        MERGE (a)-[:NEXT {
            doc_id: $doc_id,
            from_chunk_id: $from_chunk_id,
            to_chunk_id: $to_chunk_id
        }]->(b)
        """

        with driver.session(database=self._cfg.database) as session:
            for _, doc_chunks in grouped.items():
                doc_chunks.sort(key=lambda c: (
                    0 if c.page_num is None else int(c.page_num),
                    0 if c.start_char is None else int(c.start_char),
                    0 if c.end_char is None else int(c.end_char),
                    c.chunk_id,
                ))
                for left, right in zip(doc_chunks, doc_chunks[1:]):
                    session.run(
                        query,
                        from_chunk_id=left.chunk_id,
                        to_chunk_id=right.chunk_id,
                        collection_id=left.collection_id,
                        doc_id=left.doc_id,
                    ).consume()

    def _stamp_chunk_metadata(self, driver, chunks: list[SourceChunk]) -> None:
        """
        Stamp our metadata onto KGPipeline-created Chunk nodes.
        Match by first 200 chars of text — KGPipeline preserves text exactly.
        """
        stamp_query = """
        MATCH (c:Chunk)
        WHERE (c.chunk_id IS NULL OR c.chunk_id = "")
        AND left(coalesce(c.text, c.text_clean, ""), 200) = left($text_clean, 200)
        WITH c LIMIT 1
        SET c.collection_id = $collection_id,
            c.doc_id        = $doc_id,
            c.chunk_id      = $chunk_id,
            c.page_num      = $page_num,
            c.start_char    = $start_char,
            c.end_char      = $end_char,
            c.text_clean    = $text_clean,
            c.text          = $text_clean
        """
        with driver.session(database=self._cfg.database) as session:
            for ch in chunks:
                session.run(
                    stamp_query,
                    collection_id=ch.collection_id,
                    doc_id=ch.doc_id,
                    chunk_id=ch.chunk_id,
                    page_num=ch.page_num,
                    start_char=ch.start_char,
                    end_char=ch.end_char,
                    text_clean=ch.text_clean,
                ).consume()