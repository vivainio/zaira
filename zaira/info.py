"""Query Jira instance metadata."""

import argparse
import json
import sys

from zaira.jira_client import get_jira, get_schema_path, get_project_schema_path, CACHE_DIR
from zaira.types import ProjectSchema, ZSchema


def load_schema() -> ZSchema | None:
    """Load cached instance schema from global cache directory.

    Returns:
        Schema dict if found, None otherwise.
    """
    schema_file = get_schema_path()
    if not schema_file.exists():
        return None
    return json.load(schema_file.open())


def save_schema(schema: ZSchema) -> None:
    """Save instance schema to global cache directory."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    schema_file = get_schema_path()
    schema_file.write_text(json.dumps(schema, indent=2))


def update_schema(key: str, value: dict | list) -> None:
    """Update a single key in the cached schema."""
    schema = load_schema() or {}
    schema[key] = value
    save_schema(schema)


def get_field_id(name: str) -> str | None:
    """Look up field ID by name (reverse lookup).

    Args:
        name: Human-readable field name (e.g., "Epic Link")

    Returns:
        Field ID (e.g., "customfield_10001") or None if not found.
    """
    schema = load_schema()
    if not schema or "fields" not in schema:
        return None
    # Schema stores {id: name}, reverse it
    for field_id, field_name in schema["fields"].items():
        if field_name.lower() == name.lower():
            return field_id
    return None


def get_field_name(field_id: str) -> str | None:
    """Look up field name by ID.

    Args:
        field_id: Jira field ID (e.g., "customfield_10001")

    Returns:
        Human-readable name (e.g., "Epic Link") or None if not found.
    """
    schema = load_schema()
    if not schema or "fields" not in schema:
        return None
    return schema["fields"].get(field_id)


def get_field_map() -> dict[str, str]:
    """Get full field name -> ID mapping.

    Returns:
        Dict mapping field names to IDs.
    """
    schema = load_schema()
    if not schema or "fields" not in schema:
        return {}
    return {name: field_id for field_id, name in schema["fields"].items()}


def load_project_schema(project: str) -> ProjectSchema | None:
    """Load cached project schema from global cache directory.

    Returns:
        Project schema dict if found, None otherwise.
    """
    schema_file = get_project_schema_path(project)
    if not schema_file.exists():
        return None
    return json.load(schema_file.open())


def link_types_command(args: argparse.Namespace) -> None:
    """List available link types."""
    refresh = getattr(args, "refresh", False)
    schema = load_schema()

    if not refresh and schema and "linkTypes" in schema:
        link_types = schema["linkTypes"]
    else:
        jira = get_jira()
        try:
            types = jira.issue_link_types()
            link_types = {t.name: {"outward": t.outward, "inward": t.inward} for t in types}
            update_schema("linkTypes", link_types)
        except Exception as e:
            print(f"Error fetching link types: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"{'Type':<20} {'Outward':<25} {'Inward':<25}")
    print("-" * 70)
    for name in sorted(link_types.keys()):
        t = link_types[name]
        print(f"{name:<20} {t['outward']:<25} {t['inward']:<25}")


def statuses_command(args: argparse.Namespace) -> None:
    """List available statuses."""
    refresh = getattr(args, "refresh", False)
    schema = load_schema()

    if not refresh and schema and "statuses" in schema:
        statuses = schema["statuses"]
    else:
        jira = get_jira()
        try:
            raw = jira.statuses()
            statuses = {
                s.name: s.statusCategory.name if hasattr(s, "statusCategory") else None
                for s in raw
            }
            update_schema("statuses", statuses)
        except Exception as e:
            print(f"Error fetching statuses: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"{'Status':<30} {'Category':<20}")
    print("-" * 50)
    for name in sorted(statuses.keys()):
        category = statuses[name] or "-"
        print(f"{name:<30} {category:<20}")


def priorities_command(args: argparse.Namespace) -> None:
    """List available priorities."""
    refresh = getattr(args, "refresh", False)
    schema = load_schema()

    if not refresh and schema and "priorities" in schema:
        priorities = schema["priorities"]
    else:
        jira = get_jira()
        try:
            raw = jira.priorities()
            priorities = [p.name for p in raw]
            update_schema("priorities", priorities)
        except Exception as e:
            print(f"Error fetching priorities: {e}", file=sys.stderr)
            sys.exit(1)

    print("Priorities:")
    for name in priorities:
        print(f"  {name}")


def issue_types_command(args: argparse.Namespace) -> None:
    """List available issue types."""
    refresh = getattr(args, "refresh", False)
    schema = load_schema()

    if not refresh and schema and "issueTypes" in schema:
        issue_types = schema["issueTypes"]
    else:
        jira = get_jira()
        try:
            raw = jira.issue_types()
            issue_types = {t.name: {"subtask": t.subtask} for t in raw}
            update_schema("issueTypes", issue_types)
        except Exception as e:
            print(f"Error fetching issue types: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"{'Type':<25} {'Subtask':<10}")
    print("-" * 35)
    for name in sorted(issue_types.keys()):
        subtask = "yes" if issue_types[name]["subtask"] else "no"
        print(f"{name:<25} {subtask:<10}")


def fields_command(args: argparse.Namespace) -> None:
    """List custom fields."""
    refresh = getattr(args, "refresh", False)
    schema = load_schema()

    if not refresh and schema and "fields" in schema:
        # Cache stores {id: name}, convert to list of dicts
        fields = [{"id": k, "name": v} for k, v in schema["fields"].items()]
    else:
        jira = get_jira()
        try:
            fields = jira.fields()
            update_schema("fields", {f["id"]: f["name"] for f in fields})
        except Exception as e:
            print(f"Error fetching fields: {e}", file=sys.stderr)
            sys.exit(1)

    # Filter to custom fields only (unless --all)
    show_all = getattr(args, "all", False)
    filter_text = getattr(args, "filter", None)

    if show_all:
        result = fields
    else:
        # Custom fields have id starting with "customfield_"
        result = [f for f in fields if f.get("custom") or f["id"].startswith("customfield_")]

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
    project: str | None = None,
    components: list[str] | None = None,
    labels: list[str] | None = None,
) -> None:
    """Fetch Jira instance metadata and save to global cache.

    Instance schema: ~/.cache/zaira/zschema_PROFILE.json
    Project schema: ~/.cache/zaira/zproject_PROFILE_PROJECT.json
    """
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

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Save instance schema
    schema_file = get_schema_path()
    schema_file.write_text(json.dumps(schema, indent=2))
    print(f"Saved instance schema to {schema_file}")

    # Save project schema if provided
    if project and (components is not None or labels is not None):
        project_schema: ProjectSchema = {}
        if components is not None:
            project_schema["components"] = components
        if labels is not None:
            project_schema["labels"] = labels
        project_file = get_project_schema_path(project)
        project_file.write_text(json.dumps(project_schema, indent=2))
        print(f"Saved project schema to {project_file}")


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
        print("\nUse 'zaira info --save' to refresh cached schema")
        sys.exit(1)
