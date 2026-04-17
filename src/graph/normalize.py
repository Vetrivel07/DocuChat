from __future__ import annotations

import hashlib
import re


_SPACE_RE = re.compile(r"\s+")
_PUNCT_EDGE_RE = re.compile(r"^[\W_]+|[\W_]+$")


def normalize_entity_text(text: str) -> str:
    s = (text or "").strip()
    s = _SPACE_RE.sub(" ", s)
    return s.casefold()


def canonicalize_entity_text(text: str) -> str:
    s = (text or "").strip()
    s = _SPACE_RE.sub(" ", s)
    s = _PUNCT_EDGE_RE.sub("", s)
    return s


def make_entity_id(entity_type: str, canonical_name: str) -> str:
    raw = f"{entity_type.strip().upper()}|{normalize_entity_text(canonical_name)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def looks_like_heading(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if len(s) > 80:
        return False
    if s.isupper():
        return True
    title_like = s == s.title()
    return title_like and len(s.split()) <= 6