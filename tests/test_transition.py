"""Tests for transition module."""

from unittest.mock import MagicMock

import pytest

from zaira.transition import get_transitions, transition_ticket


class TestGetTransitions:
    """Tests for get_transitions function with mocked Jira."""

    def test_returns_transitions(self, mock_jira):
        """Returns list of transitions."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "2", "name": "Done", "to": {"name": "Done"}},
        ]

        result = get_transitions("TEST-123")

        assert len(result) == 2
        assert result[0]["name"] == "Start Progress"
        mock_jira.transitions.assert_called_once_with("TEST-123")

    def test_returns_empty_on_error(self, mock_jira, capsys):
        """Returns empty list on error."""
        mock_jira.transitions.side_effect = Exception("Not found")

        result = get_transitions("INVALID-1")

        assert result == []
        captured = capsys.readouterr()
        assert "Error getting transitions" in captured.err


class TestTransitionTicket:
    """Tests for transition_ticket function with mocked Jira."""

    def test_transitions_by_name(self, mock_jira):
        """Transitions ticket by transition name."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "2", "name": "Done", "to": {"name": "Done"}},
        ]

        result = transition_ticket("TEST-123", "Start Progress")

        assert result is True
        mock_jira.transition_issue.assert_called_once_with("TEST-123", "1")

    def test_transitions_by_target_status(self, mock_jira):
        """Transitions ticket by target status name."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start Progress", "to": {"name": "In Progress"}},
        ]

        result = transition_ticket("TEST-123", "In Progress")

        assert result is True
        mock_jira.transition_issue.assert_called_once_with("TEST-123", "1")

    def test_case_insensitive_match(self, mock_jira):
        """Matches status case-insensitively."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Done", "to": {"name": "Done"}},
        ]

        result = transition_ticket("TEST-123", "done")

        assert result is True

    def test_returns_false_for_invalid_status(self, mock_jira, capsys):
        """Returns False and shows available transitions."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start", "to": {"name": "In Progress"}},
        ]

        result = transition_ticket("TEST-123", "Invalid Status")

        assert result is False
        captured = capsys.readouterr()
        assert "No transition to 'Invalid Status'" in captured.err
        assert "Available transitions:" in captured.err
        assert "Start → In Progress" in captured.err

    def test_returns_false_on_api_error(self, mock_jira, capsys):
        """Returns False on API error."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Done", "to": {"name": "Done"}},
        ]
        mock_jira.transition_issue.side_effect = Exception("Permission denied")

        result = transition_ticket("TEST-123", "Done")

        assert result is False
        captured = capsys.readouterr()
        assert "Error transitioning" in captured.err
