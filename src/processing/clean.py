from __future__ import annotations

import re
import unicodedata
from typing import Dict, Tuple


_WS_RE = re.compile(r"[ \t\f\v]+")
_NL_RE = re.compile(r"\n{3,}")
_CTRL_RE = re.compile(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]")


def _normalize_text(s: str) -> str:
    if not s:
        return ""

    # Unicode normalize (stable representation)
    s = unicodedata.normalize("NFKC", s)

    # Remove ASCII control chars (keep \n)
    s = _CTRL_RE.sub("", s)

    # Normalize newlines first
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse repeated whitespace inside lines
    s = _WS_RE.sub(" ", s)

    # Trim trailing spaces per line
    s = "\n".join(line.rstrip() for line in s.split("\n"))

    # Collapse too many blank lines
    s = _NL_RE.sub("\n\n", s)

    return s.strip()


def _garbage_flags(original: str, cleaned: str) -> Dict:
    """
    Minimal, safe heuristics (no heavy NLP).
    Flags are *advisory*; downstream chunker can decide what to do.
    """
    o = original or ""
    c = cleaned or ""

    reasons = []
    if not c:
        reasons.append("EMPTY_AFTER_CLEAN")

    # too short to be useful
    if len(c) > 0 and len(c) < 30:
        reasons.append("TOO_SHORT")

    # nonprintable ratio (on original) — catches ghosty PDFs
    if o:
        non_printable = sum(1 for ch in o if (not ch.isprintable()) and ch != "\n" and ch != "\t")
        ratio = non_printable / max(1, len(o))
    else:
        ratio = 0.0

    if ratio > 0.10:
        reasons.append("HIGH_NONPRINTABLE_RATIO")

    return {
        "is_garbage": len(reasons) > 0,
        "reasons": reasons,
        "nonprintable_ratio": round(ratio, 4),
    }


def clean_page_text(text_original: str) -> Tuple[str, Dict]:
    text_clean = _normalize_text(text_original or "")
    flags = _garbage_flags(text_original or "", text_clean)
    return text_clean, flags
