"""Tests for zaira.util."""

from unittest.mock import patch

import pytest

from zaira.util import atomic_write_text


class TestAtomicWriteText:
    """Tests for atomic_write_text function."""

    def test_writes_new_file(self, tmp_path) -> None:
        """Writes content to a file that doesn't exist yet."""
        target = tmp_path / "new.txt"

        atomic_write_text(target, "hello")

        assert target.read_text(encoding="utf-8") == "hello"

    def test_overwrites_existing_file(self, tmp_path) -> None:
        """Replaces the contents of an existing file."""
        target = tmp_path / "existing.txt"
        target.write_text("old", encoding="utf-8")

        atomic_write_text(target, "new")

        assert target.read_text(encoding="utf-8") == "new"

    def test_no_leftover_temp_files(self, tmp_path) -> None:
        """Leaves no temp file behind after a successful write."""
        target = tmp_path / "file.txt"

        atomic_write_text(target, "content")

        assert list(tmp_path.iterdir()) == [target]

    def test_failed_write_leaves_previous_file_intact(self, tmp_path) -> None:
        """A failure during replacement doesn't touch the previous file."""
        target = tmp_path / "file.txt"
        target.write_text("original", encoding="utf-8")

        with (
            patch("os.replace", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            atomic_write_text(target, "new content")

        assert target.read_text(encoding="utf-8") == "original"
        assert list(tmp_path.iterdir()) == [target]

    def test_failed_write_to_new_file_leaves_no_file(self, tmp_path) -> None:
        """A failure writing a brand-new file leaves nothing behind."""
        target = tmp_path / "new.txt"

        with (
            patch("os.replace", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            atomic_write_text(target, "content")

        assert not target.exists()
        assert list(tmp_path.iterdir()) == []

    def test_custom_encoding(self, tmp_path) -> None:
        """Honors a non-default encoding."""
        target = tmp_path / "latin1.txt"

        atomic_write_text(target, "café", encoding="latin-1")

        assert target.read_bytes() == "café".encode("latin-1")
