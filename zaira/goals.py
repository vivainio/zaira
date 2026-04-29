"""Atlassian Goals (Townsquare/Atlas) export via GraphQL.

Goals live at home.atlassian.com / townsquare and are accessed through the
GraphQL gateway on the same Atlassian site as Jira/Confluence. Auth is the
same email + API token zaira already stores.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from zaira.jira_client import get_credentials, get_jira_site

GRAPHQL_PATH = "/gateway/api/graphql"

MINIMAL_FIELDS = """
id
key
name
url
isArchived
owner { accountId name }
status { value score }
targetDate { label confidence }
startDate
""".strip()

FULL_FIELDS = """
id
key
name
url
isArchived
isPrivate
description
creationDate
startDate
targetDate { label confidence }
status { value score localizedLabel { messageId } }
owner { accountId name picture }
goalType @optIn(to: "Townsquare") { id name { ... on TownsquareGoalTypeCustomName { value } ... on TownsquareLocalizationField { messageId defaultValue } } }
progress { type percentage }
tags(first: 50) { edges { node { id name } } }
parentGoal { id key name }
subGoals(first: 100) { edges { node { id key name status { value } } } }
projects(first: 100) { edges { node { id key name } } }
risks(first: 50) { edges { node { id summary description resolvedDate creator { name } } } }
draftUpdate { input modifiedDate author { accountId name } }
latestUpdateDate
latestUserUpdate {
  uuid
  creationDate
  updateType
  summary
  newScore
  newState { value }
  newTargetDate
  newTargetDateConfidence
  lastEditedBy { accountId name }
}
""".strip()


def _endpoint() -> str:
    site = get_jira_site()
    if not site:
        print("Error: Jira site not configured. Run 'zaira init'.", file=sys.stderr)
        sys.exit(1)
    return f"https://{site}{GRAPHQL_PATH}"


_cached_cloud_id: str | None = None


def get_cloud_id() -> str:
    """Resolve the current site's cloud ID via _edge/tenant_info."""
    global _cached_cloud_id
    if _cached_cloud_id:
        return _cached_cloud_id
    site = get_jira_site()
    resp = requests.get(f"https://{site}/_edge/tenant_info", timeout=10)
    resp.raise_for_status()
    cid = resp.json().get("cloudId")
    if not cid:
        raise RuntimeError(f"Could not resolve cloudId from https://{site}")
    _cached_cloud_id = cid
    return cid


def parse_goals_url(url: str) -> dict[str, str]:
    """Parse a home.atlassian.com goals URL into {cloud_id, tql, org_id}.

    Example URL:
      https://home.atlassian.com/o/<orgId>/goals?cloudId=<cloudId>&tql=<encoded>
    """
    parts = urlparse(url)
    qs = parse_qs(parts.query)
    out: dict[str, str] = {}
    if "cloudId" in qs:
        out["cloud_id"] = qs["cloudId"][0]
    if "tql" in qs:
        out["tql"] = qs["tql"][0]
    segs = [s for s in parts.path.split("/") if s]
    if len(segs) >= 2 and segs[0] == "o":
        out["org_id"] = segs[1]
    return out


def _post_graphql(query: str, variables: dict) -> dict:
    _, email, token = get_credentials()
    resp = requests.post(
        _endpoint(),
        auth=(email, token),
        json={"query": query, "variables": variables},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"GraphQL HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    if data.get("errors"):
        raise RuntimeError(
            "GraphQL errors: "
            + json.dumps(data["errors"], indent=2, ensure_ascii=False)
        )
    return data["data"]


def search_goals(
    cloud_id: str,
    tql: str = "archived = false",
    full: bool = False,
    with_updates: bool = False,
    page_size: int = 50,
) -> list[dict]:
    """Page through goals_search and return a flat list of goal nodes."""
    fields = FULL_FIELDS if full else MINIMAL_FIELDS
    if with_updates:
        fields = (
            fields
            + '\nupdates(first: 20) @optIn(to: "Townsquare") '
            + "{ edges { node { "
            + UPDATE_FIELDS
            + " } } }"
        )
    container = f"ari:cloud:townsquare::site/{cloud_id}"
    query = f"""
    query GoalsSearch($containerId: ID!, $q: String, $first: Int!, $after: String) {{
      goals_search(containerId: $containerId, searchString: $q, first: $first, after: $after) {{
        edges {{ node {{ {fields} }} }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
    """

    nodes: list[dict] = []
    cursor: str | None = None
    while True:
        data = _post_graphql(
            query,
            {
                "containerId": container,
                "q": tql,
                "first": page_size,
                "after": cursor,
            },
        )
        result = data.get("goals_search") or {}
        for edge in result.get("edges") or []:
            if edge and edge.get("node"):
                nodes.append(edge["node"])
        page = result.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        cursor = page.get("endCursor")
        if not cursor:
            break
    return nodes


_STATUS_LABELS = {
    "pending": "Pending",
    "on_track": "On track",
    "at_risk": "At risk",
    "off_track": "Off track",
    "done": "Done",
    "cancelled": "Cancelled",
    "paused": "Paused",
    "archived": "Archived",
}


def _status_label(status: dict | None) -> str:
    if not status:
        return ""
    raw = status.get("value") or ""
    return _STATUS_LABELS.get(raw, raw)


def _adf_to_text(node: dict | str | list | None, depth: int = 0) -> str:
    """Convert Atlassian Document Format JSON to plain markdown-ish text."""
    if node is None:
        return ""
    if isinstance(node, str):
        try:
            node = json.loads(node)
        except Exception:
            return node
    if isinstance(node, list):
        return "".join(_adf_to_text(n, depth) for n in node)

    t = node.get("type")
    children = node.get("content") or []

    if t == "doc":
        return _adf_to_text(children, depth).strip()
    if t == "paragraph":
        return _adf_to_text(children, depth) + "\n"
    if t == "heading":
        level = (node.get("attrs") or {}).get("level", 1)
        return f"{'#' * level} " + _adf_to_text(children, depth) + "\n"
    if t == "bulletList":
        return "".join(
            "  " * depth + "- " + _adf_to_text(li, depth + 1).rstrip() + "\n"
            for li in children
        )
    if t == "orderedList":
        return "".join(
            "  " * depth + f"{i + 1}. " + _adf_to_text(li, depth + 1).rstrip() + "\n"
            for i, li in enumerate(children)
        )
    if t == "listItem":
        return _adf_to_text(children, depth)
    if t == "hardBreak":
        return "\n"
    if t == "text":
        text = node.get("text", "")
        for mark in node.get("marks") or []:
            mt = mark.get("type")
            if mt == "strong":
                text = f"**{text}**"
            elif mt == "em":
                text = f"*{text}*"
            elif mt == "code":
                text = f"`{text}`"
            elif mt == "link":
                href = (mark.get("attrs") or {}).get("href", "")
                text = f"[{text}]({href})"
        return text
    if t == "codeBlock":
        return "```\n" + _adf_to_text(children, depth) + "\n```\n"
    if t == "blockquote":
        inner = _adf_to_text(children, depth).rstrip()
        return "".join(f"> {ln}\n" for ln in inner.splitlines())
    if t == "rule":
        return "---\n"
    return _adf_to_text(children, depth)


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + ln for ln in text.rstrip().splitlines())


def _cell(text: str) -> str:
    """Escape pipes/newlines for a markdown table cell."""
    if not text:
        return ""
    return text.replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _to_table(goals: list[dict]) -> str:
    headers = [
        "Key",
        "Name",
        "Owner",
        "Status",
        "Target",
        "Description",
        "Latest update",
        "Open risks",
    ]
    out = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for g in goals:
        key = g.get("key") or ""
        name = g.get("name") or ""
        owner = (g.get("owner") or {}).get("name") or ""
        status = _status_label(g.get("status"))
        td = g.get("targetDate")
        target = ((td.get("label") if isinstance(td, dict) else td) or "") if td else ""
        desc = _adf_to_text(g.get("description")).strip()
        latest = g.get("latestUserUpdate") or {}
        update_text = _adf_to_text(latest.get("summary")).strip()
        if update_text and latest.get("creationDate"):
            update_text = f"({latest['creationDate'][:10]}) {update_text}"
        risks = ((g.get("risks") or {}).get("edges")) or []
        open_risks = [
            (r.get("node") or {}).get("summary", "")
            for r in risks
            if (r.get("node") or {}).get("summary")
            and not (r.get("node") or {}).get("resolvedDate")
        ]
        risks_cell = "; ".join(r for r in open_risks if r)
        row = [
            key,
            name,
            owner,
            status,
            target,
            desc,
            update_text,
            risks_cell,
        ]
        out.append("| " + " | ".join(_cell(c) for c in row) + " |")
    return "\n".join(out) + "\n"


def _to_markdown(goals: list[dict]) -> str:
    lines = [f"# Goals export ({len(goals)})", ""]
    for g in goals:
        name = g.get("name") or "(unnamed)"
        key = g.get("key") or g.get("id") or ""
        lines.append(f"## {name}  `{key}`")
        url = g.get("url")
        if url:
            lines.append(f"- URL: {url}")
        status = _status_label(g.get("status"))
        if status:
            lines.append(f"- Status: {status}")
        owner = (g.get("owner") or {}).get("name")
        if owner:
            lines.append(f"- Owner: {owner}")
        td = g.get("targetDate")
        if td:
            if isinstance(td, dict):
                td = td.get("label") or td.get("date") or ""
            lines.append(f"- Target: {td}")
        if g.get("isArchived"):
            lines.append("- Archived: true")
        parent = g.get("parentGoal") or {}
        if parent.get("name"):
            lines.append(f"- Parent: {parent['name']} ({parent.get('key', '')})")
        subs = ((g.get("subGoals") or {}).get("edges")) or []
        if subs:
            lines.append(f"- Sub-goals: {len(subs)}")
            for s in subs:
                n = s.get("node") or {}
                lines.append(f"  - {n.get('name')} ({n.get('key', '')})")
        desc = g.get("description")
        if desc:
            text = _adf_to_text(desc)
            if text:
                lines.append("- Description:")
                lines.append(_indent(text))
        latest = g.get("latestUserUpdate") or {}
        if latest.get("summary"):
            text = _adf_to_text(latest["summary"])
            lines.append(f"- Latest update ({latest.get('creationDate', '')}):")
            lines.append(_indent(text))
        lines.append("")
    return "\n".join(lines)


UPDATE_FIELDS = """
uuid
creationDate
updateType
summary
oldState { value }
newState { value }
oldScore
newScore
oldTargetDate
newTargetDate
missedUpdate
creator { accountId name }
lastEditedBy { accountId name }
url
updateNotes(first: 50) {
  edges { node { summary description archived creationDate creator { name } } }
}
""".strip()


def get_goal_updates(
    key_or_id: str, cloud_id: str | None = None, limit: int = 50
) -> list[dict]:
    """Fetch the raw check-in update history for a goal, newest first."""
    is_ari = key_or_id.startswith("ari:")
    inner = (
        f'updates(first: {limit}) @optIn(to: "Townsquare") '
        f"{{ edges {{ node {{ {UPDATE_FIELDS} }} }} }}"
    )
    if is_ari:
        query = f"query GoalUpdatesById($id: ID!) {{ goals_byId(id: $id) {{ key name {inner} }} }}"
        data = _post_graphql(query, {"id": key_or_id})
        goal = data.get("goals_byId") or {}
    else:
        cid = cloud_id or get_cloud_id()
        container = f"ari:cloud:townsquare::site/{cid}"
        query = (
            "query GoalUpdatesByKey($containerId: ID!, $goalKey: String!) { "
            f"goals_byKey(containerId: $containerId, goalKey: $goalKey) {{ key name {inner} }} "
            "}"
        )
        data = _post_graphql(query, {"containerId": container, "goalKey": key_or_id})
        goal = data.get("goals_byKey") or {}
    edges = ((goal.get("updates") or {}).get("edges")) or []
    return [e["node"] for e in edges if e and e.get("node")]


def _updates_to_markdown(key: str, updates: list[dict]) -> str:
    lines = [f"# Updates for {key} ({len(updates)})", ""]
    for u in updates:
        date = (u.get("creationDate") or "")[:10]
        old = (u.get("oldState") or {}).get("value") or ""
        new = (u.get("newState") or {}).get("value") or ""
        creator = (u.get("creator") or {}).get("name") or ""
        transition = (
            f"{_STATUS_LABELS.get(old, old)} → {_STATUS_LABELS.get(new, new)}"
            if old or new
            else ""
        )
        head = f"## {date}  {transition}".rstrip()
        if creator:
            head += f"  — {creator}"
        lines.append(head)
        if u.get("missedUpdate"):
            lines.append("- _missed update_")
        text = _adf_to_text(u.get("summary")).strip()
        if text:
            lines.append(text)
        notes = ((u.get("updateNotes") or {}).get("edges")) or []
        live_notes = [
            (ne.get("node") or {})
            for ne in notes
            if not (ne.get("node") or {}).get("archived")
        ]
        if live_notes:
            lines.append("")
            lines.append("**Notes:**")
            for n in live_notes:
                s = _adf_to_text(n.get("summary")).strip()
                d = _adf_to_text(n.get("description")).strip()
                lines.append("- " + (": ".join(p for p in (s, d) if p)))
        lines.append("")
    return "\n".join(lines)


def updates_command(args: argparse.Namespace) -> None:
    try:
        updates = get_goal_updates(args.key, cloud_id=args.cloud_id, limit=args.limit)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    fmt = args.format
    if not fmt and args.output:
        fmt = "md" if args.output.endswith(".md") else "json"
    fmt = fmt or "md"

    if fmt == "md":
        text = _updates_to_markdown(args.key, updates)
    else:
        text = json.dumps(updates, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {len(updates)} updates for {args.key} to {args.output}")
    else:
        print(text)


def get_goal(
    key_or_id: str, full: bool = True, cloud_id: str | None = None
) -> dict | None:
    """Fetch a single goal by key (e.g. 'TEAM-42') or ARI/id."""
    fields = FULL_FIELDS if full else MINIMAL_FIELDS
    is_ari = key_or_id.startswith("ari:")
    if is_ari:
        query = f"query GoalById($id: ID!) {{ goals_byId(id: $id) {{ {fields} }} }}"
        data = _post_graphql(query, {"id": key_or_id})
        return data.get("goals_byId")
    cid = cloud_id or get_cloud_id()
    container = f"ari:cloud:townsquare::site/{cid}"
    query = (
        "query GoalByKey($containerId: ID!, $goalKey: String!) { "
        f"goals_byKey(containerId: $containerId, goalKey: $goalKey) {{ {fields} }} "
        "}"
    )
    data = _post_graphql(query, {"containerId": container, "goalKey": key_or_id})
    return data.get("goals_byKey")


def get_command(args: argparse.Namespace) -> None:
    keys = list(args.keys)
    fmt = args.format
    output = args.output
    if not fmt and output and not Path(output).is_dir() and not output.endswith("/"):
        fmt = "md" if output.endswith(".md") else "json"
    fmt = fmt or "json"

    try:
        if len(keys) == 1 and not keys[0].startswith("ari:"):
            single = get_goal(keys[0], full=not args.minimal, cloud_id=args.cloud_id)
            goals = [single] if single else []
            missing = [] if single else [keys[0]]
        else:
            goals, missing = _batch_get_goals(
                keys, full=not args.minimal, cloud_id=args.cloud_id
            )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    for k in missing:
        print(f"Goal not found: {k}", file=sys.stderr)
    if not goals:
        sys.exit(1)

    if output and (
        Path(output).is_dir()
        or output.endswith("/")
        or len(goals) > 1
        and "." not in Path(output).name
    ):
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        for g in goals:
            key = g.get("key") or g.get("id", "goal").replace("/", "_")
            ext = "md" if fmt == "md" else "json"
            text = (
                _to_markdown([g])
                if fmt == "md"
                else json.dumps(g, indent=2, ensure_ascii=False)
            )
            (out_dir / f"{key}.{ext}").write_text(text, encoding="utf-8")
        print(f"Wrote {len(goals)} goals to {out_dir}/")
        return

    if fmt == "md":
        text = _to_markdown(goals)
    else:
        text = json.dumps(
            goals if len(goals) > 1 else goals[0], indent=2, ensure_ascii=False
        )

    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"Wrote {len(goals)} goal(s) to {output}")
    else:
        print(text)


def _batch_get_goals(
    keys: list[str], full: bool, cloud_id: str | None
) -> tuple[list[dict], list[str]]:
    """Batch-fetch goals by key (or ARI). Uses TQL OR-list for keys, goals_byIds for ARIs."""
    aris = [k for k in keys if k.startswith("ari:")]
    plain = [k for k in keys if not k.startswith("ari:")]
    fields = FULL_FIELDS if full else MINIMAL_FIELDS
    out: list[dict] = []
    found_keys: set[str] = set()

    if plain:
        cid = cloud_id or get_cloud_id()
        tql = " OR ".join(f"key = {k}" for k in plain)
        goals = search_goals(cid, tql=tql, full=full, page_size=max(50, len(plain)))
        for g in goals:
            if g.get("key"):
                found_keys.add(g["key"])
        out.extend(goals)

    if aris:
        query = f"query GoalsByIds($ids: [ID!]!) {{ goals_byIds(goalIds: $ids) {{ {fields} }} }}"
        data = _post_graphql(query, {"ids": aris})
        for g in data.get("goals_byIds") or []:
            if g:
                out.append(g)
                if g.get("id"):
                    found_keys.add(g["id"])

    missing = [
        k
        for k in keys
        if k not in found_keys
        and not (k.startswith("ari:") and any(g.get("id") == k for g in out))
    ]
    return out, missing


def goals_command(args: argparse.Namespace) -> None:
    if hasattr(args, "goals_func"):
        args.goals_func(args)
    else:
        print("Usage: zaira goals <export|get|updates>", file=sys.stderr)
        sys.exit(1)


def export_command(args: argparse.Namespace) -> None:
    cloud_id = args.cloud_id
    tql = args.tql

    if args.url:
        parsed = parse_goals_url(args.url)
        cloud_id = cloud_id or parsed.get("cloud_id")
        if not args.tql and parsed.get("tql"):
            tql = parsed["tql"]

    if not cloud_id:
        print(
            "Error: cloudId required (--cloud-id or --url with cloudId param).",
            file=sys.stderr,
        )
        sys.exit(1)
    if not tql:
        tql = "archived = false"

    try:
        goals = search_goals(
            cloud_id,
            tql=tql,
            full=args.full,
            with_updates=getattr(args, "with_updates", False),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    fmt = args.format
    if not fmt and args.output:
        fmt = "md" if args.output.endswith(".md") else "json"
    fmt = fmt or "json"

    if fmt == "md":
        text = _to_markdown(goals)
    elif fmt == "table":
        text = _to_table(goals)
    else:
        text = json.dumps(goals, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {len(goals)} goals to {args.output}")
    else:
        print(text)
