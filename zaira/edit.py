"""Edit Jira ticket fields."""

import argparse
import sys
from typing import Any

import yaml

from zaira.info import get_editmeta_field
from zaira.jira_client import format_jira_error, get_jira, get_jira_site


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


def _get_project_components(project: str) -> list:
    """Fetch project components from Jira, cached per process."""
    if project not in _component_cache:
        jira = get_jira()
        _component_cache[project] = jira.project_components(project)
    return _component_cache[project]


_component_cache: dict = {}


def _resolve_component(name: str, project: str) -> dict:
    """Resolve component name case-insensitively to {"id": ...} using live project components."""
    if not project:
        return {"name": name}
    name_lower = name.lower()
    components = _get_project_components(project)
    for comp in components:
        if comp.name.lower() == name_lower:
            return {"id": comp.id}
    valid = sorted(c.name for c in components)
    print(f"Error: component '{name}' not found in project {project}.", file=sys.stderr)
    print(f"Valid components: {', '.join(valid)}", file=sys.stderr)
    sys.exit(1)


def map_field(
    name: str, value: str, project: str = "", issue_type: str = ""
) -> tuple[str, Any]:
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
            names = (
                value
                if isinstance(value, list)
                else [c.strip() for c in value.split(",")]
            )
            return field_id, [_resolve_component(n, project) for n in names]
        return field_id, value

    # Look up in editmeta
    em = get_editmeta_field(project, issue_type, name)
    if em:
        field_id, field_def = em
        formatted = format_field_value(
            field_id, value, project=project, issue_type=issue_type
        )
        _validate_field_value(field_id, value, field_def)
        return field_id, formatted

    # Fall back to using name as-is (might be a field ID)
    return name, format_field_value(name, value, project=project, issue_type=issue_type)


def format_field_value(
    field_id: str, value: Any, project: str = "", issue_type: str = ""
) -> Any:
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

    # Look up type from editmeta
    field_type = None
    item_type = None
    from zaira.info import _parse_field_type

    em = get_editmeta_field(project, issue_type, field_id)
    if em:
        _, field_def = em
        type_str = field_def.get("type", "")
        if type_str:
            field_type, item_type = _parse_field_type(type_str)

    if field_type == "number":
        if isinstance(value, str):
            return _parse_number(value)
        return value
    elif field_type in (
        "resolution",
        "priority",
        "version",
        "issuetype",
        "securitylevel",
    ):
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
            print(
                f"Warning: '{v}' not in allowed values for {field_name}",
                file=sys.stderr,
            )
            if len(allowed) <= 20:
                print(f"  Allowed: {', '.join(allowed)}", file=sys.stderr)
            else:
                print(
                    f"  Allowed ({len(allowed)} values): {', '.join(allowed[:20])}, ...",
                    file=sys.stderr,
                )
            break  # One warning per field is enough


def parse_field_args(
    field_args: list[str], project: str = "", issue_type: str = ""
) -> dict:
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
        field_id, formatted_value = map_field(
            name.strip(), value.strip(), project=project, issue_type=issue_type
        )
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
        field_id, formatted_value = map_field(
            name, value, project=project, issue_type=issue_type
        )
        fields[field_id] = formatted_value
    return fields


def get_allowed_values(
    jira, key: str, field_ids: list[str], issue_type: str = ""
) -> dict[str, list[str]]:
    """Get allowed values for fields.

    Checks editmeta cache first, then tries API editmeta, then autocomplete.

    Returns:
        Dict of field_id -> list of allowed value strings
    """
    from zaira.info import get_field_name, load_editmeta

    result = {}

    # Check editmeta cache first (fields keyed by name, search by ID)
    project = key.split("-")[0]

    # For components, always use live project_components — editmeta returns an unreliable superset
    if "components" in field_ids:
        result["components"] = sorted(c.name for c in _get_project_components(project))

    editmeta = load_editmeta(project, issue_type) if issue_type else None
    if editmeta and "fields" in editmeta:
        # Build ID -> field_def lookup
        id_to_field = {
            fdef["id"]: fdef for fdef in editmeta["fields"].values() if "id" in fdef
        }
        for fid in field_ids:
            if fid in id_to_field and fid not in result:
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
        print(f"Error updating {key}: {format_jira_error(e)}", file=sys.stderr)
        return

    try:
        error_data = json.loads(e.response.text)
    except (json.JSONDecodeError, ValueError):
        print(f"Error updating {key}: {format_jira_error(e)}", file=sys.stderr)
        return

    errors = error_data.get("errors", {})
    error_messages = error_data.get("errorMessages", [])

    # Check if any error mentions "not on the appropriate screen"
    has_screen_error = any(
        "appropriate screen" in str(msg).lower() for msg in error_messages
    ) or any("appropriate screen" in str(msg).lower() for msg in errors.values())

    for msg in error_messages:
        print(f"Error from Jira server: {msg}", file=sys.stderr)
    for msg in errors.values():
        print(f"Error from Jira server: {msg}", file=sys.stderr)

    # Suggest cache reset for "appropriate screen" errors
    if has_screen_error:
        print(
            "\nTroubleshooting: If the server-side workflow was recently changed,",
            file=sys.stderr,
        )
        print("try 'zaira reset' to clear the cached schema.", file=sys.stderr)

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

    # Fetch issue type and ensure editmeta is cached
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="issuetype")
        issue_type = issue.fields.issuetype.name
    except Exception as e:
        print(
            f"Error: Could not fetch issue {key}: {format_jira_error(e)}",
            file=sys.stderr,
        )
        sys.exit(1)

    from zaira.info import ensure_editmeta

    ensure_editmeta(key, issue_type)

    fields = {}

    # Handle --title and --description (legacy)
    if args.title:
        fields["summary"] = args.title
    if args.description:
        from zaira.create import detect_markdown
        from zaira.mdconv import markdown_to_jira_wiki

        desc = read_input(args.description)
        if detect_markdown(desc):
            desc = markdown_to_jira_wiki(desc)
        fields["description"] = desc

    # Handle --field arguments
    field_args = getattr(args, "field", None) or []
    if field_args:
        fields.update(
            parse_field_args(field_args, project=project, issue_type=issue_type)
        )

    # Handle --from file/stdin
    from_input = getattr(args, "from_file", None)
    if from_input:
        content = read_input(from_input)
        fields.update(
            parse_yaml_fields(content, project=project, issue_type=issue_type)
        )

    if not fields:
        print(
            "Error: No fields to update. Use --title, --description, --field, or --from",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check allowed_fields whitelist (unless --no-check is set)
    if not getattr(args, "no_check", False):
        from zaira.rules import check_field_allowed, load_allowed_fields

        allowed = load_allowed_fields(project=project)
        field_errors = []
        for field_id in fields.keys():
            error = check_field_allowed(field_id, allowed)
            if error:
                field_errors.append(error)

        if field_errors:
            print("Error: The following fields are not allowed:", file=sys.stderr)
            for err in field_errors:
                field_name = err["field"]
                suggestions = err["suggestions"]
                print(f"  - {field_name}", file=sys.stderr)
                if suggestions:
                    print("    Did you mean:", file=sys.stderr)
                    for s in suggestions:
                        print(f"      {s}", file=sys.stderr)
            print("\nUse --no-check to skip validation.", file=sys.stderr)
            sys.exit(1)

    jira_site = get_jira_site()

    if edit_ticket(key, fields):
        print(f"Updated {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record

        user_field_names = []
        if args.title:
            user_field_names.append("title")
        if args.description:
            user_field_names.append("description")
        for f in getattr(args, "field", None) or []:
            user_field_names.append(f.split("=")[0].strip())
        if getattr(args, "from_file", None):
            user_field_names.append("(from file)")
        record("edit", key, ", ".join(user_field_names) or ", ".join(fields.keys()))
    else:
        sys.exit(1)
