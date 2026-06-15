"""Convert stored .docx versions (draft / redline / counsel_edit / final) to
safe HTML for in-browser viewing.

- Walks paragraphs/runs with python-docx: headings (style name or bold
  heuristic), bold/italic/underline, simple tables and lists.
- Revision marks: python-docx's high-level API skips ``w:ins`` / ``w:del``
  elements (the redline writer in services/redline.py appends them as raw
  OXML), so paragraph XML is walked directly. Insertions become
  ``<ins class="rl-ins">`` and deletions ``<del class="rl-del">`` so the
  frontend can style them green/red.
- Injection-safe by construction: ALL text content goes through
  ``html.escape`` and only a fixed whitelist of tags is emitted
  (p, h1-h3, strong, em, u, ins, del, table/tr/td, ul/ol/li, br) with fixed
  class names — no attribute ever comes from document content.
"""
from __future__ import annotations

import html
import io
from typing import Any, Optional

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

# Fixed class names (the ONLY attributes ever emitted).
INS_CLASS = "rl-ins"
DEL_CLASS = "rl-del"
TABLE_CLASS = "doc-table"

_HEADING_MAX_CHARS = 100

# Cap on rendered top-level blocks; pathologically large documents are
# truncated with a clear note rather than producing unbounded HTML.
_MAX_BLOCKS = 5000
_TRUNCATION_NOTE = "<p>[…documento truncado para visualización…]</p>"


def _run_text(r_el: Any) -> str:
    """Escaped text of one run (w:t + w:delText + w:br/w:tab)."""
    parts: list[str] = []
    for child in r_el.iterchildren():
        tag = child.tag
        if tag in (qn("w:t"), qn("w:delText")):
            parts.append(html.escape(child.text or ""))
        elif tag == qn("w:br"):
            parts.append("<br/>")
        elif tag == qn("w:tab"):
            parts.append(" ")
    return "".join(parts)


def _run_flag(r_el: Any, flag: str) -> bool:
    """True when the run property `flag` (w:b / w:i / w:u) is on."""
    r_pr = r_el.find(qn("w:rPr"))
    if r_pr is None:
        return False
    el = r_pr.find(qn(f"w:{flag}"))
    if el is None:
        return False
    val = el.get(qn("w:val"))
    return val not in ("false", "0", "none")


def _render_run(r_el: Any) -> str:
    text = _run_text(r_el)
    if not text:
        return ""
    if _run_flag(r_el, "u"):
        text = f"<u>{text}</u>"
    if _run_flag(r_el, "i"):
        text = f"<em>{text}</em>"
    if _run_flag(r_el, "b"):
        text = f"<strong>{text}</strong>"
    return text


def _render_inline(element: Any, stats: dict[str, int]) -> str:
    """Inline HTML for the children of a paragraph (or w:ins/w:del wrapper)."""
    parts: list[str] = []
    for child in element.iterchildren():
        tag = child.tag
        if tag == qn("w:r"):
            parts.append(_render_run(child))
        elif tag == qn("w:ins"):
            inner = _render_inline(child, stats)
            if inner:
                stats["insertions"] += 1
                parts.append(f'<ins class="{INS_CLASS}">{inner}</ins>')
        elif tag == qn("w:del"):
            inner = _render_inline(child, stats)
            if inner:
                stats["deletions"] += 1
                parts.append(f'<del class="{DEL_CLASS}">{inner}</del>')
        elif tag == qn("w:hyperlink"):
            # Text only — never emit href or any document-provided attribute.
            parts.append(_render_inline(child, stats))
    return "".join(parts)


def _has_revisions(p_el: Any) -> bool:
    return p_el.find(qn("w:ins")) is not None or p_el.find(qn("w:del")) is not None


def _heading_level(paragraph: Paragraph) -> Optional[int]:
    """Heading level 1-3, by style name or bold+short-line heuristic."""
    if _has_revisions(paragraph._p):
        return None  # keep ins/del rendering inside revised paragraphs
    try:
        style_name = paragraph.style.name or ""
    except Exception:
        style_name = ""
    if style_name.startswith("Heading"):
        suffix = style_name.removeprefix("Heading").strip()
        level = int(suffix) if suffix.isdigit() else 1
        return min(level, 3)
    runs = paragraph.runs
    text = paragraph.text.strip()
    if runs and text and len(text) <= _HEADING_MAX_CHARS and all(r.bold for r in runs):
        return 2
    return None


def _is_list_item(p_el: Any) -> bool:
    p_pr = p_el.find(qn("w:pPr"))
    return p_pr is not None and p_pr.find(qn("w:numPr")) is not None


def _list_tag(paragraph: Paragraph) -> str:
    try:
        style_name = paragraph.style.name or ""
    except Exception:
        style_name = ""
    return "ol" if "Number" in style_name else "ul"


def _render_table(tbl_el: Any, stats: dict[str, int]) -> str:
    rows: list[str] = []
    for tr in tbl_el.findall(qn("w:tr")):
        cells: list[str] = []
        for tc in tr.findall(qn("w:tc")):
            cell_parts = [
                inner
                for p in tc.findall(qn("w:p"))
                if (inner := _render_inline(p, stats))
            ]
            cells.append(f"<td>{'<br/>'.join(cell_parts)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f'<table class="{TABLE_CLASS}">{"".join(rows)}</table>'


def docx_to_html(docx_bytes: bytes) -> dict[str, Any]:
    """Render .docx bytes as safe HTML.

    Returns ``{"html": str, "stats": {"insertions": n, "deletions": n}}``;
    the stats are zero for non-redline documents.
    """
    document = Document(io.BytesIO(docx_bytes))
    stats = {"insertions": 0, "deletions": 0}
    blocks: list[str] = []
    pending_items: list[str] = []
    pending_tag = "ul"

    def flush_list() -> None:
        nonlocal pending_items
        if pending_items:
            items = "".join(f"<li>{item}</li>" for item in pending_items)
            blocks.append(f"<{pending_tag}>{items}</{pending_tag}>")
            pending_items = []

    for child in document.element.body.iterchildren():
        if len(blocks) >= _MAX_BLOCKS:
            blocks.append(_TRUNCATION_NOTE)
            break
        if child.tag == qn("w:tbl"):
            flush_list()
            blocks.append(_render_table(child, stats))
            continue
        if child.tag != qn("w:p"):
            continue
        paragraph = Paragraph(child, document)
        inner = _render_inline(child, stats)
        if not inner:
            flush_list()
            continue
        if _is_list_item(child):
            if not pending_items:
                pending_tag = _list_tag(paragraph)
            pending_items.append(inner)
            continue
        flush_list()
        level = _heading_level(paragraph)
        if level is not None:
            # Headings carry plain escaped text; the bold wrapper is redundant.
            blocks.append(f"<h{level}>{html.escape(paragraph.text.strip())}</h{level}>")
        else:
            blocks.append(f"<p>{inner}</p>")
    flush_list()

    return {"html": "\n".join(blocks), "stats": stats}
