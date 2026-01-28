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


class TestGenerateDashboardReport:
    """Tests for generate_dashboard_report function."""

    def test_returns_empty_for_no_dashboard(self, mock_jira):
        """Returns empty when dashboard not found."""
        from zaira.report import generate_dashboard_report
        from unittest.mock import patch

        with patch("zaira.report.get_dashboard", return_value=None):
            result, total = generate_dashboard_report(12345)

        assert result == ""
        assert total == 0

    def test_handles_dashboard_with_no_jql_gadgets(self, mock_jira):
        """Handles dashboard with no JQL gadgets."""
        from zaira.report import generate_dashboard_report
        from unittest.mock import patch, MagicMock

        mock_dashboard = MagicMock()
        mock_dashboard.name = "Test Dashboard"

        with (
            patch("zaira.report.get_dashboard", return_value=mock_dashboard),
            patch("zaira.report.get_dashboard_gadgets", return_value=[]),
        ):
            result, total = generate_dashboard_report(123, to_stdout=True)

        assert "Test Dashboard" in result
        assert "No gadgets with JQL queries found" in result
        assert total == 0

    def test_generates_report_with_gadgets(self, mock_jira):
        """Generates full report from dashboard gadgets."""
        from zaira.report import generate_dashboard_report
        from unittest.mock import patch, MagicMock

        mock_dashboard = MagicMock()
        mock_dashboard.name = "My Dashboard"
        mock_dashboard.description = "A test dashboard"
        mock_dashboard.view_url = "https://jira.example.com/dashboard/123"

        mock_gadget = MagicMock()
        mock_gadget.id = 1
        mock_gadget.title = "Backlog"
        mock_gadget.filter_name = "My Backlog"
        mock_gadget.jql = "project = TEST"
        mock_gadget.position = 0

        tickets = [
            {
                "key": "TEST-1",
                "summary": "Test ticket",
                "issuetype": "Bug",
                "status": "Open",
                "updated": "2024-01-15T10:00:00+0000",
            }
        ]

        with (
            patch("zaira.report.get_dashboard", return_value=mock_dashboard),
            patch("zaira.report.get_dashboard_gadgets", return_value=[mock_gadget]),
            patch("zaira.report.search_tickets", return_value=tickets),
        ):
            result, total = generate_dashboard_report(123, to_stdout=True)

        assert "My Dashboard" in result
        assert "A test dashboard" in result
        assert "My Backlog" in result
        assert "TEST-1" in result
        assert total == 1

    def test_handles_grouping(self, mock_jira):
        """Generates grouped report from dashboard."""
        from zaira.report import generate_dashboard_report
        from unittest.mock import patch, MagicMock

        mock_dashboard = MagicMock()
        mock_dashboard.name = "Grouped Dashboard"
        mock_dashboard.description = None
        mock_dashboard.view_url = "https://jira.example.com/dashboard/456"

        mock_gadget = MagicMock()
        mock_gadget.id = 1
        mock_gadget.title = "Issues"
        mock_gadget.filter_name = None
        mock_gadget.jql = "project = TEST"
        mock_gadget.position = 0

        tickets = [
            {"key": "T-1", "status": "Open", "issuetype": "Bug", "updated": "", "summary": "A"},
            {"key": "T-2", "status": "Done", "issuetype": "Bug", "updated": "", "summary": "B"},
        ]

        with (
            patch("zaira.report.get_dashboard", return_value=mock_dashboard),
            patch("zaira.report.get_dashboard_gadgets", return_value=[mock_gadget]),
            patch("zaira.report.search_tickets", return_value=tickets),
        ):
            result, total = generate_dashboard_report(456, group_by="status", to_stdout=True)

        assert "### Open" in result
        assert "### Done" in result
        assert total == 2


class TestReportCommand:
    """Tests for report_command function."""

    def test_lists_reports_when_no_args(self, mock_jira, capsys):
        """Lists available reports when no arguments given."""
        from zaira.report import report_command
        from unittest.mock import patch, MagicMock
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard=None,
            output=None,
            group_by=None,
            title=None,
        )

        reports = {
            "backlog": {"query": "backlog", "group_by": "status"},
            "sprint": {"board": 123, "sprint": 456},
        }

        with (
            patch("zaira.project.list_reports", return_value=reports),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Available reports" in captured.out
        assert "backlog" in captured.out

    def test_exits_when_no_reports_defined(self, mock_jira, capsys):
        """Exits with message when no reports defined."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard=None,
            output=None,
            group_by=None,
            title=None,
        )

        with (
            patch("zaira.project.list_reports", return_value={}),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No reports defined" in captured.out

    def test_generates_report_with_jql(self, mock_jira, capsys, tmp_path):
        """Generates report from JQL query."""
        from zaira.report import report_command
        from unittest.mock import patch, MagicMock
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql="project = TEST",
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title="Test Report",
            format="md",
            files=False,
        )

        tickets = [
            {
                "key": "TEST-1",
                "summary": "Test",
                "issuetype": "Bug",
                "status": "Open",
                "updated": "",
                "parent": None,
            }
        ]

        with patch("zaira.report.search_tickets", return_value=tickets):
            report_command(args)

        captured = capsys.readouterr()
        assert "Test Report" in captured.out
        assert "TEST-1" in captured.out

    def test_exits_when_no_tickets_found(self, mock_jira, capsys):
        """Exits with message when no tickets found."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql="project = EMPTY",
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        with (
            patch("zaira.report.search_tickets", return_value=[]),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No tickets found" in captured.out

    def test_generates_json_format(self, mock_jira, capsys):
        """Generates JSON format report."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse
        import json

        args = argparse.Namespace(
            name=None,
            query=None,
            jql="project = TEST",
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title="JSON Report",
            format="json",
            files=False,
        )

        tickets = [{"key": "TEST-1", "summary": "Test", "updated": ""}]

        with patch("zaira.report.search_tickets", return_value=tickets):
            report_command(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["title"] == "JSON Report"
        assert len(data["tickets"]) == 1

    def test_generates_csv_format(self, mock_jira, capsys):
        """Generates CSV format report."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql="project = TEST",
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title="CSV Report",
            format="csv",
            files=False,
        )

        tickets = [
            {
                "key": "TEST-1",
                "summary": "Test",
                "issuetype": "Bug",
                "status": "Open",
                "priority": "High",
                "assignee": "user",
                "labels": ["bug"],
                "parent": None,
                "created": "2024-01-01",
                "updated": "2024-01-02",
            }
        ]

        with patch("zaira.report.search_tickets", return_value=tickets):
            report_command(args)

        captured = capsys.readouterr()
        assert "key" in captured.out
        assert "TEST-1" in captured.out

    def test_uses_named_query(self, mock_jira, capsys):
        """Uses named query from project config."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query="backlog",
            jql=None,
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        tickets = [{"key": "T-1", "summary": "A", "issuetype": "Bug", "status": "Open", "updated": "", "parent": None}]

        with (
            patch("zaira.project.get_query", return_value="project = BACKLOG"),
            patch("zaira.report.search_tickets", return_value=tickets),
        ):
            report_command(args)

        captured = capsys.readouterr()
        assert "Backlog" in captured.out  # Title derived from query name

    def test_exits_when_query_not_found(self, mock_jira, capsys):
        """Exits when named query not found."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query="nonexistent",
            jql=None,
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        with (
            patch("zaira.project.get_query", return_value=None),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 1

    def test_uses_board_jql(self, mock_jira, capsys):
        """Uses board ID to generate JQL."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board="123",
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        tickets = [{"key": "T-1", "summary": "A", "issuetype": "Task", "status": "Open", "updated": "", "parent": None}]

        with (
            patch("zaira.report.get_board_issues_jql", return_value="filter = 999"),
            patch("zaira.report.search_tickets", return_value=tickets),
        ):
            report_command(args)

        captured = capsys.readouterr()
        assert "T-1" in captured.out

    def test_uses_sprint_jql(self, mock_jira, capsys):
        """Uses sprint ID to generate JQL."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board=None,
            sprint=456,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        tickets = [{"key": "T-1", "summary": "A", "issuetype": "Story", "status": "Done", "updated": "", "parent": None}]

        with (
            patch("zaira.report.get_sprint_issues_jql", return_value="Sprint = 456"),
            patch("zaira.report.search_tickets", return_value=tickets),
        ):
            report_command(args)

        captured = capsys.readouterr()
        assert "T-1" in captured.out

    def test_adds_label_filter(self, mock_jira, capsys):
        """Adds label filter to JQL."""
        from zaira.report import report_command
        from unittest.mock import patch, call
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql="project = TEST",
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
            label="urgent",
        )

        tickets = [{"key": "T-1", "summary": "A", "issuetype": "Bug", "status": "Open", "updated": "", "parent": None}]

        with patch("zaira.report.search_tickets", return_value=tickets) as mock_search:
            report_command(args)
            # Verify label was added to JQL
            mock_search.assert_called_once()
            called_jql = mock_search.call_args[0][0]
            assert 'labels = "urgent"' in called_jql

    def test_saves_to_file(self, mock_jira, tmp_path):
        """Saves report to file."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        output_file = tmp_path / "report.md"
        args = argparse.Namespace(
            name=None,
            query=None,
            jql="project = TEST",
            board=None,
            sprint=None,
            dashboard=None,
            output=str(output_file),
            group_by=None,
            title="File Report",
            format="md",
            files=False,
        )

        tickets = [{"key": "T-1", "summary": "A", "issuetype": "Bug", "status": "Open", "updated": "", "parent": None}]

        with patch("zaira.report.search_tickets", return_value=tickets):
            report_command(args)

        assert output_file.exists()
        content = output_file.read_text()
        assert "File Report" in content
        assert "T-1" in content

    def test_exits_when_no_jql_source(self, mock_jira, capsys):
        """Exits when no JQL source provided."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        # Named report that has no JQL source in its definition
        args = argparse.Namespace(
            name="empty-report",
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        # Report exists but has no jql/query/board/sprint
        empty_report_def = {"title": "Empty Report"}

        with (
            patch("zaira.project.list_reports", return_value={"empty-report": empty_report_def}),
            patch("zaira.project.get_report", return_value=empty_report_def),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--query, --jql, --board, or --sprint is required" in captured.out

    def test_handles_dashboard_report(self, mock_jira, capsys):
        """Handles dashboard report generation."""
        from zaira.report import report_command
        from unittest.mock import patch, MagicMock
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard="789",
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        with (
            patch("zaira.project.list_reports", return_value={}),
            patch("zaira.report.generate_dashboard_report", return_value=("# Dashboard Report\n\nContent", 5)),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        # Dashboard report prints to stdout and exits with 0
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Dashboard Report" in captured.out

    def test_handles_dashboard_url(self, mock_jira, capsys):
        """Extracts dashboard ID from URL."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard="https://jira.example.com/jira/dashboards/12345",
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        with (
            patch("zaira.project.list_reports", return_value={}),
            patch("zaira.report.generate_dashboard_report", return_value=("Report", 1)) as mock_gen,
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)
            mock_gen.assert_called_once()
            # Verify dashboard ID was extracted
            assert mock_gen.call_args[0][0] == 12345

        assert exc_info.value.code == 0

    def test_exits_when_dashboard_not_found(self, mock_jira, capsys):
        """Exits when dashboard not found."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard="99999",
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        with (
            patch("zaira.report.generate_dashboard_report", return_value=("", 0)),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 1

    def test_uses_named_report(self, mock_jira, capsys):
        """Uses named report from project config."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name="my-report",
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        report_def = {"jql": "project = MYREPORT", "title": "My Report"}
        tickets = [{"key": "T-1", "summary": "A", "issuetype": "Task", "status": "Open", "updated": "", "parent": None}]

        with (
            patch("zaira.project.list_reports", return_value={"my-report": report_def}),
            patch("zaira.project.get_report", return_value=report_def),
            patch("zaira.report.search_tickets", return_value=tickets),
        ):
            report_command(args)

        captured = capsys.readouterr()
        assert "My Report" in captured.out

    def test_exits_when_named_report_not_found(self, mock_jira, capsys):
        """Exits when named report not found."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name="nonexistent",
            query=None,
            jql=None,
            board=None,
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        with (
            patch("zaira.project.list_reports", return_value={}),
            patch("zaira.project.get_report", return_value=None),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 1

    def test_uses_board_name_from_config(self, mock_jira, capsys):
        """Resolves board name from project config."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board="my-board",  # Name, not ID
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        tickets = [{"key": "T-1", "summary": "A", "issuetype": "Task", "status": "Open", "updated": "", "parent": None}]

        with (
            patch("zaira.project.list_reports", return_value={}),
            patch("zaira.project.get_board", return_value=123),
            patch("zaira.report.get_board_issues_jql", return_value="filter = 123"),
            patch("zaira.report.search_tickets", return_value=tickets),
        ):
            report_command(args)

        captured = capsys.readouterr()
        assert "T-1" in captured.out

    def test_exits_when_board_not_found(self, mock_jira, capsys):
        """Exits when board name not found in config."""
        from zaira.report import report_command
        from unittest.mock import patch
        import argparse

        args = argparse.Namespace(
            name=None,
            query=None,
            jql=None,
            board="unknown-board",
            sprint=None,
            dashboard=None,
            output="-",
            group_by=None,
            title=None,
            format="md",
            files=False,
        )

        with (
            patch("zaira.project.list_reports", return_value={}),
            patch("zaira.project.get_board", return_value=None),
            pytest.raises(SystemExit) as exc_info,
        ):
            report_command(args)

        assert exc_info.value.code == 1
