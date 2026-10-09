"""Tests for zaira get output."""

import argparse
import json
from unittest.mock import patch

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
