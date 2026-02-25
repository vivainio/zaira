"""Tests for put module."""

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest

from zaira.put import parse_description, put_command


class TestParseDescription:
    """Tests for parse_description function."""

    def test_extracts_between_description_and_links(self):
        body = (
            "# FOO-123: Title\n\n"
            "## Description\n\n"
            "The description.\n\n"
            "## Links\n\n"
            "- Relates: BAR-456\n"
        )
        assert parse_description(body) == "The description."

    def test_preserves_subheadings_in_description(self):
        body = (
            "## Description\n\n"
            "Intro text.\n\n"
            "## Requirements\n\n"
            "- Item 1\n"
            "- Item 2\n\n"
            "## Links\n\n"
            "- Relates: BAR-456\n"
        )
        assert parse_description(body) == (
            "Intro text.\n\n"
            "## Requirements\n\n"
            "- Item 1\n"
            "- Item 2"
        )

    def test_captures_to_end_when_no_links(self):
        body = "## Description\n\nSome text.\n\n## Notes\n\nMore text.\n"
        assert parse_description(body) == "Some text.\n\n## Notes\n\nMore text."

    def test_returns_none_when_no_description_heading(self):
        assert parse_description("Just some text.") is None
        assert parse_description("## Links\n\n- foo") is None

    def test_empty_description_section(self):
        body = "## Description\n\n## Links\n\n- foo"
        assert parse_description(body) == ""


class TestPutCommand:
    """Tests for put_command function."""

    def _make_args(self, file="-", dry_run=False):
        return argparse.Namespace(file=file, dry_run=dry_run)

    def test_full_format_updates_summary_and_description(self, mock_jira, capsys):
        content = (
            "---\nkey: FOO-123\nsummary: New title\nstatus: Open\n---\n\n"
            "## Description\n\nNew desc.\n\n## Links\n\n- foo\n"
        )
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Old title"
        mock_issue.fields.description = "Old desc."
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)), \
             patch("zaira.put.get_jira_site", return_value="jira.example.com"):
            put_command(self._make_args())

        mock_issue.update.assert_called_once_with(
            fields={"summary": "New title", "description": "New desc."}
        )
        captured = capsys.readouterr()
        assert "Updated FOO-123" in captured.out

    def test_minimal_format_uses_body_as_description(self, mock_jira, capsys):
        content = "---\nkey: FOO-123\n---\nNew description body."
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Title"
        mock_issue.fields.description = "Old desc."
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)), \
             patch("zaira.put.get_jira_site", return_value="jira.example.com"):
            put_command(self._make_args())

        mock_issue.update.assert_called_once_with(
            fields={"description": "New description body."}
        )

    def test_minimal_format_with_summary_updates_both(self, mock_jira, capsys):
        content = "---\nkey: FOO-123\nsummary: New title\n---\nNew description body."
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Old title"
        mock_issue.fields.description = "Old desc."
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)), \
             patch("zaira.put.get_jira_site", return_value="jira.example.com"):
            put_command(self._make_args())

        mock_issue.update.assert_called_once_with(
            fields={"summary": "New title", "description": "New description body."}
        )

    def test_full_format_does_not_fallback_to_body(self, mock_jira, capsys):
        """Full export without ## Description should not push the entire body."""
        content = (
            "---\nkey: FOO-123\nsummary: Same title\nstatus: Open\n---\n\n"
            "# FOO-123: Same title\n\nRandom body text.\n"
        )
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Same title"
        mock_issue.fields.description = "Existing desc."
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)):
            put_command(self._make_args())

        captured = capsys.readouterr()
        assert "No changes" in captured.out

    def test_no_changes(self, mock_jira, capsys):
        content = (
            "---\nkey: FOO-123\nsummary: Same\nstatus: Open\n---\n\n"
            "## Description\n\nSame desc.\n\n## Links\n"
        )
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Same"
        mock_issue.fields.description = "Same desc."
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)):
            put_command(self._make_args())

        captured = capsys.readouterr()
        assert "No changes" in captured.out

    def test_dry_run(self, mock_jira, capsys):
        content = "---\nkey: FOO-123\nsummary: New\nstatus: Open\n---\n\n## Description\n\nNew desc.\n"
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Old"
        mock_issue.fields.description = "Old desc."
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)):
            put_command(self._make_args(dry_run=True))

        mock_issue.update.assert_not_called()
        captured = capsys.readouterr()
        assert "Dry run" in captured.out
        assert "summary" in captured.out

    def test_missing_key_errors(self, capsys):
        content = "---\nsummary: No key\n---\nBody."
        with patch("sys.stdin", MagicMock(read=lambda: content)):
            with pytest.raises(SystemExit):
                put_command(self._make_args())
        captured = capsys.readouterr()
        assert "key" in captured.err

    def test_reads_from_file(self, mock_jira, tmp_path, capsys):
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("---\nkey: FOO-1\n---\nNew desc.")
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Title"
        mock_issue.fields.description = "Old"
        mock_jira.issue.return_value = mock_issue

        with patch("zaira.put.get_jira_site", return_value="jira.example.com"):
            put_command(self._make_args(file=str(ticket_file)))

        mock_issue.update.assert_called_once_with(fields={"description": "New desc."})

    def test_file_not_found(self, capsys):
        with pytest.raises(SystemExit):
            put_command(self._make_args(file="/nonexistent/ticket.md"))
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_converts_markdown_to_jira_wiki(self, mock_jira, capsys):
        content = "---\nkey: FOO-1\n---\n## Heading\n\n**bold** text"
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Title"
        mock_issue.fields.description = "old"
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)), \
             patch("zaira.put.get_jira_site", return_value="jira.example.com"):
            put_command(self._make_args())

        call_fields = mock_issue.update.call_args[1]["fields"]
        assert "##" not in call_fields["description"]
        assert "h2." in call_fields["description"]

    def test_logs_activity(self, mock_jira, capsys):
        content = "---\nkey: FOO-1\n---\nNew desc."
        mock_issue = MagicMock()
        mock_issue.fields.summary = "Title"
        mock_issue.fields.description = "Old"
        mock_jira.issue.return_value = mock_issue

        with patch("sys.stdin", MagicMock(read=lambda: content)), \
             patch("zaira.put.get_jira_site", return_value="jira.example.com"), \
             patch("zaira.activity_log.record") as mock_record:
            put_command(self._make_args())

        mock_record.assert_called_once_with("put", "FOO-1", "description")
