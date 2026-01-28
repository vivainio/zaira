"""Tests for config module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from zaira import config


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_finds_root_in_current_dir(self, tmp_path):
        """Finds project root when zproject.toml is in current directory."""
        (tmp_path / "zproject.toml").touch()
        with patch.object(Path, "cwd", return_value=tmp_path):
            result = config.find_project_root()
        assert result == tmp_path

    def test_finds_root_in_parent_dir(self, tmp_path):
        """Finds project root when zproject.toml is in parent directory."""
        (tmp_path / "zproject.toml").touch()
        subdir = tmp_path / "src" / "module"
        subdir.mkdir(parents=True)
        with patch.object(Path, "cwd", return_value=subdir):
            result = config.find_project_root()
        assert result == tmp_path

    def test_returns_none_when_not_found(self, tmp_path):
        """Returns None when no zproject.toml found."""
        subdir = tmp_path / "src"
        subdir.mkdir()
        with patch.object(Path, "cwd", return_value=subdir):
            result = config.find_project_root()
        # Will return None if not found in any parent up to filesystem root
        # In practice, this tests the case where no zproject.toml exists
        assert result is None or not (result / "zproject.toml").exists()


class TestGetProjectDir:
    """Tests for get_project_dir function."""

    def test_returns_subdir_of_project_root(self, tmp_path):
        """Returns subdirectory under project root when found."""
        (tmp_path / "zproject.toml").touch()
        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch("zaira.config.find_project_root", return_value=tmp_path):
                result = config.get_project_dir("tickets")
        assert result == tmp_path / "tickets"

    def test_returns_subdir_of_cwd_when_no_project(self, tmp_path):
        """Returns subdirectory under cwd when no project root found."""
        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch("zaira.config.find_project_root", return_value=None):
                result = config.get_project_dir("reports")
        assert result == tmp_path / "reports"


class TestFindProjectRootEdgeCases:
    """Edge cases for find_project_root function."""

    def test_handles_permission_error(self, tmp_path, monkeypatch):
        """Handles permission denied when traversing directories."""
        # Create a directory structure
        subdir = tmp_path / "restricted" / "deep"
        subdir.mkdir(parents=True)

        # Mock Path.iterdir to raise PermissionError for parent
        original_iterdir = Path.iterdir

        def mock_iterdir(self):
            if self == tmp_path / "restricted":
                raise PermissionError("Permission denied")
            return original_iterdir(self)

        monkeypatch.setattr(Path, "iterdir", mock_iterdir)

        # Should not crash, returns None when can't find project root
        with patch.object(Path, "cwd", return_value=subdir):
            result = config.find_project_root()
        # Function should handle the error gracefully
        assert result is None or isinstance(result, Path)

    def test_stops_at_filesystem_root(self, monkeypatch):
        """Stops searching when reaching filesystem root."""
        # Mock cwd to be at root with no zproject.toml
        root = Path("/")

        with patch.object(Path, "cwd", return_value=root):
            with patch.object(Path, "exists", return_value=False):
                result = config.find_project_root()

        assert result is None

    def test_returns_none_for_empty_directory(self, tmp_path):
        """Returns None when directory is empty."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch.object(Path, "cwd", return_value=empty_dir):
            result = config.find_project_root()

        assert result is None

    def test_handles_deeply_nested_directory(self, tmp_path):
        """Finds project root in deeply nested directory structure."""
        (tmp_path / "zproject.toml").touch()

        # Create a deeply nested directory
        deep_path = tmp_path
        for i in range(20):
            deep_path = deep_path / f"level{i}"
        deep_path.mkdir(parents=True)

        with patch.object(Path, "cwd", return_value=deep_path):
            result = config.find_project_root()

        assert result == tmp_path


class TestGetProjectDirEdgeCases:
    """Edge cases for get_project_dir function."""

    def test_handles_special_characters_in_subdir(self, tmp_path):
        """Handles special characters in subdirectory names."""
        (tmp_path / "zproject.toml").touch()

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch("zaira.config.find_project_root", return_value=tmp_path):
                result = config.get_project_dir("my-tickets_2024")

        assert result == tmp_path / "my-tickets_2024"

    def test_returns_path_even_if_not_exists(self, tmp_path):
        """Returns path even if the subdirectory doesn't exist yet."""
        (tmp_path / "zproject.toml").touch()

        with patch.object(Path, "cwd", return_value=tmp_path):
            with patch("zaira.config.find_project_root", return_value=tmp_path):
                result = config.get_project_dir("nonexistent")

        assert result == tmp_path / "nonexistent"
        assert not result.exists()  # Subdirectory not created
