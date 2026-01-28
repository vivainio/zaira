"""Tests for link module."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from zaira.link import get_link_types, create_link, link_command


class TestGetLinkTypes:
    """Tests for get_link_types function with mocked Jira."""

    def test_returns_link_type_names(self, mock_jira):
        """Returns list of link type names."""
        mock_lt1 = MagicMock()
        mock_lt1.name = "Blocks"
        mock_lt2 = MagicMock()
        mock_lt2.name = "Relates"

        mock_jira.issue_link_types.return_value = [mock_lt1, mock_lt2]

        result = get_link_types()

        assert result == ["Blocks", "Relates"]


class TestCreateLink:
    """Tests for create_link function with mocked Jira."""

    def test_creates_link_successfully(self, mock_jira):
        """Returns True when link is created."""
        result = create_link("TEST-1", "TEST-2", "Blocks")

        assert result is True
        mock_jira.create_issue_link.assert_called_once_with("Blocks", "TEST-1", "TEST-2")

    def test_returns_false_on_error(self, mock_jira, capsys):
        """Returns False on general error."""
        mock_jira.create_issue_link.side_effect = Exception("API Error")

        result = create_link("TEST-1", "TEST-2", "Blocks")

        assert result is False
        captured = capsys.readouterr()
        assert "Error creating link" in captured.err

    def test_shows_valid_link_types_on_invalid_type(self, mock_jira, capsys):
        """Shows valid link types when type is invalid."""
        mock_jira.create_issue_link.side_effect = Exception(
            "No issue link type with name 'Invalid'"
        )
        mock_lt = MagicMock()
        mock_lt.name = "Blocks"
        mock_jira.issue_link_types.return_value = [mock_lt]

        result = create_link("TEST-1", "TEST-2", "Invalid")

        assert result is False
        captured = capsys.readouterr()
        assert "Unknown link type" in captured.err
        assert "Valid link types:" in captured.err
        assert "Blocks" in captured.err


class TestLinkCommand:
    """Tests for link_command function."""

    def test_creates_link_successfully(self, mock_jira, capsys):
        """Creates link and shows success message."""
        args = argparse.Namespace(
            from_key="test-1",
            to_key="test-2",
            type="Blocks",
        )

        with patch("zaira.link.get_jira_site", return_value="jira.example.com"):
            link_command(args)

        captured = capsys.readouterr()
        assert "Linking TEST-1 --[Blocks]--> TEST-2" in captured.out
        assert "Link created: TEST-1 Blocks TEST-2" in captured.out
        assert "jira.example.com" in captured.out

    def test_exits_on_failure(self, mock_jira, capsys):
        """Exits with error when link creation fails."""
        mock_jira.create_issue_link.side_effect = Exception("API Error")

        args = argparse.Namespace(
            from_key="test-1",
            to_key="test-2",
            type="Blocks",
        )

        with patch("zaira.link.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                link_command(args)

        assert exc_info.value.code == 1

    def test_uppercases_ticket_keys(self, mock_jira, capsys):
        """Converts ticket keys to uppercase."""
        args = argparse.Namespace(
            from_key="test-1",
            to_key="proj-2",
            type="Relates",
        )

        with patch("zaira.link.get_jira_site", return_value="jira.example.com"):
            link_command(args)

        mock_jira.create_issue_link.assert_called_once_with("Relates", "TEST-1", "PROJ-2")
