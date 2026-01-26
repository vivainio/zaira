"""Add comments to Jira tickets."""

import argparse
import sys

from zaira.create import detect_markdown
from zaira.jira_client import get_jira, get_jira_site


def read_body(body: str) -> str:
    """Read comment body, supporting stdin with '-'."""
    if body == "-":
        return sys.stdin.read()
    return body


def add_comment(key: str, body: str) -> bool:
    """Add a comment to a Jira ticket.

    Args:
        key: Ticket key (e.g., PROJ-123)
        body: Comment text

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        comment = jira.add_comment(key, body)
        return comment is not None
    except Exception as e:
        print(f"Error adding comment to {key}: {e}", file=sys.stderr)
        return False


def comment_command(args: argparse.Namespace) -> None:
    """Handle comment subcommand."""
    key = args.key.upper()
    body = read_body(args.body)

    if not body.strip():
        print("Error: Comment body cannot be empty", file=sys.stderr)
        sys.exit(1)

    md_errors = detect_markdown(body)
    if md_errors:
        print(
            "Error: Comment contains markdown syntax. Use Jira wiki markup instead:",
            file=sys.stderr,
        )
        for err in md_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    jira_site = get_jira_site()
    print(f"Adding comment to {key}...")

    if add_comment(key, body):
        print(f"Comment added to {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
    else:
        sys.exit(1)
