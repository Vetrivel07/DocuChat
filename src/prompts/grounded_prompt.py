# src/prompts/grounded_prompt.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from src.retrieval.vector_retriever import RetrievedChunk


@dataclass(frozen=True)
class PromptConfig:
    max_context_chunks: int = 3


def _format_source(i: int, c: RetrievedChunk, source_name: str) -> str:
    """
    Format a retrieved chunk as a labelled source block.

    Header format:
      [SOURCE N | filename | page=X | section=Main > Sub | type_hint]
    """
    # ── location ───────────────────────────────────────────────────────────────
    loc_parts = []
    if c.page_num is not None:
        loc_parts.append(f"page={c.page_num}")
    if c.start_char is not None and c.end_char is not None:
        loc_parts.append(f"chars={c.start_char}-{c.end_char}")
    loc_s = ", ".join(loc_parts) if loc_parts else "loc=unknown"

    # ── section path ───────────────────────────────────────────────────────────
    section_path = getattr(c, "section_path", [])
    if not section_path:
        # fallback to flat section_context for old chunks
        sc = getattr(c, "section_context", "")
        section_parts = [sc] if sc else []
    else:
        section_parts = [s.strip() for s in section_path if s.strip()]

    section_s = ""
    if section_parts:
        section_s = f" | section={' > '.join(section_parts)}"

    # ── chunk type hint ────────────────────────────────────────────────────────
    chunk_type = getattr(c, "chunk_type", "semantic_text")
    type_hint  = ""
    if chunk_type == "table":
        type_hint = " | [TABLE — interpret as structured data with rows and columns]"
    elif chunk_type == "formula":
        type_hint = " | [FORMULA — mathematical/technical expression]"
    elif chunk_type == "reference":
        type_hint = " | [REFERENCE — bibliographic citation only, not factual evidence]"
    elif chunk_type == "list_item":
        type_hint = " | [LIST ITEM — one item from a structured list]"
    elif chunk_type == "figure":
        type_hint = " | [FIGURE — visual content description]"

    header = (
        f"[SOURCE {i} | {source_name} | {loc_s}"
        f"{section_s}{type_hint}]"
    )

    return f"{header}\n{c.text}".strip()


def build_grounded_prompt(
    *,
    question:     str,
    chunks:       List[RetrievedChunk],
    source_names: Optional[Sequence[str]] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
    cfg:          Optional[PromptConfig]  = None,
) -> str:
    cfg    = cfg or PromptConfig()
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

    # build conversation history block
    history_block = ""
    if chat_history:
        turns = []
        for entry in chat_history:
            role = entry.get("role", "")
            content = (entry.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                turns.append(f"User: {content}")
            elif role == "assistant":
                turns.append(f"Assistant: {content}")
        if turns:
            history_block = "\n\nCONVERSATION HISTORY (for context only — do not treat as source evidence):\n" + "\n".join(turns)

    return f"""You are a document-grounded assistant.

RULES (strict):
- Use ONLY the provided CONTEXT. Do not use external knowledge.
- If the answer is not explicitly supported by the CONTEXT, reply exactly: Not found in documents.
- Every factual sentence MUST include citations to supporting SOURCE number(s) in square brackets, e.g. [1] or [1][2].
- Do not cite sources that do not support the sentence. No invented citations.
- For TABLE sources: read the data as structured rows and columns.
- For LIST ITEM sources: treat each item as an independent piece of evidence.
- For REFERENCE sources: only use these to attribute claims to external works, not as factual evidence.
- You may use CONVERSATION HISTORY to understand context and pronouns (e.g. "it", "that project") but do NOT treat history as source evidence.{history_block}

QUESTION:
{question}

CONTEXT:
{context_blocks}

ANSWER:
"""