"""Show recently viewed Jira tickets and Confluence pages."""

import argparse
import sys
from datetime import datetime, timezone

import requests
from requests.auth import HTTPBasicAuth

from zaira.jira_client import (
    format_jira_error,
    get_jira,
    get_server_from_config,
    load_credentials,
)


JIRA_RECENT_JQL = "issuekey in issueHistory() ORDER BY lastViewed DESC"


def recent_command(args: argparse.Namespace) -> None:
    """Show Jira tickets the current user has recently viewed."""
    from jira.exceptions import JIRAError

    jira = get_jira()
    try:
        jira.myself()
    except JIRAError as e:
        print(f"Error: {format_jira_error(e)}", file=sys.stderr)
        sys.exit(1)

    limit = args.limit or 20
    try:
        issues = jira.search_issues(JIRA_RECENT_JQL, maxResults=limit)
    except JIRAError as e:
        print(f"Error: {format_jira_error(e)}", file=sys.stderr)
        sys.exit(1)

    if not issues:
        print("No recently viewed tickets.")
        return

    key_width = max(len(i.key) for i in issues)
    for issue in issues:
        summary = issue.fields.summary or ""
        status = issue.fields.status.name if issue.fields.status else "?"
        if len(summary) > 90:
            summary = summary[:87] + "..."
        print(f"{issue.key:<{key_width}}  {status[:15]:<15}  {summary}")


def wiki_recent_command(args: argparse.Namespace) -> None:
    """Show Confluence pages the current user has recently viewed."""
    creds = load_credentials()
    server = get_server_from_config()
    if not server or not creds.get("email") or not creds.get("api_token"):
        print("Error: Credentials not configured. Run 'zaira init'.", file=sys.stderr)
        sys.exit(1)

    auth = HTTPBasicAuth(creds["email"], creds["api_token"])
    limit = args.limit or 20

    r = requests.get(
        f"{server}/wiki/rest/recentlyviewed/1.0/recent",
        params={"limit": limit},
        auth=auth,
        timeout=15,
    )
    if not r.ok:
        print(f"Error: {r.status_code} {r.reason}", file=sys.stderr)
        sys.exit(1)

    items = r.json()
    if not items:
        print("No recently viewed pages.")
        return

    for item in items[:limit]:
        title = item.get("title", "")
        space = item.get("spaceKey", "")
        ts = item.get("lastSeen")
        when = ""
        if ts:
            when = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M"
            )
        rel = item.get("url", "")
        if rel and not rel.startswith("/wiki"):
            rel = "/wiki" + rel
        url = server + rel
        print(f"{when}  [{space}]  {title}")
        print(f"  {url}")
