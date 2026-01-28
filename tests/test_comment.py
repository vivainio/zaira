"""Tests for comment module."""

from unittest.mock import MagicMock, patch
import sys

import pytest

from zaira.comment import read_body, add_comment


class TestReadBody:
    """Tests for read_body function."""

    def test_returns_body_unchanged(self):
        """Returns body text unchanged."""
        assert read_body("Hello world") == "Hello world"
        assert read_body("Multi\nline\ntext") == "Multi\nline\ntext"

    def test_reads_from_stdin(self, monkeypatch):
        """Reads from stdin when body is '-'."""
        monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: "stdin content"))

        result = read_body("-")

        assert result == "stdin content"


class TestAddComment:
    """Tests for add_comment function with mocked Jira."""

    def test_adds_comment_successfully(self, mock_jira):
        """Returns True when comment is added."""
        mock_jira.add_comment.return_value = MagicMock()

        result = add_comment("TEST-123", "This is a comment")

        assert result is True
        mock_jira.add_comment.assert_called_once_with("TEST-123", "This is a comment")

    def test_returns_false_on_error(self, mock_jira, capsys):
        """Returns False and prints error on failure."""
        mock_jira.add_comment.side_effect = Exception("Permission denied")

        result = add_comment("TEST-123", "Comment")

        assert result is False
        captured = capsys.readouterr()
        assert "Error adding comment" in captured.err

    def test_returns_false_when_no_comment_returned(self, mock_jira):
        """Returns False when add_comment returns None."""
        mock_jira.add_comment.return_value = None

        result = add_comment("TEST-123", "Comment")

        assert result is False
