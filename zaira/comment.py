"""Add comments to Jira tickets."""

import argparse
import sys

from zaira.create import detect_markdown
from zaira.jira_client import format_jira_error, get_jira, get_jira_site


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
        print(f"Error adding comment to {key}: {format_jira_error(e)}", file=sys.stderr)
        return False


def comment_command(args: argparse.Namespace) -> None:
    """Handle comment subcommand."""
    key = args.key.upper()
    body = read_body(args.body)

    if not body.strip():
        print("Error: Comment body cannot be empty", file=sys.stderr)
        sys.exit(1)

    if detect_markdown(body):
        from zaira.mdconv import markdown_to_jira_wiki
        body = markdown_to_jira_wiki(body)

    jira_site = get_jira_site()
    print(f"Adding comment to {key}...")

    if add_comment(key, body):
        print(f"Comment added to {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record
        record("comment", key)
    else:
        sys.exit(1)
