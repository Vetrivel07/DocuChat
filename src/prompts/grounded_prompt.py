# from __future__ import annotations

# from dataclasses import dataclass
# from typing import List, Optional

# from src.retrieval.vector_retriever import RetrievedChunk


# @dataclass(frozen=True)
# class PromptConfig:
#     max_context_chunks: int = 3


# def _format_chunk(c: RetrievedChunk) -> str:
#     loc = []
#     if c.page_num is not None:
#         loc.append(f"page={c.page_num}")
#     if c.start_char is not None and c.end_char is not None:
#         loc.append(f"chars={c.start_char}-{c.end_char}")
#     loc_s = (", ".join(loc)) if loc else "loc=unknown"

#     # Chunk header MUST include chunk_id for citation
#     return (
#         f"[CHUNK {c.chunk_id} | doc={c.doc_id} | {loc_s}]\n"
#         f"{c.text}".strip()
#     )


# def build_grounded_prompt(
#     *,
#     question: str,
#     chunks: List[RetrievedChunk],
#     cfg: Optional[PromptConfig] = None,
# ) -> str:
#     cfg = cfg or PromptConfig()
#     chunks = (chunks or [])[: cfg.max_context_chunks]

#     context_blocks = "\n\n---\n\n".join(_format_chunk(c) for c in chunks)

#     return f"""You are a document-grounded assistant.

# RULES (strict):
# - Use ONLY the provided CONTEXT. Do not use external knowledge.
# - If the answer is not explicitly supported by the CONTEXT, reply exactly: Not found in documents.
# - Every factual sentence MUST include citations to supporting chunk_id(s) in square brackets, e.g. [bb7a...].
# - Do not cite chunks that do not support the sentence. No invented citations.
# - If multiple chunks support a sentence, cite all relevant chunk_ids.

# QUESTION:
# {question}

# CONTEXT:
# {context_blocks}

# ANSWER:
# """


from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from src.retrieval.vector_retriever import RetrievedChunk


@dataclass(frozen=True)
class PromptConfig:
    max_context_chunks: int = 3


def _format_source(i: int, c: RetrievedChunk, source_name: str) -> str:
    loc = []
    if c.page_num is not None:
        loc.append(f"page={c.page_num}")
    if c.start_char is not None and c.end_char is not None:
        loc.append(f"chars={c.start_char}-{c.end_char}")
    loc_s = (", ".join(loc)) if loc else "loc=unknown"

    # IMPORTANT:
    # - Citations are numeric: [1], [2], ...
    # - We do NOT put chunk_id in brackets to avoid model citing hashes.
    return (
        f"[SOURCE {i} | {source_name} | {loc_s}]\n"
        f"{c.text}".strip()
    )


def build_grounded_prompt(
    *,
    question: str,
    chunks: List[RetrievedChunk],
    source_names: Optional[Sequence[str]] = None,
    cfg: Optional[PromptConfig] = None,
) -> str:
    cfg = cfg or PromptConfig()
    chunks = (chunks or [])[: cfg.max_context_chunks]

    names: List[str] = []
    if source_names is None:
        names = [getattr(c, "doc_id", "unknown") for c in chunks]
    else:
        names = list(source_names)[: len(chunks)]
        while len(names) < len(chunks):
            names.append(getattr(chunks[len(names)], "doc_id", "unknown"))

    context_blocks = "\n\n---\n\n".join(
        _format_source(i + 1, c, names[i]) for i, c in enumerate(chunks)
    )

    return f"""You are a document-grounded assistant.

RULES (strict):
- Use ONLY the provided CONTEXT. Do not use external knowledge.
- If the answer is not explicitly supported by the CONTEXT, reply exactly: Not found in documents.
- Every factual sentence MUST include citations to supporting SOURCE number(s) in square brackets, e.g. [1] or [1][2].
- Do not cite sources that do not support the sentence. No invented citations.

QUESTION:
{question}

CONTEXT:
{context_blocks}

ANSWER:
"""