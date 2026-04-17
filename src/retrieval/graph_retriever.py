from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from neo4j import GraphDatabase

from src.config import Settings
from src.retrieval.vector_retriever import RetrievedChunk


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{2,}")


@dataclass
class GraphRetriever:
    s: Settings

    def _query_terms(self, query_text: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for m in _TOKEN_RE.finditer(query_text or ""):
            t = m.group(0).casefold()
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    def search(
        self,
        *,
        collection_id: str,
        query_text: str,
        top_k: int,
    ) -> List[RetrievedChunk]:
        if not self.s.graph.enabled:
            return []

        terms = self._query_terms(query_text)
        if not terms:
            return []

        driver = GraphDatabase.driver(
            self.s.graph.uri,
            auth=(self.s.graph.user, self.s.graph.password),
        )

        cypher = """
        WITH $terms AS terms
        MATCH (e)-[:FROM_CHUNK]->(c:Chunk {collection_id: $collection_id})
        WHERE c.chunk_id IS NOT NULL
        WITH e, c, terms,
             [k IN keys(e) WHERE k <> '__tmp_internal_id' AND k <> 'embedding'][0] AS first_key
        WITH e, c, terms,
             coalesce(e.name, e.title, e.description, e[first_key], "") AS entity_text
        WHERE ANY(term IN terms WHERE toLower(entity_text) CONTAINS term)
        WITH c,
             collect(DISTINCT entity_text) AS matched_entities,
             count(DISTINCT e) AS entity_hits
        RETURN
            c.chunk_id AS chunk_id,
            c.doc_id AS doc_id,
            c.page_num AS page_num,
            c.start_char AS start_char,
            c.end_char AS end_char,
            coalesce(c.text_clean, c.text, "") AS text,
            entity_hits AS score,
            matched_entities
        ORDER BY entity_hits DESC, c.doc_id ASC, c.page_num ASC, c.start_char ASC
        LIMIT $top_k
        """

        out: list[RetrievedChunk] = []
        try:
            with driver.session(database=self.s.graph.database) as session:
                rows = session.run(
                    cypher,
                    collection_id=collection_id,
                    terms=terms,
                    top_k=int(top_k),
                )
                for row in rows:
                    chunk_id = str(row.get("chunk_id") or "")
                    doc_id = str(row.get("doc_id") or "")
                    text = str(row.get("text") or "")
                    if not chunk_id or not doc_id or not text:
                        continue

                    out.append(
                        RetrievedChunk(
                            chunk_id=chunk_id,
                            doc_id=doc_id,
                            page_num=int(row["page_num"]) if row.get("page_num") is not None else None,
                            start_char=int(row["start_char"]) if row.get("start_char") is not None else None,
                            end_char=int(row["end_char"]) if row.get("end_char") is not None else None,
                            score=float(row.get("score") or 0.0),  # graph score: higher is better
                            text=text,
                        )
                    )
        finally:
            driver.close()

        return out