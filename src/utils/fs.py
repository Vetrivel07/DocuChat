from __future__ import annotations
import re

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1F]') 

def safe_name(s: str) -> str:
    s = s.strip()
    s = _INVALID.sub("_", s)
    s = re.sub(r"\s+", "_", s)
    return s[:180] 
