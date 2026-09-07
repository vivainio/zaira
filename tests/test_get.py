"""Tests for get module."""

import argparse
import json
from unittest.mock import patch

import pytest

from zaira.errors import ApplicationError
from zaira.get import get_command


def _args(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "keys": [],
        "web": False,
        "jql": None,
        "board": None,
        "sprint": None,
        "format": "md",
        "output": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _fake_export(key: str, **kwargs: object) -> bool:
    print(json.dumps({"key": key}, indent=2))
    return True


def test_multiple_keys_json_is_one_array(capsys) -> None:
    with (
        patch("zaira.get.export_to_stdout", side_effect=_fake_export),
        patch("zaira.project.load_config", return_value={}),
    ):
        get_command(_args(keys=["A-1", "B-2"], format="json"))

    assert json.loads(capsys.readouterr().out) == [{"key": "A-1"}, {"key": "B-2"}]


def test_single_key_json_stays_an_object(capsys) -> None:
    with (
        patch("zaira.get.export_to_stdout", side_effect=_fake_export),
        patch("zaira.project.load_config", return_value={}),
    ):
        get_command(_args(keys=["A-1"], format="json"))

    assert json.loads(capsys.readouterr().out) == {"key": "A-1"}


class TestGetWeb:
    """Tests for `zaira get --web`."""

    def test_opens_single_ticket_in_browser(self, capsys) -> None:
        with (
            patch("zaira.get.get_jira_site", return_value="example.atlassian.net"),
            patch("zaira.get.webbrowser.open") as mock_open,
        ):
            get_command(_args(keys=["FOO-123"], web=True))

        mock_open.assert_called_once_with(
            "https://example.atlassian.net/browse/FOO-123"
        )
        assert "https://example.atlassian.net/browse/FOO-123" in capsys.readouterr().out

    def test_uppercases_the_key(self) -> None:
        with (
            patch("zaira.get.get_jira_site", return_value="example.atlassian.net"),
            patch("zaira.get.webbrowser.open") as mock_open,
        ):
            get_command(_args(keys=["foo-123"], web=True))

        mock_open.assert_called_once_with(
            "https://example.atlassian.net/browse/FOO-123"
        )

    def test_rejects_multiple_keys(self) -> None:
        with patch("zaira.get.webbrowser.open") as mock_open:
            with pytest.raises(ApplicationError, match="exactly one ticket key"):
                get_command(_args(keys=["FOO-1", "FOO-2"], web=True))
        mock_open.assert_not_called()

    def test_rejects_no_keys(self) -> None:
        with pytest.raises(ApplicationError, match="exactly one ticket key"):
            get_command(_args(keys=[], web=True))

    def test_rejects_jql(self) -> None:
        with pytest.raises(ApplicationError, match="single ticket key"):
            get_command(_args(keys=["FOO-1"], web=True, jql="project = FOO"))

    def test_errors_when_site_not_configured(self) -> None:
        with patch("zaira.get.get_jira_site", return_value=""):
            with pytest.raises(ApplicationError, match="not configured"):
                get_command(_args(keys=["FOO-1"], web=True))
