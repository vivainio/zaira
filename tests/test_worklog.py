"""Tests for worklog module."""

import argparse
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from zaira.worklog import (
    list_worklogs,
    add_worklog,
    log_command,
    spread_hours,
    _parse_time_to_hours,
    _round_half_hour,
    _distribute_rounded,
    _parse_spread,
    _ExistingHours,
)


def _mock_worklog(
    author_name="user@example.com",
    time_spent="2h",
    started="2026-02-06T09:00:00.000+0000",
    comment=None,
):
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
        mock_jira.add_worklog.assert_called_once_with(issue="TEST-123", timeSpent="2h")

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

        args = argparse.Namespace(
            key="test-123", time=None, comment=None, date=None, list=True
        )
        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
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

        args = argparse.Namespace(
            key="TEST-123", time=None, comment=None, date=None, list=True
        )
        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        captured = capsys.readouterr()
        assert "Total: 3.0h" in captured.out

    def test_lists_no_worklogs(self, mock_jira, capsys):
        """Shows message when no worklogs found."""
        mock_jira.worklogs.return_value = []

        args = argparse.Namespace(
            key="TEST-123", time=None, comment=None, date=None, list=True
        )
        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        captured = capsys.readouterr()
        assert "No worklogs found" in captured.out

    def test_exits_when_no_time_and_no_list(self, capsys):
        """Exits with error when neither time nor --list provided."""
        args = argparse.Namespace(
            key="test-123", time=None, comment=None, date=None, list=False
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                log_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Specify time spent or use --list" in captured.err

    def test_logs_time_successfully(self, mock_jira, capsys):
        """Logs time and shows success message."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(
            key="test-123", time="2h", comment=None, date=None, list=False
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        captured = capsys.readouterr()
        assert "Logged 2h to TEST-123" in captured.out
        assert "jira.example.com" in captured.out

    def test_logs_time_with_comment(self, mock_jira, capsys):
        """Passes comment when logging time."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(
            key="TEST-123", time="1h", comment="Code review", date=None, list=False
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="1h", comment="Code review"
        )

    def test_logs_time_with_date(self, mock_jira, capsys):
        """Parses date and passes started datetime."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(
            key="TEST-123", time="3h", comment=None, date="2026-02-05", list=False
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        mock_jira.add_worklog.assert_called_once_with(
            issue="TEST-123", timeSpent="3h", started=datetime(2026, 2, 5)
        )

    def test_exits_on_invalid_date(self, capsys):
        """Exits with error on invalid date format."""
        args = argparse.Namespace(
            key="TEST-123", time="2h", comment=None, date="02/05/2026", list=False
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                log_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid date" in captured.err
        assert "YYYY-MM-DD" in captured.err

    def test_exits_on_add_failure(self, mock_jira, capsys):
        """Exits with error when add_worklog fails."""
        mock_jira.add_worklog.side_effect = Exception("Permission denied")

        args = argparse.Namespace(
            key="TEST-123", time="1h", comment=None, date=None, list=False
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                log_command(args)

        assert exc_info.value.code == 1

    def test_uppercases_ticket_key(self, mock_jira, capsys):
        """Converts ticket key to uppercase."""
        mock_jira.add_worklog.return_value = MagicMock()

        args = argparse.Namespace(
            key="test-123", time="1h", comment=None, date=None, list=False
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            log_command(args)

        mock_jira.add_worklog.assert_called_once_with(issue="TEST-123", timeSpent="1h")


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


class TestRoundHalfHour:
    """Tests for _round_half_hour helper."""

    def test_exact_hour(self):
        assert _round_half_hour(3.0) == 3.0

    def test_exact_half(self):
        assert _round_half_hour(2.5) == 2.5

    def test_rounds_down(self):
        assert _round_half_hour(2.2) == 2.0

    def test_rounds_up(self):
        assert _round_half_hour(2.3) == 2.5

    def test_rounds_quarter_to_half(self):
        # Python banker's rounding: 2.25 * 2 = 4.5 rounds to 4
        assert _round_half_hour(2.25) == 2.0
        # 2.75 * 2 = 5.5 rounds to 6
        assert _round_half_hour(2.75) == 3.0

    def test_zero(self):
        assert _round_half_hour(0.0) == 0.0


class TestDistributeRounded:
    """Tests for _distribute_rounded."""

    def test_even_split(self):
        """16h / 4 days = 4h each."""
        result = _distribute_rounded(16.0, 4)
        assert result == [4.0, 4.0, 4.0, 4.0]
        assert sum(result) == 16.0

    def test_remainder_handling(self):
        """16h / 5 days = 3.2h each, rounds to mix of 3.0 and 3.5."""
        result = _distribute_rounded(16.0, 5)
        assert all(r % 0.5 == 0 for r in result)
        assert sum(result) == 16.0
        assert sorted(result) == [3.0, 3.0, 3.0, 3.5, 3.5]

    def test_single_day(self):
        result = _distribute_rounded(2.5, 1)
        assert result == [2.5]

    def test_zero_days(self):
        result = _distribute_rounded(10.0, 0)
        assert result == []

    def test_small_amount_many_days(self):
        """1h across 3 days."""
        result = _distribute_rounded(1.0, 3)
        assert all(r % 0.5 == 0 for r in result)
        assert sum(result) == 1.0

    def test_total_preserved_odd_split(self):
        """7h across 3 days."""
        result = _distribute_rounded(7.0, 3)
        assert sum(result) == 7.0
        assert all(r % 0.5 == 0 for r in result)


class TestParseSpread:
    """Tests for _parse_spread."""

    def test_day_count(self):
        assert _parse_spread("5d") == 5

    def test_day_count_single(self):
        assert _parse_spread("1d") == 1

    def test_date_range(self):
        result = _parse_spread("2026-01-27,2026-01-31")
        assert result == ("2026-01-27", "2026-01-31")

    def test_date_range_with_spaces(self):
        result = _parse_spread("2026-01-27, 2026-01-31")
        assert result == ("2026-01-27", "2026-01-31")

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid --spread"):
            _parse_spread("5")

    def test_invalid_date(self):
        with pytest.raises(ValueError):
            _parse_spread("2026-13-01,2026-01-31")


class TestSpreadHours:
    """Tests for spread_hours function."""

    def test_spread_5_workdays(self):
        """16h across 5 workdays from a known Friday."""
        # Use a date range for a known Mon-Fri week
        result = spread_hours("16h", ("2026-02-02", "2026-02-06"))
        assert len(result) == 5
        total = sum(_parse_time_to_hours(dur) for _, dur in result)
        assert total == 16.0
        # All durations rounded to 0.5h
        for _, dur in result:
            hrs = _parse_time_to_hours(dur)
            assert hrs % 0.5 == 0

    def test_skips_weekends(self):
        """Date range spanning a weekend skips Sat/Sun."""
        # 2026-02-06 is Fri, 2026-02-09 is Mon
        result = spread_hours("8h", ("2026-02-06", "2026-02-09"))
        dates = [d for d, _ in result]
        assert "2026-02-07" not in dates  # Saturday
        assert "2026-02-08" not in dates  # Sunday
        assert len(result) == 2  # Fri + Mon

    def test_include_weekends(self):
        """With skip_weekends=False, includes Sat/Sun."""
        result = spread_hours("8h", ("2026-02-06", "2026-02-09"), skip_weekends=False)
        assert len(result) == 4  # Fri, Sat, Sun, Mon

    def test_day_count_mode(self):
        """Spread with int days counts back from today."""
        result = spread_hours("8h", 2)
        assert len(result) == 2
        total = sum(_parse_time_to_hours(dur) for _, dur in result)
        assert total == 8.0

    def test_empty_for_zero_hours(self):
        result = spread_hours("0h", 5)
        assert result == []

    def test_format_durations(self):
        """Durations formatted as 'Xh', 'Xh 30m', or '30m'."""
        result = spread_hours("16h", ("2026-02-02", "2026-02-06"))
        import re

        for _, dur in result:
            assert re.match(r"^(\d+h( 30m)?|30m)$", dur), f"Bad format: {dur}"

    def test_date_range_reversed(self):
        """Reversed date range still works."""
        result = spread_hours("8h", ("2026-02-06", "2026-02-02"))
        assert len(result) == 5

    def test_single_day_range(self):
        """Range of one day."""
        result = spread_hours("4h", ("2026-02-03", "2026-02-03"))
        assert len(result) == 1
        assert result[0] == ("2026-02-03", "4h")

    @patch("zaira.worklog.get_max_hours_per_day", return_value=7.5)
    def test_respects_existing_hours(self, _mock):
        """Reduces allocation on days with existing worklogs."""
        existing = {"2026-02-03": 6.0}  # Mon already has 6h
        result = spread_hours(
            "16h",
            ("2026-02-02", "2026-02-06"),
            existing_hours=existing,
        )
        for date_str, dur in result:
            existing_h = existing.get(date_str, 0.0)
            assert existing_h + _parse_time_to_hours(dur) <= 7.5
        total = sum(_parse_time_to_hours(dur) for _, dur in result)
        assert total == 16.0

    @patch("zaira.worklog.get_max_hours_per_day", return_value=7.5)
    def test_existing_hours_full_day_skipped(self, _mock):
        """Day with max hours already logged gets no allocation."""
        existing = {"2026-02-03": 7.5}
        result = spread_hours(
            "8h",
            ("2026-02-02", "2026-02-06"),
            existing_hours=existing,
        )
        dates = [d for d, _ in result]
        assert "2026-02-03" not in dates
        total = sum(_parse_time_to_hours(dur) for _, dur in result)
        assert total == 8.0

    @patch("zaira.worklog.get_max_hours_per_day", return_value=7.5)
    def test_raises_when_not_enough_capacity(self, _mock):
        """Raises ValueError when existing hours leave insufficient capacity."""
        existing = {
            "2026-02-02": 7.0,
            "2026-02-03": 7.0,
            "2026-02-04": 7.0,
            "2026-02-05": 7.0,
            "2026-02-06": 7.0,
        }
        with pytest.raises(ValueError, match="Cannot fit"):
            spread_hours(
                "10h",
                ("2026-02-02", "2026-02-06"),
                existing_hours=existing,
            )


class TestLogCommandSpread:
    """Tests for log_command with --spread flag."""

    _patch_fetch = patch(
        "zaira.worklog._fetch_existing_hours",
        return_value=_ExistingHours({}, {}),
    )

    def test_spread_dry_run(self, mock_jira, capsys):
        """Shows preview and tells user to re-run with --yes."""
        args = argparse.Namespace(
            key="TEST-123",
            time="8h",
            comment=None,
            date=None,
            list=False,
            spread="2026-02-02,2026-02-06",
            yes=False,
            include_weekends=False,
        )

        with (
            patch("zaira.worklog.get_jira_site", return_value="jira.example.com"),
            self._patch_fetch,
        ):
            log_command(args)

        captured = capsys.readouterr()
        assert "Spreading 8h across 5 workdays" in captured.out
        assert "preview" in captured.out.lower()
        assert "--yes" in captured.out
        mock_jira.add_worklog.assert_not_called()

    def test_spread_yes_skips_prompt(self, mock_jira, capsys):
        """--yes flag skips confirmation."""
        mock_jira.add_worklog.return_value = MagicMock()
        args = argparse.Namespace(
            key="TEST-123",
            time="8h",
            comment=None,
            date=None,
            list=False,
            spread="2026-02-02,2026-02-06",
            yes=True,
            include_weekends=False,
        )

        with (
            patch("zaira.worklog.get_jira_site", return_value="jira.example.com"),
            self._patch_fetch,
        ):
            log_command(args)

        assert mock_jira.add_worklog.call_count == 5

    def test_spread_invalid_format(self, capsys):
        """Exits on invalid --spread value."""
        args = argparse.Namespace(
            key="TEST-123",
            time="8h",
            comment=None,
            date=None,
            list=False,
            spread="bad",
            yes=True,
            include_weekends=False,
        )

        with patch("zaira.worklog.get_jira_site", return_value="jira.example.com"):
            with pytest.raises(SystemExit) as exc_info:
                log_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid --spread" in captured.err

    def test_spread_shows_day_names(self, mock_jira, capsys):
        """Preview shows day names like Mon, Tue."""
        mock_jira.add_worklog.return_value = MagicMock()
        args = argparse.Namespace(
            key="TEST-123",
            time="8h",
            comment=None,
            date=None,
            list=False,
            spread="2026-02-02,2026-02-06",
            yes=True,
            include_weekends=False,
        )

        with (
            patch("zaira.worklog.get_jira_site", return_value="jira.example.com"),
            self._patch_fetch,
        ):
            log_command(args)

        captured = capsys.readouterr()
        assert "(Mon)" in captured.out
        assert "(Fri)" in captured.out

    def test_spread_shows_existing_tickets(self, mock_jira, capsys):
        """Preview shows existing ticket details."""
        mock_jira.add_worklog.return_value = MagicMock()
        args = argparse.Namespace(
            key="TEST-123",
            time="8h",
            comment=None,
            date=None,
            list=False,
            spread="2026-02-02,2026-02-06",
            yes=True,
            include_weekends=False,
        )
        existing = _ExistingHours(
            {"2026-02-03": 4.0},
            {"2026-02-03": [("FOO-1", 2.5), ("FOO-2", 1.5)]},
        )

        with (
            patch("zaira.worklog.get_jira_site", return_value="jira.example.com"),
            patch("zaira.worklog._fetch_existing_hours", return_value=existing),
        ):
            log_command(args)

        captured = capsys.readouterr()
        assert "FOO-1 2.5h" in captured.out
        assert "FOO-2 1.5h" in captured.out
