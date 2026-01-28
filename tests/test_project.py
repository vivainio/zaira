"""Tests for project configuration module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from zaira import project


class TestLoadConfig:
    """Tests for load_config function."""

    def test_loads_toml_file(self, tmp_path, monkeypatch):
        """Loads and parses zproject.toml correctly."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[queries]
backlog = "project = TEST AND status = Open"

[boards]
main = 123
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = project.load_config()
        assert result["queries"]["backlog"] == "project = TEST AND status = Open"
        assert result["boards"]["main"] == 123

    def test_returns_empty_dict_when_missing(self, tmp_path, monkeypatch):
        """Returns empty dict when zproject.toml doesn't exist."""
        monkeypatch.chdir(tmp_path)
        result = project.load_config()
        assert result == {}


class TestGetQuery:
    """Tests for get_query function."""

    def test_returns_query_when_exists(self, tmp_path, monkeypatch):
        """Returns query string when it exists."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[queries]
backlog = "project = TEST"
urgent = "priority = Critical"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        assert project.get_query("backlog") == "project = TEST"
        assert project.get_query("urgent") == "priority = Critical"

    def test_returns_none_when_not_found(self, tmp_path, monkeypatch):
        """Returns None when query doesn't exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "zproject.toml").write_bytes(b"[queries]")

        assert project.get_query("nonexistent") is None

    def test_returns_none_when_no_config(self, tmp_path, monkeypatch):
        """Returns None when no config file."""
        monkeypatch.chdir(tmp_path)
        assert project.get_query("any") is None


class TestGetBoard:
    """Tests for get_board function."""

    def test_returns_board_id_when_exists(self, tmp_path, monkeypatch):
        """Returns board ID when it exists."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[boards]
main = 123
scrum = 456
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        assert project.get_board("main") == 123
        assert project.get_board("scrum") == 456

    def test_returns_none_for_non_int_value(self, tmp_path, monkeypatch):
        """Returns None when board value isn't an integer."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[boards]
invalid = "not-a-number"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        assert project.get_board("invalid") is None

    def test_returns_none_when_not_found(self, tmp_path, monkeypatch):
        """Returns None when board doesn't exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "zproject.toml").write_bytes(b"[boards]")

        assert project.get_board("nonexistent") is None


class TestListQueries:
    """Tests for list_queries function."""

    def test_returns_all_queries(self, tmp_path, monkeypatch):
        """Returns all queries from config."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[queries]
backlog = "status = Open"
done = "status = Done"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = project.list_queries()
        assert result == {"backlog": "status = Open", "done": "status = Done"}

    def test_returns_empty_dict_when_no_queries(self, tmp_path, monkeypatch):
        """Returns empty dict when no queries section."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "zproject.toml").write_bytes(b"[boards]")

        assert project.list_queries() == {}


class TestListBoards:
    """Tests for list_boards function."""

    def test_returns_all_boards(self, tmp_path, monkeypatch):
        """Returns all integer board values."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[boards]
main = 100
sprint = 200
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = project.list_boards()
        assert result == {"main": 100, "sprint": 200}

    def test_filters_non_int_values(self, tmp_path, monkeypatch):
        """Filters out non-integer board values."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[boards]
valid = 123
invalid = "string"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = project.list_boards()
        assert result == {"valid": 123}


class TestGetReport:
    """Tests for get_report function."""

    def test_returns_report_when_exists(self, tmp_path, monkeypatch):
        """Returns report definition when it exists."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[reports.weekly]
jql = "updated >= -7d"
group_by = "status"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = project.get_report("weekly")
        assert result == {"jql": "updated >= -7d", "group_by": "status"}

    def test_returns_none_when_not_found(self, tmp_path, monkeypatch):
        """Returns None when report doesn't exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "zproject.toml").write_bytes(b"[reports]")

        assert project.get_report("nonexistent") is None


class TestListReports:
    """Tests for list_reports function."""

    def test_returns_all_reports(self, tmp_path, monkeypatch):
        """Returns all report definitions."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[reports.weekly]
jql = "updated >= -7d"

[reports.monthly]
jql = "updated >= -30d"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = project.list_reports()
        assert "weekly" in result
        assert "monthly" in result
        assert result["weekly"]["jql"] == "updated >= -7d"
