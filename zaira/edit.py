"""Edit Jira ticket fields."""

import argparse
import sys

from zaira.jira_client import get_jira, get_jira_site


def read_body(body: str) -> str:
    """Read body, supporting stdin with '-'."""
    if body == "-":
        return sys.stdin.read()
    return body


def edit_ticket(key: str, title: str | None = None, description: str | None = None) -> bool:
    """Edit a Jira ticket's title and/or description.

    Args:
        key: Ticket key (e.g., PROJ-123)
        title: New title/summary (optional)
        description: New description text (optional)

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        issue = jira.issue(key)
        fields = {}
        if title is not None:
            fields["summary"] = title
        if description is not None:
            fields["description"] = description
        if fields:
            issue.update(fields=fields)
        return True
    except Exception as e:
        print(f"Error updating {key}: {e}", file=sys.stderr)
        return False


def edit_command(args: argparse.Namespace) -> None:
    """Handle edit subcommand."""
    key = args.key.upper()
    title = args.title
    description = read_body(args.description) if args.description else None

    if not title and not description:
        print("Error: Specify --title and/or --description", file=sys.stderr)
        sys.exit(1)

    jira_site = get_jira_site()

    fields = []
    if title:
        fields.append("title")
    if description:
        fields.append("description")

    print(f"Updating {', '.join(fields)} for {key}...")

    if edit_ticket(key, title=title, description=description):
        print(f"Updated {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
    else:
        sys.exit(1)
