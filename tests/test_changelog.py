"""Tests for changelog module."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from zaira.changelog import (
    _extract_value,
    _format_diff,
    _is_long_text,
    changelog_command,
    extract_field_revisions,
    fetch_changelog,
    format_changelog,
    format_revisions,
)


class TestExtractValue:
    def test_none(self):
        assert _extract_value(None) == ""

    def test_string(self):
        assert _extract_value("hello") == "hello"

    def test_dict_with_name(self):
        assert _extract_value({"name": "Done"}) == "Done"

    def test_dict_with_value(self):
        assert _extract_value({"value": "High"}) == "High"

    def test_dict_with_display_name(self):
        assert _extract_value({"displayName": "John"}) == "John"

    def test_fallback_str(self):
        assert _extract_value(42) == "42"


class TestIsLongText:
    def test_short(self):
        assert not _is_long_text("short")

    def test_multiline(self):
        assert _is_long_text("line1\nline2")

    def test_long(self):
        assert _is_long_text("x" * 121)


class TestFormatDiff:
    def test_basic_diff(self):
        result = _format_diff("old text", "new text")
        assert "-old text" in result
        assert "+new text" in result

    def test_no_changes(self):
        result = _format_diff("same", "same")
        assert result == "(no visible changes)"

    def test_multiline_diff(self):
        old = "line1\nline2\nline3"
        new = "line1\nchanged\nline3"
        result = _format_diff(old, new)
        assert "-line2" in result
        assert "+changed" in result


def _make_history(items, author="user@test.com", created="2026-01-15T10:30:00.000+0000"):
    """Build a mock changelog history entry."""
    history = MagicMock()
    history.author = MagicMock()
    history.author.emailAddress = author
    history.author.displayName = author
    history.created = created
    mock_items = []
    for field, field_id, from_str, to_str in items:
        item = MagicMock()
        item.field = field
        item.fieldId = field_id
        item.fromString = from_str
        item.toString = to_str
        mock_items.append(item)
    history.items = mock_items
    return history


class TestFetchChangelog:
    def test_basic_fetch(self, mock_jira):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history([("status", "status", "Open", "In Progress")]),
        ]
        mock_jira.issue.return_value = issue

        entries = fetch_changelog("TEST-1")

        assert len(entries) == 1
        assert entries[0]["items"][0]["field"] == "status"
        assert entries[0]["items"][0]["from"] == "Open"
        assert entries[0]["items"][0]["to"] == "In Progress"
        mock_jira.issue.assert_called_once_with("TEST-1", expand="changelog")

    def test_multiple_histories(self, mock_jira):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history([("status", "status", "Open", "In Progress")]),
            _make_history([("assignee", "assignee", None, "dev@test.com")]),
        ]
        mock_jira.issue.return_value = issue

        entries = fetch_changelog("TEST-1")

        assert len(entries) == 2

    def test_resolves_custom_field_names(self, mock_jira):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history([("Custom Field", "customfield_12345", "", "value")]),
        ]
        mock_jira.issue.return_value = issue

        with patch("zaira.changelog.get_field_name", return_value="Story Points"):
            entries = fetch_changelog("TEST-1")

        assert entries[0]["items"][0]["field"] == "Story Points"

    def test_exits_on_error(self, mock_jira):
        mock_jira.issue.side_effect = Exception("Not found")

        with pytest.raises(SystemExit):
            fetch_changelog("NOPE-999")


class TestFormatChangelog:
    def test_empty(self):
        assert format_changelog([]) == "(no changelog entries)"

    def test_simple_change(self):
        entries = [{
            "author": "user@test.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [{"field": "status", "from": "Open", "to": "Done"}],
        }]
        result = format_changelog(entries)
        assert "user@test.com" in result
        assert "status" in result
        assert "Open → Done" in result

    def test_field_set_from_empty(self):
        entries = [{
            "author": "u@t.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [{"field": "assignee", "from": "", "to": "dev@test.com"}],
        }]
        result = format_changelog(entries)
        assert "→ dev@test.com" in result

    def test_field_cleared(self):
        entries = [{
            "author": "u@t.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [{"field": "assignee", "from": "dev@test.com", "to": ""}],
        }]
        result = format_changelog(entries)
        assert "*(cleared)*" in result

    def test_field_filter(self):
        entries = [{
            "author": "u@t.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [
                {"field": "status", "from": "Open", "to": "Done"},
                {"field": "priority", "from": "Low", "to": "High"},
            ],
        }]
        result = format_changelog(entries, field_filter="status")
        assert "status" in result
        assert "priority" not in result

    def test_field_filter_no_match(self):
        entries = [{
            "author": "u@t.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [{"field": "status", "from": "Open", "to": "Done"}],
        }]
        result = format_changelog(entries, field_filter="description")
        assert result == "(no matching changes)"

    def test_long_text_shows_diff_by_default(self):
        """Long text fields show diffs by default."""
        entries = [{
            "author": "u@t.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [{
                "field": "description",
                "from": "old line 1\nold line 2\nold line 3",
                "to": "old line 1\nnew line 2\nold line 3",
            }],
        }]
        result = format_changelog(entries)
        assert "```diff" in result
        assert "-old line 2" in result
        assert "+new line 2" in result

    def test_short_values_no_diff(self):
        """Short values use arrow notation, not diffs."""
        entries = [{
            "author": "u@t.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [{"field": "status", "from": "Open", "to": "Done"}],
        }]
        result = format_changelog(entries)
        assert "```diff" not in result
        assert "Open → Done" in result

    def test_full_mode_shows_raw_long_text(self):
        """--full shows complete old/new values instead of diffs."""
        entries = [{
            "author": "u@t.com",
            "created": "2026-01-15T10:30:00.000+0000",
            "items": [{
                "field": "description",
                "from": "old line 1\nold line 2",
                "to": "new line 1\nnew line 2",
            }],
        }]
        result = format_changelog(entries, full=True)
        assert "```diff" not in result
        assert "old line 1\nold line 2" in result
        assert "new line 1\nnew line 2" in result


class TestChangelogCommand:
    def test_basic_run(self, mock_jira, capsys):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history([("status", "status", "Open", "Done")]),
        ]
        mock_jira.issue.return_value = issue

        args = argparse.Namespace(key="test-1", tail=None, full=False, field=None, revisions=False, rev=None)
        changelog_command(args)

        captured = capsys.readouterr()
        assert "Open → Done" in captured.out

    def test_tail_limit(self, mock_jira, capsys):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history(
                [("status", "status", "Open", "In Progress")],
                created="2026-01-01T10:00:00.000+0000",
            ),
            _make_history(
                [("status", "status", "In Progress", "Done")],
                created="2026-01-02T10:00:00.000+0000",
            ),
        ]
        mock_jira.issue.return_value = issue

        args = argparse.Namespace(key="TEST-1", tail=1, full=False, field=None, revisions=False, rev=None)
        changelog_command(args)

        captured = capsys.readouterr()
        assert "In Progress → Done" in captured.out
        assert "Open → In Progress" not in captured.out

    def test_uppercases_key(self, mock_jira, capsys):
        issue = MagicMock()
        issue.changelog.histories = []
        mock_jira.issue.return_value = issue

        args = argparse.Namespace(key="test-1", tail=None, full=False, field=None, revisions=False, rev=None)
        changelog_command(args)

        mock_jira.issue.assert_called_once_with("TEST-1", expand="changelog")

    def test_revisions_requires_field(self, mock_jira, capsys):
        args = argparse.Namespace(
            key="TEST-1", tail=None, full=False, field=None,
            revisions=True, rev=None,
        )
        with pytest.raises(SystemExit):
            changelog_command(args)
        assert "--field" in capsys.readouterr().err

    def test_rev_requires_field(self, mock_jira, capsys):
        args = argparse.Namespace(
            key="TEST-1", tail=None, full=False, field=None,
            revisions=False, rev=3,
        )
        with pytest.raises(SystemExit):
            changelog_command(args)
        assert "--field" in capsys.readouterr().err

    def test_rev_prints_specific_revision(self, mock_jira, capsys):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history(
                [("description", "description", "v1 text", "v2 text")],
                created="2026-01-01T10:00:00.000+0000",
            ),
            _make_history(
                [("description", "description", "v2 text", "v3 text")],
                created="2026-01-02T10:00:00.000+0000",
            ),
        ]
        mock_jira.issue.return_value = issue

        args = argparse.Namespace(
            key="TEST-1", tail=None, full=False, field="description",
            revisions=False, rev=1,
        )
        changelog_command(args)
        assert capsys.readouterr().out.strip() == "v1 text"

    def test_rev_prints_latest(self, mock_jira, capsys):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history(
                [("description", "description", "v1", "v2")],
                created="2026-01-01T10:00:00.000+0000",
            ),
        ]
        mock_jira.issue.return_value = issue

        args = argparse.Namespace(
            key="TEST-1", tail=None, full=False, field="description",
            revisions=False, rev=2,
        )
        changelog_command(args)
        assert capsys.readouterr().out.strip() == "v2"

    def test_rev_not_found(self, mock_jira, capsys):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history([("description", "description", "v1", "v2")]),
        ]
        mock_jira.issue.return_value = issue

        args = argparse.Namespace(
            key="TEST-1", tail=None, full=False, field="description",
            revisions=False, rev=99,
        )
        with pytest.raises(SystemExit):
            changelog_command(args)
        assert "revision 99 not found" in capsys.readouterr().err

    def test_revisions_list(self, mock_jira, capsys):
        issue = MagicMock()
        issue.changelog.histories = [
            _make_history(
                [("description", "description", "first", "second")],
                author="a@t.com",
                created="2026-01-01T10:00:00.000+0000",
            ),
            _make_history(
                [("description", "description", "second", "third")],
                author="b@t.com",
                created="2026-01-02T10:00:00.000+0000",
            ),
        ]
        mock_jira.issue.return_value = issue

        args = argparse.Namespace(
            key="TEST-1", tail=None, full=False, field="description",
            revisions=True, rev=None,
        )
        changelog_command(args)
        out = capsys.readouterr().out
        assert "1" in out
        assert "2" in out
        assert "3" in out
        assert "first" in out


class TestExtractFieldRevisions:
    def test_builds_revision_chain(self):
        entries = [
            {
                "author": "a@t.com",
                "created": "2026-01-01T10:00:00.000+0000",
                "items": [{"field": "description", "from": "v1", "to": "v2"}],
            },
            {
                "author": "b@t.com",
                "created": "2026-01-02T10:00:00.000+0000",
                "items": [{"field": "description", "from": "v2", "to": "v3"}],
            },
        ]
        revs = extract_field_revisions(entries, "description")
        assert len(revs) == 3
        assert revs[0]["rev"] == 1
        assert revs[0]["value"] == "v1"
        assert revs[1]["rev"] == 2
        assert revs[1]["value"] == "v2"
        assert revs[2]["rev"] == 3
        assert revs[2]["value"] == "v3"

    def test_empty_entries(self):
        assert extract_field_revisions([], "description") == []

    def test_no_matching_field(self):
        entries = [{
            "author": "a@t.com",
            "created": "2026-01-01T10:00:00.000+0000",
            "items": [{"field": "status", "from": "Open", "to": "Done"}],
        }]
        assert extract_field_revisions(entries, "description") == []

    def test_case_insensitive_field_match(self):
        entries = [{
            "author": "a@t.com",
            "created": "2026-01-01T10:00:00.000+0000",
            "items": [{"field": "Description", "from": "v1", "to": "v2"}],
        }]
        revs = extract_field_revisions(entries, "description")
        assert len(revs) == 2
