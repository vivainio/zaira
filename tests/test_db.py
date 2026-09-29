"""Tests for the db (SQLite snapshot) module."""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zaira import db
from zaira.errors import ApplicationError

STATUSES = {
    "To Do": ("new", "To Do"),
    "In Progress": ("indeterminate", "In Progress"),
    "Review": ("indeterminate", "In Progress"),
    "Done": ("done", "Done"),
}


def _user(uid: str, name: str) -> dict[str, Any]:
    return {"accountId": uid, "displayName": name, "emailAddress": f"{uid}@x.io"}


def _history(hid: int, ts: str, frm: str, to: str) -> dict[str, Any]:
    return {
        "id": str(hid),
        "created": ts,
        "author": _user("u1", "Alice"),
        "items": [
            {"field": "status", "fromString": frm, "toString": to},
            {"field": "assignee", "fromString": None, "toString": "Alice"},
        ],
    }


def _raw_issue(
    key: str = "AC-1",
    status: str = "Done",
    category: str = "done",
    histories: list[dict] | None = None,
) -> dict[str, Any]:
    histories = histories or []
    return {
        "id": "10001",
        "key": key,
        "fields": {
            "summary": f"Summary of {key}",
            "description": "h2. Heading\n\nSome *bold* text",
            "project": {"key": "AC"},
            "issuetype": {"name": "Story"},
            "status": {
                "name": status,
                "statusCategory": {"key": category, "name": status},
            },
            "priority": {"name": "High"},
            "resolution": {"name": "Fixed"} if category == "done" else None,
            "assignee": _user("u1", "Alice"),
            "reporter": _user("u2", "Bob"),
            "creator": _user("u2", "Bob"),
            "parent": {"key": "AC-100"},
            "created": "2026-01-01T09:00:00.000+0200",
            "updated": "2026-01-10T12:00:00.000+0000",
            "resolutiondate": "2026-01-10T12:00:00.000+0000"
            if category == "done"
            else None,
            "duedate": "2026-02-01",
            "labels": ["b", "a", "a"],
            "components": [{"name": "API"}, {"name": "API"}],
            "fixVersions": [{"name": "1.0"}],
            "customfield_1": {"value": "Team Red"},
            "customfield_2": None,
            "customfield_20": [
                {
                    "id": 7,
                    "name": "Sprint 7",
                    "state": "closed",
                    "boardId": 3,
                    "startDate": "2026-01-01T00:00:00.000Z",
                    "endDate": "2026-01-14T00:00:00.000Z",
                    "completeDate": "2026-01-14T10:00:00.000Z",
                }
            ],
            "issuelinks": [
                {
                    "type": {
                        "name": "Blocks",
                        "outward": "blocks",
                        "inward": "is blocked by",
                    },
                    "outwardIssue": {"key": "AC-2"},
                }
            ],
            "comment": {
                "total": 1,
                "comments": [
                    {
                        "id": "500",
                        "author": _user("u2", "Bob"),
                        "created": "2026-01-02T10:00:00.000+0000",
                        "updated": "2026-01-02T10:00:00.000+0000",
                        "body": "Looks good",
                    }
                ],
            },
            "attachment": [
                {
                    "id": "900",
                    "filename": "a.png",
                    "size": 10,
                    "mimeType": "image/png",
                    "author": _user("u1", "Alice"),
                    "created": "2026-01-02T10:00:00.000+0000",
                }
            ],
        },
        "changelog": {"total": len(histories), "histories": histories},
    }


FLOW = [
    # deliberately out of order: rows must be sorted by time
    _history(3, "2026-01-05T09:00:00.000+0000", "In Progress", "Done"),
    _history(1, "2026-01-02T09:00:00.000+0000", "To Do", "In Progress"),
    _history(4, "2026-01-06T09:00:00.000+0000", "Done", "In Progress"),
    _history(5, "2026-01-10T12:00:00.000+0000", "In Progress", "Done"),
]

FIELD_NAMES = {"customfield_1": "Team", "customfield_20": "Sprint"}
SPRINT_FIELDS = {"customfield_20"}


def _rows(raw: dict[str, Any]) -> db.IssueRows:
    return db.extract_issue_rows(
        raw,
        raw["changelog"]["histories"],
        raw["fields"]["comment"]["comments"],
        FIELD_NAMES,
        SPRINT_FIELDS,
    )


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = db.connect(tmp_path / "z.db")
    yield c
    c.close()


def _write(conn: sqlite3.Connection, scope: str, raws: list[dict], synced: str) -> None:
    db.write_scope(
        conn,
        scope,
        f"jql for {scope}",
        [_rows(r) for r in raws],
        STATUSES,
        "example.atlassian.net",
        synced,
    )


class TestToUtc:
    def test_offset_converted(self) -> None:
        assert db.to_utc("2026-01-01T09:00:00.000+0200") == "2026-01-01T07:00:00Z"

    def test_zulu(self) -> None:
        assert db.to_utc("2026-01-01T00:00:00.000Z") == "2026-01-01T00:00:00Z"

    def test_empty(self) -> None:
        assert db.to_utc(None) is None
        assert db.to_utc("") is None

    def test_unparseable_passthrough(self) -> None:
        assert db.to_utc("garbage") == "garbage"


class TestParseSprint:
    def test_cloud_dict(self) -> None:
        s = db.parse_sprint({"id": 7, "name": "S7", "state": "ACTIVE", "boardId": 3})
        assert s is not None
        assert (s["id"], s["name"], s["state"], s["board_id"]) == (
            7,
            "S7",
            "active",
            3,
        )

    def test_server_string(self) -> None:
        s = db.parse_sprint(
            "com.atlassian.greenhopper.service.sprint.Sprint@1a2b[id=12,"
            "rapidViewId=4,state=CLOSED,name=Sprint 12,"
            "startDate=2026-01-01T00:00:00.000Z,endDate=<null>,sequence=12]"
        )
        assert s is not None
        assert (s["id"], s["name"], s["state"], s["board_id"]) == (
            12,
            "Sprint 12",
            "closed",
            4,
        )
        assert s["start_date"] == "2026-01-01T00:00:00Z"
        assert s["end_date"] is None

    def test_invalid(self) -> None:
        assert db.parse_sprint("nonsense") is None
        assert db.parse_sprint({"name": "no id"}) is None
        assert db.parse_sprint(42) is None


class TestExtractIssueRows:
    def test_core_fields(self) -> None:
        rows = _rows(_raw_issue(histories=FLOW))
        issue = rows.issue
        assert issue["key"] == "AC-1"
        assert issue["status_category"] == "done"
        assert issue["assignee_id"] == "u1"
        assert issue["created"] == "2026-01-01T07:00:00Z"
        assert issue["parent_key"] == "AC-100"
        assert "## Heading" in issue["description"]
        assert json.loads(issue["raw"])["summary"] == "Summary of AC-1"

    def test_lists_deduplicated(self) -> None:
        rows = _rows(_raw_issue())
        assert rows.labels == ["a", "b"]
        assert rows.components == ["API"]
        assert rows.fix_versions == ["1.0"]

    def test_custom_fields_named_and_nulls_skipped(self) -> None:
        rows = _rows(_raw_issue())
        by_id = {fid: (name, value) for fid, name, value in rows.custom_fields}
        assert by_id["customfield_1"] == ("Team", '"Team Red"')
        assert "customfield_2" not in by_id

    def test_sprints(self) -> None:
        rows = _rows(_raw_issue())
        assert [s["id"] for s in rows.sprints] == [7]

    def test_links(self) -> None:
        rows = _rows(_raw_issue())
        assert rows.links == [("AC-2", "Blocks", "outward", "blocks")]

    def test_transitions_sorted_and_status_only(self) -> None:
        rows = _rows(_raw_issue(histories=FLOW))
        assert [
            (t["seq"], t["from_status"], t["to_status"]) for t in rows.transitions
        ] == [
            (0, "To Do", "In Progress"),
            (1, "In Progress", "Done"),
            (2, "Done", "In Progress"),
            (3, "In Progress", "Done"),
        ]

    def test_users_collected(self) -> None:
        rows = _rows(_raw_issue(histories=FLOW))
        assert rows.users["u2"]["display_name"] == "Bob"
        assert set(rows.users) == {"u1", "u2"}


class TestWriteScope:
    def test_v_issues_flow_metrics(self, conn: sqlite3.Connection) -> None:
        _write(conn, "team", [_raw_issue(histories=FLOW)], "2026-01-20T00:00:00Z")
        row = conn.execute(
            "SELECT assignee, labels, sprint, first_in_progress, done_at, "
            "reopen_count, cycle_time_days, url FROM v_issues"
        ).fetchone()
        assert row == (
            "Alice",
            "a, b",
            "Sprint 7",
            "2026-01-02T09:00:00Z",
            "2026-01-10T12:00:00Z",
            1,
            8.13,
            "https://example.atlassian.net/browse/AC-1",
        )

    def test_wip_age_for_in_progress(self, conn: sqlite3.Connection) -> None:
        raw = _raw_issue(
            status="In Progress", category="indeterminate", histories=FLOW[1:2]
        )
        _write(conn, "team", [raw], "2026-01-12T09:00:00Z")
        done_at, wip_age = conn.execute(
            "SELECT done_at, wip_age_days FROM v_issues"
        ).fetchone()
        assert done_at is None
        assert wip_age == 10.0

    def test_status_intervals(self, conn: sqlite3.Connection) -> None:
        _write(conn, "team", [_raw_issue(histories=FLOW)], "2026-01-20T00:00:00Z")
        rows = conn.execute(
            "SELECT status, entered_at, left_at FROM v_status_intervals "
            "ORDER BY entered_at"
        ).fetchall()
        assert rows == [
            ("To Do", "2026-01-01T07:00:00Z", "2026-01-02T09:00:00Z"),
            ("In Progress", "2026-01-02T09:00:00Z", "2026-01-05T09:00:00Z"),
            ("Done", "2026-01-05T09:00:00Z", "2026-01-06T09:00:00Z"),
            ("In Progress", "2026-01-06T09:00:00Z", "2026-01-10T12:00:00Z"),
            ("Done", "2026-01-10T12:00:00Z", None),
        ]
        seconds = conn.execute(
            "SELECT seconds FROM v_status_intervals WHERE left_at IS NULL"
        ).fetchone()[0]
        assert seconds == (9 * 24 + 12) * 3600

    def test_issue_without_transitions_has_one_interval(
        self, conn: sqlite3.Connection
    ) -> None:
        _write(conn, "team", [_raw_issue()], "2026-01-20T00:00:00Z")
        rows = conn.execute("SELECT status, left_at FROM v_status_intervals").fetchall()
        assert rows == [("Done", None)]

    def test_resync_replaces_scope(self, conn: sqlite3.Connection) -> None:
        _write(conn, "team", [_raw_issue("AC-1"), _raw_issue("AC-2")], "t1")
        _write(conn, "team", [_raw_issue("AC-2")], "t2")
        keys = [r[0] for r in conn.execute("SELECT key FROM issues")]
        assert keys == ["AC-2"]
        # child rows of the removed issue cascade away; sprint still referenced
        assert conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM sprints").fetchone()[0] == 1
        assert conn.execute(
            "SELECT issue_count, synced_at FROM scopes WHERE name = 'team'"
        ).fetchone() == (1, "t2")

    def test_issue_kept_while_in_another_scope(self, conn: sqlite3.Connection) -> None:
        _write(conn, "a", [_raw_issue("AC-1")], "t1")
        _write(conn, "b", [_raw_issue("AC-1")], "t1")
        _write(conn, "a", [], "t2")
        assert conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 1
        _write(conn, "b", [], "t3")
        assert conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sprints").fetchone()[0] == 0

    def test_failure_rolls_back(self, conn: sqlite3.Connection) -> None:
        _write(conn, "team", [_raw_issue("AC-1")], "t1")
        bad = _rows(_raw_issue("AC-2"))
        bad.issue["bogus_column"] = 1
        with pytest.raises(sqlite3.OperationalError):
            db.write_scope(conn, "team", "jql", [bad], STATUSES, "site", "t2")
        keys = [r[0] for r in conn.execute("SELECT key FROM issues")]
        assert keys == ["AC-1"]


class TestConnect:
    def test_sets_version(self, tmp_path: Path) -> None:
        c = db.connect(tmp_path / "z.db")
        assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        c.close()

    def test_version_mismatch_recreates(self, tmp_path: Path) -> None:
        path = tmp_path / "z.db"
        c = db.connect(path)
        _write(c, "team", [_raw_issue()], "t1")
        c.execute("PRAGMA user_version = 999")
        c.close()
        c = db.connect(path)
        assert c.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0
        assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        c.close()


class TestFormatRows:
    def test_table(self) -> None:
        out = db.format_rows(["a", "bb"], [(1, None), ("x\ny", "z")], "table")
        assert out.splitlines() == ["a    bb", "---  --", "1", "x y  z"]

    def test_csv(self) -> None:
        assert db.format_rows(["a"], [(1,)], "csv") == "a\n1"

    def test_json(self) -> None:
        assert json.loads(db.format_rows(["a"], [(1,)], "json")) == [{"a": 1}]


class TestQueryCommand:
    def _args(self, path: Path, sql: str) -> argparse.Namespace:
        return argparse.Namespace(db=str(path), sql=sql, format="csv")

    def test_select(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        path = tmp_path / "z.db"
        c = db.connect(path)
        _write(c, "team", [_raw_issue()], "t1")
        c.close()
        db.query_command(self._args(path, "SELECT key, status FROM v_issues"))
        assert capsys.readouterr().out.strip() == "key,status\nAC-1,Done"

    def test_read_only(self, tmp_path: Path) -> None:
        path = tmp_path / "z.db"
        db.connect(path).close()
        with pytest.raises(ApplicationError, match="readonly"):
            db.query_command(self._args(path, "DELETE FROM issues"))

    def test_missing_db(self, tmp_path: Path) -> None:
        with pytest.raises(ApplicationError, match="not found"):
            db.query_command(self._args(tmp_path / "none.db", "SELECT 1"))


def _write_project(tmp_path: Path, body: str) -> None:
    (tmp_path / "zproject.toml").write_text(body)


class TestResolveScopes:
    def _args(self, **kw: Any) -> argparse.Namespace:
        return argparse.Namespace(**{"scopes": [], "jql": None, "name": None, **kw})

    def test_jql(self) -> None:
        assert db._resolve_scopes(self._args(jql="x = 1", name="n")) == [("n", "x = 1")]
        assert db._resolve_scopes(self._args(jql="x = 1")) == [("adhoc", "x = 1")]

    def test_named_and_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_project(
            tmp_path,
            '[queries]\nmine = "assignee = currentUser()"\nall = "project = AC"\n'
            '[db]\nscopes = ["all"]\n',
        )
        sub = tmp_path / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)
        assert db._resolve_scopes(self._args(scopes=["mine"])) == [
            ("mine", "assignee = currentUser()")
        ]
        assert db._resolve_scopes(self._args()) == [("all", "project = AC")]

    def test_unknown_query(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_project(tmp_path, "[queries]\n")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ApplicationError, match="unknown query"):
            db._resolve_scopes(self._args(scopes=["nope"]))

    def test_nothing_configured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ApplicationError, match="no scopes"):
            db._resolve_scopes(self._args())


class TestDbPath:
    def test_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from zaira.config import get_db_path

        _write_project(tmp_path, "")
        (tmp_path / "sub").mkdir()
        monkeypatch.chdir(tmp_path / "sub")
        assert get_db_path() == tmp_path / "zaira.db"
        _write_project(tmp_path, '[db]\npath = "data/snap.db"\n')
        assert get_db_path() == tmp_path / "data" / "snap.db"

    def test_outside_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from zaira.config import get_db_path

        monkeypatch.chdir(tmp_path)
        assert get_db_path() == tmp_path / "zaira.db"


class TestFetch:
    def test_truncated_changelog_and_comments_fetched(
        self, mock_jira: MagicMock
    ) -> None:
        raw = _raw_issue(histories=FLOW[:1])
        raw["changelog"]["total"] = 2
        raw["fields"]["comment"]["total"] = 2
        extra_comment = {**raw["fields"]["comment"]["comments"][0], "id": "501"}

        def get_json(path: str, params: dict) -> dict:
            if path.endswith("/changelog"):
                return {"values": FLOW[:2], "total": 2, "isLast": True}
            return {
                "comments": [raw["fields"]["comment"]["comments"][0], extra_comment],
                "total": 2,
            }

        mock_jira._get_json.side_effect = get_json
        mock_jira.search_issues.return_value = [MagicMock(raw=raw)]
        with patch.object(
            db, "_field_metadata", return_value=(FIELD_NAMES, SPRINT_FIELDS)
        ):
            (rows,) = db.fetch_scope("project = AC")
        assert len(rows.transitions) == 2
        assert [c["id"] for c in rows.comments] == ["500", "501"]
        mock_jira.search_issues.assert_called_once_with(
            "project = AC", maxResults=False, fields="*all", expand="changelog"
        )

    def test_sync_command_end_to_end(
        self, mock_jira: MagicMock, tmp_path: Path
    ) -> None:
        mock_jira.search_issues.return_value = [
            MagicMock(raw=_raw_issue(histories=FLOW))
        ]
        mock_jira.statuses.return_value = [
            MagicMock(raw={"name": n, "statusCategory": {"key": k, "name": cn}})
            for n, (k, cn) in STATUSES.items()
        ]
        path = tmp_path / "z.db"
        args = argparse.Namespace(
            scopes=[], jql="project = AC", name=None, db=str(path)
        )
        with (
            patch.object(
                db, "_field_metadata", return_value=(FIELD_NAMES, SPRINT_FIELDS)
            ),
            patch.object(db, "get_jira_site", return_value="example.atlassian.net"),
        ):
            db.sync_command(args)
        c = sqlite3.connect(path)
        assert c.execute("SELECT key, reopen_count FROM v_issues").fetchall() == [
            ("AC-1", 1)
        ]
        assert c.execute("SELECT COUNT(*) FROM statuses").fetchone()[0] == 4
        c.close()
