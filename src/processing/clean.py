# src/processing/clean.py
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Tuple

# ── regexes ────────────────────────────────────────────────────────────────────

_WS_RE   = re.compile(r"[ \t\f\v]+")
_NL_RE   = re.compile(r"\n{3,}")
_CTRL_RE = re.compile(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]")

# Standalone page number lines (e.g. "2", " 3 ", "- 4 -")
_PAGE_NUM_LINE_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")

# Our extraction markers — preserve these as-is
_FORMULA_MARKER_RE    = re.compile(r"^\[FORMULA:.*\]$",     re.DOTALL)
_FIGURE_TEXT_MARKER_RE = re.compile(r"^\[FIGURE TEXT:.*\]$", re.DOTALL)

# Table markdown row (has pipe characters)
_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|")


# ── core normalisation ────────────────────────────────────────────────────────

def _normalize_text(s: str) -> str:
    if not s:
        return ""

    # Unicode normalize (stable representation)
    s = unicodedata.normalize("NFKC", s)

    # Remove ASCII control chars (keep \n \t)
    s = _CTRL_RE.sub("", s)

    # Normalize line endings
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # Process line by line
    lines = s.split("\n")
    cleaned_lines = []

    for line in lines:
        # Keep formula / figure-text markers exactly as-is
        stripped = line.strip()
        if _FORMULA_MARKER_RE.match(stripped) or _FIGURE_TEXT_MARKER_RE.match(stripped):
            cleaned_lines.append(stripped)
            continue

        # Keep table markdown rows — only collapse inner whitespace
        if _TABLE_ROW_RE.match(line):
            cleaned_lines.append(_WS_RE.sub(" ", line).rstrip())
            continue

        # Strip standalone page number lines
        if _PAGE_NUM_LINE_RE.match(line):
            continue

        # Normal line: collapse whitespace, trim
        line = _WS_RE.sub(" ", line).rstrip()
        cleaned_lines.append(line)

    s = "\n".join(cleaned_lines)

    # Collapse 3+ blank lines → 2
    s = _NL_RE.sub("\n\n", s)

    return s.strip()


# ── garbage flags ─────────────────────────────────────────────────────────────

def _garbage_flags(original: str, cleaned: str) -> Dict:
    """
    Minimal, safe heuristics (no heavy NLP).
    Flags are advisory; downstream chunker can decide what to do.
    """
    o = original or ""
    c = cleaned  or ""

    reasons = []

    if not c:
        reasons.append("EMPTY_AFTER_CLEAN")

    if len(c) > 0 and len(c) < 30:
        reasons.append("TOO_SHORT")

    # nonprintable ratio on original (catches ghosty PDFs)
    # exclude our marker brackets from the count
    o_check = re.sub(r"\[(?:FORMULA|FIGURE TEXT):.*?\]", "", o, flags=re.DOTALL)
    if o_check:
        non_printable = sum(
            1 for ch in o_check
            if (not ch.isprintable()) and ch not in ("\n", "\t")
        )
        ratio = non_printable / max(1, len(o_check))
    else:
        ratio = 0.0

    if ratio > 0.10:
        reasons.append("HIGH_NONPRINTABLE_RATIO")

    return {
        "is_garbage":        len(reasons) > 0,
        "reasons":           reasons,
        "nonprintable_ratio": round(ratio, 4),
    }


# ── public API (Stage 4 contract — unchanged) ─────────────────────────────────

def clean_page_text(text_original: str) -> Tuple[str, Dict]:
    """
    Clean a page's text_original and return (text_clean, flags).
    Contract with runner.py and chunk.py is unchanged.
    """
    text_clean = _normalize_text(text_original or "")
    flags      = _garbage_flags(text_original or "", text_clean)
    return text_clean, flags