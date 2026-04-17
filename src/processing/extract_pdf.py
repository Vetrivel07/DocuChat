# # src/processing/extract_pdf.py
# from __future__ import annotations

# import io
# import re
# from typing import Dict, List, Optional, Tuple

# import fitz  # pymupdf

# # ── optional heavy deps ────────────────────────────────────────────────────────
# try:
#     import pdfplumber
#     _PDFPLUMBER = True
# except ImportError:
#     _PDFPLUMBER = False

# try:
#     import pix2text
#     _PIX2TEXT = True
# except ImportError:
#     _PIX2TEXT = False

# try:
#     import pytesseract
#     from PIL import Image as PILImage
#     _TESSERACT = True
# except ImportError:
#     pytesseract = None
#     PILImage = None
#     _TESSERACT = False

# # ── constants ──────────────────────────────────────────────────────────────────

# # IEEE-style section heading ONLY — strict patterns to avoid matching list items
# # Matches:  "I. TITLE"  "II. TITLE"  "III. TITLE"  "A. Background"
# # Does NOT match: "1. Complete evaluation" "2. Expand dataset" (numbered list items)
# _SECTION_RE = re.compile(
#     r"^\s*(?:"
#     r"(?:[IVX]{1,6}\.)\s+[A-Z]"      # Roman numeral: I. INTRO  II. METHOD
#     r"|(?:[A-Z]\.)\s+[A-Z]"           # Letter:        A. Background
#     r")\s*",
#     re.IGNORECASE,
# )

# # Figure / table caption lines
# _CAPTION_RE = re.compile(
#     r"^\s*(?:Fig\.?|Figure|TABLE|Table)\s*[\dIVX]+[\.\:]",
#     re.IGNORECASE,
# )

# # Standalone page number:  "2", " 3 ", "- 4 -"
# _PAGE_NUM_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")

# # Formula-like block heuristics (high symbol density)
# _MATH_CHARS = set(r"∑∏∫∂∇∆αβγδεζηθλμνξπρστφχψωΩΓΔΘΛΞΠΣΦΨ±×÷√∞≈≠≤≥∈∉⊂⊃∪∩")
# _LATEX_RE   = re.compile(r"\\[a-zA-Z]+\{|\\frac|\\sum|\\int|\$.*?\$")


# def _is_formula_block(text: str) -> bool:
#     """Heuristic: is this block mostly math/formula content?"""
#     if not text or len(text) < 3:
#         return False
#     if _LATEX_RE.search(text):
#         return True
#     math_ratio = sum(1 for c in text if c in _MATH_CHARS) / max(1, len(text))
#     return math_ratio > 0.08


# def _is_page_noise(text: str) -> bool:
#     """True for standalone page numbers, running headers/footers (short + no sentence)."""
#     t = text.strip()
#     if not t:
#         return True
#     if _PAGE_NUM_RE.match(t):
#         return True
#     # very short lines that are pure digits or common footer patterns
#     if len(t) <= 6 and t.replace(" ", "").isdigit():
#         return True
#     return False


# def _column_band(x0: float, page_width: float, n_cols: int) -> int:
#     """Return 0-based column index for a block given its left x."""
#     col_width = page_width / n_cols
#     return min(int(x0 / col_width), n_cols - 1)


# def _detect_columns(blocks: list, page_width: float) -> int:
#     """
#     Guess 1, 2, or 3 columns by checking x0 distribution of text blocks.
#     Returns number of columns.
#     """
#     if not blocks:
#         return 1
#     xs = [b["x0"] for b in blocks if b.get("type") == "text" and b.get("text", "").strip()]
#     if not xs:
#         return 1
#     # If most blocks start in the left third AND some start in the middle → 2 col
#     mid = page_width / 2
#     left  = sum(1 for x in xs if x < mid * 0.6)
#     right = sum(1 for x in xs if x > mid * 0.4)
#     if left > 1 and right > 1:
#         # check for 3-col: right third
#         third = page_width / 3
#         far_right = sum(1 for x in xs if x > third * 1.8)
#         if far_right > 1:
#             return 3
#         return 2
#     return 1


# def _sort_blocks_reading_order(blocks: list, page_width: float) -> list:
#     """
#     Sort blocks in human reading order:
#       - Detect number of columns
#       - Within each column, sort top-to-bottom
#       - Columns read left-to-right
#     Full-width blocks (spanning > 60% of page) are treated as column=0 and
#     inserted at their vertical position relative to other full-width blocks.
#     """
#     if not blocks:
#         return blocks

#     n_cols = _detect_columns(blocks, page_width)

#     def sort_key(b):
#         x0   = b.get("x0", 0)
#         y0   = b.get("y0", 0)
#         x1   = b.get("x1", page_width)
#         width = x1 - x0
#         # full-width block → treat as col 0 but use exact y for ordering
#         if width > page_width * 0.6:
#             return (0, y0, x0)
#         col = _column_band(x0, page_width, n_cols)
#         return (col, y0, x0)

#     return sorted(blocks, key=sort_key)


# # ── pdfplumber table extraction ────────────────────────────────────────────────

# def _extract_tables_pdfplumber(
#     pdf_bytes: bytes,
#     page_num_1based: int,
# ) -> List[Dict]:
#     """
#     Extract structured tables from a single page using pdfplumber.
#     Returns list of dicts: {markdown, bbox, row_count, col_count}
#     """
#     if not _PDFPLUMBER:
#         return []
#     tables_out = []
#     try:
#         with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
#             if page_num_1based > len(pdf.pages):
#                 return []
#             page = pdf.pages[page_num_1based - 1]
#             for tbl in page.extract_tables():
#                 if not tbl:
#                     continue
#                 rows = []
#                 for row in tbl:
#                     cells = [str(c or "").strip().replace("\n", " ") for c in row]
#                     rows.append(cells)
#                 if not rows:
#                     continue
#                 # build markdown table
#                 header = rows[0]
#                 sep    = ["---"] * len(header)
#                 md_lines = [
#                     "| " + " | ".join(header) + " |",
#                     "| " + " | ".join(sep)    + " |",
#                 ]
#                 for row in rows[1:]:
#                     # pad/trim to header length
#                     r = (row + [""] * len(header))[: len(header)]
#                     md_lines.append("| " + " | ".join(r) + " |")
#                 tables_out.append({
#                     "markdown":  "\n".join(md_lines),
#                     "row_count": len(rows),
#                     "col_count": len(header),
#                 })
#     except Exception:
#         pass
#     return tables_out


# # ── pix2text formula extraction ────────────────────────────────────────────────

# _p2t_instance = None

# def _get_p2t():
#     global _p2t_instance
#     if _p2t_instance is None and _PIX2TEXT:
#         try:
#             _p2t_instance = pix2text.Pix2Text.from_config()
#         except Exception:
#             pass
#     return _p2t_instance


# def _extract_formula_from_region(page: fitz.Page, rect: fitz.Rect) -> Optional[str]:
#     """
#     Render a region of a page to image and run pix2text on it.
#     Returns LaTeX/math string or None.
#     """
#     p2t = _get_p2t()
#     if p2t is None:
#         return None
#     try:
#         clip  = page.get_pixmap(clip=rect, dpi=150)
#         img   = PILImage.open(io.BytesIO(clip.tobytes("png")))
#         result = p2t.recognize_formula(img)
#         if result and str(result).strip():
#             return str(result).strip()
#     except Exception:
#         pass
#     return None


# # ── pytesseract OCR for figure image regions ───────────────────────────────────

# def _ocr_region(page: fitz.Page, rect: fitz.Rect) -> Optional[str]:
#     if not _TESSERACT or PILImage is None:
#         return None
#     try:
#         clip = page.get_pixmap(clip=rect, dpi=200)
#         img  = PILImage.open(io.BytesIO(clip.tobytes("png")))
#         text = pytesseract.image_to_string(img) or ""
#         text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
#         return text if text else None
#     except Exception:
#         return None


# # ── per-page extraction ────────────────────────────────────────────────────────

# def _extract_page(
#     fitz_doc:   fitz.Document,
#     pdf_bytes:  bytes,
#     page_num:   int,          # 1-based
#     enable_ocr: bool,
#     enable_formula: bool,
# ) -> Dict:
#     """
#     Extract one page.  Returns the page dict matching the Stage 3 contract:
#       page_num, text_original, text_clean="", flags={...},
#       figures=[], tables=[], sections=[]
#     """
#     page      = fitz_doc.load_page(page_num - 1)
#     page_rect = page.rect
#     pw        = page_rect.width

#     # ── 1. get blocks with full geometry ──────────────────────────────────────
#     raw_dict  = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
#     raw_blocks = raw_dict.get("blocks", [])

#     # Flatten into a normalised list we can sort
#     flat_blocks = []
#     for blk in raw_blocks:
#         btype = blk.get("type", -1)
#         bbox  = blk.get("bbox", (0, 0, 0, 0))
#         x0, y0, x1, y1 = bbox

#         if btype == 0:  # text block
#             lines_text = []
#             for line in blk.get("lines", []):
#                 line_parts = []
#                 for span in line.get("spans", []):
#                     t = span.get("text", "")
#                     if t:
#                         line_parts.append(t)
#                 if line_parts:
#                     # Join spans with space only when adjacent spans don't
#                     # already have whitespace — fixes word-broken justified text
#                     # in 2-column PDFs where each word is a separate span
#                     joined = ""
#                     for i, part in enumerate(line_parts):
#                         if i == 0:
#                             joined = part
#                         else:
#                             if joined and not joined[-1].isspace() and not part[0].isspace():
#                                 joined += " " + part
#                             else:
#                                 joined += part
#                     lines_text.append(joined)
#             text = "\n".join(lines_text).strip()
#             flat_blocks.append({
#                 "type": "text",
#                 "x0": x0, "y0": y0, "x1": x1, "y1": y1,
#                 "text": text,
#             })

#         elif btype == 1:  # image block
#             flat_blocks.append({
#                 "type": "image",
#                 "x0": x0, "y0": y0, "x1": x1, "y1": y1,
#                 "text": "",
#             })

#     # ── 2. sort into reading order ─────────────────────────────────────────────
#     flat_blocks = _sort_blocks_reading_order(flat_blocks, pw)

#     # ── 3. get pdfplumber tables for this page ─────────────────────────────────
#     plumber_tables = _extract_tables_pdfplumber(pdf_bytes, page_num)

#     # ── 4. classify & reconstruct text ────────────────────────────────────────
#     parts:    List[str]  = []
#     figures:  List[Dict] = []
#     tables:   List[Dict] = plumber_tables[:]  # start with plumber tables
#     sections: List[str]  = []
#     has_formulas = False

#     # Track which table index we've appended to avoid duplicates
#     tables_appended = set()

#     for blk in flat_blocks:

#         if blk["type"] == "image":
#             # Try OCR on figure region
#             if enable_ocr and _TESSERACT:
#                 rect     = fitz.Rect(blk["x0"], blk["y0"], blk["x1"], blk["y1"])
#                 ocr_text = _ocr_region(page, rect)
#                 if ocr_text:
#                     parts.append(f"[FIGURE TEXT: {ocr_text}]")
#                     figures.append({"type": "image_ocr", "text": ocr_text, "page_num": page_num})
#             continue

#         text = blk["text"]
#         if not text:
#             continue

#         # strip page noise
#         if _is_page_noise(text):
#             continue

#         # detect section headings
#         if _SECTION_RE.match(text.split("\n")[0]):
#             sec = text.split("\n")[0].strip()
#             if sec not in sections:
#                 sections.append(sec)

#         # detect figure captions — FIRST LINE only
#         # remaining lines after caption are body text, keep them separately
#         first_line = text.split("\n")[0].strip()
#         if _CAPTION_RE.match(first_line):
#             # store only the caption line itself
#             figures.append({"caption": first_line, "page_num": page_num})
#             parts.append(first_line)
#             # if block has more lines after the caption, keep them as body text
#             remaining_lines = "\n".join(text.split("\n")[1:]).strip()
#             if remaining_lines:
#                 parts.append(remaining_lines)
#             continue

#         # detect formula blocks
#         if enable_formula and _is_formula_block(text):
#             has_formulas = True
#             if enable_formula and _PIX2TEXT and _TESSERACT:
#                 rect    = fitz.Rect(blk["x0"], blk["y0"], blk["x1"], blk["y1"])
#                 formula = _extract_formula_from_region(page, rect)
#                 if formula:
#                     parts.append(f"[FORMULA: {formula}]")
#                     continue
#             # fallback: keep raw text but tag it
#             parts.append(f"[FORMULA: {text}]")
#             continue

#         # normal text block — check if it's a table region (covered by pdfplumber)
#         # we still keep text but mark it; pdfplumber table is richer
#         parts.append(text)

#     # ── 5. inject pdfplumber tables into text at end of page ──────────────────
#     # (they'll be picked up by chunker as atomic table chunks)
#     for i, tbl in enumerate(plumber_tables):
#         if i not in tables_appended:
#             parts.append("\n" + tbl["markdown"] + "\n")
#             tables_appended.add(i)

#     # ── 6. assemble text_original ──────────────────────────────────────────────
#     text_original = "\n\n".join(p.strip() for p in parts if p.strip())

#     flags = {
#         "method":        "structured",
#         "warnings":      [],
#         "has_figures":   len(figures) > 0,
#         "has_tables":    len(plumber_tables) > 0,
#         "has_formulas":  has_formulas,
#         "sections_found": sections,
#         "pdfplumber":    _PDFPLUMBER,
#         "pix2text":      _PIX2TEXT,
#         "tesseract":     _TESSERACT,
#     }

#     return {
#         "page_num":      page_num,
#         "text_original": text_original,
#         "text_clean":    "",          # Stage 4 fills this
#         "flags":         flags,
#         "figures":       figures,
#         "tables":        plumber_tables,
#         "sections":      sections,
#     }


# # ── public API (Stage 3 contract) ─────────────────────────────────────────────

# def extract_pdf_pages(
#     pdf_bytes:          bytes,
#     *,
#     ocr_min_text_chars: int  = 40,
#     enable_ocr:         bool = True,
#     enable_formula:     bool = True,
# ) -> Tuple[List[Dict], str]:
#     """
#     Stage 3 contract (unchanged signature):
#       returns (pages, full_text_original)

#     Each page dict:
#       page_num, text_original, text_clean="", flags={}
#       + NEW optional fields: figures=[], tables=[], sections=[]

#     runner.py and chunk.py need zero changes.
#     """
#     doc    = fitz.open(stream=pdf_bytes, filetype="pdf")
#     pages: List[Dict] = []
#     full_parts: List[str] = []

#     for page_num in range(1, doc.page_count + 1):
#         page_dict = _extract_page(
#             fitz_doc=doc,
#             pdf_bytes=pdf_bytes,
#             page_num=page_num,
#             enable_ocr=enable_ocr,
#             enable_formula=enable_formula,
#         )

#         # OCR fallback: if after all processing text is still too short
#         raw_text = page_dict["text_original"]
#         if enable_ocr and _TESSERACT and len(raw_text.strip()) < ocr_min_text_chars:
#             fitz_page = doc.load_page(page_num - 1)
#             pix       = fitz_page.get_pixmap(dpi=200)
#             img       = PILImage.open(io.BytesIO(pix.tobytes("png")))
#             try:
#                 ocr_raw = (pytesseract.image_to_string(img) or "").strip()
#                 if ocr_raw:
#                     page_dict["text_original"] = ocr_raw
#                     page_dict["flags"]["method"] = "ocr_fallback"
#             except Exception as e:
#                 page_dict["flags"]["warnings"].append(f"OCR_FAILED: {e}")

#         pages.append(page_dict)
#         if page_dict["text_original"]:
#             full_parts.append(page_dict["text_original"])

#     doc.close()
#     full_text_original = "\n\n".join(t for t in full_parts if t).strip()
#     return pages, full_text_original

# src/processing/extract_pdf.py
from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

import fitz  # pymupdf

# ── optional heavy deps ────────────────────────────────────────────────────────
try:
    import pdfplumber
    _PDFPLUMBER = True
except ImportError:
    _PDFPLUMBER = False

try:
    import pix2text
    _PIX2TEXT = True
except ImportError:
    _PIX2TEXT = False

try:
    import pytesseract
    from PIL import Image as PILImage
    _TESSERACT = True
except ImportError:
    pytesseract = None
    PILImage = None
    _TESSERACT = False

# ── constants ──────────────────────────────────────────────────────────────────

# IEEE-style section heading ONLY — strict patterns to avoid matching list items
# Matches:  "I. TITLE"  "II. TITLE"  "III. TITLE"  "A. Background"
# Does NOT match: "1. Complete evaluation" "2. Expand dataset" (numbered list items)
_SECTION_RE = re.compile(
    r"^\s*(?:"
    r"(?:[IVX]{1,6}\.)\s+[A-Z]"      # Roman numeral: I. INTRO  II. METHOD
    r"|(?:[A-Z]\.)\s+[A-Z]"           # Letter:        A. Background
    r")\s*",
    re.IGNORECASE,
)

# Figure / table caption lines
_CAPTION_RE = re.compile(
    r"^\s*(?:Fig\.?|Figure|TABLE|Table)\s*[\dIVX]+[\.\:]",
    re.IGNORECASE,
)

# Standalone page number:  "2", " 3 ", "- 4 -"
_PAGE_NUM_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")

# Formula-like block heuristics (high symbol density)
_MATH_CHARS = set(r"∑∏∫∂∇∆αβγδεζηθλμνξπρστφχψωΩΓΔΘΛΞΠΣΦΨ±×÷√∞≈≠≤≥∈∉⊂⊃∪∩")
_LATEX_RE   = re.compile(r"\\[a-zA-Z]+\{|\\frac|\\sum|\\int|\$.*?\$")


def _is_formula_block(text: str) -> bool:
    """Heuristic: is this block mostly math/formula content?"""
    if not text or len(text) < 3:
        return False
    if _LATEX_RE.search(text):
        return True
    math_ratio = sum(1 for c in text if c in _MATH_CHARS) / max(1, len(text))
    return math_ratio > 0.08


def _is_page_noise(text: str) -> bool:
    """True for standalone page numbers, running headers/footers (short + no sentence)."""
    t = text.strip()
    if not t:
        return True
    if _PAGE_NUM_RE.match(t):
        return True
    # very short lines that are pure digits or common footer patterns
    if len(t) <= 6 and t.replace(" ", "").isdigit():
        return True
    return False


def _column_band(x0: float, page_width: float, n_cols: int) -> int:
    """Return 0-based column index for a block given its left x."""
    col_width = page_width / n_cols
    return min(int(x0 / col_width), n_cols - 1)


def _detect_columns(blocks: list, page_width: float) -> int:
    """
    Guess 1, 2, or 3 columns by checking x0 distribution of text blocks.
    Returns number of columns.
    """
    if not blocks:
        return 1
    xs = [b["x0"] for b in blocks if b.get("type") == "text" and b.get("text", "").strip()]
    if not xs:
        return 1
    # If most blocks start in the left third AND some start in the middle → 2 col
    mid = page_width / 2
    left  = sum(1 for x in xs if x < mid * 0.6)
    right = sum(1 for x in xs if x > mid * 0.4)
    if left > 1 and right > 1:
        # check for 3-col: right third
        third = page_width / 3
        far_right = sum(1 for x in xs if x > third * 1.8)
        if far_right > 1:
            return 3
        return 2
    return 1


def _sort_blocks_reading_order(blocks: list, page_width: float) -> list:
    """
    Sort blocks in human reading order:
      - Detect number of columns
      - Within each column, sort top-to-bottom
      - Columns read left-to-right
    Full-width blocks (spanning > 60% of page) are treated as column=0 and
    inserted at their vertical position relative to other full-width blocks.
    """
    if not blocks:
        return blocks

    n_cols = _detect_columns(blocks, page_width)

    def sort_key(b):
        x0   = b.get("x0", 0)
        y0   = b.get("y0", 0)
        x1   = b.get("x1", page_width)
        width = x1 - x0
        # full-width block → treat as col 0 but use exact y for ordering
        if width > page_width * 0.6:
            return (0, y0, x0)
        col = _column_band(x0, page_width, n_cols)
        return (col, y0, x0)

    return sorted(blocks, key=sort_key)


# ── same-line block merging ────────────────────────────────────────────────────

def _merge_same_line_blocks(blocks: list, y_tolerance: float = 8.0) -> list:
    """
    Merge consecutive text blocks that sit on the same visual line
    (y0 within y_tolerance points of each other).

    This fixes word-broken text in justified/2-column PDFs where the PDF
    encoder stores each word or phrase as a separate block at the same y.

    Image blocks are never merged — they pass through as-is.
    Merged block inherits: min x0, min y0, max x1, max y1 of all members.
    Text is joined with a space (smart: no double-space if already present).
    font_size and is_bold come from the first block in the merge group.
    """
    if not blocks:
        return blocks

    merged: list = []
    i = 0

    while i < len(blocks):
        blk = blocks[i]

        # image blocks pass through unchanged
        if blk.get("type") != "text":
            merged.append(blk)
            i += 1
            continue

        # start a merge group with this block
        group = [blk]
        j = i + 1

        while j < len(blocks):
            nxt = blocks[j]
            # only merge text blocks on the same line
            if nxt.get("type") != "text":
                break
            # same line = y0 within tolerance
            if abs(nxt["y0"] - blk["y0"]) > y_tolerance:
                break
            group.append(nxt)
            j += 1

        if len(group) == 1:
            # no merge needed
            merged.append(blk)
        else:
            # sort group left-to-right by x0
            group.sort(key=lambda b: b["x0"])
            # join text with smart spacing
            joined_text = ""
            for g in group:
                t = g.get("text", "")
                if not t:
                    continue
                if joined_text and not joined_text[-1].isspace() and not t[0].isspace():
                    joined_text += " " + t
                else:
                    joined_text += t
            merged.append({
                "type":      "text",
                "x0":        min(g["x0"] for g in group),
                "y0":        min(g["y0"] for g in group),
                "x1":        max(g["x1"] for g in group),
                "y1":        max(g["y1"] for g in group),
                "text":      joined_text.strip(),
                "font_size": blk.get("font_size", 0),
                "is_bold":   blk.get("is_bold", False),
            })

        i = j if len(group) > 1 else i + 1

    return merged


# ── pdfplumber table extraction ────────────────────────────────────────────────

def _extract_tables_pdfplumber(
    pdf_bytes: bytes,
    page_num_1based: int,
) -> List[Dict]:
    """
    Extract structured tables from a single page using pdfplumber.
    Returns list of dicts: {markdown, bbox, row_count, col_count}
    """
    if not _PDFPLUMBER:
        return []
    tables_out = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_num_1based > len(pdf.pages):
                return []
            page = pdf.pages[page_num_1based - 1]
            for tbl in page.extract_tables():
                if not tbl:
                    continue
                rows = []
                for row in tbl:
                    cells = [str(c or "").strip().replace("\n", " ") for c in row]
                    rows.append(cells)
                if not rows:
                    continue
                # build markdown table
                header = rows[0]
                sep    = ["---"] * len(header)
                md_lines = [
                    "| " + " | ".join(header) + " |",
                    "| " + " | ".join(sep)    + " |",
                ]
                for row in rows[1:]:
                    # pad/trim to header length
                    r = (row + [""] * len(header))[: len(header)]
                    md_lines.append("| " + " | ".join(r) + " |")
                tables_out.append({
                    "markdown":  "\n".join(md_lines),
                    "row_count": len(rows),
                    "col_count": len(header),
                })
    except Exception:
        pass
    return tables_out


# ── pix2text formula extraction ────────────────────────────────────────────────

_p2t_instance = None

def _get_p2t():
    global _p2t_instance
    if _p2t_instance is None and _PIX2TEXT:
        try:
            _p2t_instance = pix2text.Pix2Text.from_config()
        except Exception:
            pass
    return _p2t_instance


def _extract_formula_from_region(page: fitz.Page, rect: fitz.Rect) -> Optional[str]:
    """
    Render a region of a page to image and run pix2text on it.
    Returns LaTeX/math string or None.
    """
    p2t = _get_p2t()
    if p2t is None:
        return None
    try:
        clip  = page.get_pixmap(clip=rect, dpi=150)
        img   = PILImage.open(io.BytesIO(clip.tobytes("png")))
        result = p2t.recognize_formula(img)
        if result and str(result).strip():
            return str(result).strip()
    except Exception:
        pass
    return None


# ── pytesseract OCR for figure image regions ───────────────────────────────────

def _ocr_region(page: fitz.Page, rect: fitz.Rect) -> Optional[str]:
    if not _TESSERACT or PILImage is None:
        return None
    try:
        clip = page.get_pixmap(clip=rect, dpi=200)
        img  = PILImage.open(io.BytesIO(clip.tobytes("png")))
        text = pytesseract.image_to_string(img) or ""
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        return text if text else None
    except Exception:
        return None


# ── per-page extraction ────────────────────────────────────────────────────────

def _extract_page(
    fitz_doc:   fitz.Document,
    pdf_bytes:  bytes,
    page_num:   int,          # 1-based
    enable_ocr: bool,
    enable_formula: bool,
) -> Dict:
    """
    Extract one page.  Returns the page dict matching the Stage 3 contract:
      page_num, text_original, text_clean="", flags={...},
      figures=[], tables=[], sections=[]
    """
    page      = fitz_doc.load_page(page_num - 1)
    page_rect = page.rect
    pw        = page_rect.width

    # ── 1. get blocks with full geometry ──────────────────────────────────────
    raw_dict  = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    raw_blocks = raw_dict.get("blocks", [])

    # Flatten into a normalised list we can sort
    flat_blocks = []
    for blk in raw_blocks:
        btype = blk.get("type", -1)
        bbox  = blk.get("bbox", (0, 0, 0, 0))
        x0, y0, x1, y1 = bbox

        if btype == 0:  # text block
            lines_text = []
            # collect font metadata from all spans
            span_sizes  = []
            span_bolds  = []
            for line in blk.get("lines", []):
                line_parts = []
                for span in line.get("spans", []):
                    t = span.get("text", "")
                    if t:
                        line_parts.append(t)
                        span_sizes.append(span.get("size", 0))
                        # bold flag: bit 4 (value 16) in PyMuPDF flags int
                        span_bolds.append(bool(span.get("flags", 0) & 16))
                if line_parts:
                    # Join spans with space only when adjacent spans don't
                    # already have whitespace — fixes word-broken justified text
                    # in 2-column PDFs where each word is a separate span
                    joined = ""
                    for i, part in enumerate(line_parts):
                        if i == 0:
                            joined = part
                        else:
                            if joined and not joined[-1].isspace() and not part[0].isspace():
                                joined += " " + part
                            else:
                                joined += part
                    lines_text.append(joined)
            text = "\n".join(lines_text).strip()

            # block-level font summary
            blk_font_size = (sum(span_sizes) / len(span_sizes)) if span_sizes else 0
            blk_is_bold   = (sum(span_bolds) / max(1, len(span_bolds))) > 0.5  # majority bold

            flat_blocks.append({
                "type":      "text",
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "text":      text,
                "font_size": blk_font_size,
                "is_bold":   blk_is_bold,
            })

        elif btype == 1:  # image block
            flat_blocks.append({
                "type": "image",
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "text":      "",
                "font_size": 0,
                "is_bold":   False,
            })

    # ── 2. sort into reading order ─────────────────────────────────────────────
    flat_blocks = _sort_blocks_reading_order(flat_blocks, pw)

    # ── 2b. merge same-line blocks (fixes word-broken text) ───────────────────
    flat_blocks = _merge_same_line_blocks(flat_blocks)

    # ── 2c. compute page font statistics for heading/caption detection ─────────
    text_sizes = [b["font_size"] for b in flat_blocks
                  if b.get("type") == "text" and b.get("font_size", 0) > 0]
    page_avg_font  = (sum(text_sizes) / len(text_sizes)) if text_sizes else 10.0
    page_body_font = sorted(text_sizes)[len(text_sizes) // 2] if text_sizes else 10.0  # median

    # ── 3. get pdfplumber tables for this page ─────────────────────────────────
    plumber_tables = _extract_tables_pdfplumber(pdf_bytes, page_num)

    # ── 4. classify & reconstruct text ────────────────────────────────────────
    parts:    List[str]  = []
    figures:  List[Dict] = []
    tables:   List[Dict] = plumber_tables[:]  # start with plumber tables
    sections: List[str]  = []
    has_formulas = False

    # Track which table index we've appended to avoid duplicates
    tables_appended = set()

    for blk in flat_blocks:

        if blk["type"] == "image":
            # Try OCR on figure region
            if enable_ocr and _TESSERACT:
                rect     = fitz.Rect(blk["x0"], blk["y0"], blk["x1"], blk["y1"])
                ocr_text = _ocr_region(page, rect)
                if ocr_text:
                    parts.append(f"[FIGURE TEXT: {ocr_text}]")
                    figures.append({"type": "image_ocr", "text": ocr_text, "page_num": page_num})
            continue

        text = blk["text"]
        if not text:
            continue

        # strip page noise
        if _is_page_noise(text):
            continue

        first_line  = text.split("\n")[0].strip()
        font_size   = blk.get("font_size", page_body_font)
        is_bold     = blk.get("is_bold", False)
        is_short    = len(first_line) < 120          # headings/captions are short
        ends_period = first_line.endswith(".")        # body sentences end with .
        is_larger   = font_size > (page_body_font * 1.05)  # 5% larger than body
        # a heading must be a standalone single-line block — multi-line blocks
        # are body paragraphs, never headings
        is_single_line_block = "\n" not in text.strip()

        # ── detect section headings ────────────────────────────────────────────
        # Universal rule:
        #   (bold OR larger font) AND short AND no trailing period
        #   AND the entire block is just one line (not a paragraph)
        # Regex catches IEEE Roman/Letter patterns even when font info is poor
        is_heading = (
            (is_bold or is_larger)
            and is_short
            and not ends_period
            and is_single_line_block
            and len(first_line) > 1
        ) or bool(_SECTION_RE.match(first_line))

        if is_heading:
            sec = first_line
            if sec not in sections:
                sections.append(sec)

        # ── detect figure/table captions ───────────────────────────────────────
        # Universal rule: explicit caption marker word + number only.
        # near_image proximity removed — too unreliable in image-dense docs.
        # Any document that has proper captions uses a marker word.
        # Catches all variants: "Fig 1", "Fig. 1", "Figure 1", "Fig 1:",
        #   "Fig 2 Arduino Code" (no separator), "TABLE I", "Tab. 3"
        is_caption = is_short and bool(re.match(
            r"^\s*(?:Fig\.?|Figure|Table|TABLE|Tab\.?|Chart|Diagram|Exhibit|Image|Photo|Plate)\s*[\dIVX]+",
            first_line, re.IGNORECASE
        ))

        if is_caption:
            figures.append({"caption": first_line, "page_num": page_num})
            parts.append(first_line)
            # keep any remaining lines as body text — never discard
            remaining_lines = "\n".join(text.split("\n")[1:]).strip()
            if remaining_lines:
                parts.append(remaining_lines)
            continue

        # detect formula blocks
        if enable_formula and _is_formula_block(text):
            has_formulas = True
            if enable_formula and _PIX2TEXT and _TESSERACT:
                rect    = fitz.Rect(blk["x0"], blk["y0"], blk["x1"], blk["y1"])
                formula = _extract_formula_from_region(page, rect)
                if formula:
                    parts.append(f"[FORMULA: {formula}]")
                    continue
            # fallback: keep raw text but tag it
            parts.append(f"[FORMULA: {text}]")
            continue

        # normal text block — check if it's a table region (covered by pdfplumber)
        # we still keep text but mark it; pdfplumber table is richer
        parts.append(text)

    # ── 5. inject pdfplumber tables into text at end of page ──────────────────
    # (they'll be picked up by chunker as atomic table chunks)
    for i, tbl in enumerate(plumber_tables):
        if i not in tables_appended:
            parts.append("\n" + tbl["markdown"] + "\n")
            tables_appended.add(i)

    # ── 6. assemble text_original ──────────────────────────────────────────────
    text_original = "\n\n".join(p.strip() for p in parts if p.strip())

    flags = {
        "method":        "structured",
        "warnings":      [],
        "has_figures":   len(figures) > 0,
        "has_tables":    len(plumber_tables) > 0,
        "has_formulas":  has_formulas,
        "sections_found": sections,
        "pdfplumber":    _PDFPLUMBER,
        "pix2text":      _PIX2TEXT,
        "tesseract":     _TESSERACT,
    }

    return {
        "page_num":      page_num,
        "text_original": text_original,
        "text_clean":    "",          # Stage 4 fills this
        "flags":         flags,
        "figures":       figures,
        "tables":        plumber_tables,
        "sections":      sections,
    }


# ── public API (Stage 3 contract) ─────────────────────────────────────────────

def extract_pdf_pages(
    pdf_bytes:          bytes,
    *,
    ocr_min_text_chars: int  = 40,
    enable_ocr:         bool = True,
    enable_formula:     bool = True,
) -> Tuple[List[Dict], str]:
    """
    Stage 3 contract (unchanged signature):
      returns (pages, full_text_original)

    Each page dict:
      page_num, text_original, text_clean="", flags={}
      + NEW optional fields: figures=[], tables=[], sections=[]

    runner.py and chunk.py need zero changes.
    """
    doc    = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: List[Dict] = []
    full_parts: List[str] = []

    for page_num in range(1, doc.page_count + 1):
        page_dict = _extract_page(
            fitz_doc=doc,
            pdf_bytes=pdf_bytes,
            page_num=page_num,
            enable_ocr=enable_ocr,
            enable_formula=enable_formula,
        )

        # OCR fallback: if after all processing text is still too short
        raw_text = page_dict["text_original"]
        if enable_ocr and _TESSERACT and len(raw_text.strip()) < ocr_min_text_chars:
            fitz_page = doc.load_page(page_num - 1)
            pix       = fitz_page.get_pixmap(dpi=200)
            img       = PILImage.open(io.BytesIO(pix.tobytes("png")))
            try:
                ocr_raw = (pytesseract.image_to_string(img) or "").strip()
                if ocr_raw:
                    page_dict["text_original"] = ocr_raw
                    page_dict["flags"]["method"] = "ocr_fallback"
            except Exception as e:
                page_dict["flags"]["warnings"].append(f"OCR_FAILED: {e}")

        pages.append(page_dict)
        if page_dict["text_original"]:
            full_parts.append(page_dict["text_original"])

    doc.close()
    full_text_original = "\n\n".join(t for t in full_parts if t).strip()
    return pages, full_text_original