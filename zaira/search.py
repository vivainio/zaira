"""Search Jira tickets."""

import argparse
import sys

from zaira.jira_client import get_jira
from zaira.report import humanize_age


PAGE_SIZE = 50


def print_row(
    key: str, status: str, created: str, summary: str, key_width: int
) -> None:
    """Print a single search result row."""
    age = humanize_age(created)
    if len(summary) > 90:
        summary = summary[:87] + "..."
    status_short = status[:15]
    print(f"{key:<{key_width}}  {status_short:<15}  {age:>5}  {summary}")


def search_command(args: argparse.Namespace) -> None:
    """Handle search subcommand."""
    jql = build_jql(args)
    limit = args.limit
    jira = get_jira()

    start = 0
    total_printed = 0
    key_width = 10  # reasonable default, adjusts if needed

    while True:
        page_size = min(PAGE_SIZE, limit - total_printed) if limit else PAGE_SIZE
        issues = jira.search_issues(jql, startAt=start, maxResults=page_size)

        if not issues:
            break

        for issue in issues:
            fields = issue.fields
            key = issue.key
            if len(key) > key_width:
                key_width = len(key)
            print_row(
                key,
                fields.status.name if fields.status else "?",
                fields.created or "",
                fields.summary or "",
                key_width,
            )
            total_printed += 1
            if limit and total_printed >= limit:
                break

        if limit and total_printed >= limit:
            break
        if len(issues) < page_size:
            break
        start += len(issues)

    if total_printed == 0:
        print("No tickets found.")


def _looks_like_jql(text: str) -> bool:
    """Detect if text looks like JQL (heuristic check)."""
    if not text:
        return False
    text_upper = text.upper()
    # Check for JQL keywords and operators
    jql_indicators = [
        "=",
        " AND ",
        " OR ",
        " NOT ",
        "ORDER BY",
        "PROJECT",
        "TYPE",
        "STATUS",
        "ASSIGNEE",
        "PRIORITY",
        "LABEL",
        "COMPONENT",
    ]
    return any(indicator in text_upper for indicator in jql_indicators)


def build_jql(args: argparse.Namespace) -> str:
    """Build JQL from search arguments."""
    if args.jql:
        return args.jql

    # Auto-detect if text argument looks like JQL
    if args.text and _looks_like_jql(args.text):
        return args.text

    clauses = []
    if args.text:
        clauses.append(f'text ~ "{args.text}"')
    if args.project:
        clauses.append(f"project = {args.project}")
    if args.status:
        clauses.append(f'status = "{args.status}"')
    if args.assignee:
        clauses.append(f'assignee = "{args.assignee}"')

    if not clauses:
        print("Provide search text, --jql, or filters (-p, -s, -a).")
        sys.exit(1)

    return " AND ".join(clauses) + " ORDER BY updated DESC"
