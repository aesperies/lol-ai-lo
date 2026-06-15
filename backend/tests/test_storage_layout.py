"""Per-gestora storage taxonomy: the four siloed folders + traversal guard.

Each gestora gets four separate folders (modelos / playbooks / precedentes /
outputs). The path builders are the single source of truth for these logical
paths; the local path-traversal guard still rejects ``..`` escapes.
"""
from __future__ import annotations

import pytest

from services import storage


def test_modelos_path_layout():
    assert storage.modelos_path("g1", "p1-v2.docx") == "gestoras/g1/modelos/p1-v2.docx"


def test_playbooks_path_layout():
    assert storage.playbooks_path("g1", "pb1.docx") == "gestoras/g1/playbooks/pb1.docx"


def test_precedentes_path_layout():
    assert storage.precedentes_path("g1", "p1-v1.docx") == "gestoras/g1/precedentes/p1-v1.docx"


def test_outputs_path_layout():
    assert (
        storage.outputs_path("g1", "f1", "r1", "draft.docx")
        == "gestoras/g1/outputs/f1/r1/draft.docx"
    )


def test_four_folders_are_distinct_per_gestora():
    folders = {
        storage.modelos_path("g1", "x").rsplit("/", 1)[0],
        storage.playbooks_path("g1", "x").rsplit("/", 1)[0],
        storage.precedentes_path("g1", "x").rsplit("/", 1)[0],
        storage.outputs_path("g1", "f1", "r1", "x").rsplit("/", 1)[0],
    }
    assert len(folders) == 4


def test_roundtrip_save_read_for_each_folder():
    paths = [
        storage.modelos_path("g1", "p1-v1.docx"),
        storage.playbooks_path("g1", "pb1.docx"),
        storage.precedentes_path("g1", "p1-v1.docx"),
        storage.outputs_path("g1", "f1", "r1", "draft.docx"),
    ]
    for idx, logical in enumerate(paths):
        key = storage.save(logical, f"payload-{idx}".encode())
        assert key == f"local:{logical}"
        assert storage.read(key) == f"payload-{idx}".encode()


def test_path_traversal_guard_still_holds():
    # A logical path escaping the storage root is rejected at save and read.
    with pytest.raises(ValueError):
        storage.save("gestoras/g1/modelos/../../../../etc/passwd", b"x")
    with pytest.raises(ValueError):
        storage.read("local:gestoras/g1/../../../../etc/passwd")
