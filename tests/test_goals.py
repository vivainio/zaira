"""Tests for goals module."""

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest

from zaira import goals
from zaira.goals import (
    _adf_to_text,
    _batch_get_goals,
    _cell,
    _indent,
    _post_graphql,
    _status_label,
    _to_markdown,
    _to_table,
    _updates_to_markdown,
    export_command,
    get_cloud_id,
    get_command,
    get_goal,
    get_goal_updates,
    goals_command,
    parse_goals_url,
    search_goals,
    updates_command,
)


@pytest.fixture(autouse=True)
def _reset_cloud_id_cache() -> object:
    goals._cached_cloud_id = None
    yield
    goals._cached_cloud_id = None


class TestParseGoalsUrl:
    def test_parses_cloud_id_tql_org_id(self):
        url = (
            "https://home.atlassian.com/o/org123/goals"
            "?cloudId=cloud456&tql=archived%20%3D%20false"
        )
        result = parse_goals_url(url)
        assert result["cloud_id"] == "cloud456"
        assert result["tql"] == "archived = false"
        assert result["org_id"] == "org123"

    def test_missing_params_omitted(self):
        result = parse_goals_url("https://home.atlassian.com/o/org123/goals")
        assert "cloud_id" not in result
        assert "tql" not in result
        assert result["org_id"] == "org123"

    def test_no_org_segment(self):
        result = parse_goals_url("https://home.atlassian.com/goals?cloudId=abc")
        assert result["cloud_id"] == "abc"
        assert "org_id" not in result


class TestStatusLabel:
    def test_known_status(self):
        assert _status_label({"value": "on_track"}) == "On track"

    def test_unknown_status_passthrough(self):
        assert _status_label({"value": "mystery"}) == "mystery"

    def test_none_status(self):
        assert _status_label(None) == ""

    def test_missing_value(self):
        assert _status_label({}) == ""


class TestAdfToText:
    def test_none(self):
        assert _adf_to_text(None) == ""

    def test_plain_string_passthrough_on_bad_json(self):
        assert _adf_to_text("not json") == "not json"

    def test_string_json_doc(self):
        doc = json.dumps(
            {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Hello"}],
                    }
                ],
            }
        )
        assert _adf_to_text(doc) == "Hello"

    def test_heading(self):
        node = {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": "Title"}],
        }
        assert _adf_to_text(node) == "## Title\n"

    def test_bullet_list(self):
        node = {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "one"}],
                        }
                    ],
                },
                {
                    "type": "listItem",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "two"}],
                        }
                    ],
                },
            ],
        }
        result = _adf_to_text(node)
        assert "- one" in result
        assert "- two" in result

    def test_ordered_list(self):
        node = {
            "type": "orderedList",
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "first"}],
                        }
                    ],
                },
            ],
        }
        assert "1. first" in _adf_to_text(node)

    def test_text_marks(self):
        node = {"type": "text", "text": "bold", "marks": [{"type": "strong"}]}
        assert _adf_to_text(node) == "**bold**"

    def test_link_mark(self):
        node = {
            "type": "text",
            "text": "click",
            "marks": [{"type": "link", "attrs": {"href": "https://example.com"}}],
        }
        assert _adf_to_text(node) == "[click](https://example.com)"

    def test_code_block(self):
        node = {"type": "codeBlock", "content": [{"type": "text", "text": "x = 1"}]}
        assert _adf_to_text(node) == "```\nx = 1\n```\n"

    def test_blockquote(self):
        node = {
            "type": "blockquote",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "quoted"}]}
            ],
        }
        assert _adf_to_text(node) == "> quoted\n"

    def test_hard_break(self):
        assert _adf_to_text({"type": "hardBreak"}) == "\n"

    def test_rule(self):
        assert _adf_to_text({"type": "rule"}) == "---\n"

    def test_list_of_nodes(self):
        nodes = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        assert _adf_to_text(nodes) == "ab"


class TestIndent:
    def test_indents_each_line(self):
        assert _indent("a\nb") == "  a\n  b"

    def test_custom_prefix(self):
        assert _indent("a\nb", prefix="> ") == "> a\n> b"

    def test_strips_trailing_whitespace(self):
        assert _indent("a\n") == "  a"


class TestCell:
    def test_empty(self):
        assert _cell("") == ""
        assert _cell(None) == ""

    def test_escapes_pipe(self):
        assert _cell("a|b") == "a\\|b"

    def test_converts_newline_to_br(self):
        assert _cell("a\nb") == "a<br>b"

    def test_strips_carriage_return(self):
        assert _cell("a\r\nb") == "a<br>b"


class TestToTable:
    def test_header_row(self):
        result = _to_table([])
        assert (
            "| Key | Name | Owner | Status | Target | Description | "
            "Latest update | Open risks |" in result
        )

    def test_goal_row(self):
        goal = {
            "key": "TEAM-1",
            "name": "Ship it",
            "owner": {"name": "Alice"},
            "status": {"value": "on_track"},
            "targetDate": {"label": "Q1"},
            "description": None,
            "risks": {"edges": [{"node": {"summary": "Risk 1", "resolvedDate": None}}]},
        }
        result = _to_table([goal])
        assert "TEAM-1" in result
        assert "Ship it" in result
        assert "Alice" in result
        assert "On track" in result
        assert "Q1" in result
        assert "Risk 1" in result

    def test_resolved_risks_excluded(self):
        goal = {
            "key": "TEAM-1",
            "name": "Ship it",
            "risks": {
                "edges": [
                    {"node": {"summary": "Old risk", "resolvedDate": "2026-01-01"}}
                ]
            },
        }
        result = _to_table([goal])
        assert "Old risk" not in result


class TestToMarkdown:
    def test_basic_goal(self):
        goal = {"name": "Ship it", "key": "TEAM-1", "url": "https://example.com/TEAM-1"}
        result = _to_markdown([goal])
        assert "# Goals export (1)" in result
        assert "## Ship it  `TEAM-1`" in result
        assert "URL: https://example.com/TEAM-1" in result

    def test_unnamed_goal(self):
        result = _to_markdown([{}])
        assert "(unnamed)" in result

    def test_includes_owner_status_target(self):
        goal = {
            "name": "Ship it",
            "status": {"value": "at_risk"},
            "owner": {"name": "Bob"},
            "targetDate": {"label": "Q2"},
        }
        result = _to_markdown([goal])
        assert "Status: At risk" in result
        assert "Owner: Bob" in result
        assert "Target: Q2" in result

    def test_archived_flag(self):
        result = _to_markdown([{"name": "Old goal", "isArchived": True}])
        assert "Archived: true" in result

    def test_sub_goals_listed(self):
        goal = {
            "name": "Parent",
            "subGoals": {"edges": [{"node": {"name": "Child", "key": "TEAM-2"}}]},
        }
        result = _to_markdown([goal])
        assert "Sub-goals: 1" in result
        assert "Child (TEAM-2)" in result

    def test_description_rendered(self):
        goal = {
            "name": "Goal",
            "description": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Details here"}],
                    }
                ],
            },
        }
        result = _to_markdown([goal])
        assert "Description:" in result
        assert "Details here" in result


class TestUpdatesToMarkdown:
    def test_header_count(self):
        result = _updates_to_markdown("TEAM-1", [])
        assert "# Updates for TEAM-1 (0)" in result

    def test_transition_and_creator(self):
        update = {
            "creationDate": "2026-01-15T10:00:00Z",
            "oldState": {"value": "on_track"},
            "newState": {"value": "at_risk"},
            "creator": {"name": "Alice"},
            "summary": None,
        }
        result = _updates_to_markdown("TEAM-1", [update])
        assert "## 2026-01-15  On track → At risk  — Alice" in result

    def test_missed_update_flag(self):
        update = {"creationDate": "2026-01-15T10:00:00Z", "missedUpdate": True}
        result = _updates_to_markdown("TEAM-1", [update])
        assert "_missed update_" in result

    def test_live_notes_included_archived_excluded(self):
        update = {
            "creationDate": "2026-01-15T10:00:00Z",
            "updateNotes": {
                "edges": [
                    {
                        "node": {
                            "summary": "Live note",
                            "description": "",
                            "archived": False,
                        }
                    },
                    {
                        "node": {
                            "summary": "Archived note",
                            "description": "",
                            "archived": True,
                        }
                    },
                ]
            },
        }
        result = _updates_to_markdown("TEAM-1", [update])
        assert "Live note" in result
        assert "Archived note" not in result


class TestGetCloudId:
    @patch("zaira.goals.requests.get")
    @patch("zaira.goals.get_jira_site", return_value="foo.atlassian.net")
    def test_fetches_and_caches(self, _mock_site, mock_get):
        resp = MagicMock()
        resp.json.return_value = {"cloudId": "abc-123"}
        mock_get.return_value = resp

        cid = get_cloud_id()

        assert cid == "abc-123"
        mock_get.assert_called_once_with(
            "https://foo.atlassian.net/_edge/tenant_info", timeout=10
        )

    @patch("zaira.goals.requests.get")
    @patch("zaira.goals.get_jira_site", return_value="foo.atlassian.net")
    def test_caches_result(self, _mock_site, mock_get):
        resp = MagicMock()
        resp.json.return_value = {"cloudId": "abc-123"}
        mock_get.return_value = resp

        get_cloud_id()
        get_cloud_id()

        mock_get.assert_called_once()

    @patch("zaira.goals.requests.get")
    @patch("zaira.goals.get_jira_site", return_value="foo.atlassian.net")
    def test_missing_cloud_id_raises(self, _mock_site, mock_get):
        resp = MagicMock()
        resp.json.return_value = {}
        mock_get.return_value = resp

        with pytest.raises(RuntimeError, match="Could not resolve cloudId"):
            get_cloud_id()


class TestPostGraphql:
    @patch(
        "zaira.goals._endpoint",
        return_value="https://foo.atlassian.net/gateway/api/graphql",
    )
    @patch("zaira.goals.requests.post")
    @patch(
        "zaira.goals.get_credentials",
        return_value=("https://foo.atlassian.net", "me@test.com", "tok"),
    )
    def test_returns_data_on_success(self, _mock_creds, mock_post, _mock_endpoint):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"foo": "bar"}}
        mock_post.return_value = resp

        result = _post_graphql("query {}", {"a": 1})

        assert result == {"foo": "bar"}
        _, kwargs = mock_post.call_args
        assert kwargs["auth"] == ("me@test.com", "tok")
        assert kwargs["json"] == {"query": "query {}", "variables": {"a": 1}}

    @patch(
        "zaira.goals._endpoint",
        return_value="https://foo.atlassian.net/gateway/api/graphql",
    )
    @patch("zaira.goals.requests.post")
    @patch(
        "zaira.goals.get_credentials",
        return_value=("https://foo.atlassian.net", "me@test.com", "tok"),
    )
    def test_raises_on_http_error(self, _mock_creds, mock_post, _mock_endpoint):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "server error"
        mock_post.return_value = resp

        with pytest.raises(RuntimeError, match="GraphQL HTTP 500"):
            _post_graphql("query {}", {})

    @patch(
        "zaira.goals._endpoint",
        return_value="https://foo.atlassian.net/gateway/api/graphql",
    )
    @patch("zaira.goals.requests.post")
    @patch(
        "zaira.goals.get_credentials",
        return_value=("https://foo.atlassian.net", "me@test.com", "tok"),
    )
    def test_raises_on_graphql_errors(self, _mock_creds, mock_post, _mock_endpoint):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"errors": [{"message": "bad query"}], "data": None}
        mock_post.return_value = resp

        with pytest.raises(RuntimeError, match="GraphQL errors"):
            _post_graphql("query {}", {})


class TestSearchGoals:
    @patch("zaira.goals._post_graphql")
    def test_single_page(self, mock_post):
        mock_post.return_value = {
            "goals_search": {
                "edges": [{"node": {"key": "TEAM-1"}}, {"node": {"key": "TEAM-2"}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

        result = search_goals("cloud-1")

        assert [g["key"] for g in result] == ["TEAM-1", "TEAM-2"]
        mock_post.assert_called_once()

    @patch("zaira.goals._post_graphql")
    def test_pagination(self, mock_post):
        mock_post.side_effect = [
            {
                "goals_search": {
                    "edges": [{"node": {"key": "TEAM-1"}}],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                }
            },
            {
                "goals_search": {
                    "edges": [{"node": {"key": "TEAM-2"}}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            },
        ]

        result = search_goals("cloud-1")

        assert [g["key"] for g in result] == ["TEAM-1", "TEAM-2"]
        assert mock_post.call_count == 2

    @patch("zaira.goals._post_graphql")
    def test_full_fields_includes_extra_query_fields(self, mock_post):
        mock_post.return_value = {
            "goals_search": {"edges": [], "pageInfo": {"hasNextPage": False}}
        }

        search_goals("cloud-1", full=True)

        query = mock_post.call_args[0][0]
        assert "isPrivate" in query  # only present in FULL_FIELDS

    @patch("zaira.goals._post_graphql")
    def test_with_updates_appends_update_fields(self, mock_post):
        mock_post.return_value = {
            "goals_search": {"edges": [], "pageInfo": {"hasNextPage": False}}
        }

        search_goals("cloud-1", with_updates=True)

        query = mock_post.call_args[0][0]
        assert "updates(first: 20)" in query

    @patch("zaira.goals._post_graphql")
    def test_empty_result(self, mock_post):
        mock_post.return_value = {}

        result = search_goals("cloud-1")

        assert result == []


class TestGetGoal:
    @patch("zaira.goals._post_graphql")
    def test_by_key(self, mock_post):
        mock_post.return_value = {"goals_byKey": {"key": "TEAM-1", "name": "Ship it"}}

        result = get_goal("TEAM-1", cloud_id="cloud-1")

        assert result == {"key": "TEAM-1", "name": "Ship it"}
        _, variables = mock_post.call_args[0]
        assert variables == {
            "containerId": "ari:cloud:townsquare::site/cloud-1",
            "goalKey": "TEAM-1",
        }

    @patch("zaira.goals._post_graphql")
    def test_by_ari(self, mock_post):
        mock_post.return_value = {"goals_byId": {"id": "ari:cloud:townsquare::goal/1"}}

        result = get_goal("ari:cloud:townsquare::goal/1")

        assert result == {"id": "ari:cloud:townsquare::goal/1"}
        _, variables = mock_post.call_args[0]
        assert variables == {"id": "ari:cloud:townsquare::goal/1"}

    @patch("zaira.goals.get_cloud_id", return_value="auto-cloud")
    @patch("zaira.goals._post_graphql")
    def test_resolves_cloud_id_when_missing(self, mock_post, _mock_cloud):
        mock_post.return_value = {"goals_byKey": {"key": "TEAM-1"}}

        get_goal("TEAM-1")

        _, variables = mock_post.call_args[0]
        assert variables["containerId"] == "ari:cloud:townsquare::site/auto-cloud"


class TestBatchGetGoals:
    @patch("zaira.goals.search_goals")
    def test_plain_keys_found(self, mock_search):
        mock_search.return_value = [{"key": "TEAM-1"}, {"key": "TEAM-2"}]

        goals_out, missing = _batch_get_goals(
            ["TEAM-1", "TEAM-2"], full=False, cloud_id="cloud-1"
        )

        assert len(goals_out) == 2
        assert missing == []

    @patch("zaira.goals.search_goals")
    def test_missing_keys_reported(self, mock_search):
        mock_search.return_value = [{"key": "TEAM-1"}]

        goals_out, missing = _batch_get_goals(
            ["TEAM-1", "TEAM-2"], full=False, cloud_id="cloud-1"
        )

        assert missing == ["TEAM-2"]

    @patch("zaira.goals._post_graphql")
    def test_ari_keys_use_goals_by_ids(self, mock_post):
        mock_post.return_value = {"goals_byIds": [{"id": "ari:1"}]}

        goals_out, missing = _batch_get_goals(["ari:1"], full=False, cloud_id="cloud-1")

        assert goals_out == [{"id": "ari:1"}]
        assert missing == []

    @patch("zaira.goals._post_graphql")
    def test_missing_ari_reported(self, mock_post):
        mock_post.return_value = {"goals_byIds": []}

        goals_out, missing = _batch_get_goals(["ari:1"], full=False, cloud_id="cloud-1")

        assert missing == ["ari:1"]


class TestGetGoalUpdates:
    @patch("zaira.goals._post_graphql")
    def test_by_key(self, mock_post):
        mock_post.return_value = {
            "goals_byKey": {"updates": {"edges": [{"node": {"uuid": "u1"}}]}}
        }

        result = get_goal_updates("TEAM-1", cloud_id="cloud-1")

        assert result == [{"uuid": "u1"}]

    @patch("zaira.goals._post_graphql")
    def test_by_ari(self, mock_post):
        mock_post.return_value = {
            "goals_byId": {"updates": {"edges": [{"node": {"uuid": "u2"}}]}}
        }

        result = get_goal_updates("ari:cloud:townsquare::goal/1")

        assert result == [{"uuid": "u2"}]

    @patch("zaira.goals._post_graphql")
    def test_no_updates(self, mock_post):
        mock_post.return_value = {"goals_byKey": {}}

        result = get_goal_updates("TEAM-1", cloud_id="cloud-1")

        assert result == []


class TestGoalsCommand:
    def test_dispatches_to_goals_func(self):
        called = {}

        def fake_func(args: argparse.Namespace) -> None:
            called["ran"] = True

        goals_command(argparse.Namespace(goals_func=fake_func))

        assert called["ran"] is True

    def test_no_subcommand_prints_usage(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            goals_command(argparse.Namespace())

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage: zaira goals" in captured.err


class TestExportCommand:
    @patch("zaira.goals.search_goals")
    def test_requires_cloud_id(self, mock_search, capsys):
        args = argparse.Namespace(
            cloud_id=None, tql=None, url=None, full=False, format=None, output=None
        )

        with pytest.raises(SystemExit) as exc_info:
            export_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "cloudId required" in captured.err
        mock_search.assert_not_called()

    @patch("zaira.goals.search_goals")
    def test_defaults_tql_when_missing(self, mock_search):
        mock_search.return_value = []
        args = argparse.Namespace(
            cloud_id="cloud-1",
            tql=None,
            url=None,
            full=False,
            format="json",
            output=None,
        )

        export_command(args)

        _, kwargs = mock_search.call_args
        assert kwargs["tql"] == "archived = false"

    @patch("zaira.goals.search_goals")
    def test_url_supplies_cloud_id_and_tql(self, mock_search):
        mock_search.return_value = []
        args = argparse.Namespace(
            cloud_id=None,
            tql=None,
            url=(
                "https://home.atlassian.com/o/org1/goals"
                "?cloudId=cloud-9&tql=archived%20%3D%20false"
            ),
            full=False,
            format="json",
            output=None,
        )

        export_command(args)

        call_args, kwargs = mock_search.call_args
        assert call_args[0] == "cloud-9"
        assert kwargs["tql"] == "archived = false"

    @patch("zaira.goals.search_goals")
    def test_table_format_output(self, mock_search, capsys):
        mock_search.return_value = [{"key": "TEAM-1", "name": "Ship it"}]
        args = argparse.Namespace(
            cloud_id="cloud-1",
            tql=None,
            url=None,
            full=False,
            format="table",
            output=None,
        )

        export_command(args)

        captured = capsys.readouterr()
        assert "| Key | Name" in captured.out
        assert "TEAM-1" in captured.out

    @patch("zaira.goals.search_goals")
    def test_writes_to_file(self, mock_search, tmp_path, capsys):
        mock_search.return_value = [{"key": "TEAM-1", "name": "Ship it"}]
        out_file = tmp_path / "goals.md"
        args = argparse.Namespace(
            cloud_id="cloud-1",
            tql=None,
            url=None,
            full=False,
            format=None,
            output=str(out_file),
        )

        export_command(args)

        assert out_file.exists()
        assert "TEAM-1" in out_file.read_text()
        captured = capsys.readouterr()
        assert "Wrote 1 goals" in captured.out

    @patch("zaira.goals.search_goals", side_effect=RuntimeError("boom"))
    def test_error_exits(self, _mock_search, capsys):
        args = argparse.Namespace(
            cloud_id="cloud-1", tql=None, url=None, full=False, format=None, output=None
        )

        with pytest.raises(SystemExit) as exc_info:
            export_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "boom" in captured.err


class TestGetCommand:
    @patch("zaira.goals.get_goal")
    def test_single_key_found(self, mock_get_goal, capsys):
        mock_get_goal.return_value = {"key": "TEAM-1", "name": "Ship it"}
        args = argparse.Namespace(
            keys=["TEAM-1"], format="json", output=None, minimal=False, cloud_id=None
        )

        get_command(args)

        mock_get_goal.assert_called_once_with("TEAM-1", full=True, cloud_id=None)
        captured = capsys.readouterr()
        assert "TEAM-1" in captured.out

    @patch("zaira.goals.get_goal")
    def test_single_key_missing_exits(self, mock_get_goal, capsys):
        mock_get_goal.return_value = None
        args = argparse.Namespace(
            keys=["TEAM-9"], format="json", output=None, minimal=False, cloud_id=None
        )

        with pytest.raises(SystemExit) as exc_info:
            get_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Goal not found: TEAM-9" in captured.err

    @patch("zaira.goals._batch_get_goals")
    def test_multiple_keys(self, mock_batch, capsys):
        mock_batch.return_value = ([{"key": "TEAM-1"}, {"key": "TEAM-2"}], [])
        args = argparse.Namespace(
            keys=["TEAM-1", "TEAM-2"],
            format="json",
            output=None,
            minimal=False,
            cloud_id=None,
        )

        get_command(args)

        captured = capsys.readouterr()
        assert "TEAM-1" in captured.out
        assert "TEAM-2" in captured.out

    @patch("zaira.goals._batch_get_goals")
    def test_writes_to_directory(self, mock_batch, tmp_path):
        mock_batch.return_value = (
            [{"key": "TEAM-1", "name": "A"}, {"key": "TEAM-2", "name": "B"}],
            [],
        )
        out_dir = tmp_path / "goals"
        args = argparse.Namespace(
            keys=["TEAM-1", "TEAM-2"],
            format="md",
            output=str(out_dir),
            minimal=False,
            cloud_id=None,
        )

        get_command(args)

        assert (out_dir / "TEAM-1.md").exists()
        assert (out_dir / "TEAM-2.md").exists()

    @patch("zaira.goals.get_goal")
    def test_error_exits(self, mock_get_goal, capsys):
        mock_get_goal.side_effect = RuntimeError("network fail")
        args = argparse.Namespace(
            keys=["TEAM-1"], format="json", output=None, minimal=False, cloud_id=None
        )

        with pytest.raises(SystemExit) as exc_info:
            get_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "network fail" in captured.err


class TestUpdatesCommand:
    @patch("zaira.goals.get_goal_updates")
    def test_prints_markdown_by_default(self, mock_updates, capsys):
        mock_updates.return_value = [
            {"creationDate": "2026-01-15T10:00:00Z", "creator": {"name": "Alice"}}
        ]
        args = argparse.Namespace(
            key="TEAM-1", cloud_id=None, limit=50, format=None, output=None
        )

        updates_command(args)

        captured = capsys.readouterr()
        assert "# Updates for TEAM-1" in captured.out

    @patch("zaira.goals.get_goal_updates")
    def test_json_format(self, mock_updates, capsys):
        mock_updates.return_value = [{"uuid": "u1"}]
        args = argparse.Namespace(
            key="TEAM-1", cloud_id=None, limit=50, format="json", output=None
        )

        updates_command(args)

        captured = capsys.readouterr()
        assert '"uuid": "u1"' in captured.out

    @patch("zaira.goals.get_goal_updates")
    def test_writes_to_file(self, mock_updates, tmp_path, capsys):
        mock_updates.return_value = [
            {"uuid": "u1", "creationDate": "2026-01-15T10:00:00Z"}
        ]
        out_file = tmp_path / "updates.md"
        args = argparse.Namespace(
            key="TEAM-1", cloud_id=None, limit=50, format=None, output=str(out_file)
        )

        updates_command(args)

        assert out_file.exists()
        captured = capsys.readouterr()
        assert "Wrote 1 updates" in captured.out

    @patch("zaira.goals.get_goal_updates", side_effect=RuntimeError("nope"))
    def test_error_exits(self, _mock_updates, capsys):
        args = argparse.Namespace(
            key="TEAM-1", cloud_id=None, limit=50, format=None, output=None
        )

        with pytest.raises(SystemExit) as exc_info:
            updates_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "nope" in captured.err
