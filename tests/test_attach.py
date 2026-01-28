"""Tests for attach module."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from zaira.attach import attach_file


class TestAttachFile:
    """Tests for attach_file function with mocked Jira."""

    def test_uploads_file_successfully(self, mock_jira, tmp_path):
        """Returns True when file is uploaded."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = attach_file("TEST-123", test_file)

        assert result is True
        mock_jira.add_attachment.assert_called_once()
        call_args = mock_jira.add_attachment.call_args
        assert call_args[0][0] == "TEST-123"
        assert call_args[1]["filename"] == "test.txt"

    def test_returns_false_on_error(self, mock_jira, tmp_path, capsys):
        """Returns False and prints error on failure."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        mock_jira.add_attachment.side_effect = Exception("Upload failed")

        result = attach_file("TEST-123", test_file)

        assert result is False
        captured = capsys.readouterr()
        assert "Error uploading" in captured.err
