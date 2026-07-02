"""Add, edit, delete, and list comments on Jira tickets."""

import argparse
import sys

from zaira.create import detect_markdown
from zaira.jira_client import format_jira_error, get_jira, get_jira_site


def read_body(body: str) -> str:
    """Read comment body, supporting stdin with '-'."""
    if body == "-":
        return sys.stdin.read()
    return body


def _to_jira_wiki(body: str) -> str:
    """Convert markdown body to Jira wiki syntax if it looks like markdown."""
    if detect_markdown(body):
        from zaira.mdconv import markdown_to_jira_wiki

        return markdown_to_jira_wiki(body)
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


def update_comment(key: str, comment_id: str, body: str) -> bool:
    """Edit an existing comment on a Jira ticket.

    Args:
        key: Ticket key (e.g., PROJ-123)
        comment_id: Comment ID (from `zaira comment KEY --list`)
        body: New comment text

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        comment = jira.comment(key, comment_id)
        comment.update(body=body)
        return True
    except Exception as e:
        print(
            f"Error editing comment {comment_id} on {key}: {format_jira_error(e)}",
            file=sys.stderr,
        )
        return False


def delete_comment(key: str, comment_id: str) -> bool:
    """Delete a comment from a Jira ticket.

    Args:
        key: Ticket key (e.g., PROJ-123)
        comment_id: Comment ID (from `zaira comment KEY --list`)

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        comment = jira.comment(key, comment_id)
        comment.delete()
        return True
    except Exception as e:
        print(
            f"Error deleting comment {comment_id} on {key}: {format_jira_error(e)}",
            file=sys.stderr,
        )
        return False


def _print_comment_list(key: str) -> None:
    """Print comments on a ticket with their IDs, for use with --edit/--delete."""
    from zaira.export import get_comments

    comments = get_comments(key, raw=True)
    if not comments:
        print(f"No comments on {key}")
        return

    for c in comments:
        first_line = c.body.strip().splitlines()[0] if c.body.strip() else ""
        snippet = first_line if len(first_line) <= 80 else first_line[:77] + "..."
        print(f"{c.id}\t{c.created}\t{c.author}\t{snippet}")


def comment_command(args: argparse.Namespace) -> None:
    """Handle comment subcommand: add (default), --list, --edit ID, --delete ID."""
    key = args.key.upper()

    if args.list:
        _print_comment_list(key)
        return

    if args.delete:
        comment_id = args.delete
        if delete_comment(key, comment_id):
            print(f"Comment {comment_id} deleted from {key}")
            from zaira.activity_log import record

            record("comment-delete", key, comment_id)
        else:
            sys.exit(1)
        return

    if args.body is None:
        print(
            "Error: comment body required (or use --list / --delete ID)",
            file=sys.stderr,
        )
        sys.exit(1)

    body = read_body(args.body)
    if not body.strip():
        print("Error: Comment body cannot be empty", file=sys.stderr)
        sys.exit(1)
    body = _to_jira_wiki(body)

    jira_site = get_jira_site()

    if args.edit:
        comment_id = args.edit
        print(f"Editing comment {comment_id} on {key}...")
        if update_comment(key, comment_id, body):
            print(f"Comment {comment_id} updated on {key}")
            print(f"View at: https://{jira_site}/browse/{key}")
            from zaira.activity_log import record

            record("comment-edit", key, comment_id)
        else:
            sys.exit(1)
        return

    print(f"Adding comment to {key}...")
    if add_comment(key, body):
        print(f"Comment added to {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record

        record("comment", key)
    else:
        sys.exit(1)
