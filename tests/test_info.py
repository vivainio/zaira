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


class TestLoadSchema:
    """Tests for load_schema function."""

    def test_returns_none_when_no_file(self, tmp_path):
        """Returns None when schema file doesn't exist."""
        with patch("zaira.info.get_schema_path", return_value=tmp_path / "nonexistent.json"):
            result = load_schema()
        assert result is None

    def test_loads_schema_from_file(self, tmp_path):
        """Loads schema from JSON file."""
        schema_file = tmp_path / "schema.json"
        schema_data = {"fields": {"customfield_123": "Story Points"}}
        schema_file.write_text(json.dumps(schema_data))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = load_schema()

        assert result == schema_data


class TestSaveSchema:
    """Tests for save_schema function."""

    def test_saves_schema_to_file(self, tmp_path):
        """Saves schema to JSON file."""
        schema_file = tmp_path / "schema.json"
        schema_data = {"fields": {"customfield_456": "Epic Link"}}

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
        existing = {"fields": {"old": "value"}}
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
        schema = {"fields": {"customfield_10551": "Story Points"}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_id("Story Points")

        assert result == "customfield_10551"

    def test_case_insensitive_lookup(self, tmp_path):
        """Lookup is case-insensitive."""
        schema_file = tmp_path / "schema.json"
        schema = {"fields": {"customfield_123": "Epic Link"}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            assert get_field_id("epic link") == "customfield_123"
            assert get_field_id("EPIC LINK") == "customfield_123"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when field not found."""
        schema_file = tmp_path / "schema.json"
        schema = {"fields": {"customfield_123": "Existing"}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_id("Nonexistent Field")

        assert result is None

    def test_returns_none_when_no_schema(self, tmp_path):
        """Returns None when no schema exists."""
        with patch("zaira.info.get_schema_path", return_value=tmp_path / "nonexistent.json"):
            result = get_field_id("Any Field")

        assert result is None


class TestGetFieldName:
    """Tests for get_field_name function."""

    def test_returns_field_name_by_id(self, tmp_path):
        """Returns field name for given ID."""
        schema_file = tmp_path / "schema.json"
        schema = {"fields": {"customfield_10551": "Story Points"}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_name("customfield_10551")

        assert result == "Story Points"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when field ID not found."""
        schema_file = tmp_path / "schema.json"
        schema = {"fields": {"customfield_123": "Existing"}}
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
            "fields": {
                "customfield_123": "Story Points",
                "customfield_456": "Epic Link",
            }
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
        with patch("zaira.info.get_schema_path", return_value=tmp_path / "nonexistent.json"):
            result = get_field_map()

        assert result == {}


class TestGetFieldType:
    """Tests for get_field_type function."""

    def test_returns_field_type(self, tmp_path):
        """Returns field type for given ID."""
        schema_file = tmp_path / "schema.json"
        schema = {"fieldTypes": {"customfield_123": "number", "customfield_456": "option"}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            assert get_field_type("customfield_123") == "number"
            assert get_field_type("customfield_456") == "option"

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when field type not found."""
        schema_file = tmp_path / "schema.json"
        schema = {"fieldTypes": {}}
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
        with patch("zaira.info.get_project_schema_path", return_value=tmp_path / "nonexistent.json"):
            result = load_project_schema("TEST")

        assert result is None


class TestFetchCachedData:
    """Tests for _fetch_cached_data function."""

    def test_returns_cached_data(self, tmp_path):
        """Returns cached data when available."""
        schema_file = tmp_path / "schema.json"
        schema = {"statuses": {"Open": "To Do", "Done": "Done"}}
        schema_file.write_text(json.dumps(schema))

        fetch_called = False

        def mock_fetch():
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
        schema = {"statuses": {"old": "data"}}
        schema_file.write_text(json.dumps(schema))

        def mock_fetch():
            return {"new": "data"}

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = _fetch_cached_data("statuses", mock_fetch, refresh=True)

        assert result == {"new": "data"}

    def test_fetches_when_key_missing(self, tmp_path):
        """Fetches data when key not in cache."""
        schema_file = tmp_path / "schema.json"
        schema = {"other_key": "value"}
        schema_file.write_text(json.dumps(schema))

        def mock_fetch():
            return ["High", "Medium", "Low"]

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = _fetch_cached_data("priorities", mock_fetch, refresh=False)

        assert result == ["High", "Medium", "Low"]


class TestGetFieldIdEdgeCases:
    """Additional tests for get_field_id edge cases."""

    def test_returns_none_for_missing_fields_key(self, tmp_path):
        """Returns None when 'fields' key is missing."""
        schema_file = tmp_path / "schema.json"
        schema = {"statuses": {}}  # No 'fields' key
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_id("Story Points")

        assert result is None


class TestGetFieldNameEdgeCases:
    """Additional tests for get_field_name edge cases."""

    def test_returns_none_for_missing_fields_key(self, tmp_path):
        """Returns None when 'fields' key is missing."""
        schema_file = tmp_path / "schema.json"
        schema = {"statuses": {}}
        schema_file.write_text(json.dumps(schema))

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            result = get_field_name("customfield_123")

        assert result is None


class TestGetFieldTypeEdgeCases:
    """Additional tests for get_field_type edge cases."""

    def test_returns_none_for_missing_fieldtypes_key(self, tmp_path):
        """Returns None when 'fieldTypes' key is missing."""
        schema_file = tmp_path / "schema.json"
        schema = {"fields": {}}  # No 'fieldTypes' key
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
            "linkTypes": {
                "Blocks": {"outward": "blocks", "inward": "is blocked by"},
                "Relates": {"outward": "relates to", "inward": "relates to"},
            }
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
            "statuses": {
                "Open": "To Do",
                "In Progress": "In Progress",
                "Done": "Done",
            }
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


class TestPrioritiesCommand:
    """Tests for priorities_command function."""

    def test_displays_priorities_from_cache(self, mock_jira, capsys, tmp_path):
        """Displays priorities from cached schema."""
        from zaira.info import priorities_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {"priorities": ["Highest", "High", "Medium", "Low", "Lowest"]}
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False)

        with patch("zaira.info.get_schema_path", return_value=schema_file):
            priorities_command(args)

        captured = capsys.readouterr()
        assert "Priorities:" in captured.out
        assert "Highest" in captured.out
        assert "Low" in captured.out

    def test_fetches_priorities_on_refresh(self, mock_jira, capsys, tmp_path):
        """Fetches priorities from API on refresh."""
        from zaira.info import priorities_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema_file.write_text("{}")

        mock_priority = MagicMock()
        mock_priority.name = "High"
        mock_jira.priorities.return_value = [mock_priority]

        args = argparse.Namespace(refresh=True)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            priorities_command(args)

        captured = capsys.readouterr()
        assert "High" in captured.out

    def test_handles_api_error(self, mock_jira, capsys, tmp_path):
        """Handles API errors gracefully."""
        from zaira.info import priorities_command
        import argparse

        schema_file = tmp_path / "nonexistent.json"
        mock_jira.priorities.side_effect = Exception("API Error")

        args = argparse.Namespace(refresh=False)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            pytest.raises(SystemExit) as exc_info,
        ):
            priorities_command(args)

        assert exc_info.value.code == 1


class TestIssueTypesCommand:
    """Tests for issue_types_command function."""

    def test_displays_issue_types_from_cache(self, mock_jira, capsys, tmp_path):
        """Displays issue types from cached schema."""
        from zaira.info import issue_types_command
        import argparse

        schema_file = tmp_path / "schema.json"
        schema = {
            "issueTypes": {
                "Bug": {"subtask": False},
                "Story": {"subtask": False},
                "Sub-task": {"subtask": True},
            }
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
            "fields": {
                "customfield_10001": "Story Points",
                "customfield_10002": "Sprint",
                "summary": "Summary",  # Standard field
            }
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False, all=False, filter=None)

        with patch("zaira.info.get_schema_path", return_value=schema_file):
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
            "fields": {
                "customfield_10001": "Story Points",
                "summary": "Summary",
            }
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
            "fields": {
                "customfield_10001": "Story Points",
                "customfield_10002": "Sprint",
                "customfield_10003": "Epic Link",
            }
        }
        schema_file.write_text(json.dumps(schema))

        args = argparse.Namespace(refresh=False, all=False, filter="sprint")

        with patch("zaira.info.get_schema_path", return_value=schema_file):
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
            {"id": "customfield_10001", "name": "Story Points", "custom": True, "schema": {"type": "number"}},
        ]

        args = argparse.Namespace(refresh=True, all=False, filter=None)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            fields_command(args)

        captured = capsys.readouterr()
        assert "Story Points" in captured.out

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


class TestComponentsCommand:
    """Tests for components_command function."""

    def test_displays_components(self, mock_jira, capsys, tmp_path):
        """Displays components for a project."""
        from zaira.info import components_command
        import argparse

        project_schema_file = tmp_path / "project_schema.json"
        project_schema = {"components": ["Backend", "Frontend", "API"]}
        project_schema_file.write_text(json.dumps(project_schema))

        args = argparse.Namespace(project="TEST")

        with patch("zaira.info.get_project_schema_path", return_value=project_schema_file):
            components_command(args)

        captured = capsys.readouterr()
        assert "Components for TEST:" in captured.out
        assert "Backend" in captured.out
        assert "Frontend" in captured.out

    def test_handles_no_components(self, mock_jira, capsys, tmp_path):
        """Handles project with no components."""
        from zaira.info import components_command
        import argparse

        project_schema_file = tmp_path / "project_schema.json"
        project_schema = {"components": []}
        project_schema_file.write_text(json.dumps(project_schema))

        args = argparse.Namespace(project="EMPTY")

        with patch("zaira.info.get_project_schema_path", return_value=project_schema_file):
            components_command(args)

        captured = capsys.readouterr()
        assert "No components found" in captured.out

    def test_exits_when_no_cached_components(self, mock_jira, capsys, tmp_path):
        """Exits when no cached components exist."""
        from zaira.info import components_command
        import argparse

        args = argparse.Namespace(project="NOCACHE")

        with (
            patch("zaira.info.get_project_schema_path", return_value=tmp_path / "nonexistent.json"),
            pytest.raises(SystemExit) as exc_info,
        ):
            components_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No cached components" in captured.err


class TestLabelsCommand:
    """Tests for labels_command function."""

    def test_displays_labels(self, mock_jira, capsys, tmp_path):
        """Displays labels for a project."""
        from zaira.info import labels_command
        import argparse

        project_schema_file = tmp_path / "project_schema.json"
        project_schema = {"labels": ["bug", "feature", "urgent"]}
        project_schema_file.write_text(json.dumps(project_schema))

        args = argparse.Namespace(project="TEST")

        with patch("zaira.info.get_project_schema_path", return_value=project_schema_file):
            labels_command(args)

        captured = capsys.readouterr()
        assert "Labels for TEST:" in captured.out
        assert "bug" in captured.out
        assert "urgent" in captured.out

    def test_handles_no_labels(self, mock_jira, capsys, tmp_path):
        """Handles project with no labels."""
        from zaira.info import labels_command
        import argparse

        project_schema_file = tmp_path / "project_schema.json"
        project_schema = {"labels": []}
        project_schema_file.write_text(json.dumps(project_schema))

        args = argparse.Namespace(project="EMPTY")

        with patch("zaira.info.get_project_schema_path", return_value=project_schema_file):
            labels_command(args)

        captured = capsys.readouterr()
        assert "No labels found" in captured.out

    def test_exits_when_no_cached_labels(self, mock_jira, capsys, tmp_path):
        """Exits when no cached labels exist."""
        from zaira.info import labels_command
        import argparse

        args = argparse.Namespace(project="NOCACHE")

        with (
            patch("zaira.info.get_project_schema_path", return_value=tmp_path / "nonexistent.json"),
            pytest.raises(SystemExit) as exc_info,
        ):
            labels_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No cached labels" in captured.err


class TestFetchAndSaveSchema:
    """Tests for fetch_and_save_schema function."""

    def test_fetches_and_saves_full_schema(self, mock_jira, capsys, tmp_path):
        """Fetches all schema data and saves to file."""
        from zaira.info import fetch_and_save_schema

        # Mock all Jira API calls
        mock_jira.fields.return_value = [
            {"id": "customfield_10001", "name": "Story Points", "schema": {"type": "number"}},
        ]

        mock_status = MagicMock()
        mock_status.name = "Open"
        mock_status.statusCategory.name = "To Do"
        mock_jira.statuses.return_value = [mock_status]

        mock_priority = MagicMock()
        mock_priority.name = "High"
        mock_jira.priorities.return_value = [mock_priority]

        mock_type = MagicMock()
        mock_type.name = "Bug"
        mock_type.subtask = False
        mock_jira.issue_types.return_value = [mock_type]

        mock_link = MagicMock()
        mock_link.name = "Blocks"
        mock_link.outward = "blocks"
        mock_link.inward = "is blocked by"
        mock_jira.issue_link_types.return_value = [mock_link]

        schema_file = tmp_path / "schema.json"

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            fetch_and_save_schema()

        assert schema_file.exists()
        saved = json.loads(schema_file.read_text())
        assert "fields" in saved
        assert "statuses" in saved
        assert "priorities" in saved
        assert "issueTypes" in saved
        assert "linkTypes" in saved

    def test_saves_project_schema(self, mock_jira, capsys, tmp_path):
        """Saves project-specific schema when provided."""
        from zaira.info import fetch_and_save_schema

        # Minimal mocks - just enough to not error
        mock_jira.fields.return_value = []
        mock_jira.statuses.return_value = []
        mock_jira.priorities.return_value = []
        mock_jira.issue_types.return_value = []
        mock_jira.issue_link_types.return_value = []

        schema_file = tmp_path / "schema.json"
        project_file = tmp_path / "project_TEST.json"

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.get_project_schema_path", return_value=project_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            fetch_and_save_schema(
                project="TEST",
                components=["Backend", "Frontend"],
                labels=["bug", "feature"],
            )

        assert project_file.exists()
        saved = json.loads(project_file.read_text())
        assert saved["components"] == ["Backend", "Frontend"]
        assert saved["labels"] == ["bug", "feature"]

    def test_handles_api_errors_gracefully(self, mock_jira, capsys, tmp_path):
        """Continues despite individual API errors."""
        from zaira.info import fetch_and_save_schema

        # Make all APIs fail
        mock_jira.fields.side_effect = Exception("Fields error")
        mock_jira.statuses.side_effect = Exception("Statuses error")
        mock_jira.priorities.side_effect = Exception("Priorities error")
        mock_jira.issue_types.side_effect = Exception("Types error")
        mock_jira.issue_link_types.side_effect = Exception("Links error")

        schema_file = tmp_path / "schema.json"

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            fetch_and_save_schema()

        # Should still save (empty) schema
        assert schema_file.exists()
        captured = capsys.readouterr()
        assert "Warning:" in captured.err  # Errors logged as warnings


class TestInfoCommand:
    """Tests for info_command function."""

    def test_runs_save_when_flag_set(self, mock_jira, capsys, tmp_path):
        """Runs fetch_and_save_schema when --save flag is set."""
        from zaira.info import info_command
        import argparse

        # Minimal mocks
        mock_jira.fields.return_value = []
        mock_jira.statuses.return_value = []
        mock_jira.priorities.return_value = []
        mock_jira.issue_types.return_value = []
        mock_jira.issue_link_types.return_value = []

        schema_file = tmp_path / "schema.json"

        args = argparse.Namespace(save=True)

        with (
            patch("zaira.info.get_schema_path", return_value=schema_file),
            patch("zaira.info.CACHE_DIR", tmp_path),
        ):
            info_command(args)

        assert schema_file.exists()

    def test_calls_info_func(self, mock_jira, capsys, tmp_path):
        """Calls info_func when present on args."""
        from zaira.info import info_command
        import argparse

        called = []

        def mock_func(args):
            called.append(True)

        args = argparse.Namespace(save=False, info_func=mock_func)

        info_command(args)

        assert called == [True]

    def test_shows_usage_when_no_subcommand(self, mock_jira, capsys):
        """Shows usage when no subcommand specified."""
        from zaira.info import info_command
        import argparse

        args = argparse.Namespace(save=False)
        # No info_func attribute

        with pytest.raises(SystemExit) as exc_info:
            info_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.out
        assert "zaira info <subcommand>" in captured.out
