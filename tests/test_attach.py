"""Tests for attach module."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from zaira.attach import attach_file, attach_command


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


class TestAttachCommand:
    """Tests for attach_command function."""

    def test_exits_on_missing_file(self, tmp_path, capsys):
        """Exits with error when file doesn't exist."""
        args = argparse.Namespace(
            key="test-123",
            files=[str(tmp_path / "nonexistent.txt")],
        )

        with pytest.raises(SystemExit) as exc_info:
            attach_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_uploads_multiple_files_successfully(self, mock_jira, tmp_path, capsys):
        """Uploads multiple files and reports success."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        args = argparse.Namespace(
            key="test-123",
            files=[str(file1), str(file2)],
        )

        with patch("zaira.attach.get_jira_site", return_value="jira.example.com"):
            attach_command(args)

        captured = capsys.readouterr()
        assert "Uploading 2 file(s) to TEST-123" in captured.out
        assert "Uploaded 2/2 files" in captured.out
        assert "jira.example.com" in captured.out

    def test_reports_partial_failure(self, mock_jira, tmp_path, capsys):
        """Reports partial failure when some uploads fail."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        # First upload succeeds, second fails
        mock_jira.add_attachment.side_effect = [None, Exception("Upload failed")]

        args = argparse.Namespace(
            key="test-123",
            files=[str(file1), str(file2)],
        )

        with patch("zaira.attach.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                attach_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Uploaded 1/2 files" in captured.out

    def test_uppercases_ticket_key(self, mock_jira, tmp_path, capsys):
        """Converts ticket key to uppercase."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args = argparse.Namespace(
            key="test-123",
            files=[str(test_file)],
        )

        with patch("zaira.attach.get_jira_site", return_value="jira.example.com"):
            attach_command(args)

        # Check that the key was uppercased in the add_attachment call
        call_args = mock_jira.add_attachment.call_args
        assert call_args[0][0] == "TEST-123"
