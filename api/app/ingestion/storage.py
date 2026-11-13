"""Where statement PDFs live: Azure Blob Storage in the cloud, a local folder otherwise.

Files are content-addressed (`<source>/<sha256>.pdf`), so writing the same file twice is harmless.
"""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class StatementStore(Protocol):
    """Where statement PDFs are kept."""

    def put(self, key: str, data: bytes) -> None:
        """Store `data` under `key`."""
        ...

    def get(self, key: str) -> bytes:
        """The bytes stored under `key`; raises when there are none."""
        ...


class LocalStore:
    """Statements in a local folder (a Docker volume locally)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid storage key.")
        return path

    def put(self, key: str, data: bytes) -> None:
        """Write the bytes to a file under the statements folder."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        """Read the file stored under `key`."""
        return self._path(key).read_bytes()


class BlobStore:  # pragma: no cover - exercised in Azure, not in CI
    """Statements in a private Azure Blob container, signed in with the managed identity."""

    def __init__(self, account_url: str, container: str) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        self.container = service.get_container_client(container)

    def put(self, key: str, data: bytes) -> None:
        """Upload the bytes as a PDF blob."""
        from azure.storage.blob import ContentSettings

        self.container.upload_blob(
            key,
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/pdf"),
        )

    def get(self, key: str) -> bytes:
        """Download the blob's bytes."""
        return bytes(self.container.download_blob(key).readall())


@lru_cache
def get_store() -> StatementStore:
    """FastAPI dependency; tests override it with a LocalStore on a temp folder."""
    s = get_settings()
    if s.storage_account_url:
        return BlobStore(s.storage_account_url, s.statements_container)  # pragma: no cover
    return LocalStore(s.statements_dir)
