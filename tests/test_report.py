"""Tests for report module."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from zaira.report import (
    _group_tickets_by,
    humanize_age,
    generate_front_matter,
    generate_report,
    generate_table,
    generate_json_report,
    generate_csv_report,
    search_tickets,
    get_ticket_dates,
)


class TestGroupTicketsBy:
    """Tests for _group_tickets_by function."""

    def test_group_by_status(self):
        """Groups tickets by status field."""
        tickets = [
            {"key": "T-1", "status": "Open"},
            {"key": "T-2", "status": "Open"},
            {"key": "T-3", "status": "Done"},
        ]
        result = _group_tickets_by(tickets, "status")

        assert len(result["Open"]) == 2
        assert len(result["Done"]) == 1

    def test_group_by_labels_multi_value(self):
        """Groups tickets by labels (multi-value field)."""
        tickets = [
            {"key": "T-1", "labels": ["bug", "urgent"]},
            {"key": "T-2", "labels": ["bug"]},
            {"key": "T-3", "labels": []},
        ]
        result = _group_tickets_by(tickets, "labels")

        assert len(result["bug"]) == 2
        assert len(result["urgent"]) == 1
        assert len(result["(no label)"]) == 1

    def test_group_by_components_multi_value(self):
        """Groups tickets by components (multi-value field)."""
        tickets = [
            {"key": "T-1", "components": ["Backend", "API"]},
            {"key": "T-2", "components": ["Frontend"]},
            {"key": "T-3", "components": []},
        ]
        result = _group_tickets_by(tickets, "components")

        assert len(result["Backend"]) == 1
        assert len(result["API"]) == 1
        assert len(result["Frontend"]) == 1
        assert len(result["(no component)"]) == 1

    def test_group_by_parent(self):
        """Groups tickets by parent."""
        tickets = [
            {"key": "T-1", "parent": {"key": "EPIC-1", "summary": "Epic One"}},
            {"key": "T-2", "parent": {"key": "EPIC-1", "summary": "Epic One"}},
            {"key": "T-3", "parent": None},
        ]
        result = _group_tickets_by(tickets, "parent")

        assert len(result["EPIC-1: Epic One"]) == 2
        assert len(result["(no parent)"]) == 1

    def test_group_by_unknown_field(self):
        """Groups by unknown field uses 'Unknown' as default."""
        tickets = [
            {"key": "T-1"},
            {"key": "T-2", "customfield": "value"},
        ]
        result = _group_tickets_by(tickets, "customfield")

        assert "Unknown" in result or "value" in result


class TestHumanizeAge:
    """Tests for humanize_age function."""

    def test_empty_timestamp(self):
        """Returns '-' for empty timestamp."""
        assert humanize_age("") == "-"
        assert humanize_age(None) == "-"

    def test_invalid_timestamp(self):
        """Returns '-' for invalid timestamp."""
        assert humanize_age("not-a-date") == "-"

    def test_recent_seconds(self):
        """Returns 'now' for very recent timestamps."""
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        assert humanize_age(ts) == "now"

    def test_minutes_ago(self):
        """Returns minutes for timestamps < 1 hour."""
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(minutes=30)).isoformat()
        result = humanize_age(ts)
        assert result.endswith("m")
        assert int(result[:-1]) >= 29  # Allow some tolerance

    def test_hours_ago(self):
        """Returns hours for timestamps < 1 day."""
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=5)).isoformat()
        result = humanize_age(ts)
        assert result.endswith("h")

    def test_days_ago(self):
        """Returns days for timestamps < 1 week."""
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(days=3)).isoformat()
        result = humanize_age(ts)
        assert result.endswith("d")

    def test_weeks_ago(self):
        """Returns weeks for timestamps < 1 month."""
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(weeks=2)).isoformat()
        result = humanize_age(ts)
        assert result.endswith("w")

    def test_months_ago(self):
        """Returns months for timestamps < 1 year."""
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(days=60)).isoformat()
        result = humanize_age(ts)
        assert result.endswith("mo")

    def test_years_ago(self):
        """Returns years for old timestamps."""
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(days=400)).isoformat()
        result = humanize_age(ts)
        assert result.endswith("y")


class TestGenerateFrontMatter:
    """Tests for generate_front_matter function."""

    def test_basic_front_matter(self):
        """Generates basic front matter."""
        result = generate_front_matter("Test Report")

        assert "---" in result
        assert "title: Test Report" in result
        assert "generated:" in result
        assert "refresh:" in result

    def test_with_jql(self):
        """Includes JQL in front matter."""
        result = generate_front_matter("Report", jql="project = TEST")

        assert 'jql: "project = TEST"' in result

    def test_with_query_name(self):
        """Includes query name in front matter."""
        result = generate_front_matter("Report", query="backlog")

        assert "query: backlog" in result

    def test_with_board(self):
        """Includes board in front matter."""
        result = generate_front_matter("Report", board=123)

        assert "board: 123" in result

    def test_with_sprint(self):
        """Includes sprint in front matter."""
        result = generate_front_matter("Report", sprint=456)

        assert "sprint: 456" in result

    def test_with_group_by(self):
        """Includes group_by in front matter."""
        result = generate_front_matter("Report", group_by="status")

        assert "group_by: status" in result

    def test_with_label(self):
        """Includes label filter in front matter."""
        result = generate_front_matter("Report", label="urgent")

        assert "label: urgent" in result

    def test_refresh_command(self):
        """Generates correct refresh command."""
        result = generate_front_matter(
            "My Report", query="backlog", group_by="status"
        )

        assert 'refresh: zaira report --query backlog --group-by status --title "My Report"' in result


class TestGenerateTable:
    """Tests for generate_table function."""

    def test_empty_tickets(self):
        """Returns no tickets message for empty list."""
        result = generate_table([])
        assert "_No tickets_" in result

    def test_basic_table(self):
        """Generates basic markdown table."""
        tickets = [
            {
                "key": "TEST-1",
                "issuetype": "Bug",
                "status": "Open",
                "updated": "",
                "summary": "Test ticket",
            }
        ]
        result = generate_table(tickets)

        assert "| Key" in result
        assert "| TEST-1" in result
        assert "Bug" in result
        assert "Open" in result

    def test_excludes_grouped_column(self):
        """Excludes grouped column from table."""
        tickets = [
            {
                "key": "TEST-1",
                "issuetype": "Bug",
                "status": "Open",
                "updated": "",
                "summary": "Test",
            }
        ]
        result = generate_table(tickets, group_by="status")

        # Status column should be removed
        assert "| Status" not in result

    def test_includes_parent_column(self):
        """Includes parent column when tickets have parents."""
        tickets = [
            {
                "key": "TEST-1",
                "issuetype": "Task",
                "status": "Open",
                "updated": "",
                "summary": "Subtask",
                "parent": {"key": "EPIC-1", "summary": "Epic"},
            }
        ]
        result = generate_table(tickets)

        assert "Parent" in result
        assert "EPIC-1" in result

    def test_escapes_pipes_in_summary(self):
        """Escapes pipe characters in summary."""
        tickets = [
            {
                "key": "TEST-1",
                "issuetype": "Bug",
                "status": "Open",
                "updated": "",
                "summary": "Test | with | pipes",
            }
        ]
        result = generate_table(tickets)

        assert "\\|" in result

    def test_truncates_long_summaries(self):
        """Truncates summaries longer than 200 characters."""
        tickets = [
            {
                "key": "TEST-1",
                "issuetype": "Bug",
                "status": "Open",
                "updated": "",
                "summary": "A" * 250,
            }
        ]
        result = generate_table(tickets)

        assert "..." in result


class TestGenerateReport:
    """Tests for generate_report function."""

    def test_empty_report(self):
        """Generates report with no tickets message."""
        result = generate_report([], "Empty Report")

        assert "# Empty Report" in result
        assert "**Total:** 0 tickets" in result
        assert "_No tickets found._" in result

    def test_report_with_tickets(self):
        """Generates report with tickets."""
        tickets = [
            {
                "key": "T-1",
                "issuetype": "Bug",
                "status": "Open",
                "updated": "",
                "summary": "Bug one",
            }
        ]
        result = generate_report(tickets, "Bug Report")

        assert "# Bug Report" in result
        assert "**Total:** 1 tickets" in result
        assert "T-1" in result

    def test_report_with_grouping(self):
        """Generates grouped report."""
        tickets = [
            {"key": "T-1", "status": "Open", "issuetype": "Bug", "updated": "", "summary": "A"},
            {"key": "T-2", "status": "Done", "issuetype": "Bug", "updated": "", "summary": "B"},
        ]
        result = generate_report(tickets, "Grouped", group_by="status")

        assert "## Open (1)" in result
        assert "## Done (1)" in result


class TestGenerateJsonReport:
    """Tests for generate_json_report function."""

    def test_valid_json(self):
        """Generates valid JSON."""
        tickets = [{"key": "T-1", "summary": "Test"}]
        result = generate_json_report(tickets, "Test Report")

        data = json.loads(result)
        assert data["title"] == "Test Report"
        assert data["total"] == 1
        assert len(data["tickets"]) == 1

    def test_includes_metadata(self):
        """Includes query metadata."""
        tickets = []
        result = generate_json_report(
            tickets,
            "Report",
            jql="project = TEST",
            query="backlog",
            board=123,
            sprint=456,
            group_by="status",
            label="urgent",
        )

        data = json.loads(result)
        assert data["jql"] == "project = TEST"
        assert data["query"] == "backlog"
        assert data["board"] == 123
        assert data["sprint"] == 456
        assert data["group_by"] == "status"
        assert data["label"] == "urgent"


class TestGenerateCsvReport:
    """Tests for generate_csv_report function."""

    def test_empty_tickets(self):
        """Returns empty string for no tickets."""
        result = generate_csv_report([])
        assert result == ""

    def test_csv_header(self):
        """Generates CSV with header."""
        tickets = [
            {
                "key": "T-1",
                "summary": "Test",
                "issuetype": "Bug",
                "status": "Open",
                "priority": "High",
                "assignee": "user@example.com",
                "labels": ["bug"],
                "parent": None,
                "created": "2024-01-01",
                "updated": "2024-01-02",
            }
        ]
        result = generate_csv_report(tickets)

        lines = result.strip().split("\n")
        assert "key" in lines[0]
        assert "summary" in lines[0]
        assert "T-1" in lines[1]

    def test_labels_joined(self):
        """Joins labels with comma."""
        tickets = [
            {
                "key": "T-1",
                "summary": "Test",
                "issuetype": "Bug",
                "status": "Open",
                "priority": "High",
                "assignee": "user",
                "labels": ["bug", "urgent"],
                "parent": None,
                "created": "",
                "updated": "",
            }
        ]
        result = generate_csv_report(tickets)

        assert "bug,urgent" in result

    def test_parent_key_extracted(self):
        """Extracts parent key from dict."""
        tickets = [
            {
                "key": "T-1",
                "summary": "Test",
                "issuetype": "Task",
                "status": "Open",
                "priority": "Medium",
                "assignee": "user",
                "labels": [],
                "parent": {"key": "EPIC-1", "summary": "Epic"},
                "created": "",
                "updated": "",
            }
        ]
        result = generate_csv_report(tickets)

        assert "EPIC-1" in result


class TestSearchTickets:
    """Tests for search_tickets function with mocked Jira."""

    def test_search_returns_tickets(self, mock_jira):
        """Returns formatted ticket list."""
        # Create mock issue
        mock_issue = MagicMock()
        mock_issue.key = "TEST-1"
        mock_issue.fields.summary = "Test ticket"
        mock_issue.fields.issuetype.name = "Bug"
        mock_issue.fields.status.name = "Open"
        mock_issue.fields.status.statusCategory.name = "To Do"
        mock_issue.fields.priority.name = "High"
        mock_issue.fields.assignee = None
        mock_issue.fields.reporter = None
        mock_issue.fields.labels = ["bug"]
        mock_issue.fields.components = []
        mock_issue.fields.project.key = "TEST"
        mock_issue.fields.resolution = None
        mock_issue.fields.created = "2024-01-01"
        mock_issue.fields.updated = "2024-01-02"
        mock_issue.fields.parent = None

        mock_jira.search_issues.return_value = [mock_issue]

        result = search_tickets("project = TEST")

        assert len(result) == 1
        assert result[0]["key"] == "TEST-1"
        assert result[0]["summary"] == "Test ticket"
        assert result[0]["status"] == "Open"

    def test_search_handles_error(self, mock_jira, capsys):
        """Handles search errors gracefully."""
        mock_jira.search_issues.side_effect = Exception("API Error")

        result = search_tickets("invalid query")

        assert result == []
        captured = capsys.readouterr()
        assert "Error searching" in captured.out


class TestGetTicketDates:
    """Tests for get_ticket_dates function with mocked Jira."""

    def test_returns_dates(self, mock_jira):
        """Returns created and updated dates."""
        mock_issue = MagicMock()
        mock_issue.fields.created = "2024-01-01T10:00:00"
        mock_issue.fields.updated = "2024-01-02T15:00:00"
        mock_jira.issue.return_value = mock_issue

        result = get_ticket_dates("TEST-1")

        assert result["created"] == "2024-01-01T10:00:00"
        assert result["updated"] == "2024-01-02T15:00:00"

    def test_handles_error(self, mock_jira):
        """Returns empty strings on error."""
        mock_jira.issue.side_effect = Exception("Not found")

        result = get_ticket_dates("INVALID-1")

        assert result == {"created": "", "updated": ""}
