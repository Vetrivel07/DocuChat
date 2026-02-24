from __future__ import annotations

import io
from typing import Dict, List, Tuple

import fitz  # pymupdf

try:
    import pytesseract
    from PIL import Image
except Exception:
    pytesseract = None
    Image = None


def extract_pdf_pages(
    pdf_bytes: bytes,
    *,
    ocr_min_text_chars: int = 40,
    enable_ocr: bool = False,
) -> Tuple[List[Dict], str]:
    """
    Stage 3 contract:
      pages[]: {page_num, text_original, text_clean:"", flags:{}}
      full_text_original
      full_text_clean must remain empty (Stage 4)
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    pages: List[Dict] = []
    full_parts: List[str] = []

    for page_num in range(1, doc.page_count + 1):
        page = doc.load_page(page_num - 1)

        native_raw = (page.get_text("text") or "").replace("\r\n", "\n").replace("\r", "\n")
        text_original = native_raw
        flags: Dict = {"method": "native", "warnings": []}

        if enable_ocr and pytesseract and Image:
            # OCR fallback when native text is too short
            if len(native_raw.strip()) < ocr_min_text_chars:
                try:
                    pix = page.get_pixmap()
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_raw = (pytesseract.image_to_string(img) or "").replace("\r\n", "\n").replace("\r", "\n")

                    if ocr_raw.strip():
                        flags["method"] = "mixed" if native_raw.strip() else "ocr"
                        text_original = (native_raw + "\n\n" + ocr_raw).strip() if native_raw.strip() else ocr_raw.strip()

                except Exception as e:
                    flags["warnings"].append(f"OCR_FAILED: {e}")

        pages.append(
            {
                "page_num": page_num,
                "text_original": text_original,
                "text_clean": "",   # Stage 4 will fill
                "flags": flags,
            }
        )
        full_parts.append(text_original)

    doc.close()
    full_text_original = "\n\n".join([t for t in full_parts if t]).strip()
    return pages, full_text_original
