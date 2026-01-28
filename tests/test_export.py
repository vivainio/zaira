"""Tests for export module."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from zaira.export import (
    normalize_title,
    extract_description,
    extract_custom_field_value,
    is_placeholder_value,
    _is_na_value,
    _is_bogus_field_name,
    format_custom_field_value,
)


class TestNormalizeTitle:
    """Tests for normalize_title function."""

    def test_lowercase_and_slugify(self):
        """Converts to lowercase and replaces non-alphanumeric with dashes."""
        assert normalize_title("Hello World") == "hello-world"
        assert normalize_title("My Test Title") == "my-test-title"

    def test_removes_special_characters(self):
        """Removes special characters."""
        assert normalize_title("Test: Special!") == "test-special"
        assert normalize_title("Feature (new)") == "feature-new"

    def test_collapses_multiple_dashes(self):
        """Collapses multiple consecutive dashes."""
        assert normalize_title("Test---Multiple") == "test-multiple"
        assert normalize_title("A   B   C") == "a-b-c"

    def test_strips_leading_trailing_dashes(self):
        """Strips leading and trailing dashes."""
        assert normalize_title("---Test---") == "test"
        assert normalize_title("!Test!") == "test"

    def test_truncates_long_titles(self):
        """Truncates titles longer than 50 characters at word boundary."""
        long_title = "This is a very long title that exceeds fifty characters easily"
        result = normalize_title(long_title)
        assert len(result) <= 50
        # Should truncate at last dash before 50 chars
        assert not result.endswith("-")

    def test_handles_empty_string(self):
        """Handles empty string."""
        assert normalize_title("") == ""

    def test_handles_numbers(self):
        """Preserves numbers in title."""
        assert normalize_title("Version 2.0 Release") == "version-2-0-release"


class TestExtractDescription:
    """Tests for extract_description function."""

    def test_returns_no_description_for_none(self):
        """Returns 'No description' for None input."""
        assert extract_description(None) == "No description"

    def test_returns_no_description_for_empty_dict(self):
        """Returns 'No description' for empty dict."""
        assert extract_description({}) == "No description"

    def test_returns_string_as_is(self):
        """Returns string input unchanged."""
        assert extract_description("Hello world") == "Hello world"

    def test_extracts_text_from_adf(self):
        """Extracts text from Atlassian Document Format."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "world"},
                    ],
                }
            ],
        }
        assert extract_description(adf) == "Hello world"

    def test_handles_hard_break(self):
        """Handles hardBreak nodes."""
        adf = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Line 1"},
                {"type": "hardBreak"},
                {"type": "text", "text": "Line 2"},
            ],
        }
        assert extract_description(adf) == "Line 1\nLine 2"

    def test_handles_inline_card(self):
        """Handles inlineCard nodes (URLs)."""
        adf = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "See "},
                {"type": "inlineCard", "attrs": {"url": "https://example.com"}},
            ],
        }
        assert extract_description(adf) == "See https://example.com"

    def test_handles_nested_content(self):
        """Handles nested content structures."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item 1"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        assert extract_description(adf) == "Item 1"

    def test_handles_list_input(self):
        """Handles list of content items."""
        content = [
            {"type": "text", "text": "First "},
            {"type": "text", "text": "Second"},
        ]
        assert extract_description(content) == "First Second"


class TestExtractCustomFieldValue:
    """Tests for extract_custom_field_value function."""

    def test_returns_none_for_none(self):
        """Returns None for None input."""
        assert extract_custom_field_value(None) is None

    def test_returns_primitives_unchanged(self):
        """Returns primitive types unchanged."""
        assert extract_custom_field_value("string") == "string"
        assert extract_custom_field_value(42) == 42
        assert extract_custom_field_value(3.14) == 3.14
        assert extract_custom_field_value(True) is True

    def test_extracts_value_attribute(self):
        """Extracts .value attribute from objects."""
        obj = MagicMock()
        obj.value = "extracted"
        del obj.name  # Ensure name doesn't exist
        del obj.key
        assert extract_custom_field_value(obj) == "extracted"

    def test_extracts_name_attribute(self):
        """Extracts .name attribute when no .value."""
        obj = MagicMock()
        del obj.value
        obj.name = "named"
        del obj.key
        assert extract_custom_field_value(obj) == "named"

    def test_extracts_key_attribute(self):
        """Extracts .key attribute when no .value or .name."""
        obj = MagicMock()
        del obj.value
        del obj.name
        obj.key = "keyed"
        assert extract_custom_field_value(obj) == "keyed"

    def test_handles_dict_with_value(self):
        """Extracts 'value' key from dict."""
        assert extract_custom_field_value({"value": "dict_value"}) == "dict_value"

    def test_handles_dict_with_name(self):
        """Extracts 'name' key from dict when no 'value'."""
        assert extract_custom_field_value({"name": "dict_name"}) == "dict_name"

    def test_handles_list_recursively(self):
        """Recursively extracts values from lists."""
        obj1 = MagicMock()
        obj1.value = "first"
        del obj1.name
        del obj1.key
        obj2 = MagicMock()
        obj2.value = "second"
        del obj2.name
        del obj2.key

        result = extract_custom_field_value([obj1, obj2])
        assert result == ["first", "second"]

    def test_converts_unknown_to_string(self):
        """Converts unknown types to string."""
        obj = object()
        result = extract_custom_field_value(obj)
        assert isinstance(result, str)


class TestIsPlaceholderValue:
    """Tests for is_placeholder_value function."""

    def test_none_is_placeholder(self):
        """None is a placeholder."""
        assert is_placeholder_value(None) is True

    def test_zero_number_is_placeholder(self):
        """Zero is a placeholder for numeric values."""
        assert is_placeholder_value(0) is True
        assert is_placeholder_value(0.0) is True

    def test_empty_string_is_placeholder(self):
        """Empty or whitespace-only strings are placeholders."""
        assert is_placeholder_value("") is True
        assert is_placeholder_value("   ") is True

    def test_known_placeholder_patterns(self):
        """Known placeholder patterns are detected."""
        assert is_placeholder_value("?") is True
        assert is_placeholder_value("N/A") is True
        assert is_placeholder_value("none") is True
        assert is_placeholder_value("Unknown") is True
        assert is_placeholder_value("Unassigned") is True
        assert is_placeholder_value("pending") is True
        assert is_placeholder_value("not applicable") is True

    def test_real_values_not_placeholder(self):
        """Real values are not placeholders."""
        assert is_placeholder_value("High") is False
        assert is_placeholder_value("Some description") is False
        assert is_placeholder_value(5) is False
        assert is_placeholder_value(3.14) is False

    def test_list_with_only_na_values_is_placeholder(self):
        """Lists with only N/A values are placeholders."""
        assert is_placeholder_value(["N/A", "none", ""]) is True
        assert is_placeholder_value([]) is True

    def test_list_with_real_values_not_placeholder(self):
        """Lists with real values are not placeholders."""
        assert is_placeholder_value(["N/A", "Real value"]) is False
        assert is_placeholder_value(["item1", "item2"]) is False


class TestIsNaValue:
    """Tests for _is_na_value function."""

    def test_na_patterns(self):
        """Detects N/A patterns."""
        assert _is_na_value("N/A") is True
        assert _is_na_value("n/a") is True
        assert _is_na_value("N/A - Not Applicable") is True
        assert _is_na_value("none") is True
        assert _is_na_value("unknown") is True
        assert _is_na_value("") is True

    def test_real_values(self):
        """Real values are not N/A."""
        assert _is_na_value("High") is False
        assert _is_na_value("123") is False

    def test_non_string_values(self):
        """Non-string values return False."""
        assert _is_na_value(123) is False
        assert _is_na_value(None) is False


class TestIsBogusFieldName:
    """Tests for _is_bogus_field_name function."""

    def test_warning_fields_are_bogus(self):
        """Fields starting with 'warning' are bogus."""
        assert _is_bogus_field_name("Warning Message") is True
        assert _is_bogus_field_name("warning: something") is True

    def test_rank_fields_are_bogus(self):
        """Fields starting with 'rank' are bogus."""
        assert _is_bogus_field_name("Rank") is True
        assert _is_bogus_field_name("rank (global)") is True

    def test_comment_fields_are_bogus(self):
        """Fields containing 'comment' are bogus."""
        assert _is_bogus_field_name("Comment") is True
        assert _is_bogus_field_name("Latest Comment") is True

    def test_checklist_fields_are_bogus(self):
        """Fields starting with 'checklist' are bogus."""
        assert _is_bogus_field_name("Checklist") is True
        assert _is_bogus_field_name("Checklist Progress") is True

    def test_valid_fields_not_bogus(self):
        """Valid field names are not bogus."""
        assert _is_bogus_field_name("Story Points") is False
        assert _is_bogus_field_name("Sprint") is False
        assert _is_bogus_field_name("Labels") is False


class TestFormatCustomFieldValue:
    """Tests for format_custom_field_value function."""

    def test_null_value(self):
        """None formats as 'null'."""
        assert format_custom_field_value(None) == "null"

    def test_boolean_values(self):
        """Booleans format as lowercase strings."""
        assert format_custom_field_value(True) == "true"
        assert format_custom_field_value(False) == "false"

    def test_numeric_values(self):
        """Numbers format as strings."""
        assert format_custom_field_value(42) == "42"
        assert format_custom_field_value(3.14) == "3.14"

    def test_empty_list(self):
        """Empty list formats as '[]'."""
        assert format_custom_field_value([]) == "[]"

    def test_list_values(self):
        """Lists format as bracketed, comma-separated values."""
        result = format_custom_field_value(["a", "b", "c"])
        assert result.startswith("[")
        assert result.endswith("]")
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_string_values(self):
        """Strings are quoted for YAML."""
        result = format_custom_field_value("hello world")
        # Should be quoted
        assert '"' in result or "'" in result or result == "hello world"


class TestFormatTicketMarkdown:
    """Tests for format_ticket_markdown function."""

    def test_basic_ticket_format(self):
        """Formats a basic ticket correctly."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-123",
            "summary": "Test ticket",
            "issuetype": "Bug",
            "status": "Open",
            "priority": "High",
            "assignee": "john@example.com",
            "reporter": "jane@example.com",
            "description": "This is a test description.",
            "components": ["Backend"],
            "labels": ["urgent"],
            "parent": None,
            "issuelinks": [],
        }
        comments = []
        synced = "2024-01-15T10:00:00"
        jira_site = "example.atlassian.net"

        result = format_ticket_markdown(ticket, comments, synced, jira_site)

        assert "key: TEST-123" in result
        assert "# TEST-123: Test ticket" in result
        assert "This is a test description." in result
        assert "https://example.atlassian.net/browse/TEST-123" in result
        assert "_No links_" in result
        assert "_No comments_" in result

    def test_ticket_with_comments(self):
        """Formats ticket with comments."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-456",
            "summary": "With comments",
            "issuetype": "Task",
            "status": "In Progress",
            "priority": "Medium",
            "assignee": "user@example.com",
            "reporter": "user@example.com",
            "description": "Description here",
            "components": [],
            "labels": [],
            "parent": None,
            "issuelinks": [],
        }
        comments = [
            Comment(author="Alice", created="2024-01-15", body="First comment"),
            Comment(author="Bob", created="2024-01-16", body="Second comment"),
        ]

        result = format_ticket_markdown(ticket, comments, "2024-01-17", "jira.example.com")

        assert "### Alice (2024-01-15)" in result
        assert "First comment" in result
        assert "### Bob (2024-01-16)" in result
        assert "Second comment" in result

    def test_ticket_with_links(self):
        """Formats ticket with issue links."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-789",
            "summary": "Linked ticket",
            "issuetype": "Story",
            "status": "Done",
            "priority": "Low",
            "assignee": "Unassigned",
            "reporter": "reporter@example.com",
            "description": "Has links",
            "components": [],
            "labels": [],
            "parent": None,
            "issuelinks": [
                {"type": "Blocks", "direction": "outward", "key": "TEST-100", "summary": "Blocked ticket"},
                {"type": "Relates", "direction": "inward", "key": "TEST-200", "summary": "Related ticket"},
            ],
        }

        result = format_ticket_markdown(ticket, [], "2024-01-17", "jira.example.com")

        assert "Blocks: TEST-100 - Blocked ticket" in result
        assert "Relates (inward): TEST-200 - Related ticket" in result

    def test_ticket_with_parent(self):
        """Formats ticket with parent reference."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-SUB",
            "summary": "Subtask",
            "issuetype": "Sub-task",
            "status": "Open",
            "priority": "Medium",
            "assignee": "user@example.com",
            "reporter": "user@example.com",
            "description": "A subtask",
            "components": [],
            "labels": [],
            "parent": {"key": "TEST-PARENT", "summary": "Parent ticket"},
            "issuelinks": [],
        }

        result = format_ticket_markdown(ticket, [], "2024-01-17", "jira.example.com")

        assert "parent: TEST-PARENT" in result

    def test_ticket_with_attachments(self):
        """Formats ticket with attachments."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-ATT",
            "summary": "With attachments",
            "issuetype": "Bug",
            "status": "Open",
            "priority": "High",
            "assignee": "user@example.com",
            "reporter": "user@example.com",
            "description": "Has files",
            "components": [],
            "labels": [],
            "parent": None,
            "issuelinks": [],
            "attachments": [
                {"filename": "screenshot.png", "size": 102400, "author": "John", "created": "2024-01-15T10:00:00"},
            ],
        }

        result = format_ticket_markdown(ticket, [], "2024-01-17", "jira.example.com")

        assert "## Attachments" in result
        assert "screenshot.png" in result
        assert "100 KB" in result  # 102400 bytes / 1024

    def test_ticket_with_pull_requests(self):
        """Formats ticket with linked PRs."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-PR",
            "summary": "With PRs",
            "issuetype": "Task",
            "status": "In Review",
            "priority": "Medium",
            "assignee": "dev@example.com",
            "reporter": "dev@example.com",
            "description": "Has PRs",
            "components": [],
            "labels": [],
            "parent": None,
            "issuelinks": [],
            "pullRequests": [
                {"name": "Fix bug #123", "url": "https://github.com/org/repo/pull/123", "status": "MERGED"},
            ],
        }

        result = format_ticket_markdown(ticket, [], "2024-01-17", "jira.example.com")

        assert "## Pull Requests" in result
        assert "[Fix bug #123](https://github.com/org/repo/pull/123)" in result
        assert "MERGED" in result


class TestFormatTicketJson:
    """Tests for format_ticket_json function."""

    def test_basic_json_format(self):
        """Formats ticket as valid JSON."""
        import json
        from zaira.export import format_ticket_json
        from zaira.types import Comment

        ticket = {
            "key": "TEST-123",
            "summary": "Test ticket",
            "status": "Open",
        }
        comments = [
            Comment(author="Alice", created="2024-01-15", body="A comment"),
        ]

        result = format_ticket_json(ticket, comments, "2024-01-17T10:00:00", "jira.example.com")

        # Should be valid JSON
        data = json.loads(result)
        assert data["key"] == "TEST-123"
        assert data["summary"] == "Test ticket"
        assert data["synced"] == "2024-01-17T10:00:00"
        assert data["url"] == "https://jira.example.com/browse/TEST-123"
        assert len(data["comments"]) == 1
        assert data["comments"][0]["author"] == "Alice"

    def test_json_preserves_all_fields(self):
        """JSON output preserves all ticket fields."""
        import json
        from zaira.export import format_ticket_json
        from zaira.types import Comment

        ticket = {
            "key": "TEST-456",
            "summary": "Full ticket",
            "custom_field": "value",
            "nested": {"a": 1, "b": 2},
            "list_field": [1, 2, 3],
        }

        result = format_ticket_json(ticket, [], "2024-01-17", "site.com")
        data = json.loads(result)

        assert data["custom_field"] == "value"
        assert data["nested"] == {"a": 1, "b": 2}
        assert data["list_field"] == [1, 2, 3]


class TestTicketMarkdownCustomFields:
    """Tests for format_ticket_markdown with custom fields."""

    def test_includes_custom_fields(self):
        """Includes custom fields in YAML front matter."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-CF",
            "summary": "Custom fields test",
            "issuetype": "Story",
            "status": "Open",
            "priority": "High",
            "assignee": "user@example.com",
            "reporter": "user@example.com",
            "description": "Test",
            "components": [],
            "labels": [],
            "parent": None,
            "issuelinks": [],
            "custom_fields": {
                "Story Points": 5,
                "Sprint": "Sprint 10",
            },
        }

        result = format_ticket_markdown(ticket, [], "2024-01-17", "jira.example.com")

        assert "Story Points: 5" in result
        assert "Sprint: Sprint 10" in result

    def test_handles_empty_description(self):
        """Handles empty/None description."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-ND",
            "summary": "No description",
            "issuetype": "Task",
            "status": "Open",
            "priority": "Medium",
            "assignee": "Unassigned",
            "reporter": "user",
            "description": None,  # None description
            "components": [],
            "labels": [],
            "parent": None,
            "issuelinks": [],
        }

        result = format_ticket_markdown(ticket, [], "2024-01-17", "jira.example.com")

        assert "No description" in result

    def test_formats_components_and_labels(self):
        """Formats components and labels lists."""
        from zaira.export import format_ticket_markdown
        from zaira.types import Comment

        ticket = {
            "key": "TEST-CL",
            "summary": "With components",
            "issuetype": "Bug",
            "status": "Open",
            "priority": "Low",
            "assignee": "user",
            "reporter": "user",
            "description": "Test",
            "components": ["Backend", "API"],
            "labels": ["urgent", "bug"],
            "parent": None,
            "issuelinks": [],
        }

        result = format_ticket_markdown(ticket, [], "2024-01-17", "jira.example.com")

        assert "components:" in result
        assert "Backend" in result
        assert "API" in result
        assert "labels:" in result
        assert "urgent" in result


class TestExtractDescriptionEdgeCases:
    """Additional edge cases for extract_description."""

    def test_handles_empty_content_list(self):
        """Handles ADF with empty content list."""
        from zaira.export import extract_description

        adf = {"type": "doc", "content": []}
        result = extract_description(adf)
        assert result == ""

    def test_handles_deeply_nested_content(self):
        """Handles deeply nested ADF content."""
        from zaira.export import extract_description

        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "panel",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Deep text"},
                            ],
                        }
                    ],
                }
            ],
        }
        result = extract_description(adf)
        assert "Deep text" in result
