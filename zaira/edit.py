"""Edit Jira ticket fields."""

import argparse
import sys

import yaml

from zaira.info import get_field_id, get_field_type
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
        return field_id, format_field_value(field_id, value)

    # Fall back to using name as-is (might be a field ID)
    return name, format_field_value(name, value)


def format_field_value(field_id: str, value: any) -> any:
    """Format value based on field type.

    Wraps option/select field values in {"value": ...} format.
    """
    # Already formatted as dict/list - leave as is
    if isinstance(value, (dict, list)):
        return value

    field_type = get_field_type(field_id)
    if field_type == "option":
        # Single select field
        return {"value": value}
    elif field_type == "array":
        # Could be multi-select - check if string needs splitting
        if isinstance(value, str):
            values = [v.strip() for v in value.split(",")]
            # Try as option array (multi-select)
            return [{"value": v} for v in values]
        return value

    return value


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


def get_allowed_values(jira, key: str, field_ids: list[str]) -> dict[str, list[str]]:
    """Get allowed values for fields.

    Tries editmeta first, then falls back to autocomplete API.

    Returns:
        Dict of field_id -> list of allowed value strings
    """
    from zaira.info import get_field_name

    result = {}

    # Try editmeta first
    try:
        meta = jira._get_json(f"issue/{key}/editmeta")
        for fid in field_ids:
            if fid in meta.get("fields", {}):
                allowed = meta["fields"][fid].get("allowedValues", [])
                if allowed:
                    result[fid] = [v.get("value", v.get("name", "?")) for v in allowed]
    except Exception:
        pass

    # For fields not found in editmeta, try autocomplete API
    for fid in field_ids:
        if fid in result:
            continue
        field_name = get_field_name(fid)
        if not field_name:
            continue
        try:
            data = jira._get_json("jql/autocompletedata/suggestions", params={
                "fieldName": field_name
            })
            values = [r.get("value", r.get("displayName", "?")) for r in data.get("results", [])]
            if values:
                result[fid] = values
        except Exception:
            pass

    return result


def _extract_field_name(error_msg: str, fallback: str) -> str:
    """Extract field name from error message like 'Specify a valid value for X'."""
    if "valid" in error_msg.lower():
        parts = error_msg.split(" for ")
        if len(parts) > 1:
            return parts[-1]
    return fallback


def _print_allowed_values(allowed: dict[str, list[str]], errors: dict[str, str]) -> None:
    """Print allowed values for failed fields."""
    for fid, values in allowed.items():
        field_name = _extract_field_name(errors.get(fid, fid), fid)
        print(f"\nAllowed values for {field_name}:", file=sys.stderr)
        for v in values[:20]:
            print(f"  - {v}", file=sys.stderr)
        if len(values) > 20:
            print(f"  ... and {len(values) - 20} more", file=sys.stderr)


def _handle_update_error(e: Exception, jira, key: str) -> None:
    """Handle and display Jira update errors with allowed values."""
    import json

    if not (hasattr(e, "response") and hasattr(e.response, "text")):
        print(f"Error updating {key}: {e}", file=sys.stderr)
        return

    try:
        error_data = json.loads(e.response.text)
    except (json.JSONDecodeError, ValueError):
        print(f"Error updating {key}: {e}", file=sys.stderr)
        return

    errors = error_data.get("errors", {})
    error_messages = error_data.get("errorMessages", [])

    for msg in error_messages:
        print(f"Error: {msg}", file=sys.stderr)
    for msg in errors.values():
        print(f"Error: {msg}", file=sys.stderr)

    failed_fields = list(errors.keys())
    if failed_fields:
        allowed = get_allowed_values(jira, key, failed_fields)
        _print_allowed_values(allowed, errors)


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
        _handle_update_error(e, jira, key)
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

    if edit_ticket(key, fields):
        print(f"Updated {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
    else:
        sys.exit(1)
