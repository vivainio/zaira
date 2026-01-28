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


class TestGetTicket:
    """Tests for get_ticket function."""

    def test_returns_ticket_data(self, mock_jira):
        """Returns formatted ticket data."""
        from zaira.export import get_ticket

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test ticket"
        mock_issue.fields.description = "Description text"
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01T10:00:00"
        mock_issue.fields.updated = "2024-01-02T15:00:00"
        mock_issue.fields.components = []
        mock_issue.fields.labels = ["bug"]
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []

        mock_jira.issue.return_value = mock_issue

        result = get_ticket("TEST-1")

        assert result["key"] == "TEST-1"
        assert result["summary"] == "Test ticket"
        assert result["status"] == "Open"
        assert result["labels"] == ["bug"]

    def test_returns_none_on_error(self, mock_jira, capsys):
        """Returns None when ticket fetch fails."""
        from zaira.export import get_ticket

        mock_jira.issue.side_effect = Exception("Not found")

        result = get_ticket("INVALID-1")

        assert result is None
        captured = capsys.readouterr()
        assert "Error fetching" in captured.out

    def test_includes_parent_info(self, mock_jira):
        """Includes parent information when present."""
        from zaira.export import get_ticket

        mock_parent = MagicMock()
        mock_parent.key = "EPIC-1"
        mock_parent.fields.summary = "Epic ticket"

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Subtask"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Sub-task"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "Medium"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = mock_parent
        mock_issue.fields.issuelinks = []

        mock_jira.issue.return_value = mock_issue

        result = get_ticket("TEST-1")

        assert result["parent"]["key"] == "EPIC-1"
        assert result["parent"]["summary"] == "Epic ticket"

    def test_includes_issue_links(self, mock_jira):
        """Includes issue link information."""
        from zaira.export import get_ticket

        mock_outward = MagicMock()
        mock_outward.key = "TEST-2"
        mock_outward.fields.summary = "Related ticket"

        mock_link = MagicMock()
        mock_link.type.name = "Blocks"
        mock_link.outwardIssue = mock_outward
        del mock_link.inwardIssue  # Simulate outward link

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = [mock_link]

        mock_jira.issue.return_value = mock_issue

        result = get_ticket("TEST-1")

        assert len(result["issuelinks"]) == 1
        assert result["issuelinks"][0]["type"] == "Blocks"
        assert result["issuelinks"][0]["key"] == "TEST-2"
        assert result["issuelinks"][0]["direction"] == "outward"

    def test_includes_custom_fields(self, mock_jira):
        """Includes custom fields when requested."""
        from zaira.export import get_ticket
        from unittest.mock import patch

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Story"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "Medium"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.raw = {"fields": {"customfield_10001": 5}}

        mock_jira.issue.return_value = mock_issue

        with patch("zaira.export.get_field_name", return_value="Story Points"):
            result = get_ticket("TEST-1", include_custom=True)

        assert "custom_fields" in result
        assert result["custom_fields"]["Story Points"] == 5

    def test_includes_full_fields_for_json(self, mock_jira):
        """Includes extra fields when full=True."""
        from zaira.export import get_ticket

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Done"
        mock_issue.fields.status.statusCategory.name = "Done"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.creator = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.project.key = "TEST"
        mock_issue.fields.resolution.name = "Fixed"
        mock_issue.fields.resolutiondate = "2024-01-03"
        mock_issue.fields.fixVersions = []
        mock_issue.fields.versions = []
        mock_issue.fields.votes.votes = 5
        mock_issue.fields.watches.watchCount = 3
        mock_issue.fields.subtasks = []

        mock_jira.issue.return_value = mock_issue

        result = get_ticket("TEST-1", full=True)

        assert result["project"] == "TEST"
        assert result["resolution"] == "Fixed"
        assert result["votes"] == 5
        assert result["watches"] == 3

    def test_includes_attachments(self, mock_jira):
        """Includes attachment metadata when requested."""
        from zaira.export import get_ticket

        mock_attachment = MagicMock()
        mock_attachment.id = "att123"
        mock_attachment.filename = "screenshot.png"
        mock_attachment.size = 102400
        mock_attachment.mimeType = "image/png"
        mock_attachment.author.displayName = "John Doe"
        mock_attachment.created = "2024-01-15T10:00:00"

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.attachment = [mock_attachment]

        mock_jira.issue.return_value = mock_issue

        result = get_ticket("TEST-1", include_attachments=True)

        assert "attachments" in result
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["filename"] == "screenshot.png"


class TestGetComments:
    """Tests for get_comments function."""

    def test_returns_comments(self, mock_jira):
        """Returns formatted comment list."""
        from zaira.export import get_comments

        mock_comment = MagicMock()
        mock_comment.author.displayName = "Alice"
        mock_comment.created = "2024-01-15T10:00:00"
        mock_comment.body = "This is a comment"

        mock_issue = MagicMock()
        mock_issue.fields.comment.comments = [mock_comment]

        mock_jira.issue.return_value = mock_issue

        result = get_comments("TEST-1")

        assert len(result) == 1
        assert result[0].author == "Alice"
        assert result[0].body == "This is a comment"

    def test_returns_empty_on_error(self, mock_jira):
        """Returns empty list on error."""
        from zaira.export import get_comments

        mock_jira.issue.side_effect = Exception("Error")

        result = get_comments("TEST-1")

        assert result == []

    def test_handles_adf_body(self, mock_jira):
        """Handles ADF format comment body."""
        from zaira.export import get_comments

        mock_body = MagicMock()
        mock_body.raw = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "ADF comment"}]}
            ],
        }

        mock_comment = MagicMock()
        mock_comment.author.displayName = "Bob"
        mock_comment.created = "2024-01-15"
        mock_comment.body = mock_body

        mock_issue = MagicMock()
        mock_issue.fields.comment.comments = [mock_comment]

        mock_jira.issue.return_value = mock_issue

        result = get_comments("TEST-1")

        assert len(result) == 1
        assert "ADF comment" in result[0].body


class TestGetPullRequests:
    """Tests for get_pull_requests function."""

    def test_returns_pull_requests(self, mock_jira):
        """Returns formatted PR list."""
        from zaira.export import get_pull_requests

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "detail": [
                {
                    "pullRequests": [
                        {"name": "Fix bug", "url": "https://github.com/org/repo/pull/1", "status": "MERGED"},
                        {"name": "Add feature", "url": "https://github.com/org/repo/pull/2", "status": "OPEN"},
                    ]
                }
            ]
        }
        mock_jira._session.get.return_value = mock_response

        result = get_pull_requests("12345")

        assert len(result) == 2
        assert result[0]["name"] == "Fix bug"
        assert result[0]["status"] == "MERGED"

    def test_returns_empty_on_error(self, mock_jira):
        """Returns empty list on error."""
        from zaira.export import get_pull_requests

        mock_jira._session.get.side_effect = Exception("Error")

        result = get_pull_requests("12345")

        assert result == []


class TestDownloadAttachment:
    """Tests for download_attachment function."""

    def test_downloads_file(self, mock_jira, tmp_path):
        """Downloads attachment to specified directory."""
        from zaira.export import download_attachment

        mock_response = MagicMock()
        mock_response.content = b"file content"
        mock_response.raise_for_status = MagicMock()
        mock_jira._session.get.return_value = mock_response
        mock_jira._options = {"server": "https://jira.example.com"}

        attachment = {"id": "att123", "filename": "test.txt", "size": 12}
        output_dir = tmp_path / "attachments"

        result = download_attachment(attachment, output_dir)

        assert result is True
        assert (output_dir / "test.txt").exists()
        assert (output_dir / "test.txt").read_bytes() == b"file content"

    def test_skips_large_files(self, mock_jira, tmp_path, capsys):
        """Skips files larger than 10MB."""
        from zaira.export import download_attachment

        attachment = {"id": "att123", "filename": "large.zip", "size": 15 * 1024 * 1024}  # 15 MB
        output_dir = tmp_path / "attachments"

        result = download_attachment(attachment, output_dir)

        assert result is False
        captured = capsys.readouterr()
        assert "Skipping" in captured.out
        assert "10 MB limit" in captured.out

    def test_handles_download_error(self, mock_jira, tmp_path, capsys):
        """Handles download errors gracefully."""
        from zaira.export import download_attachment

        mock_jira._session.get.side_effect = Exception("Download failed")
        mock_jira._options = {"server": "https://jira.example.com"}

        attachment = {"id": "att123", "filename": "test.txt", "size": 100}
        output_dir = tmp_path / "attachments"

        result = download_attachment(attachment, output_dir)

        assert result is False
        captured = capsys.readouterr()
        assert "Error downloading" in captured.out


class TestSearchTickets:
    """Tests for search_tickets function (export module version)."""

    def test_returns_ticket_keys(self, mock_jira):
        """Returns list of ticket keys."""
        from zaira.export import search_tickets

        mock_issue1 = MagicMock()
        mock_issue1.key = "TEST-1"
        mock_issue2 = MagicMock()
        mock_issue2.key = "TEST-2"

        mock_jira.search_issues.return_value = [mock_issue1, mock_issue2]

        result = search_tickets("project = TEST")

        assert result == ["TEST-1", "TEST-2"]

    def test_returns_empty_on_error(self, mock_jira, capsys):
        """Returns empty list on error."""
        from zaira.export import search_tickets

        mock_jira.search_issues.side_effect = Exception("Search error")

        result = search_tickets("invalid query")

        assert result == []
        captured = capsys.readouterr()
        assert "Error searching" in captured.out


class TestExportTicket:
    """Tests for export_ticket function."""

    def test_exports_markdown(self, mock_jira, tmp_path, capsys):
        """Exports ticket to markdown file."""
        from zaira.export import export_ticket
        from unittest.mock import patch

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test ticket"
        mock_issue.fields.description = "Description"
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.attachment = []
        mock_issue.fields.comment.comments = []

        mock_jira.issue.return_value = mock_issue

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            result = export_ticket("TEST-1", tmp_path)

        assert result is True
        files = list(tmp_path.glob("TEST-1*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "key: TEST-1" in content
        assert "# TEST-1: Test ticket" in content

    def test_exports_json(self, mock_jira, tmp_path):
        """Exports ticket to JSON file."""
        from zaira.export import export_ticket
        from unittest.mock import patch
        import json

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-2"
        mock_issue.fields.summary = "JSON test"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Task"
        mock_issue.fields.status.name = "Done"
        mock_issue.fields.status.statusCategory.name = "Done"
        mock_issue.fields.priority.name = "Medium"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.creator = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.project.key = "TEST"
        mock_issue.fields.resolution = None
        mock_issue.fields.resolutiondate = None
        mock_issue.fields.fixVersions = []
        mock_issue.fields.versions = []
        mock_issue.fields.votes.votes = 0
        mock_issue.fields.watches.watchCount = 0
        mock_issue.fields.subtasks = []
        mock_issue.fields.attachment = []
        mock_issue.fields.comment.comments = []

        mock_jira.issue.return_value = mock_issue

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            result = export_ticket("TEST-2", tmp_path, fmt="json")

        assert result is True
        files = list(tmp_path.glob("TEST-2*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["key"] == "TEST-2"

    def test_returns_false_on_fetch_error(self, mock_jira, tmp_path, capsys):
        """Returns False when ticket fetch fails."""
        from zaira.export import export_ticket

        mock_jira.issue.side_effect = Exception("Not found")

        result = export_ticket("INVALID-1", tmp_path)

        assert result is False

    def test_creates_component_symlinks(self, mock_jira, tmp_path):
        """Creates symlinks by component."""
        from zaira.export import export_ticket
        from unittest.mock import patch

        mock_component = MagicMock()
        mock_component.name = "Backend"

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-3"
        mock_issue.fields.summary = "Component test"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = [mock_component]
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.attachment = []
        mock_issue.fields.comment.comments = []

        mock_jira.issue.return_value = mock_issue

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            export_ticket("TEST-3", tmp_path)

        symlink_dir = tmp_path / "by-component" / "backend"
        assert symlink_dir.exists()
        symlinks = list(symlink_dir.glob("TEST-3*.md"))
        assert len(symlinks) == 1
        assert symlinks[0].is_symlink()


class TestExportToStdout:
    """Tests for export_to_stdout function."""

    def test_outputs_markdown_to_stdout(self, mock_jira, capsys):
        """Outputs markdown to stdout."""
        from zaira.export import export_to_stdout
        from unittest.mock import patch

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Stdout test"
        mock_issue.fields.description = "Description"
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.comment.comments = []

        mock_jira.issue.return_value = mock_issue

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            result = export_to_stdout("TEST-1")

        assert result is True
        captured = capsys.readouterr()
        assert "key: TEST-1" in captured.out
        assert "# TEST-1: Stdout test" in captured.out

    def test_outputs_json_to_stdout(self, mock_jira, capsys):
        """Outputs JSON to stdout."""
        from zaira.export import export_to_stdout
        from unittest.mock import patch
        import json

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-2"
        mock_issue.fields.summary = "JSON stdout"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Task"
        mock_issue.fields.status.name = "Done"
        mock_issue.fields.status.statusCategory.name = "Done"
        mock_issue.fields.priority.name = "Medium"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.creator = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.project.key = "TEST"
        mock_issue.fields.resolution = None
        mock_issue.fields.resolutiondate = None
        mock_issue.fields.fixVersions = []
        mock_issue.fields.versions = []
        mock_issue.fields.votes.votes = 0
        mock_issue.fields.watches.watchCount = 0
        mock_issue.fields.subtasks = []
        mock_issue.fields.comment.comments = []

        mock_jira.issue.return_value = mock_issue

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            result = export_to_stdout("TEST-2", fmt="json")

        assert result is True
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["key"] == "TEST-2"

    def test_returns_false_on_error(self, mock_jira, capsys):
        """Returns False when ticket fetch fails."""
        from zaira.export import export_to_stdout

        mock_jira.issue.side_effect = Exception("Not found")

        result = export_to_stdout("INVALID-1")

        assert result is False
        captured = capsys.readouterr()
        assert "Error: Could not fetch" in captured.err


class TestExportCommand:
    """Tests for export_command function."""

    def test_exports_to_stdout_by_default(self, mock_jira, capsys):
        """Exports to stdout by default."""
        from zaira.export import export_command
        from unittest.mock import patch
        import argparse

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.comment.comments = []

        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            tickets=["TEST-1"],
            jql=None,
            board=None,
            sprint=None,
            output=None,
            format="md",
            files=False,
            with_prs=False,
            all_fields=False,
        )

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            export_command(args)

        captured = capsys.readouterr()
        assert "TEST-1" in captured.out

    def test_exports_to_files(self, mock_jira, tmp_path, capsys):
        """Exports to files when --files is set."""
        from zaira.export import export_command
        from unittest.mock import patch
        import argparse

        mock_issue = MagicMock()
        mock_issue.id = "12345"
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "File export"
        mock_issue.fields.description = None
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.components = []
        mock_issue.fields.labels = []
        mock_issue.fields.parent = None
        mock_issue.fields.issuelinks = []
        mock_issue.fields.attachment = []
        mock_issue.fields.comment.comments = []

        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            tickets=["TEST-1"],
            jql=None,
            board=None,
            sprint=None,
            output=str(tmp_path),
            format="md",
            files=True,
            with_prs=False,
            all_fields=False,
        )

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            export_command(args)

        files = list(tmp_path.glob("TEST-1*.md"))
        assert len(files) == 1

    def test_searches_with_jql(self, mock_jira, capsys):
        """Searches for tickets using JQL."""
        from zaira.export import export_command
        from unittest.mock import patch
        import argparse

        mock_issue1 = MagicMock()
        mock_issue1.key = "TEST-1"

        mock_issue2 = MagicMock()
        mock_issue2.id = "12345"
        mock_issue2.key = "TEST-1"
        mock_issue2.fields.summary = "Found"
        mock_issue2.fields.description = None
        mock_issue2.fields.issuetype.name = "Bug"
        mock_issue2.fields.status.name = "Open"
        mock_issue2.fields.status.statusCategory.name = "To Do"
        mock_issue2.fields.priority.name = "High"
        mock_issue2.fields.assignee = None
        mock_issue2.fields.reporter = None
        mock_issue2.fields.created = "2024-01-01"
        mock_issue2.fields.updated = "2024-01-02"
        mock_issue2.fields.components = []
        mock_issue2.fields.labels = []
        mock_issue2.fields.parent = None
        mock_issue2.fields.issuelinks = []
        mock_issue2.fields.comment.comments = []

        mock_jira.search_issues.return_value = [mock_issue1]
        mock_jira.issue.return_value = mock_issue2

        args = argparse.Namespace(
            tickets=[],
            jql="project = TEST",
            board=None,
            sprint=None,
            output=None,
            format="md",
            files=False,
            with_prs=False,
            all_fields=False,
        )

        with patch("zaira.export.get_jira_site", return_value="jira.example.com"):
            export_command(args)

        captured = capsys.readouterr()
        assert "TEST-1" in captured.out

    def test_exits_when_no_tickets(self, mock_jira, capsys):
        """Exits when no tickets specified or found."""
        from zaira.export import export_command
        import argparse

        args = argparse.Namespace(
            tickets=[],
            jql=None,
            board=None,
            sprint=None,
            output=None,
            format="md",
            files=False,
            with_prs=False,
            all_fields=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            export_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No tickets specified" in captured.out

    def test_uses_board_jql(self, mock_jira, capsys):
        """Uses board to generate JQL."""
        from zaira.export import export_command
        from unittest.mock import patch
        import argparse

        mock_issue1 = MagicMock()
        mock_issue1.key = "TEST-1"

        mock_issue2 = MagicMock()
        mock_issue2.id = "12345"
        mock_issue2.key = "TEST-1"
        mock_issue2.fields.summary = "Board ticket"
        mock_issue2.fields.description = None
        mock_issue2.fields.issuetype.name = "Story"
        mock_issue2.fields.status.name = "Open"
        mock_issue2.fields.status.statusCategory.name = "To Do"
        mock_issue2.fields.priority.name = "Medium"
        mock_issue2.fields.assignee = None
        mock_issue2.fields.reporter = None
        mock_issue2.fields.created = "2024-01-01"
        mock_issue2.fields.updated = "2024-01-02"
        mock_issue2.fields.components = []
        mock_issue2.fields.labels = []
        mock_issue2.fields.parent = None
        mock_issue2.fields.issuelinks = []
        mock_issue2.fields.comment.comments = []

        mock_jira.search_issues.return_value = [mock_issue1]
        mock_jira.issue.return_value = mock_issue2

        args = argparse.Namespace(
            tickets=[],
            jql=None,
            board=123,
            sprint=None,
            output=None,
            format="md",
            files=False,
            with_prs=False,
            all_fields=False,
        )

        with (
            patch("zaira.export.get_board_issues_jql", return_value="filter = 999"),
            patch("zaira.export.get_jira_site", return_value="jira.example.com"),
        ):
            export_command(args)

        captured = capsys.readouterr()
        assert "TEST-1" in captured.out

    def test_uses_sprint_jql(self, mock_jira, capsys):
        """Uses sprint to generate JQL."""
        from zaira.export import export_command
        from unittest.mock import patch
        import argparse

        mock_issue1 = MagicMock()
        mock_issue1.key = "TEST-1"

        mock_issue2 = MagicMock()
        mock_issue2.id = "12345"
        mock_issue2.key = "TEST-1"
        mock_issue2.fields.summary = "Sprint ticket"
        mock_issue2.fields.description = None
        mock_issue2.fields.issuetype.name = "Task"
        mock_issue2.fields.status.name = "Done"
        mock_issue2.fields.status.statusCategory.name = "Done"
        mock_issue2.fields.priority.name = "Low"
        mock_issue2.fields.assignee = None
        mock_issue2.fields.reporter = None
        mock_issue2.fields.created = "2024-01-01"
        mock_issue2.fields.updated = "2024-01-02"
        mock_issue2.fields.components = []
        mock_issue2.fields.labels = []
        mock_issue2.fields.parent = None
        mock_issue2.fields.issuelinks = []
        mock_issue2.fields.comment.comments = []

        mock_jira.search_issues.return_value = [mock_issue1]
        mock_jira.issue.return_value = mock_issue2

        args = argparse.Namespace(
            tickets=[],
            jql=None,
            board=None,
            sprint=456,
            output=None,
            format="md",
            files=False,
            with_prs=False,
            all_fields=False,
        )

        with (
            patch("zaira.export.get_sprint_issues_jql", return_value="Sprint = 456"),
            patch("zaira.export.get_jira_site", return_value="jira.example.com"),
        ):
            export_command(args)

        captured = capsys.readouterr()
        assert "TEST-1" in captured.out
