"""Tests for boards module."""

from unittest.mock import MagicMock

import pytest

from zaira.boards import (
    get_boards,
    get_sprints,
    get_board_info,
    get_board_issues_jql,
    get_sprint_issues_jql,
)
from zaira.types import Board, Sprint


class TestGetSprintIssuesJql:
    """Tests for get_sprint_issues_jql function (pure)."""

    def test_returns_sprint_jql(self):
        """Returns JQL for sprint ID."""
        result = get_sprint_issues_jql(123)
        assert result == "sprint = 123"

    def test_handles_different_ids(self):
        """Works with various sprint IDs."""
        assert get_sprint_issues_jql(1) == "sprint = 1"
        assert get_sprint_issues_jql(99999) == "sprint = 99999"


class TestGetBoards:
    """Tests for get_boards function with mocked Jira."""

    def test_returns_boards(self, mock_jira):
        """Returns list of Board objects."""
        mock_board = MagicMock()
        mock_board.id = 123
        mock_board.name = "Test Board"
        mock_board.type = "scrum"
        mock_board.location.displayName = "Test Project"

        mock_jira.boards.return_value = [mock_board]

        result = get_boards()

        assert len(result) == 1
        assert isinstance(result[0], Board)
        assert result[0].id == 123
        assert result[0].name == "Test Board"
        assert result[0].type == "scrum"

    def test_filters_by_project(self, mock_jira):
        """Filters boards by project."""
        mock_jira.boards.return_value = []

        get_boards(project="TEST")

        mock_jira.boards.assert_called_with(projectKeyOrID="TEST")

    def test_handles_error(self, mock_jira, capsys):
        """Returns empty list on error."""
        mock_jira.boards.side_effect = Exception("API Error")

        result = get_boards()

        assert result == []
        captured = capsys.readouterr()
        assert "Error fetching boards" in captured.out

    def test_handles_missing_location(self, mock_jira):
        """Handles boards without location."""
        mock_board = MagicMock()
        mock_board.id = 456
        mock_board.name = "Simple Board"
        mock_board.type = "kanban"
        del mock_board.location  # No location attribute

        mock_jira.boards.return_value = [mock_board]

        result = get_boards()

        assert len(result) == 1
        assert result[0].location == ""


class TestGetSprints:
    """Tests for get_sprints function with mocked Jira."""

    def test_returns_sprints(self, mock_jira):
        """Returns list of Sprint objects."""
        mock_sprint = MagicMock()
        mock_sprint.id = 789
        mock_sprint.name = "Sprint 1"
        mock_sprint.state = "active"

        mock_jira.sprints.return_value = [mock_sprint]

        result = get_sprints(board_id=123)

        assert len(result) == 1
        assert isinstance(result[0], Sprint)
        assert result[0].id == 789
        assert result[0].name == "Sprint 1"
        assert result[0].state == "active"

    def test_filters_by_state(self, mock_jira):
        """Filters sprints by state."""
        mock_jira.sprints.return_value = []

        get_sprints(board_id=123, state="active")

        mock_jira.sprints.assert_called_with(123, state="active")

    def test_handles_error(self, mock_jira, capsys):
        """Returns empty list on error."""
        mock_jira.sprints.side_effect = Exception("API Error")

        result = get_sprints(board_id=123)

        assert result == []
        captured = capsys.readouterr()
        assert "Error fetching sprints" in captured.out


class TestGetBoardInfo:
    """Tests for get_board_info function with mocked Jira."""

    def test_returns_board_details(self, mock_jira):
        """Returns board details dict."""
        mock_jira._get_json.return_value = {
            "id": 123,
            "name": "Test Board",
            "location": {"displayName": "Test Project (TEST)"},
        }

        result = get_board_info(123)

        assert result["id"] == 123
        assert result["name"] == "Test Board"

    def test_handles_error(self, mock_jira):
        """Returns None on error."""
        mock_jira._get_json.side_effect = Exception("Not found")

        result = get_board_info(999)

        assert result is None


class TestGetBoardIssuesJql:
    """Tests for get_board_issues_jql function with mocked Jira."""

    def test_extracts_project_from_location(self, mock_jira):
        """Extracts project key from board location."""
        mock_jira._get_json.return_value = {
            "location": {"displayName": "AP&P Common (AC)"},
        }

        result = get_board_issues_jql(123)

        assert result == "project = AC ORDER BY updated DESC"

    def test_returns_none_for_invalid_board(self, mock_jira):
        """Returns None for non-existent board."""
        mock_jira._get_json.side_effect = Exception("Not found")

        result = get_board_issues_jql(999)

        assert result is None

    def test_returns_none_for_no_project(self, mock_jira):
        """Returns None when location has no project key."""
        mock_jira._get_json.return_value = {
            "location": {"displayName": "Simple Name"},
        }

        result = get_board_issues_jql(123)

        assert result is None
