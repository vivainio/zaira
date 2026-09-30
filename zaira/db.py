"""SQLite snapshot of Jira issues for follow-up querying and dashboards.

The database is a snapshot of current state, rebuilt per scope on every
sync. Scopes are named JQL queries; an issue stays in the database as long
as at least one synced scope contains it.

Consumers should prefer the ``v_*`` views over the base tables: the views
are the stable, renderer-facing contract.
"""

import argparse
import csv
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zaira.config import get_db_path, get_db_scopes, get_project_query
from zaira.errors import ApplicationError
from zaira.export_fields import extract_custom_field_value, extract_description
from zaira.info import ensure_fields_cached, load_schema
from zaira.jira_client import format_jira_error, get_jira, get_jira_site

SCHEMA_VERSION = 1

SCHEMA_SQL = """\
CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- One row per synced scope (named JQL query).
CREATE TABLE scopes (
  name        TEXT PRIMARY KEY,
  jql         TEXT NOT NULL,
  synced_at   TEXT NOT NULL,
  issue_count INTEGER NOT NULL
);

CREATE TABLE issue_scopes (
  scope TEXT NOT NULL,
  key   TEXT NOT NULL,
  PRIMARY KEY (scope, key)
);

CREATE TABLE users (
  id           TEXT PRIMARY KEY,   -- accountId (Cloud) or key/name (Server/DC)
  display_name TEXT,
  email        TEXT
);

CREATE TABLE statuses (
  name          TEXT PRIMARY KEY,
  category      TEXT,              -- new | indeterminate | done
  category_name TEXT               -- To Do | In Progress | Done
);

-- All timestamps are ISO-8601 UTC ('YYYY-MM-DDTHH:MM:SSZ'); dates are 'YYYY-MM-DD'.
CREATE TABLE issues (
  key             TEXT PRIMARY KEY,
  id              TEXT NOT NULL,
  project         TEXT,
  issuetype       TEXT,
  summary         TEXT,
  description     TEXT,            -- markdown
  status          TEXT,
  status_category TEXT,            -- new | indeterminate | done
  priority        TEXT,
  resolution      TEXT,
  assignee_id     TEXT,
  reporter_id     TEXT,
  creator_id      TEXT,
  parent_key      TEXT,
  created         TEXT,
  updated         TEXT,
  resolved        TEXT,
  due             TEXT,
  raw             TEXT             -- full Jira 'fields' object as JSON
);

CREATE TABLE labels (
  key   TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  label TEXT NOT NULL,
  PRIMARY KEY (key, label)
);

CREATE TABLE components (
  key  TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  name TEXT NOT NULL,
  PRIMARY KEY (key, name)
);

CREATE TABLE fix_versions (
  key  TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  name TEXT NOT NULL,
  PRIMARY KEY (key, name)
);

CREATE TABLE custom_fields (
  key      TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  field_id TEXT NOT NULL,
  name     TEXT,                   -- human-readable field name, if known
  value    TEXT,                   -- JSON-encoded simplified value
  PRIMARY KEY (key, field_id)
);

CREATE TABLE sprints (
  id       INTEGER PRIMARY KEY,
  name     TEXT,
  state    TEXT,                   -- future | active | closed
  board_id INTEGER,
  start_date    TEXT,
  end_date      TEXT,
  complete_date TEXT
);

CREATE TABLE issue_sprints (
  key       TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  sprint_id INTEGER NOT NULL,
  PRIMARY KEY (key, sprint_id)
);

CREATE TABLE links (
  key       TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  other_key TEXT NOT NULL,
  link_type TEXT NOT NULL,         -- e.g. Blocks
  direction TEXT NOT NULL,         -- outward | inward
  relation  TEXT,                  -- e.g. 'blocks' / 'is blocked by'
  PRIMARY KEY (key, other_key, link_type, direction)
);

CREATE TABLE comments (
  id        TEXT PRIMARY KEY,
  key       TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  author_id TEXT,
  created   TEXT,
  updated   TEXT,
  body      TEXT                   -- markdown
);

CREATE TABLE attachments (
  id        TEXT PRIMARY KEY,
  key       TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  filename  TEXT,
  size      INTEGER,
  mime      TEXT,
  author_id TEXT,
  created   TEXT
);

-- Status changes from the issue changelog.
CREATE TABLE transitions (
  key         TEXT NOT NULL REFERENCES issues(key) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,    -- 0-based order within the issue
  ts          TEXT NOT NULL,
  author_id   TEXT,
  from_status TEXT,
  to_status   TEXT,
  PRIMARY KEY (key, seq)
);

CREATE INDEX idx_issue_scopes_key ON issue_scopes(key);
CREATE INDEX idx_issues_project_status ON issues(project, status);
CREATE INDEX idx_issues_assignee ON issues(assignee_id);
CREATE INDEX idx_issues_parent ON issues(parent_key);
CREATE INDEX idx_custom_fields_name ON custom_fields(name);
CREATE INDEX idx_issue_sprints_sprint ON issue_sprints(sprint_id);
CREATE INDEX idx_links_other ON links(other_key);
CREATE INDEX idx_comments_key ON comments(key);
CREATE INDEX idx_attachments_key ON attachments(key);
CREATE INDEX idx_transitions_to ON transitions(to_status);

-- Time spent in each status. 'left_at' is NULL for the current status;
-- 'seconds' then runs up to the snapshot time.
CREATE VIEW v_status_intervals AS
WITH ordered AS (
  SELECT key, seq, ts, from_status, to_status,
         LEAD(ts) OVER (PARTITION BY key ORDER BY seq) AS next_ts
  FROM transitions
),
intervals AS (
  SELECT o.key, o.from_status AS status, i.created AS entered_at, o.ts AS left_at
  FROM ordered o JOIN issues i ON i.key = o.key
  WHERE o.seq = 0
  UNION ALL
  SELECT key, to_status, ts, next_ts FROM ordered
  UNION ALL
  SELECT key, status, created, NULL FROM issues
  WHERE key NOT IN (SELECT key FROM transitions)
)
SELECT
  iv.key, iv.status, s.category AS status_category, iv.entered_at, iv.left_at,
  CAST(ROUND((julianday(COALESCE(iv.left_at,
      (SELECT value FROM meta WHERE key = 'synced_at')))
    - julianday(iv.entered_at)) * 86400) AS INTEGER) AS seconds
FROM intervals iv
LEFT JOIN statuses s ON s.name = iv.status;

-- One wide row per issue: names resolved, lists flattened, flow timestamps derived.
CREATE VIEW v_issues AS
WITH flow AS (
  SELECT
    i.key,
    (SELECT MIN(t.ts) FROM transitions t JOIN statuses s ON s.name = t.to_status
      WHERE t.key = i.key AND s.category = 'indeterminate') AS first_in_progress,
    CASE WHEN i.status_category = 'done' THEN COALESCE(
      (SELECT MAX(t.ts) FROM transitions t JOIN statuses s ON s.name = t.to_status
        WHERE t.key = i.key AND s.category = 'done'),
      i.resolved) END AS done_at,
    (SELECT COUNT(*) FROM transitions t
      JOIN statuses sf ON sf.name = t.from_status
      JOIN statuses st ON st.name = t.to_status
      WHERE t.key = i.key AND sf.category = 'done' AND st.category != 'done')
      AS reopen_count
  FROM issues i
)
SELECT
  i.key, i.project, i.issuetype, i.summary, i.status, i.status_category,
  i.priority, i.resolution,
  i.assignee_id, ua.display_name AS assignee,
  i.reporter_id, ur.display_name AS reporter,
  i.parent_key, p.summary AS parent_summary,
  i.created, i.updated, i.resolved, i.due,
  (SELECT group_concat(label, ', ') FROM (SELECT label FROM labels
    WHERE key = i.key ORDER BY label)) AS labels,
  (SELECT group_concat(name, ', ') FROM (SELECT name FROM components
    WHERE key = i.key ORDER BY name)) AS components,
  (SELECT group_concat(name, ', ') FROM (SELECT name FROM fix_versions
    WHERE key = i.key ORDER BY name)) AS fix_versions,
  (SELECT sp.name FROM issue_sprints isp JOIN sprints sp ON sp.id = isp.sprint_id
    WHERE isp.key = i.key ORDER BY sp.start_date DESC, sp.id DESC LIMIT 1) AS sprint,
  f.first_in_progress, f.done_at, f.reopen_count,
  ROUND(julianday(f.done_at) - julianday(f.first_in_progress), 2)
    AS cycle_time_days,
  ROUND(julianday(f.done_at) - julianday(i.created), 2) AS lead_time_days,
  CASE WHEN i.status_category = 'indeterminate' THEN ROUND(
    julianday((SELECT value FROM meta WHERE key = 'synced_at'))
    - julianday(f.first_in_progress), 2) END AS wip_age_days,
  'https://' || (SELECT value FROM meta WHERE key = 'jira_site')
    || '/browse/' || i.key AS url
FROM issues i
JOIN flow f ON f.key = i.key
LEFT JOIN users ua ON ua.id = i.assignee_id
LEFT JOIN users ur ON ur.id = i.reporter_id
LEFT JOIN issues p ON p.key = i.parent_key;
"""


# === Row extraction (pure, no I/O) ===


@dataclass
class IssueRows:
    """All database rows derived from one Jira issue."""

    issue: dict[str, Any]
    labels: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    fix_versions: list[str] = field(default_factory=list)
    custom_fields: list[tuple[str, str | None, str]] = field(default_factory=list)
    sprints: list[dict[str, Any]] = field(default_factory=list)
    links: list[tuple[str, str, str, str | None]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    statuses: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)


def to_utc(ts: str | None) -> str | None:
    """Normalize a Jira timestamp to ISO-8601 UTC ('YYYY-MM-DDTHH:MM:SSZ')."""
    if not ts:
        return None
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user(raw: dict | None, users: dict[str, dict[str, Any]]) -> str | None:
    """Register a raw Jira user object and return its stable id."""
    if not raw:
        return None
    uid = raw.get("accountId") or raw.get("key") or raw.get("name")
    if not uid:
        return None
    users[uid] = {
        "id": uid,
        "display_name": raw.get("displayName"),
        "email": raw.get("emailAddress"),
    }
    return uid


def _name(raw: dict | None) -> str | None:
    return raw.get("name") if raw else None


_SERVER_SPRINT_RE = re.compile(r"\[(.*)\]\s*$")


def parse_sprint(value: Any) -> dict[str, Any] | None:
    """Parse a sprint field entry (Cloud dict or Server/DC toString form)."""
    if isinstance(value, dict):
        data = value
        board = data.get("boardId")
    elif isinstance(value, str):
        m = _SERVER_SPRINT_RE.search(value)
        if not m:
            return None
        data = {}
        for part in m.group(1).split(","):
            k, sep, v = part.partition("=")
            if sep:
                data[k.strip()] = None if v == "<null>" else v
        board = data.get("rapidViewId")
    else:
        return None
    try:
        sprint_id = int(data["id"])  # ty: ignore[invalid-argument-type]
    except (KeyError, TypeError, ValueError):
        return None
    state = data.get("state")
    return {
        "id": sprint_id,
        "name": data.get("name"),
        "state": state.lower() if isinstance(state, str) else None,
        "board_id": int(board) if board not in (None, "") else None,
        "start_date": to_utc(data.get("startDate")),
        "end_date": to_utc(data.get("endDate")),
        "complete_date": to_utc(data.get("completeDate")),
    }


def _text(value: Any) -> str | None:
    """Convert a description/comment body (wiki string or ADF) to markdown."""
    if not value:
        return None
    return extract_description(value) or None


def extract_issue_rows(
    raw: dict[str, Any],
    histories: list[dict[str, Any]],
    comments: list[dict[str, Any]],
    field_names: dict[str, str],
    sprint_fields: set[str],
) -> IssueRows:
    """Turn a raw Jira issue JSON into database rows.

    Args:
        raw: Issue JSON as returned by the REST API (with 'fields').
        histories: Complete changelog histories for the issue.
        comments: Complete list of raw comment objects.
        field_names: Custom field id -> human-readable name.
        sprint_fields: Field ids holding sprint values.
    """
    f = raw.get("fields", {})
    key = raw["key"]
    users: dict[str, dict[str, Any]] = {}
    statuses: dict[str, tuple[str | None, str | None]] = {}

    status = f.get("status") or {}
    category = status.get("statusCategory") or {}
    if status.get("name"):
        statuses[status["name"]] = (category.get("key"), category.get("name"))

    rows = IssueRows(
        issue={
            "key": key,
            "id": str(raw.get("id", "")),
            "project": (f.get("project") or {}).get("key"),
            "issuetype": _name(f.get("issuetype")),
            "summary": f.get("summary"),
            "description": _text(f.get("description")),
            "status": status.get("name"),
            "status_category": category.get("key"),
            "priority": _name(f.get("priority")),
            "resolution": _name(f.get("resolution")),
            "assignee_id": _user(f.get("assignee"), users),
            "reporter_id": _user(f.get("reporter"), users),
            "creator_id": _user(f.get("creator"), users),
            "parent_key": (f.get("parent") or {}).get("key"),
            "created": to_utc(f.get("created")),
            "updated": to_utc(f.get("updated")),
            "resolved": to_utc(f.get("resolutiondate")),
            "due": f.get("duedate"),
            "raw": json.dumps(f, ensure_ascii=False),
        },
        labels=sorted(set(f.get("labels") or [])),
        components=sorted({c["name"] for c in f.get("components") or []}),
        fix_versions=sorted({v["name"] for v in f.get("fixVersions") or []}),
        users=users,
        statuses=statuses,
    )

    for field_id, value in f.items():
        if not field_id.startswith("customfield_") or value is None:
            continue
        if field_id in sprint_fields and isinstance(value, list):
            for entry in value:
                sprint = parse_sprint(entry)
                if sprint:
                    rows.sprints.append(sprint)
        rows.custom_fields.append(
            (
                field_id,
                field_names.get(field_id),
                json.dumps(extract_custom_field_value(value), ensure_ascii=False),
            )
        )

    seen_links: set[tuple[str, str, str]] = set()
    for link in f.get("issuelinks") or []:
        link_type = link.get("type") or {}
        for direction in ("outward", "inward"):
            other = link.get(f"{direction}Issue")
            if not other:
                continue
            ident = (other["key"], link_type.get("name", ""), direction)
            if ident in seen_links:
                continue
            seen_links.add(ident)
            rows.links.append((*ident, link_type.get(direction)))

    for c in comments:
        rows.comments.append(
            {
                "id": str(c["id"]),
                "key": key,
                "author_id": _user(c.get("author"), users),
                "created": to_utc(c.get("created")),
                "updated": to_utc(c.get("updated")),
                "body": _text(c.get("body")),
            }
        )

    for a in f.get("attachment") or []:
        rows.attachments.append(
            {
                "id": str(a["id"]),
                "key": key,
                "filename": a.get("filename"),
                "size": a.get("size"),
                "mime": a.get("mimeType"),
                "author_id": _user(a.get("author"), users),
                "created": to_utc(a.get("created")),
            }
        )

    ordered = sorted(
        histories,
        key=lambda h: (to_utc(h.get("created")) or "", int(h.get("id") or 0)),
    )
    for h in ordered:
        for item in h.get("items") or []:
            if item.get("field") != "status":
                continue
            rows.transitions.append(
                {
                    "key": key,
                    "seq": len(rows.transitions),
                    "ts": to_utc(h.get("created")),
                    "author_id": _user(h.get("author"), users),
                    "from_status": item.get("fromString"),
                    "to_status": item.get("toString"),
                }
            )

    return rows


# === Fetching ===


def _fetch_paged(path: str, items_key: str, page_size: int = 100) -> list[dict]:
    """Fetch all items from a startAt-paginated Jira REST endpoint."""
    jira = get_jira()
    items: list[dict] = []
    while True:
        data = jira._get_json(
            path, params={"startAt": len(items), "maxResults": page_size}
        )
        page = data.get(items_key) or []
        items.extend(page)
        if not page or data.get("isLast") or len(items) >= data.get("total", 0):
            return items


def _complete_histories(raw: dict[str, Any]) -> list[dict]:
    """Return the full changelog, fetching more if the search truncated it."""
    changelog = raw.get("changelog") or {}
    histories = changelog.get("histories") or []
    if changelog.get("total", len(histories)) <= len(histories):
        return histories
    key = raw["key"]
    try:
        return _fetch_paged(f"issue/{key}/changelog", "values")
    except Exception:
        # Server/DC has no changelog endpoint, but returns it complete here
        issue = get_jira().issue(key, expand="changelog")
        return issue.raw.get("changelog", {}).get("histories", [])


def _complete_comments(raw: dict[str, Any]) -> list[dict]:
    """Return all comments, fetching more if the search truncated them."""
    block = raw.get("fields", {}).get("comment") or {}
    comments = block.get("comments") or []
    if block.get("total", len(comments)) <= len(comments):
        return comments
    return _fetch_paged(f"issue/{raw['key']}/comment", "comments")


def _field_metadata() -> tuple[dict[str, str], set[str]]:
    """Return (custom field id -> name, sprint field ids) from the cached schema."""
    try:
        ensure_fields_cached()
    except Exception as e:
        print(f"Warning: could not fetch field names: {e}", file=sys.stderr)
    schema = load_schema() or {}
    fields = schema.get("fields") or {}
    names = {fid: d.get("name", "") for fid, d in fields.items() if d.get("name")}
    sprint_fields = {
        fid
        for fid, d in fields.items()
        if d.get("custom_type") == "gh-sprint" or d.get("name") == "Sprint"
    }
    return names, sprint_fields


def _fetch_statuses() -> dict[str, tuple[str | None, str | None]]:
    """Fetch all statuses with their categories (best effort)."""
    try:
        result = {}
        for s in get_jira().statuses():
            cat = s.raw.get("statusCategory") or {}
            result[s.raw["name"]] = (cat.get("key"), cat.get("name"))
        return result
    except Exception as e:
        print(f"Warning: could not fetch statuses: {e}", file=sys.stderr)
        return {}


def fetch_scope(jql: str) -> list[IssueRows]:
    """Fetch all issues matching JQL and convert them to rows."""
    field_names, sprint_fields = _field_metadata()
    jira = get_jira()
    try:
        issues = jira.search_issues(
            jql, maxResults=False, fields="*all", expand="changelog"
        )
    except Exception as e:
        raise ApplicationError(f"search failed: {format_jira_error(e)}") from e
    result = []
    for issue in issues:
        raw = issue.raw
        result.append(
            extract_issue_rows(
                raw,
                _complete_histories(raw),
                _complete_comments(raw),
                field_names,
                sprint_fields,
            )
        )
    return result


# === Database ===


def connect(path: Path) -> sqlite3.Connection:
    """Open (creating or resetting if needed) the database for writing.

    The database is a rebuildable snapshot, so a schema version mismatch
    simply drops everything and recreates the current schema.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION:
        if version != 0:
            print(
                f"Database schema changed (v{version} -> v{SCHEMA_VERSION}); "
                "recreating. Re-sync all scopes.",
                file=sys.stderr,
            )
        _reset_schema(conn)
    return conn


def _reset_schema(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN")
    objects = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    conn.execute("PRAGMA foreign_keys = OFF")
    for obj_type, name in sorted(objects, key=lambda o: o[0] != "view"):
        conn.execute(f'DROP {obj_type.upper()} IF EXISTS "{name}"')
    for statement in _split_sql(SCHEMA_SQL):
        conn.execute(statement)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.execute("COMMIT")
    conn.execute("PRAGMA foreign_keys = ON")


def _split_sql(script: str) -> list[str]:
    """Split a schema script into statements (no semicolons inside statements)."""
    lines = [ln for ln in script.splitlines() if not ln.lstrip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def _insert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))


def write_scope(
    conn: sqlite3.Connection,
    scope: str,
    jql: str,
    issues: list[IssueRows],
    statuses: dict[str, tuple[str | None, str | None]],
    jira_site: str,
    synced_at: str,
) -> None:
    """Replace one scope's contents in a single transaction."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM issue_scopes WHERE scope = ?", (scope,))
        all_statuses = dict(statuses)
        for rows in issues:
            all_statuses.update(rows.statuses)
            key = rows.issue["key"]
            conn.execute("DELETE FROM issues WHERE key = ?", (key,))
            _insert(conn, "issues", rows.issue)
            conn.executemany(
                "INSERT INTO labels VALUES (?, ?)", [(key, v) for v in rows.labels]
            )
            conn.executemany(
                "INSERT INTO components VALUES (?, ?)",
                [(key, v) for v in rows.components],
            )
            conn.executemany(
                "INSERT INTO fix_versions VALUES (?, ?)",
                [(key, v) for v in rows.fix_versions],
            )
            conn.executemany(
                "INSERT INTO custom_fields VALUES (?, ?, ?, ?)",
                [(key, *cf) for cf in rows.custom_fields],
            )
            for sprint in rows.sprints:
                conn.execute(
                    "INSERT OR REPLACE INTO sprints VALUES "
                    "(:id, :name, :state, :board_id, :start_date, :end_date, :complete_date)",
                    sprint,
                )
                conn.execute(
                    "INSERT OR IGNORE INTO issue_sprints VALUES (?, ?)",
                    (key, sprint["id"]),
                )
            conn.executemany(
                "INSERT INTO links VALUES (?, ?, ?, ?, ?)",
                [(key, *link) for link in rows.links],
            )
            for c in rows.comments:
                conn.execute("DELETE FROM comments WHERE id = ?", (c["id"],))
                _insert(conn, "comments", c)
            for a in rows.attachments:
                conn.execute("DELETE FROM attachments WHERE id = ?", (a["id"],))
                _insert(conn, "attachments", a)
            for t in rows.transitions:
                _insert(conn, "transitions", t)
            conn.executemany(
                "INSERT OR REPLACE INTO users VALUES (:id, :display_name, :email)",
                list(rows.users.values()),
            )
            conn.execute("INSERT INTO issue_scopes VALUES (?, ?)", (scope, key))

        conn.executemany(
            "INSERT OR REPLACE INTO statuses VALUES (?, ?, ?)",
            [(name, cat, cat_name) for name, (cat, cat_name) in all_statuses.items()],
        )
        conn.execute(
            "INSERT OR REPLACE INTO scopes VALUES (?, ?, ?, ?)",
            (scope, jql, synced_at, len(issues)),
        )
        # Drop issues no longer in any scope, then unreferenced sprints
        conn.execute(
            "DELETE FROM issues WHERE key NOT IN (SELECT key FROM issue_scopes)"
        )
        conn.execute(
            "DELETE FROM sprints WHERE id NOT IN (SELECT sprint_id FROM issue_sprints)"
        )
        conn.executemany(
            "INSERT OR REPLACE INTO meta VALUES (?, ?)",
            [
                ("schema_version", str(SCHEMA_VERSION)),
                ("jira_site", jira_site),
                ("synced_at", synced_at),
            ],
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


# === Commands ===


def _resolve_scopes(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Resolve CLI arguments to a list of (scope name, JQL)."""
    if args.jql:
        if args.scopes:
            raise ApplicationError("give either scope names or --jql, not both")
        return [(args.name or "adhoc", args.jql)]
    names = args.scopes or get_db_scopes()
    if not names:
        raise ApplicationError(
            "no scopes given. Pass query names from [queries] in zproject.toml, "
            'use --jql, or set [db] scopes = ["..."] in zproject.toml'
        )
    resolved = []
    for name in names:
        jql = get_project_query(name)
        if not jql:
            raise ApplicationError(f"unknown query '{name}' (see [queries])")
        resolved.append((name, jql))
    return resolved


def sync_command(args: argparse.Namespace) -> None:
    """Handle 'db sync': rebuild the given scopes from Jira."""
    scopes = _resolve_scopes(args)
    path = Path(args.db) if args.db else get_db_path()
    statuses = _fetch_statuses()
    site = get_jira_site()
    conn = connect(path)
    try:
        for name, jql in scopes:
            print(f"Syncing {name}: {jql}", file=sys.stderr)
            issues = fetch_scope(jql)
            synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            write_scope(conn, name, jql, issues, statuses, site, synced_at)
            print(f"  {len(issues)} issues", file=sys.stderr)
    finally:
        conn.close()
    print(f"Database: {path}", file=sys.stderr)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ")


def format_rows(columns: list[str], rows: list[tuple], fmt: str) -> str:
    """Render query results as table, csv, or json."""
    if fmt == "json":
        return json.dumps(
            [dict(zip(columns, r)) for r in rows], indent=2, ensure_ascii=False
        )
    if fmt == "csv":
        import io

        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
        return buf.getvalue().rstrip("\n")
    cells = [[_cell(v) for v in r] for r in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    lines = [
        "  ".join(c.ljust(w) for c, w in zip(columns, widths)).rstrip(),
        "  ".join("-" * w for w in widths),
    ]
    lines += ["  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip() for r in cells]
    return "\n".join(lines)


def query_command(args: argparse.Namespace) -> None:
    """Handle 'db query': run read-only SQL against the database."""
    path = Path(args.db) if args.db else get_db_path()
    if not path.exists():
        raise ApplicationError(f"database not found: {path} (run 'zaira db sync')")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        cursor = conn.execute(args.sql)
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchall()
    except sqlite3.Error as e:
        raise ApplicationError(f"query failed: {e}") from e
    finally:
        conn.close()
    if columns:
        print(format_rows(columns, rows, args.format))


def schema_command(args: argparse.Namespace) -> None:
    """Handle 'db schema': print the schema DDL."""
    print(f"-- zaira db schema version {SCHEMA_VERSION}")
    print(SCHEMA_SQL)


def db_command(args: argparse.Namespace) -> None:
    """Handle db subcommand."""
    if hasattr(args, "db_func"):
        args.db_func(args)
    else:
        print("Usage: zaira db <subcommand>")
        print("Subcommands: sync, query, schema")
        sys.exit(1)
