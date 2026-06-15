"""Storage abstraction.

Each gestora gets FOUR separate, siloed folders under ``gestoras/{gestora_id}/``::

    gestoras/{gestora_id}/
      ├── modelos/{precedent_id}-v{n}.docx      # gestora master templates (TOP-priority generation base)
      ├── playbooks/{playbook_id}.{ext}         # human-authored review rules used by the critic
      ├── precedentes/{precedent_id}-v{n}.docx  # past/validated documents
      └── outputs/{fund_id}/{request_id}/...    # generated draft/redline/counsel_edit/final

Global SLP / platform-base templates still live outside the gestora silo under
``lol-ai-lo-templates/{slp-curated,platform-base}/{es,en,fr}/``.

The four path-builder helpers below (:func:`modelos_path`,
:func:`playbooks_path`, :func:`precedentes_path`, :func:`outputs_path`) are the
single source of truth for these logical paths; callers must not hand-assemble
the gestora-folder segments.

If Google Drive is configured the file is uploaded there and the returned
storage key is ``drive:{file_id}``; otherwise files live on the local
filesystem under LOCAL_STORAGE_DIR and the key is ``local:{logical_path}``.
``read`` resolves either kind of key, so records remain valid across modes.
"""
from __future__ import annotations

from pathlib import Path

from config import get_settings
from services import drive


def modelos_path(gestora_id: str, filename: str) -> str:
    """Logical path for a gestora master template (TOP-priority generation base)."""
    return f"gestoras/{gestora_id}/modelos/{filename}"


def playbooks_path(gestora_id: str, filename: str) -> str:
    """Logical path for a human-authored review playbook attachment."""
    return f"gestoras/{gestora_id}/playbooks/{filename}"


def precedentes_path(gestora_id: str, filename: str) -> str:
    """Logical path for a past/validated precedent document."""
    return f"gestoras/{gestora_id}/precedentes/{filename}"


def outputs_path(gestora_id: str, fund_id: str, request_id: str, filename: str) -> str:
    """Logical path for a generated output (draft/redline/counsel_edit/final)."""
    return f"gestoras/{gestora_id}/outputs/{fund_id}/{request_id}/{filename}"


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


def delete(storage_key: str) -> None:
    """Delete the stored bytes for a storage key (GDPR retention sweep).

    Missing files are ignored: the sweep must be idempotent and a re-run after
    a partial failure should not raise.
    """
    if storage_key.startswith("drive:"):
        drive.delete_file(storage_key.removeprefix("drive:"))
        return
    logical_path = storage_key.removeprefix("local:")
    _safe_local_path(logical_path).unlink(missing_ok=True)
