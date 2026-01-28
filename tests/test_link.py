"""Tests for link module."""

from unittest.mock import MagicMock

import pytest

from zaira.link import get_link_types, create_link


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
