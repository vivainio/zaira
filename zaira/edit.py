"""Edit Jira ticket fields."""

import argparse
import sys
from typing import Any

import yaml

from zaira.info import get_editmeta_field, get_field_id, get_field_item_type, get_field_type
from zaira.jira_client import get_jira, get_jira_site


# Standard field name mappings
STANDARD_FIELDS = {
    "summary": "summary",
    "title": "summary",
    "description": "description",
    "priority": "priority",
    "resolution": "resolution",
    "assignee": "assignee",
    "labels": "labels",
    "components": "components",
}

# Standard fields that use {"name": value} format
_NAME_FIELDS = {"priority", "resolution"}


def read_input(value: str) -> str:
    """Read value, supporting stdin with '-'."""
    if value == "-":
        return sys.stdin.read()
    return value


def _format_assignee(value: str | None) -> dict | None:
    """Format assignee value for Jira API.

    Supports "me" as a special value to assign to the current user.
    Also looks up accountId by email/name for Jira Cloud compatibility.
    """
    if not value:
        return None
    jira = get_jira()
    if value.lower() == "me":
        me = jira.myself()
        return {"accountId": me["accountId"]}
    # Look up user by email/name to get accountId (required for Jira Cloud)
    users = jira.search_users(query=value)
    if users:
        return {"accountId": users[0].accountId}
    # Fall back to using value directly as accountId
    return {"accountId": value}


def map_field(name: str, value: str, project: str = "", issue_type: str = "") -> tuple[str, Any]:
    """Map a field name to Jira field ID and format value.

    Args:
        name: Field name or ID
        value: Raw value string
        project: Project key for editmeta lookup
        issue_type: Issue type name for editmeta lookup

    Returns:
        Tuple of (field_id, formatted_value)
    """
    name_lower = name.lower()

    # Handle standard fields
    if name_lower in STANDARD_FIELDS:
        field_id = STANDARD_FIELDS[name_lower]
        if field_id in _NAME_FIELDS:
            return field_id, {"name": value}
        if field_id == "assignee":
            return field_id, _format_assignee(value)
        if field_id == "labels":
            if isinstance(value, list):
                return field_id, value
            return field_id, [v.strip() for v in value.split(",")]
        if field_id == "components":
            if isinstance(value, list):
                return field_id, [{"name": c} for c in value]
            return field_id, [{"name": c.strip()} for c in value.split(",")]
        return field_id, value

    # Try editmeta lookup first (has richer type info)
    em = get_editmeta_field(project, issue_type, name)
    if em:
        field_id, field_def = em
        formatted = format_field_value(field_id, value, project=project, issue_type=issue_type)
        _validate_field_value(field_id, value, field_def)
        return field_id, formatted

    # Try custom field lookup from global schema
    field_id = get_field_id(name)
    if field_id:
        return field_id, format_field_value(field_id, value, project=project, issue_type=issue_type)

    # Fall back to using name as-is (might be a field ID)
    return name, format_field_value(name, value, project=project, issue_type=issue_type)


def format_field_value(field_id: str, value: Any, project: str = "", issue_type: str = "") -> Any:
    """Format value based on field type.

    Wraps option/select field values in {"value": ...} format.
    Converts string values to numbers for numeric fields.
    Uses editmeta for richer type info when available.
    """
    # Already formatted as dict/list - leave as is
    if isinstance(value, (dict, list)):
        return value

    # Already a number - leave as is
    if isinstance(value, (int, float)):
        return value

    # Try editmeta for type info first
    field_type = None
    item_type = None
    if project and issue_type:
        from zaira.info import _parse_field_type
        em = get_editmeta_field(project, issue_type, field_id)
        if em:
            _, field_def = em
            type_str = field_def.get("type", "")
            if type_str:
                field_type, item_type = _parse_field_type(type_str)

    # Fall back to global schema
    if field_type is None:
        field_type = get_field_type(field_id)
    if field_type == "array" and item_type is None:
        item_type = get_field_item_type(field_id)

    if field_type == "number":
        if isinstance(value, str):
            return _parse_number(value)
        return value
    elif field_type in ("resolution", "priority", "version", "issuetype", "securitylevel"):
        return {"name": value}
    elif field_type == "user":
        return _format_assignee(value)
    elif field_type == "option":
        return {"value": value}
    elif field_type == "array":
        if isinstance(value, str):
            values = [v.strip() for v in value.split(",")]
            if item_type == "string":
                return values
            if item_type == "user":
                return [_format_assignee(v) for v in values]
            return [{"value": v} for v in values]
        return value

    return value


def _parse_number(value: str) -> int | float | str:
    """Parse string to number if possible.

    Returns:
        int if value is an integer, float if decimal, original string otherwise.
    """
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _validate_field_value(field_id: str, value: Any, editmeta_field: dict) -> None:
    """Validate value against editmeta allowedValues (warning only).

    Prints a warning to stderr if the value is not in the allowed values list.
    Does not block — Jira is the authority.
    """
    allowed = editmeta_field.get("allowedValues")
    if not allowed:
        return

    field_name = editmeta_field.get("name", field_id)
    type_str = editmeta_field.get("type", "")

    # For array fields, validate each comma-separated value
    if type_str.startswith("[") and isinstance(value, str):
        values = [v.strip() for v in value.split(",")]
    else:
        values = [str(value)]

    allowed_lower = {v.lower(): v for v in allowed}
    for v in values:
        if v.lower() not in allowed_lower:
            print(f"Warning: '{v}' not in allowed values for {field_name}", file=sys.stderr)
            if len(allowed) <= 20:
                print(f"  Allowed: {', '.join(allowed)}", file=sys.stderr)
            else:
                print(f"  Allowed ({len(allowed)} values): {', '.join(allowed[:20])}, ...", file=sys.stderr)
            break  # One warning per field is enough


def parse_field_args(field_args: list[str], project: str = "", issue_type: str = "") -> dict:
    """Parse --field arguments into a fields dict.

    Args:
        field_args: List of "Name=value" strings
        project: Project key for editmeta lookup
        issue_type: Issue type name for editmeta lookup

    Returns:
        Dict of field_id -> value
    """
    fields = {}
    for arg in field_args:
        if "=" not in arg:
            print(
                f"Warning: Invalid field format '{arg}', expected 'Name=value'",
                file=sys.stderr,
            )
            continue
        name, value = arg.split("=", 1)
        field_id, formatted_value = map_field(name.strip(), value.strip(), project=project, issue_type=issue_type)
        fields[field_id] = formatted_value
    return fields


def parse_yaml_fields(content: str, project: str = "", issue_type: str = "") -> dict:
    """Parse YAML content into a fields dict.

    Args:
        content: YAML string with field: value pairs
        project: Project key for editmeta lookup
        issue_type: Issue type name for editmeta lookup

    Returns:
        Dict of field_id -> value
    """
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        return {}

    fields = {}
    for name, value in data.items():
        field_id, formatted_value = map_field(name, value, project=project, issue_type=issue_type)
        fields[field_id] = formatted_value
    return fields


def get_allowed_values(jira, key: str, field_ids: list[str], issue_type: str = "") -> dict[str, list[str]]:
    """Get allowed values for fields.

    Checks editmeta cache first, then tries API editmeta, then autocomplete.

    Returns:
        Dict of field_id -> list of allowed value strings
    """
    from zaira.info import get_field_name, load_editmeta

    result = {}

    # Check editmeta cache first (fields keyed by name, search by ID)
    project = key.split("-")[0]
    editmeta = load_editmeta(project, issue_type) if issue_type else None
    if editmeta and "fields" in editmeta:
        # Build ID -> field_def lookup
        id_to_field = {fdef["id"]: fdef for fdef in editmeta["fields"].values() if "id" in fdef}
        for fid in field_ids:
            if fid in id_to_field:
                allowed = id_to_field[fid].get("allowedValues", [])
                if allowed:
                    result[fid] = allowed

    remaining = [fid for fid in field_ids if fid not in result]
    if not remaining:
        return result

    # Try API editmeta for fields not in cache
    try:
        meta = jira._get_json(f"issue/{key}/editmeta")
        for fid in remaining:
            if fid in meta.get("fields", {}):
                allowed = meta["fields"][fid].get("allowedValues", [])
                if allowed:
                    result[fid] = [v.get("value", v.get("name", "?")) for v in allowed]
    except Exception:
        pass

    # For fields not found in editmeta, try autocomplete API
    for fid in remaining:
        if fid in result:
            continue
        field_name = get_field_name(fid)
        if not field_name:
            continue
        try:
            data = jira._get_json(
                "jql/autocompletedata/suggestions", params={"fieldName": field_name}
            )
            values = [
                r.get("value", r.get("displayName", "?"))
                for r in data.get("results", [])
            ]
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


def _print_allowed_values(
    allowed: dict[str, list[str]], errors: dict[str, str]
) -> None:
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
    project = key.split("-")[0]

    # Fetch issue type for editmeta lookup
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="issuetype")
        issue_type = issue.fields.issuetype.name
    except Exception as e:
        print(f"Error: Could not fetch issue {key}: {e}", file=sys.stderr)
        sys.exit(1)

    fields = {}

    # Handle --title and --description (legacy)
    if args.title:
        fields["summary"] = args.title
    if args.description:
        from zaira.create import detect_markdown

        desc = read_input(args.description)
        md_errors = detect_markdown(desc)
        if md_errors:
            print(
                "Error: Description contains markdown syntax. Use Jira wiki markup instead:",
                file=sys.stderr,
            )
            for err in md_errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)
        fields["description"] = desc

    # Handle --field arguments
    field_args = getattr(args, "field", None) or []
    if field_args:
        fields.update(parse_field_args(field_args, project=project, issue_type=issue_type))

    # Handle --from file/stdin
    from_input = getattr(args, "from_file", None)
    if from_input:
        content = read_input(from_input)
        fields.update(parse_yaml_fields(content, project=project, issue_type=issue_type))

    if not fields:
        print(
            "Error: No fields to update. Use --title, --description, --field, or --from",
            file=sys.stderr,
        )
        sys.exit(1)

    jira_site = get_jira_site()

    if edit_ticket(key, fields):
        print(f"Updated {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
    else:
        sys.exit(1)
