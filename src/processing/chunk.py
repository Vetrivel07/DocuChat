# src/processing/chunk.py
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from src.processing.clean import clean_page_text


# ============================================================
# Stage 5 (CHUNK) — Semantic-first + boundary snapping
#
# - Build semantic blocks per page: headings → paragraphs → lists → tables
# - Merge small blocks into target range (~1200–2200 chars clean)
# - If a block/chunk exceeds hard max (~3500–4500), split with snapping
#   (sentence → punctuation → whitespace; never mid-word/URL)
# - Overlap ONLY when forced splits happen (~300–600 chars)
# - Store both:
#   text_original = exact slice for citations
#   text_clean     = cleaned version of that slice for embeddings
# - Fallback: fixed windows with snapping + overlap if 0 chunks
# ============================================================

# ---------------------------
# Tunables (sane defaults)
# ---------------------------
MIN_CHARS_CLEAN = 250

TARGET_MIN_CHARS_CLEAN = 1200
TARGET_MAX_CHARS_CLEAN = 2200

HARD_MAX_CHARS_CLEAN = 4200

# Only when splitting oversized spans
FORCED_SPLIT_OVERLAP_CHARS = 450  # ~300–600 recommended

# Fallback (if semantic yields 0 valid chunks)
FALLBACK_WINDOW_CHARS = 1800
FALLBACK_OVERLAP_CHARS = 450


# ---------------------------
# Semantic detection
# ---------------------------
_HEADING_LINE_RE = re.compile(
    r"""^\s*(?:
        (?:[IVX]{1,8}\.)\s+\S+ |           # I. Something
        (?:[A-Z]\.)\s+\S+ |                # A. Something
        (?:\d{1,3}\.)\s+\S+ |              # 1. Something
        (?:\d{1,3}\.\d{1,3})\s+\S+ |       # 1.1 Something
        (?:[A-Z][A-Z0-9 \-]{3,60})         # ALL CAPS-ish headings
    )\s*$""",
    re.VERBOSE,
)

_LIST_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d{1,3}[.)]|[A-Za-z][.)])\s+\S+")
# Table-ish: pipes OR multiple columns separated by 2+ spaces/tabs
_TABLE_LINE_RE = re.compile(r"^\s*(?:\S+\s*\|\s*\S+).*$|^\s*\S+(?:\s{2,}|\t)\S+.*$")


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def make_chunk_id(doc_id: str, page_num: int, start: int, end: int, text_clean: str) -> str:
    payload = f"{doc_id}|{page_num}|{start}|{end}|{_sha256_hex(text_clean)}"
    return _sha256_hex(payload)


def _trim_span(original: str, start: int, end: int) -> Tuple[int, int]:
    s = original[start:end]
    if not s:
        return start, end
    left = len(s) - len(s.lstrip())
    right = len(s.rstrip())
    return start + left, start + right


def _looks_like_url_cut(left_char: str, right_char: str, nearby: str) -> bool:
    # avoid cutting in middle of "http://", "https://", "www.", or a word token
    if left_char.isalnum() and right_char.isalnum():
        return True
    n = nearby.lower()
    if "http://" in n or "https://" in n or "www." in n:
        return True
    return False


def _snap_cut(original: str, start: int, end: int, prefer_at: int, min_rel: int) -> int | None:
    """
    Choose a cut position <= prefer_at (absolute index), snapping to:
    blankline → newline → sentence end → punctuation → whitespace.
    Returns absolute cut index, or None if no good cut found.
    """
    if prefer_at <= start + min_rel:
        return None

    window = original[start:prefer_at]
    if not window:
        return None

    # Prefer strong boundaries first
    candidates: List[int] = []

    # blank line
    idx = window.rfind("\n\n")
    if idx != -1:
        candidates.append(start + idx + 2)

    # newline
    idx = window.rfind("\n")
    if idx != -1:
        candidates.append(start + idx + 1)

    # sentence end patterns
    for pat in [". ", "? ", "! "]:
        idx = window.rfind(pat)
        if idx != -1:
            candidates.append(start + idx + 1)  # cut after punctuation

    # punctuation
    for pat in ["; ", ": ", ", "]:
        idx = window.rfind(pat)
        if idx != -1:
            candidates.append(start + idx + 1)

    # whitespace (last resort)
    idx = window.rfind(" ")
    if idx != -1:
        candidates.append(start + idx + 1)

    # pick the best candidate that is not too early and not a bad cut
    best = None
    for cut in sorted(set(candidates), reverse=True):
        if cut <= start + min_rel:
            continue
        if cut >= end:
            continue

        # guard against mid-word / mid-url cuts
        left_char = original[cut - 1] if cut - 1 >= 0 else ""
        right_char = original[cut] if cut < len(original) else ""
        nearby = original[max(start, cut - 20) : min(len(original), cut + 20)]
        if _looks_like_url_cut(left_char, right_char, nearby):
            continue

        best = cut
        break

    return best


@dataclass
class LineSpan:
    start: int
    end: int
    text: str


@dataclass
class Block:
    page_num: int
    start: int
    end: int
    kind: str  # heading|paragraph|list|table


def _iter_lines_with_spans(text_original: str) -> List[LineSpan]:
    """
    Build line spans (start,end) into text_original (including newline positions in offsets).
    """
    spans: List[LineSpan] = []
    if not text_original:
        return spans

    i = 0
    n = len(text_original)
    while i < n:
        j = text_original.find("\n", i)
        if j == -1:
            j = n
            line = text_original[i:j]
            spans.append(LineSpan(i, j, line))
            break

        line = text_original[i:j]
        spans.append(LineSpan(i, j + 1, line))  # include newline char in span
        i = j + 1

    return spans


def _classify_line(line: str) -> str:
    t = (line or "").rstrip("\n").strip()
    if not t:
        return "blank"
    if _HEADING_LINE_RE.match(t):
        return "heading"
    if _TABLE_LINE_RE.match(t):
        return "table"
    if _LIST_LINE_RE.match(t):
        return "list"
    return "text"


def build_semantic_blocks(page_num: int, text_original: str) -> List[Block]:
    """
    Semantic-first blocks: headings → paragraphs → lists → tables.
    Blocks are spans into text_original.
    """
    lines = _iter_lines_with_spans(text_original)
    blocks: List[Block] = []

    cur_kind: str | None = None
    cur_start: int | None = None
    cur_end: int | None = None

    def flush():
        nonlocal cur_kind, cur_start, cur_end
        if cur_kind and cur_start is not None and cur_end is not None and cur_end > cur_start:
            s, e = _trim_span(text_original, cur_start, cur_end)
            if e > s:
                blocks.append(Block(page_num=page_num, start=s, end=e, kind=cur_kind))
        cur_kind = None
        cur_start = None
        cur_end = None

    for ln in lines:
        k = _classify_line(ln.text)
        if k == "blank":
            # blank line ends paragraphs/lists/tables
            flush()
            continue

        # headings always break
        if k == "heading":
            flush()
            s, e = _trim_span(text_original, ln.start, ln.end)
            if e > s:
                blocks.append(Block(page_num=page_num, start=s, end=e, kind="heading"))
            continue

        # list/table should group consecutive lines of same kind
        if k in ("list", "table"):
            if cur_kind != k:
                flush()
                cur_kind = k
                cur_start = ln.start
                cur_end = ln.end
            else:
                cur_end = ln.end
            continue

        # normal text -> paragraph (group consecutive text lines)
        if k == "text":
            if cur_kind != "paragraph":
                flush()
                cur_kind = "paragraph"
                cur_start = ln.start
                cur_end = ln.end
            else:
                cur_end = ln.end
            continue

    flush()
    return blocks


def _split_oversized_span(
    *,
    original: str,
    page_num: int,
    doc_id: str,
    start: int,
    end: int,
    overlap_chars: int,
) -> List[Dict[str, Any]]:
    """
    Split [start,end] into multiple chunks by snapping to boundaries.
    Overlap is applied ONLY here.
    """
    out: List[Dict[str, Any]] = []
    cur = start

    # safety: minimum to avoid tiny fragments
    min_rel = max(MIN_CHARS_CLEAN, 400)

    while cur < end:
        # try to cut around HARD_MAX_CHARS_CLEAN (roughly on original length)
        prefer = min(end, cur + HARD_MAX_CHARS_CLEAN)
        if prefer >= end:
            s, e = _trim_span(original, cur, end)
            if e > s:
                span_original = original[s:e]
                text_clean, _ = clean_page_text(span_original)
                if len(text_clean) >= MIN_CHARS_CLEAN:
                    out.append(
                        {
                            "chunk_id": make_chunk_id(doc_id, page_num, s, e, text_clean),
                            "doc_id": doc_id,
                            "page_num": page_num,
                            "start_char": s,
                            "end_char": e,
                            "text_original": span_original,
                            "text_clean": text_clean,
                        }
                    )
            break

        cut = _snap_cut(original, cur, end, prefer_at=prefer, min_rel=min_rel)
        if cut is None or cut <= cur:
            # last resort: hard cut (but still avoid mid-word/URL by snapping to whitespace)
            cut = _snap_cut(original, cur, end, prefer_at=prefer, min_rel=1) or prefer

        s, e = _trim_span(original, cur, cut)
        if e > s:
            span_original = original[s:e]
            text_clean, _ = clean_page_text(span_original)
            if len(text_clean) >= MIN_CHARS_CLEAN:
                out.append(
                    {
                        "chunk_id": make_chunk_id(doc_id, page_num, s, e, text_clean),
                        "doc_id": doc_id,
                        "page_num": page_num,
                        "start_char": s,
                        "end_char": e,
                        "text_original": span_original,
                        "text_clean": text_clean,
                    }
                )

        # forced overlap
        nxt = cut - overlap_chars
        cur = max(start, nxt)

        # ensure progress
        if cur >= cut:
            cur = cut

    return out


def _fallback_window_chunks(doc_id: str, page_num: int, original: str) -> List[Dict[str, Any]]:
    """
    Fixed-size windowing with snapping + overlap.
    Spans are still offsets into original.
    """
    out: List[Dict[str, Any]] = []
    if not original or not original.strip():
        return out

    n = len(original)
    cur = 0
    min_rel = max(MIN_CHARS_CLEAN, 400)

    while cur < n:
        prefer = min(n, cur + FALLBACK_WINDOW_CHARS)
        if prefer >= n:
            s, e = _trim_span(original, cur, n)
            if e > s:
                span_original = original[s:e]
                text_clean, _ = clean_page_text(span_original)
                if len(text_clean) >= MIN_CHARS_CLEAN:
                    out.append(
                        {
                            "chunk_id": make_chunk_id(doc_id, page_num, s, e, text_clean),
                            "doc_id": doc_id,
                            "page_num": page_num,
                            "start_char": s,
                            "end_char": e,
                            "text_original": span_original,
                            "text_clean": text_clean,
                        }
                    )
            break

        cut = _snap_cut(original, cur, n, prefer_at=prefer, min_rel=min_rel)
        if cut is None or cut <= cur:
            cut = _snap_cut(original, cur, n, prefer_at=prefer, min_rel=1) or prefer

        s, e = _trim_span(original, cur, cut)
        if e > s:
            span_original = original[s:e]
            text_clean, _ = clean_page_text(span_original)
            if len(text_clean) >= MIN_CHARS_CLEAN:
                out.append(
                    {
                        "chunk_id": make_chunk_id(doc_id, page_num, s, e, text_clean),
                        "doc_id": doc_id,
                        "page_num": page_num,
                        "start_char": s,
                        "end_char": e,
                        "text_original": span_original,
                        "text_clean": text_clean,
                    }
                )

        cur = max(0, cut - FALLBACK_OVERLAP_CHARS)
        if cur >= cut:
            cur = cut

    return out


def chunk_page(doc_id: str, page: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Semantic-first chunking for one page.
    Spans always offsets into page['text_original'].
    """
    page_num = int(page.get("page_num", 1))
    original = page.get("text_original") or ""
    if not original.strip():
        return []

    blocks = build_semantic_blocks(page_num, original)
    if not blocks:
        return _fallback_window_chunks(doc_id, page_num, original)

    chunks: List[Dict[str, Any]] = []

    buf_start: int | None = None
    buf_end: int | None = None

    def flush_buffer():
        nonlocal buf_start, buf_end
        if buf_start is None or buf_end is None or buf_end <= buf_start:
            buf_start = buf_end = None
            return

        span_original = original[buf_start:buf_end]
        text_clean, _ = clean_page_text(span_original)

        # If oversized, split with snapping + overlap
        if len(text_clean) > HARD_MAX_CHARS_CLEAN:
            chunks.extend(
                _split_oversized_span(
                    original=original,
                    page_num=page_num,
                    doc_id=doc_id,
                    start=buf_start,
                    end=buf_end,
                    overlap_chars=FORCED_SPLIT_OVERLAP_CHARS,
                )
            )
            buf_start = buf_end = None
            return

        if len(text_clean) >= MIN_CHARS_CLEAN:
            chunk_id = make_chunk_id(doc_id, page_num, buf_start, buf_end, text_clean)
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "page_num": page_num,
                    "start_char": buf_start,
                    "end_char": buf_end,
                    "text_original": span_original,
                    "text_clean": text_clean,
                }
            )

        buf_start = buf_end = None

    for b in blocks:
        # Headings: treat as section boundary (flush previous),
        # then allow heading to be merged with following content (start new buffer)
        if b.kind == "heading":
            flush_buffer()
            buf_start, buf_end = b.start, b.end
            continue

        # start or extend buffer
        if buf_start is None:
            buf_start, buf_end = b.start, b.end
        else:
            buf_end = b.end

        merged_original = original[buf_start:buf_end]
        merged_clean, _ = clean_page_text(merged_original)

        # If we exceed target max, flush now (keeps chunks in 1200–2200 range)
        if len(merged_clean) >= TARGET_MAX_CHARS_CLEAN:
            flush_buffer()
            continue

        # If we are within target band, we can flush to keep “semantic chunks”
        if len(merged_clean) >= TARGET_MIN_CHARS_CLEAN:
            flush_buffer()
            continue

        # else keep merging until we hit band or next heading forces flush

    flush_buffer()

    # Final fallback if semantic produced nothing valid
    if not chunks:
        chunks = _fallback_window_chunks(doc_id, page_num, original)

    return chunks


def chunk_processed_doc(processed: Dict[str, Any]) -> List[Dict[str, Any]]:
    doc_id = processed["doc_id"]
    chunks: List[Dict[str, Any]] = []

    for page in processed.get("pages", []):
        chunks.extend(chunk_page(doc_id, page))

    return chunks
