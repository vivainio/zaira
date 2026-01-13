"""Show my open tickets."""

import argparse

from zaira.jira_client import get_jira
from zaira.report import humanize_age
from zaira.types import MyTicket


DEFAULT_ASSIGNED_JQL = (
    "assignee = currentUser() "
    "AND status NOT IN (Done, Closed, Resolved, Disposal, Rejected) "
    "ORDER BY updated DESC"
)

DEFAULT_REPORTED_JQL = (
    "reporter = currentUser() "
    "AND status NOT IN (Done, Closed, Resolved, Disposal, Rejected) "
    "ORDER BY updated DESC"
)


def search_my_tickets(jql: str) -> list[MyTicket]:
    """Search for tickets and return minimal ticket data."""
    jira = get_jira()
    issues = jira.search_issues(jql, maxResults=False)
    tickets = []
    for issue in issues:
        fields = issue.fields
        tickets.append({
            "key": issue.key,
            "status": fields.status.name if fields.status else "?",
            "created": fields.created or "",
            "summary": fields.summary or "",
        })
    return tickets


def print_table(tickets: list[MyTicket]) -> None:
    """Print tickets grouped by status."""
    if not tickets:
        print("No open tickets.")
        return

    key_width = max(len(t["key"]) for t in tickets)

    # Group tickets by status
    groups: dict[str, list[MyTicket]] = {}
    for t in tickets:
        status = t["status"]
        if status not in groups:
            groups[status] = []
        groups[status].append(t)

    for status, group_tickets in groups.items():
        # Sort by created date (oldest first)
        group_tickets.sort(key=lambda t: t["created"])
        print(f"\n{status} ({len(group_tickets)})")
        print("-" * (len(status) + len(str(len(group_tickets))) + 3))
        for t in group_tickets:
            age = humanize_age(t["created"])
            summary = t["summary"]
            max_summary = 100
            if len(summary) > max_summary:
                summary = summary[: max_summary - 3] + "..."
            print(f"{t['key']:<{key_width}}  {age:>5}  {summary}")


def my_command(args: argparse.Namespace) -> None:
    """Handle my subcommand."""
    from zaira.project import get_query

    if args.reported:
        # Show tickets reported (created) by me
        jql = get_query("my-reported")
        if not jql:
            jql = DEFAULT_REPORTED_JQL
    else:
        # Show tickets assigned to me
        jql = get_query("my-tickets")
        if not jql:
            jql = DEFAULT_ASSIGNED_JQL

    tickets = search_my_tickets(jql)
    print_table(tickets)
