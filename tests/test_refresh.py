"""Tests for refresh module."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

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
