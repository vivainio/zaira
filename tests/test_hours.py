"""Tests for hours module."""

import argparse
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from zaira.hours import (
    _days_range,
    query_hours,
    query_ticket_hours,
    format_hours,
    format_ticket_hours,
    format_ticket_hours_csv,
    hours_command,
)


def _mock_issue(key, summary):
    """Create a mock issue."""
    issue = MagicMock()
    issue.key = key
    issue.fields.summary = summary
    return issue


def _mock_worklog(author_email, time_seconds, started, comment=None):
    """Create a mock worklog entry."""
    wl = MagicMock()
    wl.author = MagicMock()
    wl.author.emailAddress = author_email
    wl.timeSpentSeconds = time_seconds
    wl.started = started
    wl.comment = comment
    return wl


class TestDaysRange:
    """Tests for _days_range function."""

    def test_single_day(self):
        """1 day returns today-today."""
        start, end = _days_range(1)
        assert start == end

    def test_seven_days(self):
        """7 days spans 6 days back from today."""
        start, end = _days_range(7)
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        assert (end_dt - start_dt).days == 6

    def test_end_is_today(self):
        """End date is always today."""
        _, end = _days_range(14)
        assert end == datetime.now().strftime("%Y-%m-%d")


class TestQueryHours:
    """Tests for query_hours function."""

    def test_returns_empty_when_no_issues(self, mock_jira):
        """Returns empty dicts when no issues found."""
        mock_jira.search_issues.return_value = []

        daily, totals = query_hours("2026-02-02", "2026-02-06")

        assert daily == {}
        assert totals == {}

    def test_aggregates_worklogs(self, mock_jira):
        """Aggregates worklogs by day and ticket."""
        mock_jira.search_issues.return_value = [
            _mock_issue("FOO-1", "Feature one"),
        ]
        mock_jira.myself.return_value = {"emailAddress": "me@test.com"}
        mock_jira.worklogs.return_value = [
            _mock_worklog("me@test.com", 7200, "2026-02-03T09:00:00", "Morning"),
            _mock_worklog("me@test.com", 3600, "2026-02-03T14:00:00"),
            _mock_worklog("me@test.com", 7200, "2026-02-04T09:00:00"),
        ]

        daily, totals = query_hours("2026-02-02", "2026-02-06")

        assert "2026-02-03" in daily
        assert len(daily["2026-02-03"]) == 2
        assert "2026-02-04" in daily
        assert totals["FOO-1"] == pytest.approx(5.0)

    def test_filters_by_date_range(self, mock_jira):
        """Excludes worklogs outside the date range."""
        mock_jira.search_issues.return_value = [
            _mock_issue("FOO-1", "Feature one"),
        ]
        mock_jira.myself.return_value = {"emailAddress": "me@test.com"}
        mock_jira.worklogs.return_value = [
            _mock_worklog("me@test.com", 3600, "2026-02-01T09:00:00"),  # before range
            _mock_worklog("me@test.com", 3600, "2026-02-03T09:00:00"),  # in range
            _mock_worklog("me@test.com", 3600, "2026-02-07T09:00:00"),  # after range
        ]

        daily, totals = query_hours("2026-02-02", "2026-02-06")

        assert len(daily) == 1
        assert "2026-02-03" in daily
        assert totals["FOO-1"] == pytest.approx(1.0)

    def test_filters_by_author(self, mock_jira):
        """Excludes worklogs by other users."""
        mock_jira.search_issues.return_value = [
            _mock_issue("FOO-1", "Feature one"),
        ]
        mock_jira.myself.return_value = {"emailAddress": "me@test.com"}
        mock_jira.worklogs.return_value = [
            _mock_worklog("me@test.com", 3600, "2026-02-03T09:00:00"),
            _mock_worklog("other@test.com", 7200, "2026-02-03T10:00:00"),
        ]

        daily, totals = query_hours("2026-02-02", "2026-02-06")

        assert totals["FOO-1"] == pytest.approx(1.0)

    def test_multiple_tickets(self, mock_jira):
        """Handles worklogs across multiple tickets."""
        mock_jira.search_issues.return_value = [
            _mock_issue("FOO-1", "Feature one"),
            _mock_issue("FOO-2", "Feature two"),
        ]
        mock_jira.myself.return_value = {"emailAddress": "me@test.com"}
        mock_jira.worklogs.side_effect = [
            [_mock_worklog("me@test.com", 3600, "2026-02-03T09:00:00")],
            [_mock_worklog("me@test.com", 7200, "2026-02-03T14:00:00")],
        ]

        daily, totals = query_hours("2026-02-02", "2026-02-06")

        assert totals["FOO-1"] == pytest.approx(1.0)
        assert totals["FOO-2"] == pytest.approx(2.0)
        assert len(daily["2026-02-03"]) == 2


class TestFormatHours:
    """Tests for format_hours function."""

    def test_no_data(self):
        """Shows message when no worklogs found."""
        result = format_hours({}, {}, "2026-02-02", "2026-02-06")
        assert "No worklogs found" in result

    def test_daily_breakdown(self):
        """Shows daily breakdown with totals."""
        daily = {
            "2026-02-03": [("FOO-1", "Feature", 2.0, "Morning"), ("FOO-2", "Bug", 1.0, None)],
            "2026-02-04": [("FOO-1", "Feature", 3.0, None)],
        }
        totals = {"FOO-1": 5.0, "FOO-2": 1.0}

        result = format_hours(daily, totals, "2026-02-02", "2026-02-06")

        assert "2026-02-03 (Tue)" in result
        assert "[3.0h]" in result
        assert "2026-02-04 (Wed)" in result
        assert "Total: 6.0h" in result
        assert "FOO-1" in result
        assert "(Morning)" in result

    def test_summary_only(self):
        """Shows only totals when summary_only=True."""
        daily = {
            "2026-02-03": [("FOO-1", "Feature", 2.0, None)],
        }
        totals = {"FOO-1": 2.0}

        result = format_hours(daily, totals, "2026-02-02", "2026-02-06", summary_only=True)

        assert "2026-02-03" not in result  # No daily breakdown
        assert "Total: 2.0h" in result
        assert "FOO-1" in result


class TestHoursCommand:
    """Tests for hours_command function."""

    def test_default_is_last_7_days(self, mock_jira):
        """Defaults to last 7 days when no args."""
        mock_jira.search_issues.return_value = []

        args = argparse.Namespace(
            tickets=[], date_from=None, date_to=None, days=None, summary=False
        )

        hours_command(args)

        jql = mock_jira.search_issues.call_args[0][0]
        assert "worklogAuthor = currentUser()" in jql

    def test_days_flag(self, mock_jira):
        """Uses --days to look back N days."""
        mock_jira.search_issues.return_value = []

        args = argparse.Namespace(
            tickets=[], date_from=None, date_to=None, days=14, summary=False
        )

        hours_command(args)

        mock_jira.search_issues.assert_called_once()

    def test_custom_date_range(self, mock_jira):
        """Uses custom date range with --from/--to."""
        mock_jira.search_issues.return_value = []

        args = argparse.Namespace(
            tickets=[], date_from="2026-01-20", date_to="2026-01-24", days=None,
            summary=False
        )

        hours_command(args)

        jql = mock_jira.search_issues.call_args[0][0]
        assert "2026-01-20" in jql
        assert "2026-01-24" in jql

    def test_exits_when_only_from(self, capsys):
        """Exits with error when only --from is provided."""
        args = argparse.Namespace(
            tickets=[], date_from="2026-01-20", date_to=None, days=None,
            summary=False
        )

        with pytest.raises(SystemExit) as exc_info:
            hours_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--from and --to must be used together" in captured.err

    def test_exits_on_invalid_date(self, capsys):
        """Exits with error on invalid date format."""
        args = argparse.Namespace(
            tickets=[], date_from="01/20/2026", date_to="01/24/2026", days=None,
            summary=False
        )

        with pytest.raises(SystemExit) as exc_info:
            hours_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid date" in captured.err

    def test_ticket_mode(self, mock_jira, capsys):
        """Shows hours by person when tickets are provided."""
        mock_jira.issue.return_value = _mock_issue("FOO-1", "Feature one")
        mock_jira.worklogs.return_value = [
            _mock_worklog("alice@test.com", 7200, "2026-02-03T09:00:00"),
            _mock_worklog("bob@test.com", 3600, "2026-02-03T14:00:00"),
        ]

        args = argparse.Namespace(
            tickets=["FOO-1"], date_from=None, date_to=None, days=None,
            summary=False
        )

        hours_command(args)

        captured = capsys.readouterr()
        assert "FOO-1" in captured.out
        assert "alice@test.com" in captured.out
        assert "bob@test.com" in captured.out


class TestQueryTicketHours:
    """Tests for query_ticket_hours function."""

    def test_aggregates_by_author(self, mock_jira):
        """Groups hours by author per ticket."""
        mock_jira.worklogs.return_value = [
            _mock_worklog("alice@test.com", 7200, "2026-02-03T09:00:00"),
            _mock_worklog("alice@test.com", 3600, "2026-02-04T09:00:00"),
            _mock_worklog("bob@test.com", 1800, "2026-02-03T14:00:00"),
        ]

        result = query_ticket_hours(["FOO-1"])

        assert result["FOO-1"]["alice@test.com"] == pytest.approx(3.0)
        assert result["FOO-1"]["bob@test.com"] == pytest.approx(0.5)

    def test_filters_by_date(self, mock_jira):
        """Respects date filters."""
        mock_jira.worklogs.return_value = [
            _mock_worklog("alice@test.com", 3600, "2026-02-01T09:00:00"),
            _mock_worklog("alice@test.com", 3600, "2026-02-03T09:00:00"),
            _mock_worklog("alice@test.com", 3600, "2026-02-07T09:00:00"),
        ]

        result = query_ticket_hours(["FOO-1"], date_from="2026-02-02", date_to="2026-02-06")

        assert result["FOO-1"]["alice@test.com"] == pytest.approx(1.0)

    def test_multiple_tickets(self, mock_jira):
        """Handles multiple tickets."""
        mock_jira.worklogs.side_effect = [
            [_mock_worklog("alice@test.com", 3600, "2026-02-03T09:00:00")],
            [_mock_worklog("bob@test.com", 7200, "2026-02-03T09:00:00")],
        ]

        result = query_ticket_hours(["FOO-1", "FOO-2"])

        assert result["FOO-1"]["alice@test.com"] == pytest.approx(1.0)
        assert result["FOO-2"]["bob@test.com"] == pytest.approx(2.0)

    def test_skips_empty_tickets(self, mock_jira):
        """Omits tickets with no worklogs."""
        mock_jira.worklogs.return_value = []

        result = query_ticket_hours(["FOO-1"])

        assert result == {}

    def test_handles_api_error(self, mock_jira, capsys):
        """Continues on API error for a ticket."""
        mock_jira.worklogs.side_effect = Exception("Not found")

        result = query_ticket_hours(["FOO-1"])

        assert result == {}
        captured = capsys.readouterr()
        assert "Error getting worklogs" in captured.err


class TestFormatTicketHours:
    """Tests for format_ticket_hours function."""

    def test_no_data(self):
        """Shows message when no worklogs found."""
        result = format_ticket_hours({}, {})
        assert "No worklogs found" in result

    def test_shows_per_ticket_breakdown(self):
        """Shows authors and subtotals per ticket."""
        ticket_hours = {
            "FOO-1": {"alice@test.com": 5.0, "bob@test.com": 2.0},
            "FOO-2": {"alice@test.com": 1.0},
        }
        summaries = {"FOO-1": "Feature one", "FOO-2": "Bug fix"}

        result = format_ticket_hours(ticket_hours, summaries)

        assert "FOO-1: Feature one" in result
        assert "alice@test.com" in result
        assert "bob@test.com" in result
        assert "Subtotal:" in result
        assert "7.0h" in result  # FOO-1 subtotal
        assert "Total: 8.0h across 2 ticket(s)" in result


class TestFormatTicketHoursCsv:
    """Tests for format_ticket_hours_csv function."""

    def test_csv_header(self):
        """CSV output has header row."""
        result = format_ticket_hours_csv({}, {})
        assert result == "ticket,summary,author,hours"

    def test_csv_rows(self):
        """CSV output has correct rows."""
        ticket_hours = {
            "FOO-1": {"alice@test.com": 5.0, "bob@test.com": 2.0},
        }
        summaries = {"FOO-1": "Feature one"}

        result = format_ticket_hours_csv(ticket_hours, summaries)
        lines = result.split("\n")

        assert lines[0] == "ticket,summary,author,hours"
        assert lines[1] == 'FOO-1,"Feature one",alice@test.com,5.0'
        assert lines[2] == 'FOO-1,"Feature one",bob@test.com,2.0'

    def test_csv_escapes_quotes(self):
        """Escapes double quotes in summary."""
        ticket_hours = {"FOO-1": {"alice@test.com": 1.0}}
        summaries = {"FOO-1": 'Fix "broken" thing'}

        result = format_ticket_hours_csv(ticket_hours, summaries)

        assert '""broken""' in result

    def test_csv_multiple_tickets(self):
        """CSV includes rows for all tickets."""
        ticket_hours = {
            "FOO-1": {"alice@test.com": 3.0},
            "FOO-2": {"bob@test.com": 1.5},
        }
        summaries = {"FOO-1": "Feature", "FOO-2": "Bug"}

        result = format_ticket_hours_csv(ticket_hours, summaries)
        lines = result.split("\n")

        assert len(lines) == 3  # header + 2 data rows
        assert "FOO-1" in lines[1]
        assert "FOO-2" in lines[2]


class TestHoursCommandCsv:
    """Tests for hours_command with --format csv."""

    def test_ticket_mode_csv(self, mock_jira, capsys):
        """Outputs CSV in ticket mode with --format csv."""
        mock_jira.issue.return_value = _mock_issue("FOO-1", "Feature one")
        mock_jira.worklogs.return_value = [
            _mock_worklog("alice@test.com", 7200, "2026-02-03T09:00:00"),
            _mock_worklog("bob@test.com", 3600, "2026-02-03T14:00:00"),
        ]

        args = argparse.Namespace(
            tickets=["FOO-1"], date_from=None, date_to=None, days=None,
            summary=False, format="csv"
        )

        hours_command(args)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert lines[0] == "ticket,summary,author,hours"
        assert "alice@test.com" in captured.out
        assert "bob@test.com" in captured.out
