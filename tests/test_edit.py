"""Tests for edit module."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from zaira.edit import (
    read_input,
    map_field,
    parse_field_args,
    parse_yaml_fields,
    edit_ticket,
    STANDARD_FIELDS,
)


class TestReadInput:
    """Tests for read_input function."""

    def test_returns_value_unchanged(self):
        """Returns value unchanged for normal input."""
        assert read_input("hello") == "hello"
        assert read_input("multi\nline") == "multi\nline"

    def test_reads_from_stdin(self, monkeypatch):
        """Reads from stdin when value is '-'."""
        monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: "stdin content"))

        result = read_input("-")

        assert result == "stdin content"


class TestMapField:
    """Tests for map_field function."""

    def test_maps_standard_fields(self):
        """Maps standard field names."""
        field_id, value = map_field("summary", "My title")
        assert field_id == "summary"
        assert value == "My title"

    def test_maps_title_alias(self):
        """Maps 'title' to 'summary'."""
        field_id, value = map_field("title", "My title")
        assert field_id == "summary"
        assert value == "My title"

    def test_formats_priority(self):
        """Formats priority as dict with name."""
        field_id, value = map_field("priority", "High")
        assert field_id == "priority"
        assert value == {"name": "High"}

    def test_formats_labels_string(self):
        """Formats comma-separated labels string."""
        field_id, value = map_field("labels", "bug, urgent, backend")
        assert field_id == "labels"
        assert value == ["bug", "urgent", "backend"]

    def test_formats_labels_list(self):
        """Preserves labels list."""
        field_id, value = map_field("labels", ["bug", "urgent"])
        assert field_id == "labels"
        assert value == ["bug", "urgent"]

    def test_formats_components_string(self):
        """Formats comma-separated components string."""
        field_id, value = map_field("components", "Backend, API")
        assert field_id == "components"
        assert value == [{"name": "Backend"}, {"name": "API"}]

    def test_formats_components_list(self):
        """Formats components list."""
        field_id, value = map_field("components", ["Backend", "API"])
        assert field_id == "components"
        assert value == [{"name": "Backend"}, {"name": "API"}]

    def test_custom_field_lookup(self):
        """Looks up custom field by name."""
        with patch("zaira.edit.get_field_id", return_value="customfield_123"):
            with patch("zaira.edit.get_field_type", return_value=None):
                field_id, value = map_field("Story Points", "5")

        assert field_id == "customfield_123"

    def test_falls_back_to_name_as_id(self):
        """Falls back to using name as-is when not found."""
        with patch("zaira.edit.get_field_id", return_value=None):
            with patch("zaira.edit.get_field_type", return_value=None):
                field_id, value = map_field("customfield_999", "value")

        assert field_id == "customfield_999"


class TestParseFieldArgs:
    """Tests for parse_field_args function."""

    def test_parses_simple_args(self):
        """Parses simple Name=value arguments."""
        with patch("zaira.edit.map_field", side_effect=lambda n, v: (n.lower(), v)):
            result = parse_field_args(["summary=Test", "priority=High"])

        assert result["summary"] == "Test"
        assert result["priority"] == "High"

    def test_handles_value_with_equals(self):
        """Handles values containing equals signs."""
        with patch("zaira.edit.map_field", side_effect=lambda n, v: (n.lower(), v)):
            result = parse_field_args(["description=a=b=c"])

        assert result["description"] == "a=b=c"

    def test_warns_on_invalid_format(self, capsys):
        """Warns on arguments without equals sign."""
        with patch("zaira.edit.map_field", side_effect=lambda n, v: (n.lower(), v)):
            result = parse_field_args(["invalid_no_equals", "valid=value"])

        captured = capsys.readouterr()
        assert "Warning: Invalid field format" in captured.err
        assert result.get("valid") == "value"

    def test_strips_whitespace(self):
        """Strips whitespace from name and value."""
        with patch("zaira.edit.map_field", side_effect=lambda n, v: (n.lower(), v)):
            result = parse_field_args(["  summary  =  Test Value  "])

        assert result["summary"] == "Test Value"


class TestParseYamlFields:
    """Tests for parse_yaml_fields function."""

    def test_parses_yaml_content(self):
        """Parses YAML content into fields dict."""
        content = """
summary: Test Ticket
priority: High
"""
        with patch("zaira.edit.map_field", side_effect=lambda n, v: (n.lower(), v)):
            result = parse_yaml_fields(content)

        assert result["summary"] == "Test Ticket"
        assert result["priority"] == "High"

    def test_parses_list_values(self):
        """Parses list values in YAML."""
        content = """
labels:
  - bug
  - urgent
"""
        with patch("zaira.edit.map_field", side_effect=lambda n, v: (n.lower(), v)):
            result = parse_yaml_fields(content)

        assert result["labels"] == ["bug", "urgent"]

    def test_returns_empty_for_non_dict(self):
        """Returns empty dict for non-dict YAML."""
        content = "- item1\n- item2"

        result = parse_yaml_fields(content)

        assert result == {}


class TestEditTicket:
    """Tests for edit_ticket function with mocked Jira."""

    def test_updates_ticket_successfully(self, mock_jira):
        """Returns True when update succeeds."""
        mock_issue = MagicMock()
        mock_jira.issue.return_value = mock_issue

        result = edit_ticket("TEST-123", {"summary": "New title"})

        assert result is True
        mock_issue.update.assert_called_once_with(fields={"summary": "New title"})

    def test_returns_true_for_empty_fields(self, mock_jira):
        """Returns True immediately for empty fields."""
        result = edit_ticket("TEST-123", {})

        assert result is True
        mock_jira.issue.assert_not_called()

    def test_returns_false_on_error(self, mock_jira, capsys):
        """Returns False on update error."""
        mock_jira.issue.side_effect = Exception("Permission denied")

        result = edit_ticket("TEST-123", {"summary": "New"})

        assert result is False
        captured = capsys.readouterr()
        assert "Error updating" in captured.err
