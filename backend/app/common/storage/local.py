"""Local filesystem storage backend implementation."""
from __future__ import annotations

import aiofiles
from pathlib import Path

from app.common.core.logging import get_logger
from app.common.storage.base import StorageBackend

logger = get_logger(__name__)


class LocalStorage(StorageBackend):
    """Store files on the local filesystem.

    Args:
        base_dir: Root directory for all stored files.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _resolve(self, path: str) -> Path:
        """Resolve a relative path to an absolute path, with safety check."""
        resolved = (self._base_dir / path).resolve()
        # Prevent path traversal attacks
        if not str(resolved).startswith(str(self._base_dir.resolve())):
            raise ValueError(f"Path traversal detected: {path}")
        return resolved

    async def write(self, path: str, data: bytes) -> str:
        """Write data to local filesystem."""
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(data)
        logger.info("file_written", path=str(full_path), size=len(data))
        return str(full_path)

    async def read(self, path: str) -> bytes:
        """Read data from local filesystem."""
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        async with aiofiles.open(full_path, "rb") as f:
            data = await f.read()
        return data

    async def delete(self, path: str) -> bool:
        """Delete a file from local filesystem."""
        full_path = self._resolve(path)
        if not full_path.exists():
            logger.warning("file_not_found_for_delete", path=str(full_path))
            return False
        full_path.unlink()
        logger.info("file_deleted", path=str(full_path))
        return True

    async def exists(self, path: str) -> bool:
        """Check if a file exists on local filesystem."""
        full_path = self._resolve(path)
        return full_path.exists()

    async def get_full_path(self, path: str) -> str:
        """Get the full absolute path."""
        return str(self._resolve(path))
