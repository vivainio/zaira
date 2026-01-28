"""Tests for edit module."""

import argparse
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from zaira.edit import (
    read_input,
    map_field,
    parse_field_args,
    parse_yaml_fields,
    edit_ticket,
    edit_command,
    format_field_value,
    get_allowed_values,
    _format_assignee,
    _parse_number,
    _handle_update_error,
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


class TestFormatAssignee:
    """Tests for _format_assignee function."""

    def test_returns_none_for_empty(self, mock_jira):
        """Returns None for empty value."""
        assert _format_assignee(None) is None
        assert _format_assignee("") is None

    def test_handles_me_value(self, mock_jira):
        """Looks up current user for 'me' value."""
        mock_jira.myself.return_value = {"accountId": "abc123"}

        result = _format_assignee("me")

        assert result == {"accountId": "abc123"}
        mock_jira.myself.assert_called_once()

    def test_looks_up_user_by_name(self, mock_jira):
        """Looks up user by name/email."""
        mock_user = MagicMock()
        mock_user.accountId = "user456"
        mock_jira.search_users.return_value = [mock_user]

        result = _format_assignee("jsmith@example.com")

        assert result == {"accountId": "user456"}
        mock_jira.search_users.assert_called_once_with(query="jsmith@example.com")

    def test_falls_back_to_direct_value(self, mock_jira):
        """Falls back to using value as accountId when user not found."""
        mock_jira.search_users.return_value = []

        result = _format_assignee("direct-account-id")

        assert result == {"accountId": "direct-account-id"}


class TestParseNumber:
    """Tests for _parse_number function."""

    def test_parses_integer(self):
        """Parses integer string."""
        assert _parse_number("42") == 42
        assert _parse_number("-5") == -5

    def test_parses_float(self):
        """Parses float string."""
        assert _parse_number("3.14") == 3.14
        assert _parse_number("-0.5") == -0.5

    def test_returns_string_for_invalid(self):
        """Returns original string for non-numeric values."""
        assert _parse_number("abc") == "abc"
        assert _parse_number("12abc") == "12abc"


class TestFormatFieldValue:
    """Tests for format_field_value function."""

    def test_returns_dict_unchanged(self):
        """Returns dict values unchanged."""
        value = {"name": "Test"}
        assert format_field_value("field", value) == {"name": "Test"}

    def test_returns_list_unchanged(self):
        """Returns list values unchanged."""
        value = ["a", "b"]
        assert format_field_value("field", value) == ["a", "b"]

    def test_returns_number_unchanged(self):
        """Returns numeric values unchanged."""
        assert format_field_value("field", 42) == 42
        assert format_field_value("field", 3.14) == 3.14

    def test_formats_option_field(self):
        """Wraps option field value in dict."""
        with patch("zaira.edit.get_field_type", return_value="option"):
            result = format_field_value("customfield_123", "High")

        assert result == {"value": "High"}

    def test_formats_array_field(self):
        """Formats array/multi-select field."""
        with patch("zaira.edit.get_field_type", return_value="array"):
            result = format_field_value("customfield_456", "a, b, c")

        assert result == [{"value": "a"}, {"value": "b"}, {"value": "c"}]

    def test_converts_number_field(self):
        """Converts string to number for number field."""
        with patch("zaira.edit.get_field_type", return_value="number"):
            result = format_field_value("customfield_789", "42")

        assert result == 42

    def test_returns_string_for_unknown_type(self):
        """Returns string value unchanged for unknown type."""
        with patch("zaira.edit.get_field_type", return_value=None):
            result = format_field_value("customfield_999", "text")

        assert result == "text"


class TestGetAllowedValues:
    """Tests for get_allowed_values function."""

    def test_gets_values_from_editmeta(self, mock_jira):
        """Gets allowed values from editmeta API."""
        mock_jira._get_json.return_value = {
            "fields": {
                "customfield_123": {
                    "allowedValues": [
                        {"value": "Option A"},
                        {"value": "Option B"},
                    ]
                }
            }
        }

        result = get_allowed_values(mock_jira, "TEST-1", ["customfield_123"])

        assert result == {"customfield_123": ["Option A", "Option B"]}

    def test_handles_name_key_in_values(self, mock_jira):
        """Handles allowedValues with 'name' key instead of 'value'."""
        mock_jira._get_json.return_value = {
            "fields": {
                "priority": {
                    "allowedValues": [
                        {"name": "High"},
                        {"name": "Medium"},
                    ]
                }
            }
        }

        result = get_allowed_values(mock_jira, "TEST-1", ["priority"])

        assert result == {"priority": ["High", "Medium"]}

    def test_handles_editmeta_error(self, mock_jira):
        """Handles error from editmeta gracefully."""
        mock_jira._get_json.side_effect = Exception("API Error")

        result = get_allowed_values(mock_jira, "TEST-1", ["customfield_123"])

        assert result == {}


class TestHandleUpdateError:
    """Tests for _handle_update_error function."""

    def test_prints_simple_error(self, mock_jira, capsys):
        """Prints simple error message for basic exceptions."""
        error = Exception("Something went wrong")

        _handle_update_error(error, mock_jira, "TEST-123")

        captured = capsys.readouterr()
        assert "Error updating TEST-123" in captured.err

    def test_parses_jira_error_response(self, mock_jira, capsys):
        """Parses and displays Jira error response."""
        error = MagicMock()
        error.response = MagicMock()
        error.response.text = json.dumps({
            "errorMessages": ["General error"],
            "errors": {"customfield_123": "Invalid value"},
        })

        with patch("zaira.edit.get_allowed_values", return_value={}):
            _handle_update_error(error, mock_jira, "TEST-123")

        captured = capsys.readouterr()
        assert "General error" in captured.err
        assert "Invalid value" in captured.err


class TestEditCommand:
    """Tests for edit_command function."""

    def test_exits_when_no_fields_specified(self, capsys):
        """Exits with error when no fields to update."""
        args = argparse.Namespace(
            key="test-123",
            title=None,
            description=None,
            field=None,
            from_file=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            edit_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No fields to update" in captured.err

    def test_updates_title(self, mock_jira, capsys):
        """Updates ticket title."""
        mock_issue = MagicMock()
        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            key="test-123",
            title="New Title",
            description=None,
            field=None,
            from_file=None,
        )

        with patch("zaira.edit.get_jira_site", return_value="jira.example.com"):
            edit_command(args)

        mock_issue.update.assert_called_once_with(fields={"summary": "New Title"})
        captured = capsys.readouterr()
        assert "Updated TEST-123" in captured.out

    def test_updates_description(self, mock_jira, capsys):
        """Updates ticket description."""
        mock_issue = MagicMock()
        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            key="test-123",
            title=None,
            description="New description text",
            field=None,
            from_file=None,
        )

        with patch("zaira.edit.get_jira_site", return_value="jira.example.com"):
            edit_command(args)

        mock_issue.update.assert_called_once_with(
            fields={"description": "New description text"}
        )

    def test_exits_on_markdown_description(self, capsys):
        """Exits with error when description contains markdown."""
        args = argparse.Namespace(
            key="test-123",
            title=None,
            description="## Markdown heading",
            field=None,
            from_file=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            edit_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "markdown syntax" in captured.err

    def test_updates_with_field_args(self, mock_jira, capsys):
        """Updates ticket with --field arguments."""
        mock_issue = MagicMock()
        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            key="test-123",
            title=None,
            description=None,
            field=["summary=Updated", "priority=High"],
            from_file=None,
        )

        with patch("zaira.edit.get_jira_site", return_value="jira.example.com"):
            with patch("zaira.edit.map_field", side_effect=[
                ("summary", "Updated"),
                ("priority", {"name": "High"}),
            ]):
                edit_command(args)

        mock_issue.update.assert_called_once()

    def test_reads_fields_from_yaml_content(self, mock_jira, capsys):
        """Updates ticket with fields from YAML content via --from."""
        mock_issue = MagicMock()
        mock_jira.issue.return_value = mock_issue

        yaml_content = "summary: From YAML\npriority: Low\n"

        args = argparse.Namespace(
            key="test-123",
            title=None,
            description=None,
            field=None,
            from_file=yaml_content,
        )

        with patch("zaira.edit.get_jira_site", return_value="jira.example.com"):
            with patch("zaira.edit.map_field", side_effect=[
                ("summary", "From YAML"),
                ("priority", {"name": "Low"}),
            ]):
                edit_command(args)

        mock_issue.update.assert_called_once()

    def test_exits_on_update_failure(self, mock_jira, capsys):
        """Exits with error when update fails."""
        mock_jira.issue.side_effect = Exception("Permission denied")

        args = argparse.Namespace(
            key="test-123",
            title="New Title",
            description=None,
            field=None,
            from_file=None,
        )

        with patch("zaira.edit.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                edit_command(args)

        assert exc_info.value.code == 1

    def test_uppercases_ticket_key(self, mock_jira, capsys):
        """Converts ticket key to uppercase."""
        mock_issue = MagicMock()
        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            key="test-123",
            title="Title",
            description=None,
            field=None,
            from_file=None,
        )

        with patch("zaira.edit.get_jira_site", return_value="jira.example.com"):
            edit_command(args)

        mock_jira.issue.assert_called_once_with("TEST-123")

    def test_reads_description_from_stdin(self, mock_jira, monkeypatch, capsys):
        """Reads description from stdin when value is '-'."""
        mock_issue = MagicMock()
        mock_jira.issue.return_value = mock_issue
        monkeypatch.setattr(sys, "stdin", MagicMock(read=lambda: "stdin content"))

        args = argparse.Namespace(
            key="test-123",
            title=None,
            description="-",
            field=None,
            from_file=None,
        )

        with patch("zaira.edit.get_jira_site", return_value="jira.example.com"):
            edit_command(args)

        mock_issue.update.assert_called_once_with(fields={"description": "stdin content"})
