"""Edit Jira ticket fields."""

import argparse
import sys

import yaml

from zaira.info import get_field_id
from zaira.jira_client import get_jira, get_jira_site


# Standard field name mappings
STANDARD_FIELDS = {
    "summary": "summary",
    "title": "summary",
    "description": "description",
    "priority": "priority",
    "assignee": "assignee",
    "labels": "labels",
    "components": "components",
}


def read_input(value: str) -> str:
    """Read value, supporting stdin with '-'."""
    if value == "-":
        return sys.stdin.read()
    return value


def map_field(name: str, value: str) -> tuple[str, any]:
    """Map a field name to Jira field ID and format value.

    Returns:
        Tuple of (field_id, formatted_value)
    """
    name_lower = name.lower()

    # Handle standard fields
    if name_lower in STANDARD_FIELDS:
        field_id = STANDARD_FIELDS[name_lower]
        if field_id == "priority":
            return field_id, {"name": value}
        if field_id == "assignee":
            return field_id, {"name": value} if value else None
        if field_id == "labels":
            if isinstance(value, list):
                return field_id, value
            return field_id, [v.strip() for v in value.split(",")]
        if field_id == "components":
            if isinstance(value, list):
                return field_id, [{"name": c} for c in value]
            return field_id, [{"name": c.strip()} for c in value.split(",")]
        return field_id, value

    # Try custom field lookup
    field_id = get_field_id(name)
    if field_id:
        return field_id, value

    # Fall back to using name as-is (might be a field ID)
    return name, value


def parse_field_args(field_args: list[str]) -> dict:
    """Parse --field arguments into a fields dict.

    Args:
        field_args: List of "Name=value" strings

    Returns:
        Dict of field_id -> value
    """
    fields = {}
    for arg in field_args:
        if "=" not in arg:
            print(f"Warning: Invalid field format '{arg}', expected 'Name=value'", file=sys.stderr)
            continue
        name, value = arg.split("=", 1)
        field_id, formatted_value = map_field(name.strip(), value.strip())
        fields[field_id] = formatted_value
    return fields


def parse_yaml_fields(content: str) -> dict:
    """Parse YAML content into a fields dict.

    Args:
        content: YAML string with field: value pairs

    Returns:
        Dict of field_id -> value
    """
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        return {}

    fields = {}
    for name, value in data.items():
        field_id, formatted_value = map_field(name, value)
        fields[field_id] = formatted_value
    return fields


def edit_ticket(key: str, fields: dict) -> bool:
    """Edit a Jira ticket's fields.

    Args:
        key: Ticket key (e.g., PROJ-123)
        fields: Dict of field_id -> value

    Returns:
        True if successful, False otherwise
    """
    if not fields:
        return True

    jira = get_jira()
    try:
        issue = jira.issue(key)
        issue.update(fields=fields)
        return True
    except Exception as e:
        print(f"Error updating {key}: {e}", file=sys.stderr)
        return False


def edit_command(args: argparse.Namespace) -> None:
    """Handle edit subcommand."""
    key = args.key.upper()
    fields = {}

    # Handle --title and --description (legacy)
    if args.title:
        fields["summary"] = args.title
    if args.description:
        fields["description"] = read_input(args.description)

    # Handle --field arguments
    field_args = getattr(args, "field", None) or []
    if field_args:
        fields.update(parse_field_args(field_args))

    # Handle --from file/stdin
    from_input = getattr(args, "from_file", None)
    if from_input:
        content = read_input(from_input)
        fields.update(parse_yaml_fields(content))

    if not fields:
        print("Error: No fields to update. Use --title, --description, --field, or --from", file=sys.stderr)
        sys.exit(1)

    jira_site = get_jira_site()
    field_names = list(fields.keys())

    print(f"Updating {len(field_names)} field(s) for {key}...")

    if edit_ticket(key, fields):
        print(f"Updated {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
    else:
        sys.exit(1)
