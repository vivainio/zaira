"""Tests for my module."""

from unittest.mock import MagicMock

import pytest

from zaira.my import search_my_tickets, print_table


class TestSearchMyTickets:
    """Tests for search_my_tickets function with mocked Jira."""

    def test_returns_ticket_list(self, mock_jira):
        """Returns list of ticket dicts."""
        mock_issue = MagicMock()
        mock_issue.key = "TEST-1"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.created = "2024-01-15T10:00:00"
        mock_issue.fields.summary = "Test ticket"

        mock_jira.search_issues.return_value = [mock_issue]

        result = search_my_tickets("assignee = currentUser()")

        assert len(result) == 1
        assert result[0]["key"] == "TEST-1"
        assert result[0]["status"] == "Open"
        assert result[0]["summary"] == "Test ticket"

    def test_handles_missing_status(self, mock_jira):
        """Handles tickets with missing status."""
        mock_issue = MagicMock()
        mock_issue.key = "TEST-2"
        mock_issue.fields.status = None
        mock_issue.fields.created = ""
        mock_issue.fields.summary = "No status"

        mock_jira.search_issues.return_value = [mock_issue]

        result = search_my_tickets("some jql")

        assert result[0]["status"] == "?"


class TestPrintTable:
    """Tests for print_table function."""

    def test_empty_tickets(self, capsys):
        """Prints message when no tickets."""
        print_table([])

        captured = capsys.readouterr()
        assert "No open tickets" in captured.out

    def test_groups_by_status(self, capsys):
        """Groups tickets by status."""
        tickets = [
            {"key": "T-1", "status": "Open", "created": "2024-01-01", "summary": "First"},
            {"key": "T-2", "status": "Open", "created": "2024-01-02", "summary": "Second"},
            {"key": "T-3", "status": "In Progress", "created": "2024-01-03", "summary": "Third"},
        ]

        print_table(tickets)

        captured = capsys.readouterr()
        assert "Open (2)" in captured.out
        assert "In Progress (1)" in captured.out
        assert "T-1" in captured.out
        assert "T-2" in captured.out
        assert "T-3" in captured.out

    def test_truncates_long_summaries(self, capsys):
        """Truncates summaries over 100 characters."""
        tickets = [
            {
                "key": "T-1",
                "status": "Open",
                "created": "2024-01-01",
                "summary": "A" * 150,
            }
        ]

        print_table(tickets)

        captured = capsys.readouterr()
        assert "..." in captured.out
        # Should not contain full 150 A's
        assert "A" * 150 not in captured.out

    def test_sorts_by_created_date(self, capsys):
        """Sorts tickets by created date within groups."""
        tickets = [
            {"key": "T-3", "status": "Open", "created": "2024-01-03", "summary": "Newest"},
            {"key": "T-1", "status": "Open", "created": "2024-01-01", "summary": "Oldest"},
            {"key": "T-2", "status": "Open", "created": "2024-01-02", "summary": "Middle"},
        ]

        print_table(tickets)

        captured = capsys.readouterr()
        # Oldest should appear first
        oldest_pos = captured.out.find("T-1")
        newest_pos = captured.out.find("T-3")
        assert oldest_pos < newest_pos
