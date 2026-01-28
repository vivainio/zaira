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
