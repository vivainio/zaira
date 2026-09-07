"""Contract tests for the zaira CLI parser.

These tests pin down the observable CLI surface (command names, argument
names, defaults, choices, help behavior, stdout/stderr routing, and exit
codes) so that structural refactoring of zaira/cli.py cannot silently change
it. They intentionally do not exercise command *implementations* (those are
covered by each feature's own tests) -- only `build_parser()` and the
top-level dispatch in `main()`.
"""

import argparse
import subprocess
import sys

import pytest

from zaira.cli import build_parser

# Full command tree, including nested subcommands, as of the review that
# produced refactoring_plan.md. Keep this in sync deliberately -- any change
# here is an observable CLI compatibility decision, not a refactor.
EXPECTED_COMMAND_TREE: dict[str, list[str]] = {
    "report": [],
    "boards": [],
    "dashboards": [],
    "dashboard": [],
    "refresh": [],
    "init": [],
    "init-xray": [],
    "xray": ["get"],
    "init-project": [],
    "my": [],
    "recent": [],
    "search": [],
    "get": [],
    "put": [],
    "check": [],
    "comment": [],
    "log": [],
    "hours": [],
    "attach": [],
    "get-attachment": [],
    "edit": [],
    "create": [],
    "link": [],
    "transition": [],
    "learn": [],
    "info": ["link-types", "statuses", "issue-types", "fields", "field"],
    "wiki": [
        "get",
        "search",
        "create",
        "put",
        "append",
        "attach",
        "get-attachment",
        "edit",
        "delete",
        "ls",
        "recent",
    ],
    "changelog": [],
    "history": [],
    "reset": [],
    "bundle": ["install", "update"],
    "goals": ["export", "get", "updates"],
    "install-skills": [],
}


def _top_level_subparsers(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise AssertionError("parser has no subparsers action")


def _subcommand_names(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return list(action.choices.keys())
    return []


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    return build_parser()


def test_top_level_command_set_unchanged(parser: argparse.ArgumentParser) -> None:
    top = _top_level_subparsers(parser)
    assert sorted(top.choices.keys()) == sorted(EXPECTED_COMMAND_TREE.keys())


@pytest.mark.parametrize("command", sorted(EXPECTED_COMMAND_TREE.keys()))
def test_subcommand_set_unchanged(
    parser: argparse.ArgumentParser, command: str
) -> None:
    top = _top_level_subparsers(parser)
    sub = top.choices[command]
    assert sorted(_subcommand_names(sub)) == sorted(EXPECTED_COMMAND_TREE[command])


def _all_paths() -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = []
    for command, subs in EXPECTED_COMMAND_TREE.items():
        if subs:
            for sub in subs:
                paths.append((command, sub))
        else:
            paths.append((command,))
    return paths


@pytest.mark.parametrize("path", _all_paths(), ids=lambda p: " ".join(p))
def test_help_exits_zero_and_writes_stdout(
    parser: argparse.ArgumentParser,
    path: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([*path, "-h"])
    assert exc_info.value.code == 0
    out, err = capsys.readouterr()
    assert out.strip()
    assert err == ""


def test_top_level_help_exits_zero(
    parser: argparse.ArgumentParser, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["-h"])
    assert exc_info.value.code == 0
    out, err = capsys.readouterr()
    assert "zaira" in out
    assert err == ""


def test_version_flag_exits_zero(
    parser: argparse.ArgumentParser, capsys: pytest.CaptureFixture[str]
) -> None:
    from zaira import __version__

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["-V"])
    assert exc_info.value.code == 0
    out, err = capsys.readouterr()
    assert __version__ in out
    assert err == ""


def test_unknown_command_exits_two_and_writes_stderr(
    parser: argparse.ArgumentParser, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["not-a-real-command"])
    assert exc_info.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.strip()


def test_missing_required_positional_exits_two(
    parser: argparse.ArgumentParser, capsys: pytest.CaptureFixture[str]
) -> None:
    # `link` requires from_key and to_key positionals.
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["link", "PROJ-1"])
    assert exc_info.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.strip()


def test_no_command_prints_help_and_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "zaira.cli"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout.strip()
    assert "usage" in result.stdout.lower()


def test_command_defaults_have_callable_func(
    parser: argparse.ArgumentParser,
) -> None:
    top = _top_level_subparsers(parser)
    for name, sub in top.choices.items():
        try:
            args = sub.parse_args([])
        except SystemExit:
            # Command requires a positional or a subcommand to parse at
            # all (e.g. `xray`, `link`) -- func-default coverage for those
            # is exercised via the per-path help/dispatch tests instead.
            continue
        assert callable(args.func), f"{name} missing func default"


@pytest.mark.parametrize(
    "argv,dest,expected_default",
    [
        (["report"], "format", "md"),
        (["get"], "format", "md"),
        (["search"], "format", "default"),
        (["search"], "limit", 0),
        (["hours"], "format", "default"),
        (["dashboard", "123"], "format", "md"),
        (["dashboards"], "limit", 50),
        (["recent"], "limit", 20),
        (["wiki", "recent"], "limit", 20),
        (["wiki", "get"], "format", "md"),
        (["wiki", "search"], "format", "default"),
        (["wiki", "search"], "limit", 25),
        (["wiki", "ls", "SPACE"], "depth", 1),
        (["link", "A-1", "B-1"], "type", "Relates"),
        (["history"], "tail", 20),
    ],
)
def test_argument_defaults_unchanged(
    parser: argparse.ArgumentParser,
    argv: list[str],
    dest: str,
    expected_default: object,
) -> None:
    args = parser.parse_args(argv)
    assert getattr(args, dest) == expected_default


@pytest.mark.parametrize(
    "argv,dest,choices",
    [
        (["report"], "format", ["md", "json", "csv"]),
        (["get"], "format", ["md", "json", "ndjson"]),
        (["search"], "format", ["default", "json", "toon"]),
        (["hours"], "format", ["default", "csv"]),
        (["dashboard", "123"], "format", ["md", "json"]),
        (["wiki", "get"], "format", ["md", "html", "json"]),
        (["wiki", "search"], "format", ["default", "url", "id", "json", "toon"]),
        (["goals", "export"], "format", ["json", "md", "table"]),
        (["goals", "get", "K-1"], "format", ["json", "md", "table"]),
        (["goals", "updates", "K-1"], "format", ["md", "json"]),
    ],
)
def test_format_choices_unchanged(
    parser: argparse.ArgumentParser,
    argv: list[str],
    dest: str,
    choices: list[str],
) -> None:
    action = _find_action(parser, argv, dest)
    assert action.choices == choices


def _find_action(
    parser: argparse.ArgumentParser, argv: list[str], dest: str
) -> argparse.Action:
    sub = parser
    for token in argv:
        found = False
        for action in sub._actions:
            if isinstance(action, argparse._SubParsersAction) and token in (
                action.choices or {}
            ):
                sub = action.choices[token]
                found = True
                break
        if not found:
            break
    for action in sub._actions:
        if action.dest == dest:
            return action
    raise AssertionError(f"no action with dest={dest!r} for {argv}")
