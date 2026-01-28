"""Tests for create module."""

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest

from zaira.create import (
    detect_markdown,
    parse_content,
    parse_ticket_file,
    map_fields,
    create_ticket,
    create_command,
)


class TestDetectMarkdown:
    """Tests for detect_markdown function."""

    def test_no_markdown_returns_empty(self):
        """Returns empty list for valid Jira markup."""
        text = """h2. Heading

*bold text*

[link|https://example.com]
"""
        result = detect_markdown(text)
        assert result == []

    def test_detects_markdown_headings(self):
        """Detects markdown ## headings."""
        text = "## My Heading"
        result = detect_markdown(text)
        assert len(result) == 1
        assert "h2." in result[0]

    def test_allows_single_hash(self):
        """Allows single # (Jira numbered list syntax)."""
        text = "# First item\n# Second item"
        result = detect_markdown(text)
        assert result == []

    def test_detects_markdown_links(self):
        """Detects markdown [text](url) links."""
        text = "Check out [this link](https://example.com)"
        result = detect_markdown(text)
        assert len(result) == 1
        assert "[this link|https://example.com]" in result[0]

    def test_detects_markdown_bold(self):
        """Detects markdown **bold** syntax."""
        text = "This is **bold** text"
        result = detect_markdown(text)
        assert len(result) == 1
        assert "'*text*'" in result[0]

    def test_detects_multiple_issues(self):
        """Detects multiple markdown issues."""
        text = """## Heading

**bold**

[link](https://example.com)
"""
        result = detect_markdown(text)
        assert len(result) == 3

    def test_limits_link_errors(self):
        """Only shows first 3 link errors."""
        text = """
[a](https://a.com)
[b](https://b.com)
[c](https://c.com)
[d](https://d.com)
[e](https://e.com)
"""
        result = detect_markdown(text)
        link_errors = [e for e in result if "link" in e.lower()]
        assert len(link_errors) == 3


class TestParseContent:
    """Tests for parse_content function."""

    def test_parses_front_matter(self):
        """Parses YAML front matter and body."""
        content = """---
project: TEST
summary: My ticket
---

This is the description.
"""
        front_matter, body = parse_content(content)

        assert front_matter["project"] == "TEST"
        assert front_matter["summary"] == "My ticket"
        assert body == "This is the description."

    def test_parses_list_values(self):
        """Parses list values in front matter."""
        content = """---
labels:
  - bug
  - urgent
components:
  - Backend
---

Description
"""
        front_matter, body = parse_content(content)

        assert front_matter["labels"] == ["bug", "urgent"]
        assert front_matter["components"] == ["Backend"]

    def test_raises_on_no_front_matter(self):
        """Raises ValueError when no front matter."""
        content = "Just regular content"

        with pytest.raises(ValueError, match="No YAML front matter"):
            parse_content(content)

    def test_raises_on_missing_closing_marker(self):
        """Raises ValueError when closing --- is missing."""
        content = """---
project: TEST
summary: Incomplete
"""
        with pytest.raises(ValueError):
            parse_content(content)

    def test_empty_body(self):
        """Handles empty body after front matter."""
        content = """---
project: TEST
---
"""
        front_matter, body = parse_content(content)

        assert front_matter["project"] == "TEST"
        assert body == ""

    def test_multiline_body(self):
        """Preserves multiline description body."""
        content = """---
project: TEST
---

Line 1

Line 2

Line 3
"""
        front_matter, body = parse_content(content)

        assert "Line 1" in body
        assert "Line 2" in body
        assert "Line 3" in body


class TestParseTicketFile:
    """Tests for parse_ticket_file function."""

    def test_reads_and_parses_file(self, tmp_path):
        """Reads file and parses content."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: TEST
summary: My ticket
---

Description body.
""")
        front_matter, body = parse_ticket_file(ticket_file)

        assert front_matter["project"] == "TEST"
        assert front_matter["summary"] == "My ticket"
        assert body == "Description body."


class TestMapFields:
    """Tests for map_fields function."""

    def test_maps_standard_fields(self):
        """Maps standard fields correctly."""
        front_matter = {
            "project": "TEST",
            "summary": "My ticket",
            "priority": "High",
            "labels": ["bug", "urgent"],
        }

        fields = map_fields(front_matter, "Description")

        assert fields["project"] == {"key": "TEST"}
        assert fields["summary"] == "My ticket"
        assert fields["priority"] == {"name": "High"}
        assert fields["labels"] == ["bug", "urgent"]
        assert fields["description"] == "Description"

    def test_maps_issuetype_alias(self):
        """Maps 'type' to 'issuetype'."""
        front_matter = {"project": "TEST", "type": "Bug"}

        fields = map_fields(front_matter, "")

        assert fields["issuetype"] == {"name": "Bug"}

    def test_maps_components_list(self):
        """Maps components as list of dicts."""
        front_matter = {"project": "TEST", "components": ["Backend", "API"]}

        fields = map_fields(front_matter, "")

        assert fields["components"] == [{"name": "Backend"}, {"name": "API"}]

    def test_maps_components_string(self):
        """Maps comma-separated components string."""
        front_matter = {"project": "TEST", "components": "Backend, API"}

        fields = map_fields(front_matter, "")

        assert fields["components"] == [{"name": "Backend"}, {"name": "API"}]

    def test_maps_labels_string(self):
        """Maps comma-separated labels string."""
        front_matter = {"project": "TEST", "labels": "bug, urgent"}

        fields = map_fields(front_matter, "")

        assert fields["labels"] == ["bug", "urgent"]

    def test_skips_metadata_fields(self):
        """Skips metadata fields like key, url, synced."""
        front_matter = {
            "project": "TEST",
            "key": "TEST-123",
            "url": "https://...",
            "synced": "2024-01-01",
            "status": "Open",
        }

        fields = map_fields(front_matter, "")

        assert "key" not in fields
        assert "url" not in fields
        assert "synced" not in fields
        assert "status" not in fields

    def test_maps_assignee(self):
        """Maps assignee field."""
        front_matter = {"project": "TEST", "assignee": "jsmith"}

        fields = map_fields(front_matter, "")

        assert fields["assignee"] == {"name": "jsmith"}

    def test_maps_none_assignee(self):
        """Maps None assignee as None."""
        front_matter = {"project": "TEST", "assignee": None}

        fields = map_fields(front_matter, "")

        assert fields.get("assignee") is None

    def test_maps_parent(self):
        """Maps parent field for subtasks."""
        front_matter = {"project": "TEST", "parent": "TEST-100"}

        fields = map_fields(front_matter, "")

        assert fields["parent"] == {"key": "TEST-100"}

    def test_skips_none_parent(self):
        """Skips parent when set to None."""
        front_matter = {"project": "TEST", "parent": "None"}

        fields = map_fields(front_matter, "")

        assert "parent" not in fields

    def test_maps_fix_versions(self):
        """Maps fixVersions field."""
        front_matter = {"project": "TEST", "fixversions": ["1.0", "1.1"]}

        fields = map_fields(front_matter, "")

        assert fields["fixVersions"] == [{"name": "1.0"}, {"name": "1.1"}]

    def test_warns_on_unknown_field(self, capsys):
        """Warns when field is not recognized."""
        front_matter = {"project": "TEST", "unknownfield": "value"}

        with patch("zaira.create.get_field_id", return_value=None):
            fields = map_fields(front_matter, "")

        captured = capsys.readouterr()
        assert "Unknown field 'unknownfield'" in captured.err

    def test_maps_custom_field(self):
        """Maps custom field when found in schema."""
        front_matter = {"project": "TEST", "Story Points": "5"}

        with patch("zaira.create.get_field_id", return_value="customfield_123"):
            with patch("zaira.create.format_field_value", return_value=5):
                fields = map_fields(front_matter, "")

        assert fields["customfield_123"] == 5


class TestCreateTicket:
    """Tests for create_ticket function."""

    def test_creates_ticket_successfully(self, mock_jira):
        """Returns ticket key on success."""
        mock_issue = MagicMock()
        mock_issue.key = "TEST-456"
        mock_jira.create_issue.return_value = mock_issue

        result = create_ticket({"project": {"key": "TEST"}, "summary": "Test"})

        assert result == "TEST-456"
        mock_jira.create_issue.assert_called_once()

    def test_returns_none_on_error(self, mock_jira, capsys):
        """Returns None and prints error on failure."""
        mock_jira.create_issue.side_effect = Exception("Invalid field")

        result = create_ticket({"project": {"key": "TEST"}, "summary": "Test"})

        assert result is None
        captured = capsys.readouterr()
        assert "Error creating ticket" in captured.err

    def test_dry_run_mode(self, mock_jira, capsys):
        """Prints fields but doesn't create in dry run mode."""
        result = create_ticket(
            {"project": {"key": "TEST"}, "summary": "Test"},
            dry_run=True,
        )

        assert result is None
        mock_jira.create_issue.assert_not_called()
        captured = capsys.readouterr()
        assert "Dry run" in captured.out
        assert "project" in captured.out


class TestCreateCommand:
    """Tests for create_command function."""

    def test_exits_when_file_not_found(self, tmp_path, capsys):
        """Exits with error when file doesn't exist."""
        args = argparse.Namespace(file=str(tmp_path / "nonexistent.md"))

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_exits_when_no_project(self, tmp_path, capsys):
        """Exits with error when project is missing."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
summary: My ticket
---

Description.
""")
        args = argparse.Namespace(file=str(ticket_file))

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "'project' field is required" in captured.err

    def test_exits_when_no_summary(self, tmp_path, capsys):
        """Exits with error when summary is missing."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: TEST
---

Description.
""")
        args = argparse.Namespace(file=str(ticket_file))

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "'summary' field is required" in captured.err

    def test_exits_on_markdown_in_description(self, tmp_path, capsys):
        """Exits with error when description contains markdown."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: TEST
summary: My ticket
---

## This is a heading

With **bold** text.
""")
        args = argparse.Namespace(file=str(ticket_file))

        with patch("zaira.create.load_schema", return_value={"fields": {}}):
            with pytest.raises(SystemExit) as exc_info:
                create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "markdown syntax" in captured.err

    def test_warns_when_no_schema(self, tmp_path, capsys, mock_jira):
        """Warns when no schema is available for custom fields."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: TEST
summary: My ticket
---

Description.
""")
        mock_issue = MagicMock()
        mock_issue.key = "TEST-123"
        mock_jira.create_issue.return_value = mock_issue

        args = argparse.Namespace(file=str(ticket_file), dry_run=False)

        with patch("zaira.create.load_schema", return_value=None):
            create_command(args)

        captured = capsys.readouterr()
        assert "No cached schema" in captured.err

    def test_creates_ticket_successfully(self, tmp_path, capsys, mock_jira):
        """Creates ticket and prints key."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("""---
project: TEST
summary: My ticket
---

Description.
""")
        mock_issue = MagicMock()
        mock_issue.key = "TEST-789"
        mock_jira.create_issue.return_value = mock_issue

        args = argparse.Namespace(file=str(ticket_file), dry_run=False)

        with patch("zaira.create.load_schema", return_value={"fields": {}}):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created TEST-789" in captured.out

    def test_reads_from_stdin(self, monkeypatch, capsys, mock_jira):
        """Reads content from stdin when file is '-'."""
        content = """---
project: TEST
summary: Stdin ticket
---

Body from stdin.
"""
        monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: content))
        mock_issue = MagicMock()
        mock_issue.key = "TEST-111"
        mock_jira.create_issue.return_value = mock_issue

        args = argparse.Namespace(file="-", dry_run=False)

        with patch("zaira.create.load_schema", return_value={"fields": {}}):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created TEST-111" in captured.out

    def test_exits_on_stdin_parse_error(self, monkeypatch, capsys):
        """Exits with error when stdin content can't be parsed."""
        monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: "no front matter"))

        args = argparse.Namespace(file="-")

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error parsing stdin" in captured.err

    def test_exits_on_file_parse_error(self, tmp_path, capsys):
        """Exits with error when file can't be parsed."""
        ticket_file = tmp_path / "ticket.md"
        ticket_file.write_text("no front matter here")

        args = argparse.Namespace(file=str(ticket_file))

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error parsing file" in captured.err
