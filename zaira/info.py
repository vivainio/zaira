"""Query Jira instance metadata."""

import argparse
import sys

from zaira.jira_client import get_jira


def link_types_command(args: argparse.Namespace) -> None:
    """List available link types."""
    jira = get_jira()
    try:
        types = jira.issue_link_types()
    except Exception as e:
        print(f"Error fetching link types: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{'Type':<20} {'Outward':<25} {'Inward':<25}")
    print("-" * 70)
    for t in sorted(types, key=lambda x: x.name):
        print(f"{t.name:<20} {t.outward:<25} {t.inward:<25}")


def statuses_command(args: argparse.Namespace) -> None:
    """List available statuses."""
    jira = get_jira()
    try:
        statuses = jira.statuses()
    except Exception as e:
        print(f"Error fetching statuses: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{'Status':<30} {'Category':<20}")
    print("-" * 50)
    for s in sorted(statuses, key=lambda x: x.name):
        category = s.statusCategory.name if hasattr(s, 'statusCategory') else "-"
        print(f"{s.name:<30} {category:<20}")


def priorities_command(args: argparse.Namespace) -> None:
    """List available priorities."""
    jira = get_jira()
    try:
        priorities = jira.priorities()
    except Exception as e:
        print(f"Error fetching priorities: {e}", file=sys.stderr)
        sys.exit(1)

    print("Priorities:")
    for p in priorities:
        print(f"  {p.name}")


def issue_types_command(args: argparse.Namespace) -> None:
    """List available issue types."""
    jira = get_jira()
    try:
        types = jira.issue_types()
    except Exception as e:
        print(f"Error fetching issue types: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{'Type':<25} {'Subtask':<10}")
    print("-" * 35)
    for t in sorted(types, key=lambda x: x.name):
        subtask = "yes" if t.subtask else "no"
        print(f"{t.name:<25} {subtask:<10}")


def info_command(args: argparse.Namespace) -> None:
    """Handle info subcommand."""
    if hasattr(args, 'info_func'):
        args.info_func(args)
    else:
        print("Usage: zaira info <subcommand>")
        print("Subcommands: link-types, statuses, priorities, issue-types")
        sys.exit(1)
