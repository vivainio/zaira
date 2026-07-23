"""Tests for info module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zaira.info import (
    load_schema,
    save_schema,
    update_schema,
    get_field_id,
    get_field_name,
    get_field_map,
    get_field_type,
    load_project_schema,
    _fetch_cached_data,
)
from zaira.types import ZSchema


class TestLoadSchema:
    """Tests for load_schema function."""

    def test_returns_none_when_no_file(self, tmp_path):
        """Returns None when schema file doesn't exist."""
        with patch(
            "zaira.info.get_schema_path", return_value=tmp_path / "nonexistent.json"
        ):
            result = load_schema()
        assert result is None

    def test_loads_schema_from_file(self, tmp_path):
        """Loads schema from JSON file."""
        schema_file = tmp_path / "schema.json"
        schema_data = {
            "version": 2,
            "fields": {"customfield_123": {"name": "Story Points"}},
        }
        schema_file.write_text(json.dumps(schema_data))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = load_schema()

        assert result == schema_data


class TestSaveSchema:
    """Tests for save_schema function."""

    def test_saves_schema_to_file(self, tmp_path):
        """Saves schema to JSON file."""
        schema_file = tmp_path / "schema.json"
        schema_data: ZSchema = {
            "version": 2,
            "fields": {"customfield_456": {"name": "Epic Link"}},
        }

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            save_schema(schema_data)

        assert schema_file.exists()
        loaded = json.loads(schema_file.read_text())
        assert loaded == schema_data


class TestUpdateSchema:
    """Tests for update_schema function."""

    def test_updates_existing_schema(self, tmp_path):
        """Updates key in existing schema."""
        schema_file = tmp_path / "schema.json"
        existing = {"version": 2, "fields": {"old": "value"}}
        schema_file.write_text(json.dumps(existing))

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            update_schema("statuses", {"Open": "To Do"})

        loaded = json.loads(schema_file.read_text())
        assert loaded["fields"] == {"old": "value"}
        assert loaded["statuses"] == {"Open": "To Do"}

    def test_creates_schema_if_none(self, tmp_path):
        """Creates new schema if none exists."""
        schema_file = tmp_path / "schema.json"

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            update_schema("priorities", ["High", "Medium", "Low"])

        loaded = json.loads(schema_file.read_text())
        assert loaded["priorities"] == ["High", "Medium", "Low"]


class TestGetFieldId:
    """Tests for get_field_id function."""

    def test_returns_field_id_by_name(self, tmp_path):
        """Returns field ID for given name."""
        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {"customfield_10551": {"name": "Story Points"}},
        }
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_id("Story Points")

        assert result == "customfield_10551"

    def test_case_insensitive_lookup(self, tmp_path):
        """Lookup is case-insensitive."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "fields": {"customfield_123": {"name": "Epic Link"}}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            assert get_field_id("epic link") == "customfield_123"
            assert get_field_id("EPIC LINK") == "customfield_123"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when field not found."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "fields": {"customfield_123": {"name": "Existing"}}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_id("Nonexistent Field")

        assert result is None

    def test_returns_none_when_no_schema(self, tmp_path):
        """Returns None when no schema exists."""
        with patch(
            "zaira.info.get_schema_path", return_value=tmp_path / "nonexistent.json"
        ):
            result = get_field_id("Any Field")

        assert result is None


class TestGetFieldName:
    """Tests for get_field_name function."""

    def test_returns_field_name_by_id(self, tmp_path):
        """Returns field name for given ID."""
        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {"customfield_10551": {"name": "Story Points"}},
        }
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_name("customfield_10551")

        assert result == "Story Points"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when field ID not found."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "fields": {"customfield_123": {"name": "Existing"}}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_name("customfield_999")

        assert result is None


class TestGetFieldMap:
    """Tests for get_field_map function."""

    def test_returns_name_to_id_mapping(self, tmp_path):
        """Returns dict mapping names to IDs."""
        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {
                "customfield_123": {"name": "Story Points"},
                "customfield_456": {"name": "Epic Link"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_map()

        assert result == {
            "Story Points": "customfield_123",
            "Epic Link": "customfield_456",
        }

    def test_returns_empty_dict_when_no_schema(self, tmp_path):
        """Returns empty dict when no schema."""
        with patch(
            "zaira.info.get_schema_path", return_value=tmp_path / "nonexistent.json"
        ):
            result = get_field_map()

        assert result == {}


class TestGetFieldType:
    """Tests for get_field_type function."""

    def test_returns_field_type(self, tmp_path):
        """Returns field type for given ID."""
        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {
                "customfield_123": {"name": "Num Field", "type": "number"},
                "customfield_456": {"name": "Opt Field", "type": "option"},
                "customfield_789": {"name": "Labels", "type": "string list"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            assert get_field_type("customfield_123") == "number"
            assert get_field_type("customfield_456") == "option"
            assert get_field_type("customfield_789") == "array"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when field type not found."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "fields": {}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_type("customfield_999")

        assert result is None


class TestLoadProjectSchema:
    """Tests for load_project_schema function."""

    def test_loads_project_schema(self, tmp_path):
        """Loads project schema from file."""
        schema_file = tmp_path / "project_schema.json"
        schema = {"components": ["Backend", "Frontend"], "labels": ["bug", "feature"]}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_project_schema_path", return_value=schema_file):
            result = load_project_schema("TEST")

        assert result == schema

    def test_returns_none_when_no_file(self, tmp_path):
        """Returns None when file doesn't exist."""
        with patch(
            "zaira.info.get_project_schema_path",
            return_value=tmp_path / "nonexistent.json",
        ):
            result = load_project_schema("TEST")

        assert result is None


class TestFetchCachedData:
    """Tests for _fetch_cached_data function."""

    def test_returns_cached_data(self, tmp_path):
        """Returns cached data when available."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "statuses": {"Open": "To Do", "Done": "Done"}}
        schema_file.write_text(json.dumps(schema))

        fetch_called = False

        def mock_fetch() -> dict[str, object]:
            nonlocal fetch_called
            fetch_called = True
            return {}

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = _fetch_cached_data("statuses", mock_fetch, refresh=False)

        assert result == {"Open": "To Do", "Done": "Done"}
        assert not fetch_called

    def test_fetches_when_refresh_true(self, tmp_path):
        """Fetches fresh data when refresh=True."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "statuses": {"old": "data"}}
        schema_file.write_text(json.dumps(schema))

        def mock_fetch() -> dict[str, object]:
            return {"new": "data"}

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = _fetch_cached_data("statuses", mock_fetch, refresh=True)

        assert result == {"new": "data"}

    def test_fetches_when_key_missing(self, tmp_path):
        """Fetches data when key not in cache."""
        schema_file = tmp_path / "schema.json"
        schema = {"other_key": "value"}
        schema_file.write_text(json.dumps(schema))

        def mock_fetch() -> list[object]:
            return ["High", "Medium", "Low"]

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = _fetch_cached_data("priorities", mock_fetch, refresh=False)

        assert result == ["High", "Medium", "Low"]


class TestGetFieldIdEdgeCases:
    """Additional tests for get_field_id edge cases."""

    def test_returns_none_for_missing_fields_key(self, tmp_path):
        """Returns None when 'fields' key is missing."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "statuses": {}}  # No 'fields' key
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_id("Story Points")

        assert result is None


class TestGetFieldNameEdgeCases:
    """Additional tests for get_field_name edge cases."""

    def test_returns_none_for_missing_fields_key(self, tmp_path):
        """Returns None when 'fields' key is missing."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "statuses": {}}
        schema_file.write_text(json.dumps(schema))

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch(
                "zaira.info._fetch_and_cache_fields",
                side_effect=Exception("no network"),
            ),
        ):
            result = get_field_name("customfield_123")

        assert result is None


class TestGetFieldTypeEdgeCases:
    """Additional tests for get_field_type edge cases."""

    def test_returns_none_for_missing_fieldtypes_key(self, tmp_path):
        """Returns None when 'fieldTypes' key is missing."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "fields": {}}  # No 'fieldTypes' key
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_type("customfield_123")

        assert result is None


class TestLinkTypesCommand:
    """Tests for link_types_command function."""

    def test_displays_link_types_from_cache(self, mock_jira, capsys, tmp_path):
        """Displays link types from cached schema."""
        from zaira.info import link_types_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "linkTypes": {
                "Blocks": {"outward": "blocks", "inward": "is blocked by"},
                "Relates": {"outward": "relates to", "inward": "relates to"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False)

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            link_types_command(args)

        captured = capsys.readouterr()
        assert "Blocks" in captured.out
        assert "blocks" in captured.out
        assert "Relates" in captured.out

    def test_fetches_link_types_on_refresh(self, mock_jira, capsys, tmp_path):
        """Fetches link types from API on refresh."""
        from zaira.info import link_types_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema_file.write_text("{}")

        mock_type = MagicMock()
        mock_type.name = "Blocks"
        mock_type.outward = "blocks"
        mock_type.inward = "is blocked by"
        mock_jira.issue_link_types.return_value = [mock_type]

        args = argparse.Namespace(refresh=True)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            link_types_command(args)

        captured = capsys.readouterr()
        assert "Blocks" in captured.out

    def test_handles_api_error(self, mock_jira, capsys, tmp_path):
        """Handles API errors gracefully."""
        from zaira.info import link_types_command
        import argparse

        schema_file = tmp_path / "nonexistent.json"
        mock_jira.issue_link_types.side_effect = Exception("API Error")

        args = argparse.Namespace(refresh=False)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            pytest.raises(SystemExit) as exc_info,
        ):
            link_types_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error fetching link types" in captured.err


class TestStatusesCommand:
    """Tests for statuses_command function."""

    def test_displays_statuses_from_cache(self, mock_jira, capsys, tmp_path):
        """Displays statuses from cached schema."""
        from zaira.info import statuses_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "statuses": {
                "Open": "To Do",
                "In Progress": "In Progress",
                "Done": "Done",
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False)

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            statuses_command(args)

        captured = capsys.readouterr()
        assert "Open" in captured.out
        assert "To Do" in captured.out
        assert "Done" in captured.out

    def test_fetches_statuses_on_refresh(self, mock_jira, capsys, tmp_path):
        """Fetches statuses from API on refresh."""
        from zaira.info import statuses_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema_file.write_text("{}")

        mock_status = MagicMock()
        mock_status.name = "Open"
        mock_status.statusCategory.name = "To Do"
        mock_jira.statuses.return_value = [mock_status]

        args = argparse.Namespace(refresh=True)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            statuses_command(args)

        captured = capsys.readouterr()
        assert "Open" in captured.out

    def test_handles_api_error(self, mock_jira, capsys, tmp_path):
        """Handles API errors gracefully."""
        from zaira.info import statuses_command
        import argparse

        schema_file = tmp_path / "nonexistent.json"
        mock_jira.statuses.side_effect = Exception("API Error")

        args = argparse.Namespace(refresh=False)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            pytest.raises(SystemExit) as exc_info,
        ):
            statuses_command(args)

        assert exc_info.value.code == 1


class TestIssueTypesCommand:
    """Tests for issue_types_command function."""

    def test_displays_issue_types_from_cache(self, mock_jira, capsys, tmp_path):
        """Displays issue types from cached schema."""
        from zaira.info import issue_types_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "issueTypes": {
                "Bug": {"subtask": False},
                "Story": {"subtask": False},
                "Sub-task": {"subtask": True},
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False)

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            issue_types_command(args)

        captured = capsys.readouterr()
        assert "Bug" in captured.out
        assert "Story" in captured.out
        assert "Sub-task" in captured.out
        assert "yes" in captured.out  # subtask = yes

    def test_fetches_issue_types_on_refresh(self, mock_jira, capsys, tmp_path):
        """Fetches issue types from API on refresh."""
        from zaira.info import issue_types_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema_file.write_text("{}")

        mock_type = MagicMock()
        mock_type.name = "Bug"
        mock_type.subtask = False
        mock_jira.issue_types.return_value = [mock_type]

        args = argparse.Namespace(refresh=True)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            issue_types_command(args)

        captured = capsys.readouterr()
        assert "Bug" in captured.out

    def test_handles_api_error(self, mock_jira, capsys, tmp_path):
        """Handles API errors gracefully."""
        from zaira.info import issue_types_command
        import argparse

        schema_file = tmp_path / "nonexistent.json"
        mock_jira.issue_types.side_effect = Exception("API Error")

        args = argparse.Namespace(refresh=False)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            pytest.raises(SystemExit) as exc_info,
        ):
            issue_types_command(args)

        assert exc_info.value.code == 1


class TestFieldsCommand:
    """Tests for fields_command function."""

    def test_displays_custom_fields_from_cache(self, mock_jira, capsys, tmp_path):
        """Displays custom fields from cached schema."""
        from zaira.info import fields_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {
                "customfield_10001": {"name": "Story Points"},
                "customfield_10002": {"name": "Sprint"},
                "summary": {"name": "Summary"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False, all=False, filter=None)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.rules.load_allowed_fields", return_value=None),
        ):
            fields_command(args)

        captured = capsys.readouterr()
        assert "Story Points" in captured.out
        assert "Sprint" in captured.out
        # Standard fields not shown by default
        assert "Summary" not in captured.out

    def test_shows_all_fields(self, mock_jira, capsys, tmp_path):
        """Shows all fields when --all flag is set."""
        from zaira.info import fields_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {
                "customfield_10001": {"name": "Story Points"},
                "summary": {"name": "Summary"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False, all=True, filter=None)

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            fields_command(args)

        captured = capsys.readouterr()
        assert "Story Points" in captured.out
        assert "Summary" in captured.out

    def test_filters_fields(self, mock_jira, capsys, tmp_path):
        """Filters fields by name."""
        from zaira.info import fields_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {
                "customfield_10001": {"name": "Story Points"},
                "customfield_10002": {"name": "Sprint"},
                "customfield_10003": {"name": "Epic Link"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False, all=False, filter="sprint")

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.rules.load_allowed_fields", return_value=None),
        ):
            fields_command(args)

        captured = capsys.readouterr()
        assert "Sprint" in captured.out
        assert "Story Points" not in captured.out
        assert "Epic Link" not in captured.out

    def test_fetches_fields_on_refresh(self, mock_jira, capsys, tmp_path):
        """Fetches fields from API on refresh."""
        from zaira.info import fields_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema_file.write_text("{}")

        mock_jira.fields.return_value = [
            {
                "id": "customfield_10001",
                "name": "Story Points",
                "custom": True,
                "schema": {"type": "number"},
            },
        ]

        args = argparse.Namespace(refresh=True, all=False, filter=None)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
            patch("zaira.rules.load_allowed_fields", return_value=None),
        ):
            fields_command(args)

        captured = capsys.readouterr()
        assert "Story Points" in captured.out

    def test_filters_by_allowed_fields(self, mock_jira, capsys, tmp_path):
        """Shows only allowed fields when allowed_fields is configured."""
        from zaira.info import fields_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {
                "customfield_10001": {"name": "Story Points"},
                "customfield_10002": {"name": "Sprint"},
                "customfield_10003": {"name": "Epic Link"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False, all=False, filter=None)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch(
                "zaira.rules.load_allowed_fields",
                return_value={"Story Points", "Sprint"},
            ),
        ):
            fields_command(args)

        captured = capsys.readouterr()
        assert "Story Points" in captured.out
        assert "Sprint" in captured.out
        assert "Epic Link" not in captured.out
        assert "Filtered by" in captured.err
        assert "--all" in captured.err

    def test_all_flag_ignores_allowed_fields(self, mock_jira, capsys, tmp_path):
        """--all flag shows all fields even when allowed_fields is configured."""
        from zaira.info import fields_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {
                "customfield_10001": {"name": "Story Points"},
                "customfield_10002": {"name": "Sprint"},
                "summary": {"name": "Summary"},
            },
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False, all=True, filter=None)

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            fields_command(args)

        captured = capsys.readouterr()
        assert "Story Points" in captured.out
        assert "Sprint" in captured.out
        assert "Summary" in captured.out

    def test_handles_api_error(self, mock_jira, capsys, tmp_path):
        """Handles API errors gracefully."""
        from zaira.info import fields_command
        import argparse

        schema_file = tmp_path / "nonexistent.json"
        mock_jira.fields.side_effect = Exception("API Error")

        args = argparse.Namespace(refresh=True, all=False, filter=None)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            fields_command(args)

        assert exc_info.value.code == 1


class TestInfoCommand:
    """Tests for info_command function."""

    def test_calls_info_func(self, mock_jira, capsys, tmp_path):
        """Calls info_func when present on args."""
        from zaira.info import info_command
        import argparse

        called = []

        def mock_func(args: argparse.Namespace) -> None:
            called.append(True)

        args = argparse.Namespace(info_func=mock_func)

        info_command(args)

        assert called == [True]

    def test_shows_usage_when_no_subcommand(self, mock_jira, capsys):
        """Shows usage when no subcommand specified."""
        from zaira.info import info_command
        import argparse

        args = argparse.Namespace()
        # No info_func attribute

        with pytest.raises(SystemExit) as exc_info:
            info_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.out
        assert "zaira info <subcommand>" in captured.out


class TestGetFieldNameAutoFetch:
    """Tests for get_field_name auto-fetch behavior."""

    def test_auto_fetches_when_no_fields_cached(self, mock_jira, tmp_path):
        """Auto-fetches fields from API when not cached."""
        schema_file = tmp_path / "schema.json"
        schema = {"version": 2, "statuses": {}}  # No 'fields' key
        schema_file.write_text(json.dumps(schema))

        mock_jira.fields.return_value = [
            {
                "id": "customfield_10001",
                "name": "Story Points",
                "schema": {"type": "number"},
            },
        ]

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            result = get_field_name("customfield_10001")

        assert result == "Story Points"
        mock_jira.fields.assert_called_once()

    def test_auto_fetches_when_no_schema_file(self, mock_jira, tmp_path):
        """Auto-fetches fields when schema file doesn't exist."""
        schema_file = tmp_path / "nonexistent.json"

        mock_jira.fields.return_value = [
            {
                "id": "customfield_999",
                "name": "Epic Link",
                "schema": {"type": "string"},
            },
        ]

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            result = get_field_name("customfield_999")

        assert result == "Epic Link"

    def test_returns_none_when_auto_fetch_fails(self, mock_jira, tmp_path):
        """Returns None when auto-fetch raises an exception."""
        schema_file = tmp_path / "nonexistent.json"
        mock_jira.fields.side_effect = Exception("API Error")

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_name("customfield_123")

        assert result is None

    def test_returns_none_when_field_not_in_fetched_data(self, mock_jira, tmp_path):
        """Returns None when field not found even after auto-fetch."""
        schema_file = tmp_path / "nonexistent.json"

        mock_jira.fields.return_value = [
            {
                "id": "customfield_10001",
                "name": "Story Points",
                "schema": {"type": "number"},
            },
        ]

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            result = get_field_name("customfield_999")

        assert result is None

    def test_does_not_fetch_when_fields_cached(self, mock_jira, tmp_path):
        """Does not call API when fields are already cached."""
        schema_file = tmp_path / "schema.json"
        schema = {
            "version": 2,
            "fields": {"customfield_10001": {"name": "Story Points"}},
        }
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_name("customfield_10001")

        assert result == "Story Points"
        mock_jira.fields.assert_not_called()


class TestFieldCommand:
    """Tests for field_command (zaira info field)."""

    def _write_editmeta(
        self,
        tmp_path: Path,
        project: str,
        issue_type: str,
        fields: dict[str, object],
    ) -> None:
        import yaml as _yaml

        data = {"project": project, "issueType": issue_type, "fields": fields}
        path = tmp_path / f"editmeta_{project}_{issue_type}.yaml"
        path.write_text(_yaml.dump(data))

    def test_suggests_similar_field_names(self, capsys, tmp_path):
        """Shows 'did you mean' suggestions for close matches."""
        from zaira.info import field_command
        import argparse

        self._write_editmeta(
            tmp_path,
            "PROJ",
            "Story",
            {
                "Story Points": {"id": "customfield_10001", "type": "number"},
                "Sprint": {"id": "customfield_10002", "type": "string"},
                "Summary": {"id": "summary", "type": "string"},
            },
        )

        args = argparse.Namespace(names=["Story Poitns"])  # typo

        with (
            patch("zaira.info.CACHE_DIR", tmp_path),
            patch("zaira.info.load_field_descriptions", return_value={}),
        ):
            field_command(args)

        captured = capsys.readouterr()
        assert "Did you mean" in captured.out
        assert "Story Points" in captured.out

    def test_no_suggestions_for_completely_different_name(self, capsys, tmp_path):
        """Falls back to plain 'not found' when nothing is close."""
        from zaira.info import field_command
        import argparse

        self._write_editmeta(
            tmp_path,
            "PROJ",
            "Story",
            {
                "Summary": {"id": "summary", "type": "string"},
            },
        )

        args = argparse.Namespace(names=["zzzzzzzzz"])

        with (
            patch("zaira.info.CACHE_DIR", tmp_path),
            patch("zaira.info.load_field_descriptions", return_value={}),
        ):
            field_command(args)

        captured = capsys.readouterr()
        assert "not found in any editmeta cache" in captured.out
        assert "Did you mean" not in captured.out
