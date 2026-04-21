"""Abstract file storage interface.

Provides a clean abstraction over file storage backends.
Phase 1-3: LocalStorage (local filesystem)
Phase 4: MinIO (S3-compatible object storage)
"""
from __future__ import annotations

import abc
from pathlib import Path


class StorageBackend(abc.ABC):
    """Abstract base class for file storage backends."""

    @abc.abstractmethod
    async def write(self, path: str, data: bytes) -> str:
        """Write data to storage.

        Args:
            path: Relative storage path (e.g. '{kb_id}/{doc_id}/file.pdf').
            data: File content as bytes.

        Returns:
            The full storage path where the file was written.
        """

    @abc.abstractmethod
    async def read(self, path: str) -> bytes:
        """Read data from storage.

        Args:
            path: Relative storage path.

        Returns:
            File content as bytes.

        Raises:
            FileNotFoundError: If the file does not exist.
        """

    @abc.abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: Relative storage path.

        Returns:
            True if the file was deleted, False if it didn't exist.
        """

    @abc.abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists in storage.

        Args:
            path: Relative storage path.

        Returns:
            True if the file exists.
        """

    @abc.abstractmethod
    async def get_full_path(self, path: str) -> str:
        """Get the full absolute path for a relative storage path.

        Args:
            path: Relative storage path.

        Returns:
            Full absolute path string.
        """
