"""Tests for refresh module."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zaira.refresh import (
    parse_front_matter,
    extract_ticket_keys,
    find_ticket_file,
    get_local_synced_time,
    ticket_needs_export,
)


class TestParseFrontMatter:
    """Tests for parse_front_matter function."""

    def test_no_front_matter(self):
        """Returns empty dict when no front matter."""
        content = "# Title\n\nBody content"
        result = parse_front_matter(content)
        assert result == {}

    def test_parses_simple_front_matter(self):
        """Parses simple key: value pairs."""
        content = """---
title: My Report
generated: 2024-01-15
---

Body
"""
        result = parse_front_matter(content)
        assert result["title"] == "My Report"
        assert result["generated"] == "2024-01-15"

    def test_parses_quoted_values(self):
        """Parses quoted values and strips quotes."""
        content = """---
jql: "project = TEST"
query: backlog
---
"""
        result = parse_front_matter(content)
        assert result["jql"] == "project = TEST"
        assert result["query"] == "backlog"

    def test_missing_closing_delimiter(self):
        """Returns empty dict when closing --- is missing."""
        content = """---
title: Incomplete
"""
        result = parse_front_matter(content)
        assert result == {}

    def test_handles_colons_in_values(self):
        """Handles colons within values correctly."""
        content = """---
refresh: zaira report --jql "project = TEST"
---
"""
        result = parse_front_matter(content)
        assert "zaira report" in result["refresh"]


class TestExtractTicketKeys:
    """Tests for extract_ticket_keys function."""

    def test_extracts_ticket_keys_from_links(self):
        """Extracts ticket keys from markdown links."""
        content = """
| Key | Summary |
|-----|---------|
| [TEST-123](https://jira.example.com/browse/TEST-123) | First ticket |
| [PROJ-456](https://jira.example.com/browse/PROJ-456) | Second ticket |
"""
        result = extract_ticket_keys(content)
        assert set(result) == {"TEST-123", "PROJ-456"}

    def test_no_duplicates(self):
        """Returns unique keys only."""
        content = """
- [TEST-1](https://jira.example.com/TEST-1) - first
- [TEST-1](https://jira.example.com/TEST-1) - duplicate
"""
        result = extract_ticket_keys(content)
        assert result.count("TEST-1") == 1

    def test_no_keys_found(self):
        """Returns empty list when no keys found."""
        content = "No ticket links here"
        result = extract_ticket_keys(content)
        assert result == []


class TestFindTicketFile:
    """Tests for find_ticket_file function."""

    def test_finds_existing_ticket(self, tmp_path):
        """Finds existing ticket file by key."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        ticket_file = tickets_dir / "TEST-123-my-ticket.md"
        ticket_file.write_text("content")

        with patch("zaira.refresh.TICKETS_DIR", tickets_dir):
            result = find_ticket_file("TEST-123")

        assert result == ticket_file

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when ticket not found."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        with patch("zaira.refresh.TICKETS_DIR", tickets_dir):
            result = find_ticket_file("NONEXISTENT-1")

        assert result is None

    def test_returns_none_when_dir_missing(self, tmp_path):
        """Returns None when tickets dir doesn't exist."""
        with patch("zaira.refresh.TICKETS_DIR", tmp_path / "nonexistent"):
            result = find_ticket_file("TEST-1")

        assert result is None


class TestGetLocalSyncedTime:
    """Tests for get_local_synced_time function."""

    def test_parses_synced_timestamp(self, tmp_path):
        """Parses synced timestamp from front matter."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
key: TEST-1
synced: 2024-01-15T10:30:00
---

Content
""")
        result = get_local_synced_time(ticket_file)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_returns_none_when_no_synced(self, tmp_path):
        """Returns None when no synced field."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
key: TEST-1
---

Content
""")
        result = get_local_synced_time(ticket_file)
        assert result is None

    def test_returns_none_for_invalid_date(self, tmp_path):
        """Returns None for invalid date format."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
synced: invalid-date
---
""")
        result = get_local_synced_time(ticket_file)
        assert result is None


class TestTicketNeedsExport:
    """Tests for ticket_needs_export function."""

    def test_needs_export_when_jira_newer(self, tmp_path):
        """Returns True when Jira timestamp is newer."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
synced: 2024-01-15T10:00:00
---
""")
        # Jira updated timestamp is later
        jira_updated = "2024-01-15T12:00:00.000+0000"

        result = ticket_needs_export(ticket_file, jira_updated)
        assert result is True

    def test_no_export_when_local_newer(self, tmp_path):
        """Returns False when local is newer or equal."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
synced: 2024-01-15T14:00:00
---
""")
        # Jira updated timestamp is earlier
        jira_updated = "2024-01-15T12:00:00.000+0000"

        result = ticket_needs_export(ticket_file, jira_updated)
        assert result is False

    def test_needs_export_when_no_synced(self, tmp_path):
        """Returns True when no synced timestamp."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
key: TEST-1
---
""")
        result = ticket_needs_export(ticket_file, "2024-01-15T12:00:00.000+0000")
        assert result is True

    def test_needs_export_when_invalid_jira_date(self, tmp_path):
        """Returns True when Jira date can't be parsed."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
synced: 2024-01-15T10:00:00
---
""")
        result = ticket_needs_export(ticket_file, "invalid-date")
        assert result is True


class TestRefreshCommand:
    """Tests for refresh_command function."""

    def test_exits_when_report_not_found(self, tmp_path, capsys):
        """Exits with error when report file doesn't exist."""
        from zaira.refresh import refresh_command

        args = argparse.Namespace(report="nonexistent.md", full=False, force=False)

        with patch("zaira.refresh.REPORTS_DIR", tmp_path / "reports"):
            with pytest.raises(SystemExit) as exc_info:
                refresh_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Report not found" in captured.out

    def test_exits_when_no_front_matter(self, tmp_path, capsys):
        """Exits with error when report has no front matter."""
        from zaira.refresh import refresh_command

        report = tmp_path / "report.md"
        report.write_text("# Report\n\nNo front matter here.")

        args = argparse.Namespace(report=str(report), full=False, force=False)

        with pytest.raises(SystemExit) as exc_info:
            refresh_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No front matter found" in captured.out

    def test_exits_when_no_refresh_command(self, tmp_path, capsys):
        """Exits with error when no refresh command in front matter."""
        from zaira.refresh import refresh_command

        report = tmp_path / "report.md"
        report.write_text("""---
title: My Report
---

Report content.
""")

        args = argparse.Namespace(report=str(report), full=False, force=False)

        with pytest.raises(SystemExit) as exc_info:
            refresh_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No refresh command" in captured.out

    def test_finds_report_in_reports_dir(self, tmp_path, capsys):
        """Finds report in reports directory when not found directly."""
        from zaira.refresh import refresh_command

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        report = reports_dir / "myreport.md"
        report.write_text("""---
refresh: zaira report --jql "project = TEST"
---

Report content.
""")

        args = argparse.Namespace(report="myreport.md", full=False, force=False)

        # Mock subprocess to prevent actual command execution
        with patch("zaira.refresh.REPORTS_DIR", reports_dir):
            with patch("zaira.refresh.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                refresh_command(args)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "zaira" in call_args
        assert "report" in call_args

    def test_finds_report_with_md_extension(self, tmp_path, capsys):
        """Finds report when .md extension is added."""
        from zaira.refresh import refresh_command

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        report = reports_dir / "myreport.md"
        report.write_text("""---
refresh: zaira report --jql "project = TEST"
---

Content.
""")

        args = argparse.Namespace(report="myreport", full=False, force=False)

        with patch("zaira.refresh.REPORTS_DIR", reports_dir):
            with patch("zaira.refresh.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                refresh_command(args)

        mock_run.assert_called_once()

    def test_exits_on_subprocess_failure(self, tmp_path, capsys):
        """Exits with subprocess return code on failure."""
        from zaira.refresh import refresh_command

        report = tmp_path / "report.md"
        report.write_text("""---
refresh: zaira report --jql "project = TEST"
---

Content.
""")

        args = argparse.Namespace(report=str(report), full=False, force=False)

        with patch("zaira.refresh.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=2)
            with pytest.raises(SystemExit) as exc_info:
                refresh_command(args)

        assert exc_info.value.code == 2

    def test_exits_on_invalid_refresh_command(self, tmp_path, capsys):
        """Exits with error when refresh command can't be parsed."""
        from zaira.refresh import refresh_command

        report = tmp_path / "report.md"
        # Unterminated quote makes shlex.split fail
        report.write_text("""---
refresh: zaira report --jql "unterminated
---

Content.
""")

        args = argparse.Namespace(report=str(report), full=False, force=False)

        with pytest.raises(SystemExit) as exc_info:
            refresh_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Could not parse refresh command" in captured.out

    def test_adds_output_path_to_command(self, tmp_path, capsys):
        """Adds -o flag with report path to refresh command."""
        from zaira.refresh import refresh_command

        report = tmp_path / "report.md"
        report.write_text("""---
refresh: zaira report --jql "project = TEST"
---

Content.
""")

        args = argparse.Namespace(report=str(report), full=False, force=False)

        with patch("zaira.refresh.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            refresh_command(args)

        call_args = mock_run.call_args[0][0]
        assert "-o" in call_args
        assert str(report) in call_args
