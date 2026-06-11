"""Storage abstraction.

Logical paths follow the SPEC Drive layout, e.g.
``gestoras/{gestora_id}/funds/{fund_id}/documents/{request_id}/draft.docx``.

If Google Drive is configured the file is uploaded there and the returned
storage key is ``drive:{file_id}``; otherwise files live on the local
filesystem under LOCAL_STORAGE_DIR and the key is ``local:{logical_path}``.
``read`` resolves either kind of key, so records remain valid across modes.
"""
from __future__ import annotations

from pathlib import Path

from config import get_settings
from services import drive


def _local_root() -> Path:
    root = Path(get_settings().local_storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_local_path(logical_path: str) -> Path:
    root = _local_root()
    target = (root / logical_path).resolve()
    # Defense against path traversal in logical paths.
    if root != target and root not in target.parents:
        raise ValueError(f"Illegal storage path: {logical_path}")
    return target


def save(logical_path: str, data: bytes) -> str:
    """Persist bytes; returns the storage key to record in the DB."""
    if drive.is_configured():
        settings = get_settings()
        # Walk/create the folder chain under the configured Drive root.
        parts = logical_path.split("/")
        parent = (
            settings.drive_templates_folder_id
            if parts[0] == "lol-ai-lo-templates"
            else settings.drive_gestoras_folder_id
        )
        for folder_name in parts[:-1]:
            parent = drive.ensure_folder(folder_name, parent)
        file_id = drive.upload_bytes(parts[-1], data, parent)
        return f"drive:{file_id}"

    target = _safe_local_path(logical_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return f"local:{logical_path}"


def read(storage_key: str) -> bytes:
    """Load bytes for a storage key produced by save()."""
    if storage_key.startswith("drive:"):
        return drive.download_bytes(storage_key.removeprefix("drive:"))
    logical_path = storage_key.removeprefix("local:")
    return _safe_local_path(logical_path).read_bytes()
