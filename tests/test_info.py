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
