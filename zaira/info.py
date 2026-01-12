"""Query Jira instance metadata."""

import argparse
import json
import sys

from zaira.config import find_project_root
from zaira.jira_client import get_jira
from zaira.types import ZSchema


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


def fields_command(args: argparse.Namespace) -> None:
    """List custom fields."""
    jira = get_jira()
    try:
        fields = jira.fields()
    except Exception as e:
        print(f"Error fetching fields: {e}", file=sys.stderr)
        sys.exit(1)

    # Filter to custom fields only (unless --all)
    show_all = getattr(args, "all", False)
    filter_text = getattr(args, "filter", None)

    if show_all:
        result = fields
    else:
        result = [f for f in fields if f["custom"]]

    if filter_text:
        filter_lower = filter_text.lower()
        result = [
            f for f in result
            if filter_lower in f["name"].lower() or filter_lower in f["id"].lower()
        ]

    result = sorted(result, key=lambda x: x["name"].lower())

    print(f"{'ID':<25} {'Name':<40}")
    print("-" * 65)
    for f in result:
        print(f"{f['id']:<25} {f['name']:<40}")


def fetch_and_save_schema(
    project_root: "Path | None" = None,
    project: str | None = None,
    components: list[str] | None = None,
    labels: list[str] | None = None,
) -> None:
    """Fetch all Jira metadata and save to zschema.json.

    Args:
        project_root: Project root directory. If None, finds it automatically.
        project: Project key for fetching project-specific metadata.
        components: Pre-fetched components list (avoids re-fetching).
        labels: Pre-fetched labels list (avoids re-fetching).
    """
    from pathlib import Path

    if project_root is None:
        project_root = find_project_root()
    if not project_root:
        print("Error: No zproject.toml found", file=sys.stderr)
        sys.exit(1)

    jira = get_jira()
    schema: ZSchema = {}

    print("Fetching fields...")
    try:
        fields = jira.fields()
        schema["fields"] = {f["id"]: f["name"] for f in fields}
    except Exception as e:
        print(f"  Warning: Could not fetch fields: {e}", file=sys.stderr)

    print("Fetching statuses...")
    try:
        statuses = jira.statuses()
        schema["statuses"] = {
            s.name: s.statusCategory.name if hasattr(s, "statusCategory") else None
            for s in statuses
        }
    except Exception as e:
        print(f"  Warning: Could not fetch statuses: {e}", file=sys.stderr)

    print("Fetching priorities...")
    try:
        priorities = jira.priorities()
        schema["priorities"] = [p.name for p in priorities]
    except Exception as e:
        print(f"  Warning: Could not fetch priorities: {e}", file=sys.stderr)

    print("Fetching issue types...")
    try:
        issue_types = jira.issue_types()
        schema["issueTypes"] = {t.name: {"subtask": t.subtask} for t in issue_types}
    except Exception as e:
        print(f"  Warning: Could not fetch issue types: {e}", file=sys.stderr)

    print("Fetching link types...")
    try:
        link_types = jira.issue_link_types()
        schema["linkTypes"] = {
            t.name: {"outward": t.outward, "inward": t.inward} for t in link_types
        }
    except Exception as e:
        print(f"  Warning: Could not fetch link types: {e}", file=sys.stderr)

    # Project-specific metadata
    if components is not None:
        schema["components"] = components
    if labels is not None:
        schema["labels"] = labels

    schema_file = project_root / "zschema.json"
    schema_file.write_text(json.dumps(schema, indent=2))
    print(f"Saved schema to {schema_file}")


def info_command(args: argparse.Namespace) -> None:
    """Handle info subcommand."""
    if getattr(args, "save", False):
        fetch_and_save_schema()
        return
    if hasattr(args, 'info_func'):
        args.info_func(args)
    else:
        print("Usage: zaira info <subcommand>")
        print("Subcommands: link-types, statuses, priorities, issue-types, fields")
        print("\nUse 'zaira info --save' to save all metadata to zschema.json")
        sys.exit(1)
