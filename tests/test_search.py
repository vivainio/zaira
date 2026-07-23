"""Tests for search module."""

import importlib.util
import json

import pytest

from zaira.search import format_results, build_jql, _looks_like_jql, print_row
from zaira.types import SearchResult


# ---------------------------------------------------------------------------
# format_results
# ---------------------------------------------------------------------------


class TestFormatResults:
    """Tests for format_results function."""

    def test_json_empty(self) -> None:
        """Empty list produces empty JSON array."""
        out = format_results([], "json")
        assert json.loads(out) == []

    def test_json_single_result(self) -> None:
        """Single SearchResult serialises correctly."""
        results: list[SearchResult] = [
            SearchResult(
                key="PROJ-1",
                summary="Fix login",
                status="Open",
                type="Bug",
                priority="High",
                assignee="alice",
                created="2024-06-01T10:00:00",
            )
        ]
        out = format_results(results, "json")
        parsed = json.loads(out)
        assert len(parsed) == 1
        assert parsed[0]["key"] == "PROJ-1"
        assert parsed[0]["priority"] == "High"

    def test_json_multiple_results(self) -> None:
        """Multiple SearchResults are all present."""
        results: list[SearchResult] = [
            SearchResult(
                key="A-1",
                summary="First",
                status="Open",
                type="Task",
                priority="Medium",
                assignee="bob",
                created="2024-01-01",
            ),
            SearchResult(
                key="A-2",
                summary="Second",
                status="Closed",
                type="Story",
                priority="Low",
                assignee="",
                created="2024-02-01",
            ),
        ]
        out = format_results(results, "json")
        parsed = json.loads(out)
        assert len(parsed) == 2
        assert parsed[1]["key"] == "A-2"

    def test_default_format_is_json(self) -> None:
        """Omitting output_format defaults to json."""
        results: list[SearchResult] = [
            SearchResult(
                key="X-1",
                summary="Default",
                status="Open",
                type="Task",
                priority="Medium",
                assignee="",
                created="2024-03-01",
            )
        ]
        out = format_results(results)
        parsed = json.loads(out)
        assert parsed[0]["summary"] == "Default"

    @pytest.mark.skipif(
        not importlib.util.find_spec("toon_format"),
        reason="toon-format not installed",
    )
    def test_toon_format_output(self) -> None:
        """Toon format produces non-empty string."""
        pytest.importorskip("toon_format")
        results: list[SearchResult] = [
            SearchResult(
                key="Z-1",
                summary="Toon test",
                status="Open",
                type="Bug",
                priority="High",
                assignee="",
                created="2024-01-01",
            )
        ]
        out = format_results(results, "toon")
        assert "Z-1" in out
        assert "Toon test" in out


# ---------------------------------------------------------------------------
# _looks_like_jql
# ---------------------------------------------------------------------------


class TestLooksLikeJql:
    """Tests for JQL detection heuristic."""

    def test_empty_string(self) -> None:
        assert _looks_like_jql("") is False

    def test_plain_text(self) -> None:
        assert _looks_like_jql("hello world") is False

    def test_equals_operator(self) -> None:
        assert _looks_like_jql("project = DEMO") is True

    def test_and_keyword(self) -> None:
        assert _looks_like_jql("project = X AND status = Open") is True

    def test_order_by(self) -> None:
        assert _looks_like_jql("ORDER BY updated DESC") is True


# ---------------------------------------------------------------------------
# build_jql
# ---------------------------------------------------------------------------


class TestBuildJql:
    """Tests for JQL builder."""

    def _ns(self, **kwargs) -> object:
        """Build a minimal argparse.Namespace for build_jql."""
        import argparse

        defaults = dict(jql=None, text=None, project=None, status=None, assignee=None)
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_explicit_jql_passthrough(self) -> None:
        ns = self._ns(jql="project = FOO")
        assert build_jql(ns) == "project = FOO"

    def test_text_search(self) -> None:
        ns = self._ns(text="login bug")
        result = build_jql(ns)
        assert 'text ~ "login bug"' in result

    def test_project_filter(self) -> None:
        ns = self._ns(text="x", project="DEMO")
        result = build_jql(ns)
        assert 'project = "DEMO"' in result

    def test_status_filter(self) -> None:
        ns = self._ns(text="x", status="Open")
        result = build_jql(ns)
        assert 'status = "Open"' in result

    def test_assignee_filter(self) -> None:
        ns = self._ns(text="x", assignee="alice")
        result = build_jql(ns)
        assert 'assignee = "alice"' in result

    def test_auto_detect_jql_in_text(self) -> None:
        """If text looks like JQL, use it as-is."""
        ns = self._ns(text="project = FOO AND status = Open")
        result = build_jql(ns)
        assert result == "project = FOO AND status = Open"

    def test_no_args_exits(self) -> None:
        ns = self._ns()
        with pytest.raises(SystemExit):
            build_jql(ns)


# ---------------------------------------------------------------------------
# print_row
# ---------------------------------------------------------------------------


class TestPrintRow:
    """Tests for print_row output."""

    def test_basic_output(self, capsys) -> None:
        print_row("PROJ-1", "Open", "2024-01-01T00:00:00", "A summary", 10)
        captured = capsys.readouterr()
        assert "PROJ-1" in captured.out
        assert "Open" in captured.out
        assert "A summary" in captured.out

    def test_truncates_long_summary(self, capsys) -> None:
        long_summary = "X" * 200
        print_row("K-1", "Done", "2024-01-01", long_summary, 6)
        captured = capsys.readouterr()
        assert "..." in captured.out
        assert "X" * 200 not in captured.out
