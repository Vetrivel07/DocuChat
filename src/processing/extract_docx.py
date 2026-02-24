from __future__ import annotations

from typing import Dict, List, Tuple
from docx import Document


def extract_docx_pages(docx_bytes: bytes) -> Tuple[List[Dict], str]:
    """
    DOCX: no reliable pages -> treat as one page.
    """
    doc = Document(__to_bytesio(docx_bytes))

    parts: List[str] = []

    for para in doc.paragraphs:
        t = (para.text or "").strip()
        if t:
            parts.append(t)

    for table in doc.tables:
        for row in table.rows:
            row_data = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if row_data:
                parts.append(" | ".join(row_data))

    full_text_original = "\n\n".join(parts).strip()

    pages: List[Dict] = [
        {"page_num": 1, "text_original": full_text_original, "text_clean": "", "flags": {"method": "docx"}}
    ]
    return pages, full_text_original


def __to_bytesio(data: bytes):
    import io
    return io.BytesIO(data)
