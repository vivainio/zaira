"""Tests for recent module."""

import argparse
from unittest.mock import MagicMock, patch

import pytest
from jira.exceptions import JIRAError

from zaira.recent import recent_command, wiki_recent_command


def _mock_issue(key: str, summary: str, status_name: str = "Open") -> object:
    issue = MagicMock()
    issue.key = key
    issue.fields.summary = summary
    if status_name is None:
        issue.fields.status = None
    else:
        issue.fields.status = MagicMock()
        issue.fields.status.name = status_name
    return issue


class TestRecentCommand:
    """Tests for recent_command (Jira recently-viewed tickets)."""

    def test_prints_recent_tickets(self, mock_jira, capsys) -> None:
        mock_jira.search_issues.return_value = [
            _mock_issue("FOO-1", "Feature one", "In Progress"),
            _mock_issue("FOO-22", "Bug fix", "Done"),
        ]

        recent_command(argparse.Namespace(limit=None))

        captured = capsys.readouterr()
        assert "FOO-1" in captured.out
        assert "FOO-22" in captured.out
        assert "In Progress" in captured.out
        assert "Done" in captured.out

    def test_default_limit_is_20(self, mock_jira) -> None:
        mock_jira.search_issues.return_value = []

        recent_command(argparse.Namespace(limit=None))

        _, kwargs = mock_jira.search_issues.call_args
        assert kwargs["maxResults"] == 20

    def test_custom_limit(self, mock_jira) -> None:
        mock_jira.search_issues.return_value = []

        recent_command(argparse.Namespace(limit=5))

        _, kwargs = mock_jira.search_issues.call_args
        assert kwargs["maxResults"] == 5

    def test_uses_issue_history_jql(self, mock_jira) -> None:
        mock_jira.search_issues.return_value = []

        recent_command(argparse.Namespace(limit=None))

        jql = mock_jira.search_issues.call_args[0][0]
        assert "issueHistory()" in jql

    def test_no_issues(self, mock_jira, capsys) -> None:
        mock_jira.search_issues.return_value = []

        recent_command(argparse.Namespace(limit=None))

        captured = capsys.readouterr()
        assert "No recently viewed tickets." in captured.out

    def test_missing_status_shows_placeholder(self, mock_jira, capsys) -> None:
        mock_jira.search_issues.return_value = [
            _mock_issue("FOO-1", "No status ticket", status_name=None),
        ]

        recent_command(argparse.Namespace(limit=None))

        captured = capsys.readouterr()
        assert "FOO-1" in captured.out
        assert "?" in captured.out

    def test_truncates_long_summary(self, mock_jira, capsys) -> None:
        long_summary = "x" * 120
        mock_jira.search_issues.return_value = [
            _mock_issue("FOO-1", long_summary, "Open"),
        ]

        recent_command(argparse.Namespace(limit=None))

        captured = capsys.readouterr()
        assert ("x" * 87 + "...") in captured.out
        assert long_summary not in captured.out

    def test_myself_error_exits(self, mock_jira, capsys) -> None:
        mock_jira.myself.side_effect = JIRAError(status_code=401, text="Unauthorized")

        with pytest.raises(SystemExit) as exc_info:
            recent_command(argparse.Namespace(limit=None))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Unauthorized" in captured.err
        mock_jira.search_issues.assert_not_called()

    def test_search_error_exits(self, mock_jira, capsys) -> None:
        mock_jira.search_issues.side_effect = JIRAError(status_code=500, text="Boom")

        with pytest.raises(SystemExit) as exc_info:
            recent_command(argparse.Namespace(limit=None))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Boom" in captured.err


class TestWikiRecentCommand:
    """Tests for wiki_recent_command (Confluence recently-viewed pages)."""

    @patch(
        "zaira.recent.get_server_from_config", return_value="https://foo.atlassian.net"
    )
    @patch("zaira.recent.load_credentials")
    def test_missing_credentials_exits(
        self, mock_load_creds, _mock_server, capsys
    ) -> None:
        mock_load_creds.return_value = {}

        with pytest.raises(SystemExit) as exc_info:
            wiki_recent_command(argparse.Namespace(limit=None))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Credentials not configured" in captured.err

    @patch("zaira.recent.requests.get")
    @patch(
        "zaira.recent.get_server_from_config", return_value="https://foo.atlassian.net"
    )
    @patch("zaira.recent.load_credentials")
    def test_request_failure_exits(
        self, mock_load_creds, _mock_server, mock_get, capsys
    ) -> None:
        mock_load_creds.return_value = {"email": "me@test.com", "api_token": "tok"}
        response = MagicMock()
        response.ok = False
        response.status_code = 403
        response.reason = "Forbidden"
        mock_get.return_value = response

        with pytest.raises(SystemExit) as exc_info:
            wiki_recent_command(argparse.Namespace(limit=None))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "403" in captured.err
        assert "Forbidden" in captured.err

    @patch("zaira.recent.requests.get")
    @patch(
        "zaira.recent.get_server_from_config", return_value="https://foo.atlassian.net"
    )
    @patch("zaira.recent.load_credentials")
    def test_no_items(self, mock_load_creds, _mock_server, mock_get, capsys) -> None:
        mock_load_creds.return_value = {"email": "me@test.com", "api_token": "tok"}
        response = MagicMock()
        response.ok = True
        response.json.return_value = []
        mock_get.return_value = response

        wiki_recent_command(argparse.Namespace(limit=None))

        captured = capsys.readouterr()
        assert "No recently viewed pages." in captured.out

    @patch("zaira.recent.requests.get")
    @patch(
        "zaira.recent.get_server_from_config", return_value="https://foo.atlassian.net"
    )
    @patch("zaira.recent.load_credentials")
    def test_prints_pages_with_absolute_url(
        self, mock_load_creds, _mock_server, mock_get, capsys
    ) -> None:
        mock_load_creds.return_value = {"email": "me@test.com", "api_token": "tok"}
        response = MagicMock()
        response.ok = True
        response.json.return_value = [
            {
                "title": "My Page",
                "spaceKey": "DEV",
                "lastSeen": 1700000000000,
                "url": "/wiki/spaces/DEV/pages/123",
            }
        ]
        mock_get.return_value = response

        wiki_recent_command(argparse.Namespace(limit=None))

        captured = capsys.readouterr()
        assert "My Page" in captured.out
        assert "[DEV]" in captured.out
        assert "https://foo.atlassian.net/wiki/spaces/DEV/pages/123" in captured.out

    @patch("zaira.recent.requests.get")
    @patch(
        "zaira.recent.get_server_from_config", return_value="https://foo.atlassian.net"
    )
    @patch("zaira.recent.load_credentials")
    def test_prefixes_relative_url_without_wiki(
        self, mock_load_creds, _mock_server, mock_get, capsys
    ) -> None:
        mock_load_creds.return_value = {"email": "me@test.com", "api_token": "tok"}
        response = MagicMock()
        response.ok = True
        response.json.return_value = [
            {
                "title": "Other Page",
                "spaceKey": "OPS",
                "lastSeen": None,
                "url": "/spaces/OPS/pages/456",
            }
        ]
        mock_get.return_value = response

        wiki_recent_command(argparse.Namespace(limit=None))

        captured = capsys.readouterr()
        assert "https://foo.atlassian.net/wiki/spaces/OPS/pages/456" in captured.out

    @patch("zaira.recent.requests.get")
    @patch(
        "zaira.recent.get_server_from_config", return_value="https://foo.atlassian.net"
    )
    @patch("zaira.recent.load_credentials")
    def test_respects_limit_slicing(
        self, mock_load_creds, _mock_server, mock_get, capsys
    ) -> None:
        mock_load_creds.return_value = {"email": "me@test.com", "api_token": "tok"}
        response = MagicMock()
        response.ok = True
        response.json.return_value = [
            {
                "title": f"Page {i}",
                "spaceKey": "DEV",
                "lastSeen": None,
                "url": f"/wiki/{i}",
            }
            for i in range(5)
        ]
        mock_get.return_value = response

        wiki_recent_command(argparse.Namespace(limit=2))

        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"limit": 2}
        captured = capsys.readouterr()
        assert "Page 0" in captured.out
        assert "Page 1" in captured.out
        assert "Page 2" not in captured.out
