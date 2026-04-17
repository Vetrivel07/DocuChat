# src/processing/chunk.py
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.processing.clean import clean_page_text

# ── tiktoken (graceful fallback) ───────────────────────────────────────────────
try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    def _count_tokens(text: str) -> int:
        return len(_ENC.encode(text))
except Exception:
    def _count_tokens(text: str) -> int:
        return max(1, len(text) // 4)

# ── tunables ───────────────────────────────────────────────────────────────────
TARGET_MIN   = 350    # target min tokens per chunk
TARGET_MAX   = 450    # target max tokens per chunk
HARD_MAX     = 550    # absolute max — split if exceeded
MIN_INDEX    = 20     # chunks below this token count are not indexed

# ── structural patterns ────────────────────────────────────────────────────────

# IMPORTANT: _NUMBERED_ITEM_RE must be checked BEFORE _MAIN_SECTION_RE
# because _MAIN_SECTION_RE now includes \d{1,2}\. — which also matches list items.
# Classification priority order: citation > formula > table > figure >
#   numbered_item > main_section > subsection > paragraph

# Numbered list item:  "1. Title", "2. Goal", "10. Step" (up to 2 digits)
_NUMBERED_ITEM_RE = re.compile(r"^\s*(\d{1,2})\.\s+\S")

# Main section heading:
#   IEEE Roman:   "I. TITLE", "II. TITLE"
#   Single alpha: "A. Title"
#   Digit:        "1. Title", "2. Goal" — BUT only when not a list item
#   Note: digit case is a fallback; _NUMBERED_ITEM_RE is checked first
_MAIN_SECTION_RE = re.compile(
    r"^\s*(?:[IVX]{1,6}\.|[A-Z]\.|\d{1,2}\.)\s+\S"
)

# Other structural types
_CITATION_RE  = re.compile(r"^\s*\[(\d{1,3})\]\s+\S")
_FIGURE_RE    = re.compile(r"^\s*(?:Fig\.?|Figure|TABLE|Table|Tab\.?)\s*[\dIVX]+", re.IGNORECASE)
_FORMULA_RE   = re.compile(r"^\[FORMULA:.*\]$", re.DOTALL)
_MD_TABLE_RE  = re.compile(r"^\s*\|.+\|")

# Reference section detection — handles PDF artifacts like "R EFERNCES"
_REF_HEADING_RE = re.compile(
    r"^\s*(?:[IVX]{1,6}\.\s+)?(?:REFERENCES?|BIBLIOGRAPHY|WORKS\s+CITED|REFERNCES?)\s*$",
    re.IGNORECASE,
)

def _is_ref_section(text: str) -> bool:
    if not text:
        return False
    t       = re.sub(r"\s+", " ", text.strip())
    nospace = re.sub(r"\s", "", t).upper()
    return (bool(_REF_HEADING_RE.match(t)) or
            bool(re.search(r"REFER[EN]+CES?|BIBLIOGRAPH", t, re.IGNORECASE)) or
            bool(re.search(r"REFER[EN]+CES?|BIBLIOGRAPH", nospace)))


def _is_subsection_heading(line: str) -> bool:
    """
    Detect short subsection headings like "System Interface and Logging".
    Strict rules — must NOT match:
      - metadata lines ("Term: Spring 2026")
      - proper names ("Vetrivel Maheswaran")
      - deliverable items ("Presentation slides summarizing the project")
      - body sentences ("Run evaluation on the full benchmark dataset")
    """
    t = line.strip()
    if not t or len(t) < 4 or len(t) > 60:
        return False
    if t.endswith(".") or t.endswith(",") or t.endswith(":"):
        return False
    if ":" in t:                                    # rejects metadata labels
        return False
    if not t[0].isupper():
        return False
    if (_CITATION_RE.match(t) or _FIGURE_RE.match(t) or
            _FORMULA_RE.match(t) or _NUMBERED_ITEM_RE.match(t) or
            _MAIN_SECTION_RE.match(t)):
        return False
    words = t.split()
    if len(words) < 2 or len(words) > 6:           # 2–6 words only
        return False
    # Reject lines that start like body sentences or deliverable items
    _BODY_START = re.compile(
        r"^(?:Run|Collect|Identify|Develop|Finalize|Interpret|Refine|"
        r"Create|Build|Use|Presentation|Written|Functional|Live|Working|"
        r"The |This |A |An |In |For |By |To |At |When |Each |All )"
    )
    if _BODY_START.match(t):
        return False
    # Reject two-word proper names ("Firstname Lastname")
    if len(words) == 2 and words[0][0].isupper() and words[1][0].isupper():
        if not any(c in t for c in ("-", "&", "/")):
            return False
    return True


# ── helpers ────────────────────────────────────────────────────────────────────

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def make_chunk_id(doc_id: str, page_num: int, start: int, end: int, text_clean: str) -> str:
    return _sha256(f"{doc_id}|{page_num}|{start}|{end}|{_sha256(text_clean)}")

def _build_embedding_text(file_name: str, section_path: List[str], text_clean: str) -> str:
    """
    Format:
        Document: {file_name}
        Section: {Main} > {Sub}

        {text}
    """
    lines = []
    if file_name:
        lines.append(f"Document: {file_name}")
    path_str = " > ".join(s.strip() for s in section_path if s.strip())
    if path_str:
        lines.append(f"Section: {path_str}")
    prefix = "\n".join(lines)
    return f"{prefix}\n\n{text_clean}" if prefix else text_clean

def _make_chunk(*, doc_id, file_name, page_num, start, end,
                text_original, text_clean, section_path, chunk_type, index_this):
    tok = _count_tokens(text_clean)
    if tok < MIN_INDEX:
        index_this = False
    return {
        "chunk_id":        make_chunk_id(doc_id, page_num, start, end, text_clean),
        "doc_id":          doc_id,
        "page_num":        page_num,
        "page_end":        page_num,
        "start_char":      start,
        "end_char":        end,
        "text_original":   text_original,
        "text_clean":      text_clean,
        "embedding_text":  _build_embedding_text(file_name, section_path, text_clean),
        "section_path":    list(section_path),
        "section_context": " > ".join(section_path) if section_path else "",
        "chunk_type":      chunk_type,
        "token_count":     tok,
        "index_this":      index_this,
    }


# ── paragraph extraction ───────────────────────────────────────────────────────

@dataclass
class Para:
    kind:       str           # citation|formula|md_table|figure|numbered_item|
                              # main_section|subsection|paragraph
    text_orig:  str
    text_clean: str
    start:      int
    end:        int
    num:        Optional[int] = None  # for numbered_item


def _classify(first_line: str) -> Tuple[str, Optional[int]]:
    """
    Classify a paragraph by its first line.
    ORDER MATTERS: numbered_item must come before main_section.
    """
    t = first_line.strip()
    if not t:
        return "paragraph", None
    if _CITATION_RE.match(t):
        return "citation", None
    if _FORMULA_RE.match(t):
        return "formula", None
    if _MD_TABLE_RE.match(t):
        return "md_table", None
    if _FIGURE_RE.match(t):
        return "figure", None
    # numbered_item BEFORE main_section — both match \d{1,2}\.
    m = _NUMBERED_ITEM_RE.match(t)
    if m:
        return "numbered_item", int(m.group(1))
    if _MAIN_SECTION_RE.match(t):
        return "main_section", None
    if _is_subsection_heading(t):
        return "subsection", None
    return "paragraph", None


def _extract_paragraphs(text_original: str) -> List[Para]:
    """
    Split text_original on blank lines, classify each block, record char offsets.
    text_clean is derived from text_orig via clean_page_text.
    """
    paras: List[Para] = []
    i = 0
    n = len(text_original)
    while i < n:
        # Skip blank/whitespace
        while i < n and text_original[i] in ("\n", " ", "\r"):
            i += 1
        if i >= n:
            break
        # Find end of paragraph (next blank line)
        j = i
        while j < n:
            if text_original[j] == "\n":
                k = j + 1
                while k < n and text_original[k] == " ":
                    k += 1
                if k < n and text_original[k] == "\n":
                    break
            j += 1
        raw = text_original[i:j].strip()
        if not raw:
            i = j + 1
            continue
        cleaned, _ = clean_page_text(raw)
        cleaned = cleaned.strip()
        if not cleaned:
            i = j + 1
            continue
        first_line = cleaned.split("\n")[0].strip()
        kind, num  = _classify(first_line)
        paras.append(Para(kind=kind, text_orig=raw, text_clean=cleaned,
                          start=i, end=j, num=num))
        i = j + 1
    return paras


# ── token splitter ─────────────────────────────────────────────────────────────

def _split_by_sentences(clean: str, orig: str) -> List[Tuple[str, str]]:
    """Split oversized text on sentence boundaries."""
    sc = re.split(r"(?<=[.!?])\s+", clean)
    so = re.split(r"(?<=[.!?])\s+", orig)
    while len(so) < len(sc): so.append("")
    parts: List[Tuple[str, str]] = []
    cc: List[str] = []; co: List[str] = []; ct = 0
    for s, o in zip(sc, so):
        t = _count_tokens(s)
        if cc and ct + t > HARD_MAX:
            parts.append((" ".join(cc), " ".join(co)))
            cc = [s]; co = [o]; ct = t
        else:
            cc.append(s); co.append(o); ct += t
    if cc:
        parts.append((" ".join(cc), " ".join(co)))
    return parts or [(clean, orig)]


# ── look-ahead helper ─────────────────────────────────────────────────────────

def _find_next_paragraph(paras: List[Para], from_index: int,
                         lookahead: int = 3) -> Optional[Para]:
    """
    Find the next paragraph block after from_index, skipping up to `lookahead`
    non-paragraph blocks (figures, formulas, etc.).
    Returns None if not found within lookahead or if the next structural block
    is a section/subsection/numbered_item (which would start a new section).
    """
    stop_kinds = {"main_section", "subsection", "numbered_item"}
    for j in range(from_index + 1, min(from_index + 1 + lookahead, len(paras))):
        q = paras[j]
        if q.kind in stop_kinds:
            return None       # new section starts — don't steal its content
        if q.kind == "paragraph":
            return q
        # figure/formula/md_table/citation — skip over it
    return None


# ── page chunker ───────────────────────────────────────────────────────────────

def chunk_page(
    doc_id:    str,
    file_name: str,
    page:      Dict[str, Any],
    *,
    inherited_section_path: List[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Section-first semantic chunker for one page.
    Returns (chunks, section_path_at_end_of_page).
    """
    if inherited_section_path is None:
        inherited_section_path = []

    page_num  = int(page.get("page_num", 1))
    text_orig = (page.get("text_original") or "").rstrip()
    if not text_orig.strip():
        return [], inherited_section_path

    paras = _extract_paragraphs(text_orig)
    if not paras:
        return [], inherited_section_path

    chunks:       List[Dict[str, Any]] = []
    main_section: str = inherited_section_path[0] if inherited_section_path else ""
    sub_section:  str = inherited_section_path[1] if len(inherited_section_path) > 1 else ""
    in_ref:       bool = _is_ref_section(main_section)
    last_sub:     str  = sub_section

    def sec_path() -> List[str]:
        p = []
        if main_section: p.append(main_section)
        if sub_section:  p.append(sub_section)
        return p

    # paragraph merge buffer
    buf_orig:  List[str] = []
    buf_clean: List[str] = []
    buf_start: int = 0
    buf_end:   int = 0
    buf_tok:   int = 0

    def flush(sp: List[str]) -> None:
        nonlocal buf_orig, buf_clean, buf_tok
        if not buf_clean:
            return
        merged_c = "\n\n".join(x for x in buf_clean if x.strip())
        merged_o = "\n\n".join(x for x in buf_orig  if x.strip())
        if not merged_c.strip():
            buf_orig = []; buf_clean = []; buf_tok = 0
            return
        parts = _split_by_sentences(merged_c, merged_o) if _count_tokens(merged_c) > HARD_MAX else [(merged_c, merged_o)]
        for pc, po in parts:
            if pc.strip():
                chunks.append(_make_chunk(
                    doc_id=doc_id, file_name=file_name, page_num=page_num,
                    start=buf_start, end=buf_end,
                    text_original=po.strip(), text_clean=pc.strip(),
                    section_path=list(sp),
                    chunk_type="semantic_text",
                    index_this=not in_ref,
                ))
        buf_orig = []; buf_clean = []; buf_tok = 0

    def buf_add(p: Para) -> None:
        nonlocal buf_start, buf_end, buf_tok
        if not buf_clean:
            buf_start = p.start
        buf_orig.append(p.text_orig)
        buf_clean.append(p.text_clean)
        buf_end  = p.end
        buf_tok += _count_tokens(p.text_clean)

    def emit(p: Para, chunk_type: str, index: bool, sp: List[str],
             extra_orig: str = "", extra_clean: str = "",
             end_char: Optional[int] = None) -> None:
        """
        Emit a single atomic or merged chunk.
        end_char: explicit end offset for merged chunks (heading+body, item+desc).
                  When provided, the chunk spans from p.start to end_char.
        """
        orig  = (p.text_orig  + ("\n\n" + extra_orig  if extra_orig  else "")).strip()
        clean = (p.text_clean + ("\n\n" + extra_clean if extra_clean else "")).strip()
        if not clean:
            return
        chunk_end = end_char if end_char is not None else p.end
        parts = _split_by_sentences(clean, orig) if _count_tokens(clean) > HARD_MAX else [(clean, orig)]
        for pc, po in parts:
            if pc.strip():
                chunks.append(_make_chunk(
                    doc_id=doc_id, file_name=file_name, page_num=page_num,
                    start=p.start, end=chunk_end,
                    text_original=po.strip(), text_clean=pc.strip(),
                    section_path=list(sp),
                    chunk_type=chunk_type,
                    index_this=index,
                ))

    # Detect if this page is a numbered-list section (for list pairing)
    num_items    = [p for p in paras if p.kind == "numbered_item"]
    is_list_page = len(num_items) >= 2

    i = 0
    while i < len(paras):
        p = paras[i]

        # ── Fix 1: numbered_item on a non-list page = main section heading ──────
        # e.g. DOCX where "1. Introduction" is the sole section on a page.
        # is_list_page=False means there are fewer than 2 numbered items, so
        # these are section headings, not list entries.
        if p.kind == "numbered_item" and not is_list_page:
            flush(sec_path())
            main_section = p.text_clean.split("\n")[0].strip()
            sub_section  = ""
            last_sub     = ""
            in_ref       = _is_ref_section(main_section)
            nxt = _find_next_paragraph(paras, i)
            if nxt:
                emit(p, "semantic_text", not in_ref, sec_path(),
                     nxt.text_orig, nxt.text_clean, end_char=nxt.end)
                i = paras.index(nxt) + 1
            else:
                i += 1
            continue

        # ── main section heading ───────────────────────────────────────────────
        if p.kind == "main_section":
            flush(sec_path())
            main_section = p.text_clean.split("\n")[0].strip()
            sub_section  = ""
            last_sub     = ""
            in_ref       = _is_ref_section(main_section)
            nxt = _find_next_paragraph(paras, i)
            if nxt:
                emit(p, "semantic_text", not in_ref, sec_path(),
                     nxt.text_orig, nxt.text_clean, end_char=nxt.end)
                i = paras.index(nxt) + 1
            else:
                i += 1
            continue

        # ── subsection heading ─────────────────────────────────────────────────
        if p.kind == "subsection":
            flush(sec_path())
            sub_section = p.text_clean.split("\n")[0].strip()
            last_sub    = sub_section
            nxt = _find_next_paragraph(paras, i)
            if nxt:
                emit(p, "semantic_text", not in_ref, sec_path(),
                     nxt.text_orig, nxt.text_clean, end_char=nxt.end)
                i = paras.index(nxt) + 1
            else:
                i += 1
            continue

        # ── reference / citation content ───────────────────────────────────────
        if in_ref or p.kind == "citation":
            flush(sec_path())
            emit(p, "reference", False, sec_path())
            i += 1
            continue

        # ── formula ────────────────────────────────────────────────────────────
        if p.kind == "formula":
            flush(sec_path())
            emit(p, "formula", True, sec_path())
            i += 1
            continue

        # ── markdown table ─────────────────────────────────────────────────────
        if p.kind == "md_table":
            flush(sec_path())
            # Strip pipes for embedding quality
            ec = re.sub(r"^\s*\|[\s\-\|]+\|\s*$", "", p.text_clean, flags=re.MULTILINE)
            ec = re.sub(r"\|\s*", " ", ec).strip()
            c = _make_chunk(
                doc_id=doc_id, file_name=file_name, page_num=page_num,
                start=p.start, end=p.end,
                text_original=p.text_orig, text_clean=ec or p.text_clean,
                section_path=sec_path(), chunk_type="table", index_this=True,
            )
            chunks.append(c)
            i += 1
            continue

        # ── figure caption ─────────────────────────────────────────────────────
        if p.kind == "figure":
            flush(sec_path())
            lines    = p.text_clean.split("\n")
            has_body = len(lines) > 1 and len("\n".join(lines[1:]).strip()) > 40
            emit(p, "figure", has_body, sec_path())
            i += 1
            continue

        # ── numbered list item (pair with following description) ───────────────
        if p.kind == "numbered_item" and is_list_page:
            flush(sec_path())
            desc = _find_next_paragraph(paras, i)
            if desc:
                emit(p, "list_item", True, sec_path(),
                     desc.text_orig, desc.text_clean, end_char=desc.end)
                i = paras.index(desc) + 1
            else:
                emit(p, "list_item", True, sec_path())
                i += 1
            continue

        # ── paragraph — flush on subsection change, merge until token limit ────
        # Detect inline subsection heading as first line of a paragraph block
        first = p.text_clean.split("\n")[0].strip()
        if _is_subsection_heading(first) and p.kind == "paragraph":
            flush(sec_path())
            sub_section = first
            last_sub    = sub_section
            emit(p, "semantic_text", not in_ref, sec_path(), end_char=p.end)
            i += 1
            continue

        # Flush if subsection changed
        if buf_clean and sub_section != last_sub:
            flush(sec_path())
        last_sub = sub_section

        # Flush if adding this would exceed target max
        tok = _count_tokens(p.text_clean)
        if buf_clean and buf_tok + tok > TARGET_MAX:
            flush(sec_path())

        buf_add(p)

        if buf_tok >= TARGET_MIN:
            flush(sec_path())

        i += 1

    flush(sec_path())
    return chunks, [main_section, sub_section] if sub_section else ([main_section] if main_section else [])


# ── document entry point ───────────────────────────────────────────────────────

def chunk_processed_doc(processed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Contract with runner.py unchanged: same input/output.
    Carries section context across pages via inherited_section_path.
    """
    doc_id    = processed["doc_id"]
    file_name = processed.get("file_name", "")
    all_chunks:    List[Dict[str, Any]] = []
    section_path:  List[str]            = []

    for page in processed.get("pages", []):
        page_chunks, section_path = chunk_page(
            doc_id, file_name, page,
            inherited_section_path=section_path,
        )
        all_chunks.extend(page_chunks)

    return all_chunks