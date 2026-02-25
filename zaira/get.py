"""Get Jira tickets."""

import argparse
import sys
from pathlib import Path

from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
from zaira.export import export_ticket, export_to_stdout, search_tickets


def get_command(args: argparse.Namespace) -> None:
    """Handle get subcommand."""
    fmt = getattr(args, "format", "md")
    include_custom = getattr(args, "all_fields", False)
    with_prs = getattr(args, "with_prs", False)
    with_tests = getattr(args, "with_tests", False)
    minimal = getattr(args, "min", False)
    output = getattr(args, "output", None)
    to_stdout = not output

    keys = list(args.keys or [])

    # Build JQL from options
    jql = getattr(args, "jql", None)
    if getattr(args, "board", None):
        jql = get_board_issues_jql(args.board)
        if not to_stdout:
            print(f"Using board {args.board}")
    elif getattr(args, "sprint", None):
        jql = get_sprint_issues_jql(args.sprint)
        if not to_stdout:
            print(f"Using sprint {args.sprint}")

    if jql:
        if not to_stdout:
            print(f"Searching: {jql}")
        found = search_tickets(jql)
        if not to_stdout:
            print(f"Found {len(found)} tickets")
        keys.extend(found)

    if not keys:
        print("No tickets specified. Use ticket keys, --jql, --board, or --sprint.")
        sys.exit(1)

    if to_stdout:
        for key in keys:
            export_to_stdout(key, fmt=fmt, with_prs=with_prs, with_tests=with_tests, include_custom=include_custom, minimal=minimal)
    else:
        output_dir = Path(output)
        success = 0
        for key in keys:
            if export_ticket(
                key,
                output_dir,
                fmt=fmt,
                with_prs=with_prs,
                with_tests=with_tests,
                include_custom=include_custom,
                with_attachments=True,
            ):
                success += 1
        print(f"\nExported {success}/{len(keys)} tickets to {output_dir}/")
