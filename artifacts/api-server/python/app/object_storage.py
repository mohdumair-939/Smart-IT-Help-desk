"""Small FastAPI-side adapter for Replit App Storage's signed-URL sidecar."""

import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

import httpx

SIDECAR_ENDPOINT = "http://127.0.0.1:1106"
MAX_SIGNED_URL_SECONDS = 900


class ObjectStorageError(RuntimeError):
    pass


def _private_object_parts(object_path: str) -> tuple[str, str]:
    private_dir = os.environ.get("PRIVATE_OBJECT_DIR", "").strip().rstrip("/")
    if not private_dir:
        raise ObjectStorageError("App Storage is not configured.")
    if not object_path.startswith(("/objects/knowledge-base/", "/objects/tickets/")):
        raise ObjectStorageError("The private object path is invalid.")

    relative_path = object_path.removeprefix("/objects/")
    if any(part in {"", ".", ".."} for part in relative_path.split("/")):
        raise ObjectStorageError("The private object path is invalid.")
    full_path = f"{private_dir}/{relative_path}"
    parts = full_path.lstrip("/").split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise ObjectStorageError("App Storage returned an invalid object path.")
    return parts[0], parts[1]


def _sign_url(object_path: str, method: str) -> str:
    bucket_name, object_name = _private_object_parts(object_path)
    expires_at = (datetime.now(UTC) + timedelta(seconds=MAX_SIGNED_URL_SECONDS)).isoformat()
    try:
        response = httpx.post(
            f"{SIDECAR_ENDPOINT}/object-storage/signed-object-url",
            json={
                "bucket_name": bucket_name,
                "object_name": object_name,
                "method": method,
                "expires_at": expires_at,
            },
            timeout=30,
        )
        response.raise_for_status()
        signed_url = response.json().get("signed_url")
    except (httpx.HTTPError, ValueError) as exc:
        raise ObjectStorageError("Could not create a secure App Storage link.") from exc
    if not isinstance(signed_url, str) or urlparse(signed_url).scheme != "https":
        raise ObjectStorageError("App Storage returned an invalid secure link.")
    return signed_url


def create_upload_url(object_path: str) -> str:
    return _sign_url(object_path, "PUT")


def create_download_url(object_path: str) -> str:
    return _sign_url(object_path, "GET")


def uploaded_object_size(object_path: str) -> int:
    signed_url = _sign_url(object_path, "HEAD")
    try:
        response = httpx.head(signed_url, timeout=30)
        if response.status_code == 404:
            raise ObjectStorageError("The upload has not reached App Storage yet.")
        response.raise_for_status()
        declared_size = response.headers.get("content-length")
        if not declared_size:
            raise ObjectStorageError("App Storage did not return the uploaded file size.")
        return int(declared_size)
    except ObjectStorageError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise ObjectStorageError("Could not verify the uploaded file in App Storage.") from exc


def download_object(object_path: str, max_bytes: int) -> bytes:
    signed_url = _sign_url(object_path, "GET")
    try:
        with httpx.stream("GET", signed_url, timeout=60) as response:
            response.raise_for_status()
            declared_size = response.headers.get("content-length")
            if declared_size and int(declared_size) > max_bytes:
                raise ObjectStorageError("The uploaded document is larger than the allowed limit.")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ObjectStorageError("The uploaded document is larger than the allowed limit.")
            return bytes(content)
    except (httpx.HTTPError, ValueError) as exc:
        raise ObjectStorageError("Could not read the uploaded document from App Storage.") from exc


def delete_object(object_path: str) -> None:
    signed_url = _sign_url(object_path, "DELETE")
    try:
        response = httpx.delete(signed_url, timeout=30)
        if response.status_code == 404:
            return
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ObjectStorageError("Could not remove the document from App Storage.") from exc


def object_path_for(document_id: UUID, filename: str) -> str:
    return f"/objects/knowledge-base/{document_id}/{filename}"


def attachment_object_path(ticket_id: UUID, attachment_id: UUID, filename: str) -> str:
    return f"/objects/tickets/{ticket_id}/{attachment_id}/{filename}"
