"""Tests for zaira.check (the `zaira check` CLI command)."""

import argparse
from collections.abc import Iterator
from unittest.mock import patch

import pytest

import zaira.hooks as hooks_mod
from zaira.check import check_command
from zaira.hooks import HookPoint, hook, note
from zaira.types import Violation


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    hooks_mod.reset_registry()
    yield
    hooks_mod.reset_registry()


def _ticket(**overrides: object) -> dict[str, object]:
    base = {
        "key": "FOO-1",
        "summary": "Test ticket",
        "issuetype": "Story",
        "status": "To Do",
        "custom_fields": {},
    }
    base.update(overrides)
    return base


class TestCheckCommand:
    def test_ok_when_no_hooks_configured(self, capsys) -> None:
        with patch("zaira.check.get_ticket", return_value=_ticket()):
            check_command(argparse.Namespace(keys=["FOO-1"]))

        out = capsys.readouterr().out
        assert "FOO-1 (Story / To Do)" in out
        assert "ok (no hooks configured)" in out

    def test_prints_fail_and_exits_1_on_violation(self, capsys) -> None:
        @hook(HookPoint.CHECK)
        def block(ticket, status) -> Violation:
            return Violation("summary", "hook", "not acceptable")

        with patch("zaira.check.get_ticket", return_value=_ticket()):
            with pytest.raises(SystemExit) as exc_info:
                check_command(argparse.Namespace(keys=["FOO-1"]))

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "FAIL  hook        summary" in out
        assert "not acceptable" in out

    def test_prints_note_without_failing(self, capsys) -> None:
        @hook(HookPoint.CHECK)
        def informational(ticket, status) -> None:
            note("heads up: this is a note, not a violation")

        with patch("zaira.check.get_ticket", return_value=_ticket()):
            check_command(argparse.Namespace(keys=["FOO-1"]))  # must not raise

        out = capsys.readouterr().out
        assert "NOTE  heads up: this is a note, not a violation" in out
        assert "FAIL" not in out
        assert "ok" not in out  # a note replaces the "ok" line, doesn't sit beside it

    def test_note_and_violation_both_print_failure_still_exits(self, capsys) -> None:
        @hook(HookPoint.CHECK)
        def both(ticket, status) -> Violation:
            note("context for the failure below")
            return Violation("summary", "hook", "blocked")

        with patch("zaira.check.get_ticket", return_value=_ticket()):
            with pytest.raises(SystemExit):
                check_command(argparse.Namespace(keys=["FOO-1"]))

        out = capsys.readouterr().out
        assert "NOTE  context for the failure below" in out
        assert "FAIL" in out

    def test_could_not_fetch_ticket(self, capsys) -> None:
        with patch("zaira.check.get_ticket", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                check_command(argparse.Namespace(keys=["FOO-1"]))

        assert exc_info.value.code == 1
        assert "could not fetch ticket" in capsys.readouterr().err

    def test_multiple_keys_all_checked(self, capsys) -> None:
        tickets = {"FOO-1": _ticket(key="FOO-1"), "FOO-2": _ticket(key="FOO-2")}

        with patch("zaira.check.get_ticket", side_effect=lambda k, **kw: tickets[k]):
            check_command(argparse.Namespace(keys=["FOO-1", "FOO-2"]))

        out = capsys.readouterr().out
        assert "FOO-1 (Story / To Do)" in out
        assert "FOO-2 (Story / To Do)" in out

    def test_notes_dont_leak_between_tickets(self, capsys) -> None:
        """A note queued while checking one ticket must not print again for the next."""

        @hook(HookPoint.CHECK)
        def only_for_foo1(ticket, status) -> None:
            if ticket["key"] == "FOO-1":
                note("only relevant to FOO-1")

        tickets = {"FOO-1": _ticket(key="FOO-1"), "FOO-2": _ticket(key="FOO-2")}
        with patch("zaira.check.get_ticket", side_effect=lambda k, **kw: tickets[k]):
            check_command(argparse.Namespace(keys=["FOO-1", "FOO-2"]))

        out = capsys.readouterr().out
        assert out.count("only relevant to FOO-1") == 1
