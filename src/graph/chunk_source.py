from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.config import Settings
from src.ingestion.registry import load_manifest
from src.utils.atomic_io import iter_jsonl


@dataclass(frozen=True)
class SourceChunk:
    collection_id: str
    doc_id: str
    file_name: str
    file_type: str
    chunk_id: str
    page_num: int | None
    start_char: int | None
    end_char: int | None
    text_clean: str
    text_original: str


def load_collection_chunks(settings: Settings, collection_id: str) -> list[SourceChunk]:
    manifest = load_manifest(settings.collections_dir, collection_id)

    doc_meta: dict[str, dict] = {
        str(d.get("doc_id")): d for d in (manifest.get("docs") or []) if d.get("doc_id")
    }

    out: list[SourceChunk] = []
    chunk_dir = settings.chunks_dir / collection_id
    if not chunk_dir.exists():
        return out

    for p in sorted(chunk_dir.glob("*.jsonl"), key=lambda x: x.stem):
        doc_id = p.stem
        meta = doc_meta.get(doc_id, {})
        file_name = str(meta.get("file_name") or doc_id)
        file_type = str(meta.get("file_type") or "unknown")

        for row in iter_jsonl(p):
            chunk_id = str(row.get("chunk_id") or "").strip()
            if not chunk_id:
                continue

            text_clean = str(row.get("text_clean") or "").strip()
            text_original = str(row.get("text_original") or "")
            if not text_clean:
                continue

            out.append(
                SourceChunk(
                    collection_id=collection_id,
                    doc_id=doc_id,
                    file_name=file_name,
                    file_type=file_type,
                    chunk_id=chunk_id,
                    page_num=row.get("page_num"),
                    start_char=row.get("start_char"),
                    end_char=row.get("end_char"),
                    text_clean=text_clean,
                    text_original=text_original,
                )
            )

    out.sort(
        key=lambda c: (
            c.doc_id,
            0 if c.page_num is None else int(c.page_num),
            0 if c.start_char is None else int(c.start_char),
            0 if c.end_char is None else int(c.end_char),
            c.chunk_id,
        )
    )
    return out