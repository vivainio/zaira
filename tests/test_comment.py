"""Tests for comment module."""

import argparse
from unittest.mock import MagicMock, patch
import sys

import pytest

from zaira.comment import read_body, add_comment, comment_command


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


class TestCommentCommand:
    """Tests for comment_command function."""

    def test_exits_on_empty_body(self, capsys):
        """Exits with error when comment body is empty."""
        args = argparse.Namespace(key="test-123", body="   ")

        with pytest.raises(SystemExit) as exc_info:
            comment_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Comment body cannot be empty" in captured.err

    def test_exits_on_markdown_syntax(self, capsys):
        """Exits with error when body contains markdown."""
        args = argparse.Namespace(key="test-123", body="## Heading\n\nContent")

        with pytest.raises(SystemExit) as exc_info:
            comment_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "markdown syntax" in captured.err
        assert "h2." in captured.err

    def test_adds_comment_successfully(self, mock_jira, capsys):
        """Adds comment and shows success message."""
        mock_jira.add_comment.return_value = MagicMock()

        args = argparse.Namespace(key="test-123", body="This is a valid comment")

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        captured = capsys.readouterr()
        assert "Comment added to TEST-123" in captured.out
        assert "jira.example.com" in captured.out

    def test_exits_on_add_failure(self, mock_jira, capsys):
        """Exits with error when add_comment fails."""
        mock_jira.add_comment.side_effect = Exception("Permission denied")

        args = argparse.Namespace(key="test-123", body="Valid comment")

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                comment_command(args)

        assert exc_info.value.code == 1

    def test_uppercases_ticket_key(self, mock_jira, capsys):
        """Converts ticket key to uppercase."""
        mock_jira.add_comment.return_value = MagicMock()

        args = argparse.Namespace(key="test-123", body="Comment")

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        mock_jira.add_comment.assert_called_once_with("TEST-123", "Comment")

    def test_reads_body_from_stdin(self, mock_jira, monkeypatch, capsys):
        """Reads comment body from stdin when body is '-'."""
        monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: "stdin comment"))
        mock_jira.add_comment.return_value = MagicMock()

        args = argparse.Namespace(key="TEST-123", body="-")

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        mock_jira.add_comment.assert_called_once_with("TEST-123", "stdin comment")


class TestSpecialCharacters:
    """Tests for special character handling in comments."""

    def test_comment_with_quotes(self, mock_jira, capsys):
        """Handles comments containing various quote characters."""
        mock_jira.add_comment.return_value = MagicMock()

        args = argparse.Namespace(key="TEST-123", body='He said "hello" and \'goodbye\'')

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        mock_jira.add_comment.assert_called_once_with(
            "TEST-123", 'He said "hello" and \'goodbye\''
        )
        captured = capsys.readouterr()
        assert "Comment added" in captured.out

    def test_comment_with_newlines(self, mock_jira, capsys):
        """Handles comments containing newline characters."""
        mock_jira.add_comment.return_value = MagicMock()

        body = "Line 1\nLine 2\n\nLine 4 after blank"
        args = argparse.Namespace(key="TEST-123", body=body)

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        mock_jira.add_comment.assert_called_once_with("TEST-123", body)
        captured = capsys.readouterr()
        assert "Comment added" in captured.out

    def test_comment_with_unicode(self, mock_jira, capsys):
        """Handles comments containing unicode characters and emoji."""
        mock_jira.add_comment.return_value = MagicMock()

        body = "Testing unicode: café, naïve, 日本語, emoji 🎉👍"
        args = argparse.Namespace(key="TEST-123", body=body)

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        mock_jira.add_comment.assert_called_once_with("TEST-123", body)
        captured = capsys.readouterr()
        assert "Comment added" in captured.out

    def test_comment_with_special_jira_chars(self, mock_jira, capsys):
        """Handles comments with characters that have special meaning in Jira."""
        mock_jira.add_comment.return_value = MagicMock()

        body = "Code: {code}print('hello'){code} and [link|http://example.com]"
        args = argparse.Namespace(key="TEST-123", body=body)

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        mock_jira.add_comment.assert_called_once_with("TEST-123", body)

    def test_comment_with_backslashes(self, mock_jira, capsys):
        """Handles comments containing backslashes."""
        mock_jira.add_comment.return_value = MagicMock()

        body = r"Path: C:\Users\test\file.txt and regex: \d+\.\d+"
        args = argparse.Namespace(key="TEST-123", body=body)

        with patch("zaira.comment.get_jira_site", return_value="jira.example.com"):
            comment_command(args)

        mock_jira.add_comment.assert_called_once_with("TEST-123", body)
