"""Tests for zaira get output."""

import argparse
import json
from unittest.mock import patch

import pytest

from zaira.errors import ApplicationError
from zaira.get import get_command


def _args(keys: list[str]) -> argparse.Namespace:
    return argparse.Namespace(keys=keys, format="json", output=None)


def _fake_export(key: str, **kwargs: object) -> bool:
    print(json.dumps({"key": key}, indent=2))
    return True


def test_multiple_keys_json_is_one_array(capsys) -> None:
    with (
        patch("zaira.get.export_to_stdout", side_effect=_fake_export),
        patch("zaira.project.load_config", return_value={}),
    ):
        get_command(_args(["A-1", "B-2"]))

    assert json.loads(capsys.readouterr().out) == [{"key": "A-1"}, {"key": "B-2"}]


def test_single_key_json_stays_an_object(capsys) -> None:
    with (
        patch("zaira.get.export_to_stdout", side_effect=_fake_export),
        patch("zaira.project.load_config", return_value={}),
    ):
        get_command(_args(["A-1"]))

    assert json.loads(capsys.readouterr().out) == {"key": "A-1"}


def _web_args(keys: list[str]) -> argparse.Namespace:
    return argparse.Namespace(keys=keys, web=True)


def test_web_opens_ticket_in_browser(capsys) -> None:
    with (
        patch("zaira.get.get_jira_site", return_value="example.atlassian.net"),
        patch("zaira.get.webbrowser.open") as mock_open,
    ):
        get_command(_web_args(["foo-123"]))

    url = "https://example.atlassian.net/browse/FOO-123"
    mock_open.assert_called_once_with(url)
    assert url in capsys.readouterr().out


@pytest.mark.parametrize("keys", [[], ["FOO-1", "FOO-2"]])
def test_web_needs_exactly_one_key(keys: list[str]) -> None:
    with patch("zaira.get.webbrowser.open") as mock_open:
        with pytest.raises(ApplicationError, match="exactly one ticket key"):
            get_command(_web_args(keys))
    mock_open.assert_not_called()


def test_web_errors_when_site_not_configured() -> None:
    with patch("zaira.get.get_jira_site", return_value=""):
        with pytest.raises(ApplicationError, match="not configured"):
            get_command(_web_args(["FOO-1"]))
