"""Google Drive client for precedent/document storage.

Lazy-imported and fully optional: if GOOGLE_SERVICE_ACCOUNT_FILE is unset (or
the google packages are missing) callers fall back to the local filesystem via
services.storage.

Folder layout (SPEC):
  /lol-ai-lo-templates/{slp-curated,platform-base}/{es,en,fr}/
  /gestoras/{gestora_id}/precedents/
  /gestoras/{gestora_id}/funds/{fund_id}/documents/
"""
from __future__ import annotations

import io
from typing import Any, Optional

from config import ServiceNotConfiguredError, get_settings

_service: Optional[Any] = None


def is_configured() -> bool:
    """True when Drive credentials are present AND the client libs import."""
    settings = get_settings()
    if not settings.drive_configured:
        return False
    try:
        import googleapiclient  # noqa: F401  type: ignore[import-not-found]
        import google.oauth2.service_account  # noqa: F401  type: ignore[import-not-found]
    except ImportError:
        return False
    return True


def _get_service() -> Any:
    """Build (once) the Drive v3 service from the service-account file."""
    global _service
    if _service is not None:
        return _service
    settings = get_settings()
    if not settings.drive_configured:
        raise ServiceNotConfiguredError("google_drive", "Set GOOGLE_SERVICE_ACCOUNT_FILE.")
    # Lazy imports: heavy optional deps.
    from google.oauth2 import service_account  # type: ignore[import-not-found]
    from googleapiclient.discovery import build  # type: ignore[import-not-found]

    # TODO: real service-account JSON credential required here.
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    _service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return _service


def upload_bytes(name: str, data: bytes, parent_folder_id: str) -> str:
    """Upload a file; returns the Drive file id."""
    from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-not-found]

    service = _get_service()
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/octet-stream")
    file = (
        service.files()
        .create(body={"name": name, "parents": [parent_folder_id]}, media_body=media, fields="id")
        .execute()
    )
    return file["id"]


def download_bytes(file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import-not-found]

    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def ensure_folder(name: str, parent_folder_id: str) -> str:
    """Find or create a subfolder; returns its id."""
    service = _get_service()
    query = (
        f"name = '{name}' and '{parent_folder_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = service.files().list(q=query, fields="files(id)").execute()
    if res.get("files"):
        return res["files"][0]["id"]
    folder = (
        service.files()
        .create(
            body={
                "name": name,
                "parents": [parent_folder_id],
                "mimeType": "application/vnd.google-apps.folder",
            },
            fields="id",
        )
        .execute()
    )
    return folder["id"]
