"""Tests for file storage abstraction (S1-06)."""
from __future__ import annotations

import pytest

from app.storage.local import LocalStorage


@pytest.mark.unit
class TestLocalStorage:
    """LocalStorage implementation tests."""

    @pytest.fixture
    def storage(self, tmp_path) -> LocalStorage:
        """Create a LocalStorage instance with a temp directory."""
        return LocalStorage(base_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_write_and_read(self, storage: LocalStorage):
        """Should write and read back the same data."""
        data = b"hello world"
        path = "kb1/doc1/test.pdf"
        written_path = await storage.write(path, data)
        assert written_path is not None
        result = await storage.read(path)
        assert result == data

    @pytest.mark.asyncio
    async def test_exists_after_write(self, storage: LocalStorage):
        """exists() should return True after writing."""
        await storage.write("test/file.txt", b"content")
        assert await storage.exists("test/file.txt") is True

    @pytest.mark.asyncio
    async def test_exists_before_write(self, storage: LocalStorage):
        """exists() should return False for non-existent file."""
        assert await storage.exists("nonexistent.txt") is False

    @pytest.mark.asyncio
    async def test_delete_existing_file(self, storage: LocalStorage):
        """delete() should remove the file and return True."""
        await storage.write("to_delete.txt", b"data")
        result = await storage.delete("to_delete.txt")
        assert result is True
        assert await storage.exists("to_delete.txt") is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, storage: LocalStorage):
        """delete() should return False for non-existent file."""
        result = await storage.delete("nonexistent.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_read_nonexistent_raises(self, storage: LocalStorage):
        """read() should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            await storage.read("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self, storage: LocalStorage):
        """Should reject path traversal attempts."""
        with pytest.raises(ValueError, match="Path traversal"):
            await storage.write("../../etc/passwd", b"hack")

    @pytest.mark.asyncio
    async def test_nested_directory_creation(self, storage: LocalStorage):
        """Should create nested directories automatically."""
        path = "a/b/c/d/file.txt"
        await storage.write(path, b"deep")
        result = await storage.read(path)
        assert result == b"deep"

    @pytest.mark.asyncio
    async def test_get_full_path(self, storage: LocalStorage):
        """get_full_path should return absolute path."""
        full = await storage.get_full_path("test/file.txt")
        assert str(storage.base_dir) in full
