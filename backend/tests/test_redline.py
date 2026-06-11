"""Redline engine tests: tracked changes, author, formatting-change exclusion."""
from __future__ import annotations

import io
import re

from docx import Document

from services.docx_renderer import extract_text, render_docx
from services.redline import REDLINE_AUTHOR, build_redline


def _xml(docx_bytes: bytes) -> str:
    return Document(io.BytesIO(docx_bytes)).element.xml


PRECEDENT = (
    "ACTA DE REUNIÓN DEL CONSEJO\n"
    "Se aprueba la llamada de capital por importe de 100.000 euros.\n"
    "La reunión se celebra en Madrid.\n"
    "Cláusula que será eliminada en la nueva versión."
)
GENERATED = (
    "ACTA DE REUNIÓN DEL CONSEJO\n"
    "Se aprueba la llamada de capital por importe de 500.000 euros.\n"
    "La reunión se celebra en Madrid.\n"
    "Cláusula nueva añadida sobre el período de inversión."
)


class TestRedline:
    def test_contains_tracked_insertions_and_deletions(self):
        xml = _xml(build_redline(PRECEDENT, GENERATED))
        assert "<w:ins " in xml
        assert "<w:del " in xml
        # Old amount deleted, new amount inserted.
        assert "100.000" in xml and "500.000" in xml

    def test_author_is_always_lolailo_ai(self):
        xml = _xml(build_redline(PRECEDENT, GENERATED))
        authors = set(re.findall(r'w:author="([^"]+)"', xml))
        assert authors == {REDLINE_AUTHOR}
        assert REDLINE_AUTHOR == "Lol-AI-lo AI"

    def test_unchanged_paragraphs_not_marked(self):
        redline = build_redline(PRECEDENT, GENERATED)
        document = Document(io.BytesIO(redline))
        # "La reunión se celebra en Madrid." is identical -> its paragraph
        # must contain no revision elements.
        for paragraph in document.paragraphs:
            if "Madrid" in paragraph.text:
                paragraph_xml = paragraph._p.xml
                assert "<w:ins " not in paragraph_xml
                assert "<w:del " not in paragraph_xml
                break
        else:
            raise AssertionError("Unchanged paragraph missing from redline")

    def test_word_level_diff_only_marks_changed_tokens(self):
        from docx.oxml.ns import qn

        # The shared prefix of the modified sentence stays unmarked: it must
        # appear in plain w:r runs that hang directly off the paragraph
        # (i.e. not wrapped in w:ins / w:del).
        document = Document(io.BytesIO(build_redline(PRECEDENT, GENERATED)))
        target = next(p for p in document.paragraphs if "llamada de capital" in p._p.xml)
        plain_text = ""
        for child in target._p:
            if child.tag == qn("w:r"):
                t = child.find(qn("w:t"))
                if t is not None and t.text:
                    plain_text += t.text
        assert "llamada de capital" in plain_text
        assert "<w:del " in target._p.xml and "<w:ins " in target._p.xml

    def test_pure_formatting_changes_not_marked(self):
        original = "Se aprueba la llamada de capital.\nLa reunión se celebra en Madrid."
        reformatted = "Se  aprueba   la llamada de capital.\nLa reunión se celebra   en Madrid."
        xml = _xml(build_redline(original, reformatted))
        assert "<w:ins " not in xml
        assert "<w:del " not in xml

    def test_deleted_text_uses_deltext(self):
        xml = _xml(build_redline("Cláusula que desaparece por completo.", "Texto totalmente distinto."))
        assert "<w:delText" in xml


class TestDocxRenderer:
    def test_render_and_extract_roundtrip(self):
        text = "ACTA DE REUNIÓN\nPrimer acuerdo del consejo.\nSegundo acuerdo del consejo."
        extracted = extract_text(render_docx(text))
        for line in text.split("\n"):
            assert line in extracted
