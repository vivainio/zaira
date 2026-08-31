"""Tests for transition module."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from zaira.transition import get_transitions, transition_ticket, transition_command


class TestGetTransitions:
    """Tests for get_transitions function with mocked Jira."""

    def test_returns_transitions(self, mock_jira) -> None:
        """Returns list of transitions."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "2", "name": "Done", "to": {"name": "Done"}},
        ]

        result = get_transitions("TEST-123")

        assert len(result) == 2
        assert result[0]["name"] == "Start Progress"
        mock_jira.transitions.assert_called_once_with("TEST-123")

    def test_returns_empty_on_error(self, mock_jira, capsys) -> None:
        """Returns empty list on error."""
        mock_jira.transitions.side_effect = Exception("Not found")

        result = get_transitions("INVALID-1")

        assert result == []
        captured = capsys.readouterr()
        assert "Error getting transitions" in captured.err


class TestTransitionTicket:
    """Tests for transition_ticket function with mocked Jira."""

    def test_transitions_by_name(self, mock_jira) -> None:
        """Transitions ticket by transition name."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "2", "name": "Done", "to": {"name": "Done"}},
        ]

        result = transition_ticket("TEST-123", "Start Progress")

        assert result is True
        mock_jira.transition_issue.assert_called_once_with(
            "TEST-123", "1", fields={}, comment=None
        )

    def test_transitions_by_target_status(self, mock_jira) -> None:
        """Transitions ticket by target status name."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start Progress", "to": {"name": "In Progress"}},
        ]

        result = transition_ticket("TEST-123", "In Progress")

        assert result is True
        mock_jira.transition_issue.assert_called_once_with(
            "TEST-123", "1", fields={}, comment=None
        )

    def test_case_insensitive_match(self, mock_jira) -> None:
        """Matches status case-insensitively."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Done", "to": {"name": "Done"}},
        ]

        result = transition_ticket("TEST-123", "done")

        assert result is True

    def test_returns_false_for_invalid_status(self, mock_jira, capsys) -> None:
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

    def test_passes_fields_to_api(self, mock_jira) -> None:
        """Passes fields dict to transition_issue."""
        mock_jira.transitions.return_value = [
            {"id": "2", "name": "Done", "to": {"name": "Done"}},
        ]
        fields = {"resolution": {"name": "Done"}}

        result = transition_ticket("TEST-123", "Done", fields=fields)

        assert result is True
        mock_jira.transition_issue.assert_called_once_with(
            "TEST-123", "2", fields={"resolution": {"name": "Done"}}, comment=None
        )

    def test_returns_false_on_api_error(self, mock_jira, capsys) -> None:
        """Returns False on API error."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Done", "to": {"name": "Done"}},
        ]
        mock_jira.transition_issue.side_effect = Exception("Permission denied")

        result = transition_ticket("TEST-123", "Done")

        assert result is False
        captured = capsys.readouterr()
        assert "Error transitioning" in captured.err


class TestTransitionCommand:
    """Tests for transition_command function."""

    def test_lists_transitions(self, mock_jira, capsys) -> None:
        """Lists available transitions with --list flag."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "2", "name": "Resolve", "to": {"name": "Done"}},
        ]

        args = argparse.Namespace(key="test-123", list=True, status=None, field=None)

        with patch("zaira.transition.get_jira_site", return_value="jira.example.com"):
            transition_command(args)

        captured = capsys.readouterr()
        assert "Available transitions for TEST-123" in captured.out
        assert "Start Progress → In Progress" in captured.out
        assert "Resolve → Done" in captured.out

    def test_exits_when_no_status_and_no_list(self, capsys) -> None:
        """Exits with error when neither status nor --list provided."""
        args = argparse.Namespace(key="test-123", list=False, status=None, field=None)

        with patch("zaira.transition.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                transition_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Specify a status or use --list" in captured.err

    def test_transitions_successfully(self, mock_jira, capsys) -> None:
        """Transitions ticket and shows success message."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Done", "to": {"name": "Done"}},
        ]

        args = argparse.Namespace(key="test-123", list=False, status="Done", field=None)

        with patch("zaira.transition.get_jira_site", return_value="jira.example.com"):
            transition_command(args)

        captured = capsys.readouterr()
        assert "Transitioned TEST-123" in captured.out
        assert "jira.example.com" in captured.out

    def test_exits_on_transition_failure(self, mock_jira, capsys) -> None:
        """Exits with error when transition fails."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start", "to": {"name": "In Progress"}},
        ]

        args = argparse.Namespace(
            key="test-123", list=False, status="Invalid", field=None
        )

        with patch("zaira.transition.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                transition_command(args)

        assert exc_info.value.code == 1

    def test_transitions_with_fields(self, mock_jira, capsys) -> None:
        """Passes --field args to transition."""
        mock_jira.transitions.return_value = [
            {"id": "2", "name": "Done", "to": {"name": "Done"}},
        ]
        mock_issue = MagicMock()
        mock_issue.fields.issuetype.name = "Story"
        mock_jira.issue.return_value = mock_issue

        args = argparse.Namespace(
            key="test-123",
            list=False,
            status="Done",
            field=["Resolution=Done"],
        )

        with (
            patch("zaira.transition.get_jira_site", return_value="jira.example.com"),
            patch("zaira.info.ensure_editmeta", return_value=None),
            patch("zaira.rules.try_load_rules", return_value=None),
        ):
            transition_command(args)

        captured = capsys.readouterr()
        assert "Transitioned TEST-123" in captured.out
        # Verify fields were passed (resolution is a system type → {"name": ...})
        call_args = mock_jira.transition_issue.call_args
        assert call_args[1]["fields"]["resolution"] == {"name": "Done"}

    def test_dry_run_shows_screen_fields(self, mock_jira, capsys) -> None:
        """--dry-run prints the screen fields for the matching transition."""
        mock_jira.transitions.return_value = [
            {
                "id": "1",
                "name": "Start Implementation",
                "to": {"name": "Implementing"},
                "fields": {
                    "resolution": {
                        "name": "Resolution",
                        "required": True,
                        "schema": {"type": "resolution"},
                        "allowedValues": [{"name": "Done"}, {"name": "Won't Fix"}],
                    }
                },
            },
            {"id": "2", "name": "Done", "to": {"name": "Done"}, "fields": {}},
        ]

        args = argparse.Namespace(
            key="test-123",
            list=False,
            status="Start Implementation",
            field=None,
            dry_run=True,
        )

        with (
            patch("zaira.transition.get_jira_site", return_value="jira.example.com"),
            patch("zaira.rules.try_load_rules", return_value=None),
        ):
            transition_command(args)

        mock_jira.transitions.assert_called_with(
            "TEST-123", expand="transitions.fields"
        )
        captured = capsys.readouterr()
        assert "Would transition TEST-123 to 'Start Implementation'" in captured.out
        assert "Fields on this transition screen:" in captured.out
        assert "Resolution" in captured.out
        assert "id:       resolution" in captured.out
        assert "required: True" in captured.out
        assert "values:   Done, Won't Fix" in captured.out
        # Ticket was not actually transitioned.
        mock_jira.transition_issue.assert_not_called()

    def test_dry_run_no_fields_on_screen(self, mock_jira, capsys) -> None:
        """--dry-run notes when the transition screen has no fields."""
        mock_jira.transitions.return_value = [
            {"id": "2", "name": "Done", "to": {"name": "Done"}, "fields": {}},
        ]

        args = argparse.Namespace(
            key="test-123", list=False, status="Done", field=None, dry_run=True
        )

        with (
            patch("zaira.transition.get_jira_site", return_value="jira.example.com"),
            patch("zaira.rules.try_load_rules", return_value=None),
        ):
            transition_command(args)

        captured = capsys.readouterr()
        assert "(no fields on this transition screen)" in captured.out

    def test_dry_run_invalid_status_exits(self, mock_jira, capsys) -> None:
        """--dry-run exits with an error for an unknown status."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Start", "to": {"name": "In Progress"}, "fields": {}},
        ]

        args = argparse.Namespace(
            key="test-123",
            list=False,
            status="Nonexistent",
            field=None,
            dry_run=True,
        )

        with (
            patch("zaira.transition.get_jira_site", return_value="jira.example.com"),
            patch("zaira.rules.try_load_rules", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc_info:
                transition_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No transition to 'Nonexistent'" in captured.err

    def test_uppercases_ticket_key(self, mock_jira, capsys) -> None:
        """Converts ticket key to uppercase."""
        mock_jira.transitions.return_value = [
            {"id": "1", "name": "Done", "to": {"name": "Done"}},
        ]

        args = argparse.Namespace(key="test-123", list=False, status="Done", field=None)

        with patch("zaira.transition.get_jira_site", return_value="jira.example.com"):
            transition_command(args)

        # get_transitions should be called with uppercased key
        mock_jira.transitions.assert_called_with("TEST-123")
