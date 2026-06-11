"""Redline engine: tracked-changes .docx comparing generated doc vs precedent.

- Paragraph-level alignment with difflib; replaced paragraphs are further
  diffed word-by-word so only the changed runs are marked.
- Insertions/deletions are emitted as real Word revision elements
  (``w:ins`` / ``w:del``), author always "Lol-AI-lo AI" (SPEC guardrail 6).
- Pure formatting changes (whitespace-only differences) are NOT marked.
"""
from __future__ import annotations

import difflib
import io
import re
from datetime import datetime, timezone

from docx import Document
from docx.oxml.ns import qn

try:  # python-docx >= 1.x
    from docx.oxml.parser import OxmlElement
except ImportError:  # older layouts
    from docx.oxml import OxmlElement  # type: ignore[attr-defined,no-redef]

REDLINE_AUTHOR = "Lol-AI-lo AI"

_rev_id = 0


def _next_rev_id() -> str:
    global _rev_id
    _rev_id += 1
    return str(_rev_id)


def _now_w3c() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(text: str) -> str:
    """Collapse whitespace so formatting-only differences compare equal."""
    return re.sub(r"\s+", " ", text).strip()


def _make_run(text: str, del_text: bool = False) -> OxmlElement:
    run = OxmlElement("w:r")
    tag = "w:delText" if del_text else "w:t"
    t = OxmlElement(tag)
    t.set(qn("xml:space"), "preserve")
    t.text = text
    run.append(t)
    return run


def _revision_element(kind: str, text: str) -> OxmlElement:
    """Build a w:ins or w:del element wrapping a single run."""
    element = OxmlElement(kind)
    element.set(qn("w:id"), _next_rev_id())
    element.set(qn("w:author"), REDLINE_AUTHOR)
    element.set(qn("w:date"), _now_w3c())
    element.append(_make_run(text, del_text=(kind == "w:del")))
    return element


def _append_plain(paragraph, text: str) -> None:
    if text:
        paragraph._p.append(_make_run(text))


def _append_insertion(paragraph, text: str) -> None:
    if text:
        paragraph._p.append(_revision_element("w:ins", text))


def _append_deletion(paragraph, text: str) -> None:
    if text:
        paragraph._p.append(_revision_element("w:del", text))


def _tokens(text: str) -> list[str]:
    # Keep separators so reassembled text preserves spacing.
    return re.findall(r"\S+\s*", text)


def _diff_paragraph(paragraph, old: str, new: str) -> None:
    """Word-level diff inside a replaced paragraph."""
    old_tokens, new_tokens = _tokens(old), _tokens(new)
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            _append_plain(paragraph, "".join(old_tokens[a1:a2]))
        else:
            if op in ("replace", "delete"):
                _append_deletion(paragraph, "".join(old_tokens[a1:a2]))
            if op in ("replace", "insert"):
                _append_insertion(paragraph, "".join(new_tokens[b1:b2]))


def build_redline(precedent_text: str, generated_text: str) -> bytes:
    """Produce a tracked-changes .docx of generated_text vs precedent_text."""
    old_paragraphs = [p for p in precedent_text.split("\n") if p.strip()]
    new_paragraphs = [p for p in generated_text.split("\n") if p.strip()]

    document = Document()
    matcher = difflib.SequenceMatcher(
        a=[_normalize(p) for p in old_paragraphs],
        b=[_normalize(p) for p in new_paragraphs],
        autojunk=False,
    )
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            # Unchanged (incl. whitespace-only differences): keep the NEW text
            # unmarked — formatting changes are not revisions.
            for paragraph_text in new_paragraphs[b1:b2]:
                _append_plain(document.add_paragraph(), paragraph_text)
        elif op == "delete":
            for paragraph_text in old_paragraphs[a1:a2]:
                _append_deletion(document.add_paragraph(), paragraph_text)
        elif op == "insert":
            for paragraph_text in new_paragraphs[b1:b2]:
                _append_insertion(document.add_paragraph(), paragraph_text)
        else:  # replace: pair up paragraphs, word-diff each pair
            old_block = old_paragraphs[a1:a2]
            new_block = new_paragraphs[b1:b2]
            for i in range(max(len(old_block), len(new_block))):
                paragraph = document.add_paragraph()
                if i < len(old_block) and i < len(new_block):
                    _diff_paragraph(paragraph, old_block[i], new_block[i])
                elif i < len(old_block):
                    _append_deletion(paragraph, old_block[i])
                else:
                    _append_insertion(paragraph, new_block[i])

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
