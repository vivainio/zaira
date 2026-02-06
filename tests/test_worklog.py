"""Tests for worklog module."""

import argparse
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from zaira.worklog import list_worklogs, add_worklog, log_command, _parse_time_to_hours


def _mock_worklog(author_name="user@example.com", time_spent="2h",
                  started="2026-02-06T09:00:00.000+0000", comment=None):
    """Create a mock worklog entry."""
    entry = MagicMock()
    entry.author = MagicMock()
    entry.author.emailAddress = author_name
    entry.author.displayName = author_name
    entry.timeSpent = time_spent
    entry.started = started
    entry.comment = comment
    return entry


class TestListWorklogs:
    """Tests for list_worklogs function."""

    def test_returns_worklogs(self, mock_jira):
        """Returns list of Worklog entries."""
        mock_jira.worklogs.return_value = [
            _mock_worklog(time_spent="2h", comment="Code review"),
            _mock_worklog(time_spent="30m"),
        ]

        result = list_worklogs("TEST-123")

        assert len(result) == 2
        assert result[0].time_spent == "2h"
        assert result[0].comment == "Code review"
        assert result[1].time_spent == "30m"
        assert result[1].comment is None
        mock_jira.worklogs.assert_called_once_with("TEST-123")

    def test_returns_empty_on_error(self, mock_jira, capsys):
        """Returns empty list on API error."""
        mock_jira.worklogs.side_effect = Exception("Not found")

        result = list_worklogs("INVALID-1")

        assert result == []
        captured = capsys.readouterr()
        assert "Error getting worklogs" in captured.err

    def test_returns_empty_for_no_worklogs(self, mock_jira):
        """Returns empty list when ticket has no worklogs."""
        mock_jira.worklogs.return_value = []

        result = list_worklogs("TEST-123")

        assert result == []


class TestAddWorklog:
    """Tests for add_worklog function."""

    def test_adds_worklog_successfully(self, mock_jira):
        """Returns True when worklog is added."""
        mock_jira.add_worklog.return_value = MagicMock()

        result = add_worklog("TEST-123", "2h")

        assert result is True
        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="2h"
        )

    def test_adds_worklog_with_comment(self, mock_jira):
        """Passes comment to Jira API."""
        mock_jira.add_worklog.return_value = MagicMock()

        result = add_worklog("TEST-123", "1h", comment="Code review")

        assert result is True
        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="1h", comment="Code review"
        )

    def test_adds_worklog_with_started_date(self, mock_jira):
        """Passes started date to Jira API."""
        mock_jira.add_worklog.return_value = MagicMock()
        started = datetime(2026, 2, 5)

        result = add_worklog("TEST-123", "3h", started=started)

        assert result is True
        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="3h", started=started
        )

    def test_adds_worklog_with_all_options(self, mock_jira):
        """Passes all options to Jira API."""
        mock_jira.add_worklog.return_value = MagicMock()
        started = datetime(2026, 2, 5)

        result = add_worklog("TEST-123", "2h 30m", comment="Review", started=started)

        assert result is True
        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="2h 30m", comment="Review", started=started
        )

    def test_returns_false_on_error(self, mock_jira, capsys):
        """Returns False and prints error on failure."""
        mock_jira.add_worklog.side_effect = Exception("Permission denied")

        result = add_worklog("TEST-123", "1h")

        assert result is False
        captured = capsys.readouterr()
        assert "Error logging work" in captured.err

    def test_returns_false_when_none_returned(self, mock_jira):
        """Returns False when add_worklog returns None."""
        mock_jira.add_worklog.return_value = None

        result = add_worklog("TEST-123", "1h")

        assert result is False


class TestLogCommand:
    """Tests for log_command function."""

    def test_lists_worklogs(self, mock_jira, capsys):
        """Lists worklogs with --list flag."""
        mock_jira.worklogs.return_value = [
            _mock_worklog(time_spent="2h", comment="Code review"),
            _mock_worklog(time_spent="30m"),
        ]

        args = argparse.Namespace(key="test-123", time=None, comment=None,
                                  date=None, list=True)
        log_command(args)

        captured = capsys.readouterr()
        assert "Worklogs for TEST-123" in captured.out
        assert "2h" in captured.out
        assert "30m" in captured.out
        assert "Code review" in captured.out

    def test_lists_worklogs_shows_total(self, mock_jira, capsys):
        """Shows total hours when listing worklogs."""
        mock_jira.worklogs.return_value = [
            _mock_worklog(time_spent="2h"),
            _mock_worklog(time_spent="1h"),
        ]

        args = argparse.Namespace(key="TEST-123", time=None, comment=None,
                                  date=None, list=True)
        log_command(args)

        captured = capsys.readouterr()
        assert "Total: 3.0h" in captured.out

    def test_lists_no_worklogs(self, mock_jira, capsys):
        """Shows message when no worklogs found."""
        mock_jira.worklogs.return_value = []

        args = argparse.Namespace(key="TEST-123", time=None, comment=None,
                                  date=None, list=True)
        log_command(args)

        captured = capsys.readouterr()
        assert "No worklogs found" in captured.out

    def test_exits_when_no_time_and_no_list(self, capsys):
        """Exits with error when neither time nor --list provided."""
        args = argparse.Namespace(key="test-123", time=None, comment=None,
                                  date=None, list=False)

        with pytest.raises(SystemExit) as exc_info:
            log_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Specify time spent or use --list" in captured.err

    def test_logs_time_successfully(self, mock_jira, capsys):
        """Logs time and shows success message."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(key="test-123", time="2h", comment=None,
                                  date=None, list=False)

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        captured = capsys.readouterr()
        assert "Logged 2h to TEST-123" in captured.out
        assert "jira.example.com" in captured.out

    def test_logs_time_with_comment(self, mock_jira, capsys):
        """Passes comment when logging time."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(key="TEST-123", time="1h", comment="Code review",
                                  date=None, list=False)

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="1h", comment="Code review"
        )

    def test_logs_time_with_date(self, mock_jira, capsys):
        """Parses date and passes started datetime."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(key="TEST-123", time="3h", comment=None,
                                  date="2026-02-05", list=False)

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="3h", started=datetime(2026, 2, 5)
        )

    def test_exits_on_invalid_date(self, capsys):
        """Exits with error on invalid date format."""
        args = argparse.Namespace(key="TEST-123", time="2h", comment=None,
                                  date="02/05/2026", list=False)

        with pytest.raises(SystemExit) as exc_info:
            log_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid date" in captured.err
        assert "YYYY-MM-DD" in captured.err

    def test_exits_on_add_failure(self, mock_jira, capsys):
        """Exits with error when add_worklog fails."""
        mock_jira.add_worklog.side_effect = Exception("Permission denied")

        args = argparse.Namespace(key="TEST-123", time="1h", comment=None,
                                  date=None, list=False)

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                log_command(args)

        assert exc_info.value.code == 1

    def test_uppercases_ticket_key(self, mock_jira, capsys):
        """Converts ticket key to uppercase."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(key="test-123", time="1h", comment=None,
                                  date=None, list=False)

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="1h"
        )


class TestParseTimeToHours:
    """Tests for _parse_time_to_hours helper."""

    def test_hours(self):
        assert _parse_time_to_hours("2h") == 2.0

    def test_minutes(self):
        assert _parse_time_to_hours("30m") == 0.5

    def test_days(self):
        assert _parse_time_to_hours("1d") == 8.0

    def test_weeks(self):
        assert _parse_time_to_hours("1w") == 40.0

    def test_compound(self):
        assert _parse_time_to_hours("1h 30m") == 1.5

    def test_empty_string(self):
        assert _parse_time_to_hours("") == 0.0

    def test_unknown_format(self):
        assert _parse_time_to_hours("unknown") == 0.0
