"""Query Jira instance metadata."""

import argparse
import json
import sys
from typing import Callable, TypeVar

import yaml

from zaira.jira_client import (
    get_jira,
    get_schema_path,
    get_project_schema_path,
    get_editmeta_path,
    CACHE_DIR,
)
from zaira.types import EditmetaSchema, ProjectSchema, ZSchema

T = TypeVar("T")


SCHEMA_VERSION = 2
FIELD_DESCRIPTIONS_FILE = CACHE_DIR / "field_descriptions.yaml"


def load_field_descriptions() -> dict[str, str]:
    """Load shared field descriptions (field name -> description)."""
    if not FIELD_DESCRIPTIONS_FILE.exists():
        return {}
    data = yaml.safe_load(FIELD_DESCRIPTIONS_FILE.read_text())
    return data if isinstance(data, dict) else {}


def save_field_descriptions(descriptions: dict[str, str]) -> None:
    """Save shared field descriptions."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FIELD_DESCRIPTIONS_FILE.write_text(
        yaml.dump(descriptions, default_flow_style=False, sort_keys=True, allow_unicode=True)
    )


def load_schema() -> ZSchema | None:
    """Load cached instance schema from global cache directory.

    Returns None if missing or outdated (wrong version).
    """
    schema_file = get_schema_path()
    if not schema_file.exists():
        return None
    schema = json.load(schema_file.open())
    if schema.get("version") != SCHEMA_VERSION:
        return None
    return schema


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


def _parse_field_type(type_str: str) -> tuple[str, str | None]:
    """Parse compact type notation.

    Returns:
        (type, item_type): e.g. "[option]" -> ("array", "option"), "string" -> ("string", None)
    """
    if type_str.startswith("[") and type_str.endswith("]"):
        return "array", type_str[1:-1]
    return type_str, None


def _build_fields_dict(raw_fields: list[dict]) -> dict:
    """Build consolidated fields dict from Jira API response."""
    result = {}
    for f in raw_fields:
        s = f.get("schema", {})
        entry: dict = {"name": f["name"]}
        type_str = _encode_field_type(s)
        if type_str:
            entry["type"] = type_str
        result[f["id"]] = entry
    return result


def _encode_field_type(jira_schema: dict) -> str:
    """Encode Jira field schema as compact type string.

    e.g. {"type": "array", "items": "option"} -> "[option]"
         {"type": "string"} -> "string"
    """
    t = jira_schema.get("type", "")
    items = jira_schema.get("items")
    if items:
        return f"[{items}]"
    return t


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
    for field_id, field_def in schema["fields"].items():
        if field_def.get("name", "").lower() == name.lower():
            return field_id
    return None


def _fetch_and_cache_fields() -> dict:
    """Fetch fields from Jira API and cache them.

    Returns:
        Fields dict mapping field IDs to metadata.
    """
    jira = get_jira()
    raw_fields = jira.fields()
    fields = _build_fields_dict(raw_fields)
    update_schema("fields", fields)
    return fields


def get_field_name(field_id: str) -> str | None:
    """Look up field name by ID.

    Auto-fetches fields from Jira if not cached.

    Args:
        field_id: Jira field ID (e.g., "customfield_10001")

    Returns:
        Human-readable name (e.g., "Epic Link") or None if not found.
    """
    schema = load_schema()
    if not schema or "fields" not in schema:
        try:
            fields = _fetch_and_cache_fields()
        except Exception:
            return None
        field_def = fields.get(field_id)
        if field_def is None:
            return None
        return field_def.get("name")
    field_def = schema["fields"].get(field_id)
    if field_def is None:
        return None
    return field_def.get("name")


def get_field_map() -> dict[str, str]:
    """Get full field name -> ID mapping.

    Returns:
        Dict mapping field names to IDs.
    """
    schema = load_schema()
    if not schema or "fields" not in schema:
        return {}
    return {field_def.get("name", ""): field_id for field_id, field_def in schema["fields"].items()}


def get_field_type(field_id: str) -> str | None:
    """Get field type by ID.

    Args:
        field_id: Jira field ID (e.g., "customfield_10001")

    Returns:
        Field type (e.g., "option", "array", "string") or None if not found.
    """
    schema = load_schema()
    if not schema or "fields" not in schema:
        return None
    field_def = schema["fields"].get(field_id)
    if field_def is None:
        return None
    type_str = field_def.get("type", "")
    if not type_str:
        return None
    outer, _ = _parse_field_type(type_str)
    return outer


def get_field_item_type(field_id: str) -> str | None:
    """Get array item type by field ID.

    Args:
        field_id: Jira field ID (e.g., "customfield_10734")

    Returns:
        Item type (e.g., "string", "option") or None if not an array field.
    """
    schema = load_schema()
    if not schema or "fields" not in schema:
        return None
    field_def = schema["fields"].get(field_id)
    if field_def is None:
        return None
    type_str = field_def.get("type", "")
    if not type_str:
        return None
    _, item_type = _parse_field_type(type_str)
    return item_type


def load_project_schema(project: str) -> ProjectSchema | None:
    """Load cached project schema from global cache directory.

    Returns:
        Project schema dict if found, None otherwise.
    """
    schema_file = get_project_schema_path(project)
    if not schema_file.exists():
        return None
    return json.load(schema_file.open())


def _fetch_cached_data(
    schema_key: str,
    fetch_fn: Callable[[], T],
    refresh: bool = False,
) -> T:
    """Fetch data from cache or Jira API.

    Args:
        schema_key: Key in the schema cache
        fetch_fn: Function to fetch fresh data from Jira (should also call update_schema)
        refresh: Force refresh from API

    Returns:
        Cached or freshly fetched data
    """
    schema = load_schema()
    if not refresh and schema and schema_key in schema:
        return schema[schema_key]
    return fetch_fn()


def link_types_command(args: argparse.Namespace) -> None:
    """List available link types."""

    def fetch_link_types():
        jira = get_jira()
        types = jira.issue_link_types()
        data = {t.name: {"outward": t.outward, "inward": t.inward} for t in types}
        update_schema("linkTypes", data)
        return data

    try:
        link_types = _fetch_cached_data(
            "linkTypes", fetch_link_types, getattr(args, "refresh", False)
        )
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

    def fetch_statuses():
        jira = get_jira()
        raw = jira.statuses()
        data = {
            s.name: s.statusCategory.name if hasattr(s, "statusCategory") else None
            for s in raw
        }
        update_schema("statuses", data)
        return data

    try:
        statuses = _fetch_cached_data(
            "statuses", fetch_statuses, getattr(args, "refresh", False)
        )
    except Exception as e:
        print(f"Error fetching statuses: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{'Status':<30} {'Category':<20}")
    print("-" * 50)
    for name in sorted(statuses.keys()):
        category = statuses[name] or "-"
        print(f"{name:<30} {category:<20}")


def issue_types_command(args: argparse.Namespace) -> None:
    """List available issue types."""

    def fetch_issue_types():
        jira = get_jira()
        raw = jira.issue_types()
        data = {t.name: {"subtask": t.subtask} for t in raw}
        update_schema("issueTypes", data)
        return data

    try:
        issue_types = _fetch_cached_data(
            "issueTypes", fetch_issue_types, getattr(args, "refresh", False)
        )
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

    # fields_command needs special handling: cache stores {id: {...}} but we need list
    if not refresh and schema and "fields" in schema:
        fields = [{"id": k, "name": v.get("name", "")} for k, v in schema["fields"].items()]
    else:
        try:
            fields_dict = _fetch_and_cache_fields()
            fields = [{"id": k, "name": v.get("name", "")} for k, v in fields_dict.items()]
        except Exception as e:
            print(f"Error fetching fields: {e}", file=sys.stderr)
            sys.exit(1)

    # Filter to custom fields only (unless --all)
    show_all = getattr(args, "all", False)
    filter_text = getattr(args, "filter", None)

    if show_all:
        result = fields
    else:
        result = [
            f for f in fields if f.get("custom") or f["id"].startswith("customfield_")
        ]

    if filter_text:
        filter_lower = filter_text.lower()
        result = [
            f
            for f in result
            if filter_lower in f["name"].lower() or filter_lower in f["id"].lower()
        ]

    result = sorted(result, key=lambda x: x["name"].lower())

    print(f"{'ID':<25} {'Name':<40}")
    print("-" * 65)
    for f in result:
        print(f"{f['id']:<25} {f['name']:<40}")


def get_editmeta_field(
    project: str, issue_type: str, name_or_id: str
) -> tuple[str, dict] | None:
    """Look up field in editmeta by name or ID.

    Fields are keyed by name in the YAML. The Jira field ID is in the 'id' property.

    Args:
        project: Project key (e.g., "SAN")
        issue_type: Issue type name (e.g., "Story")
        name_or_id: Field name (e.g., "S&C Domain") or ID (e.g., "customfield_12345")

    Returns:
        (field_id, field_def) or None if not found.
    """
    editmeta = load_editmeta(project, issue_type)
    if not editmeta or "fields" not in editmeta:
        return None

    fields = editmeta["fields"]

    # Direct name match (exact)
    if name_or_id in fields:
        fdef = fields[name_or_id]
        return fdef["id"], fdef

    # Case-insensitive name match
    name_lower = name_or_id.lower()
    for name, fdef in fields.items():
        if name.lower() == name_lower:
            return fdef["id"], fdef

    # ID match (search the 'id' property)
    for name, fdef in fields.items():
        if fdef.get("id") == name_or_id:
            return name_or_id, fdef

    return None


def load_editmeta(project: str, issue_type: str) -> EditmetaSchema | None:
    """Load cached editmeta for a project + issue type.

    Returns None if missing.
    """
    path = get_editmeta_path(project, issue_type)
    if path.exists():
        return yaml.safe_load(path.read_text())
    return None


def _fetch_and_save_editmeta(key: str, project: str, issue_type: str) -> EditmetaSchema | None:
    """Fetch editmeta from API for a specific issue and save to cache."""
    jira = get_jira()
    server = jira._options["server"]
    try:
        resp = jira._session.get(f"{server}/rest/api/3/issue/{key}/editmeta")
        resp.raise_for_status()
    except Exception:
        return None

    all_fields = _parse_editmeta_response(resp.json())
    editmeta: EditmetaSchema = {
        "project": project,
        "issueType": issue_type,
        "learnedFrom": [key],
        "fields": all_fields,
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = get_editmeta_path(project, issue_type)
    path.write_text(yaml.dump(editmeta, default_flow_style=False, sort_keys=False))
    print(f"Learned {issue_type} editmeta from {key} ({len(all_fields)} fields)", file=sys.stderr)
    return editmeta


def ensure_editmeta(key: str, issue_type: str) -> EditmetaSchema | None:
    """Load editmeta, fetching from API and caching if missing.

    Requires an existing issue key (used by edit/transition).
    """
    project = key.split("-")[0]
    editmeta = load_editmeta(project, issue_type)
    if editmeta:
        return editmeta
    return _fetch_and_save_editmeta(key, project, issue_type)


def ensure_editmeta_for_type(project: str, issue_type: str) -> EditmetaSchema | None:
    """Load editmeta, finding a recent issue to learn from if missing.

    Used by create when no issue key exists yet.
    """
    editmeta = load_editmeta(project, issue_type)
    if editmeta:
        return editmeta

    jira = get_jira()
    issues = jira.search_issues(
        f'project = {project} AND issuetype = "{issue_type}" ORDER BY created DESC',
        maxResults=1,
    )
    if not issues:
        return None
    return _fetch_and_save_editmeta(issues[0].key, project, issue_type)


def _extract_allowed_values(field_meta: dict) -> list[str]:
    """Extract allowed value strings from editmeta field."""
    allowed = field_meta.get("allowedValues", [])
    values = []
    for av in allowed:
        if isinstance(av, dict):
            # Prefer "value" (custom fields), then "name" (system fields)
            v = av.get("value") or av.get("name")
            if v:
                values.append(v)
        elif isinstance(av, str):
            values.append(av)
    return values


def _parse_editmeta_response(raw: dict) -> dict:
    """Parse editmeta API response into our compact format.

    Returns dict keyed by field name, with field ID stored as 'id'.
    """
    fields = {}
    for field_id, meta in raw.get("fields", {}).items():
        schema = meta.get("schema", {})
        name = meta.get("name", field_id)
        entry: dict = {
            "id": field_id,
            "type": _encode_field_type(schema),
            "operations": meta.get("operations", []),
            "required": meta.get("required", False),
        }
        allowed = _extract_allowed_values(meta)
        if allowed:
            entry["allowedValues"] = allowed
        fields[name] = entry
    return fields


def _learn_from_file(filepath: str) -> None:
    """Import from a YAML file.

    If the file has project/issueType keys, treat as editmeta.
    Otherwise treat as field descriptions (field name -> description string).
    """
    from pathlib import Path

    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}", file=sys.stderr)
        return

    data = yaml.safe_load(path.read_text())
    if not data or not isinstance(data, dict):
        print(f"Invalid YAML: {filepath}", file=sys.stderr)
        return

    # If it has project + issueType, it's an editmeta file
    if data.get("project") and data.get("issueType"):
        _learn_editmeta_from_file(filepath, data)
        return

    # Otherwise treat as field descriptions: {name: description, ...}
    descriptions = load_field_descriptions()
    count = 0
    for name, value in data.items():
        if isinstance(value, str):
            descriptions[name] = value
            count += 1
    save_field_descriptions(descriptions)
    print(f"  {filepath} -> field_descriptions.yaml  ({count} descriptions)")


def _learn_editmeta_from_file(filepath: str, data: dict) -> None:
    """Import editmeta from a YAML file, merging into existing cache."""
    project = data["project"]
    issue_type = data["issueType"]

    incoming_fields = data.get("fields", {})
    if not incoming_fields:
        print(f"No fields in {filepath}", file=sys.stderr)
        return

    # Merge into existing editmeta (if any)
    existing = load_editmeta(project, issue_type)
    if existing and "fields" in existing:
        for name, fdef in incoming_fields.items():
            if name in existing["fields"]:
                existing["fields"][name].update(fdef)
            else:
                existing["fields"][name] = fdef
        merged = existing
    else:
        merged = data

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = get_editmeta_path(project, issue_type)
    dest.write_text(yaml.dump(merged, default_flow_style=False, sort_keys=False))

    n_fields = len(incoming_fields)
    print(f"  {filepath} -> {dest.name}  ({n_fields} fields, {project}/{issue_type})")


def learn_command(args: argparse.Namespace) -> None:
    """Learn editable fields from issue editmeta or YAML files."""
    raw_args = args.keys

    # Split into files and issue keys
    files = [a for a in raw_args if a.endswith((".yaml", ".yml"))]
    raw_keys = [k.upper() for k in raw_args if not k.endswith((".yaml", ".yml"))]

    # Import YAML files first
    for f in files:
        _learn_from_file(f)

    if not raw_keys:
        if not files:
            print("No issue keys or files provided.", file=sys.stderr)
            sys.exit(1)
        return

    jira = get_jira()
    server = jira._options["server"]

    # Resolve bare project keys (e.g. "AC") to one issue per issue type
    keys: list[str] = []
    for k in raw_keys:
        if "-" in k:
            keys.append(k)
        else:
            # Find one issue per issue type in the project
            issues = jira.search_issues(
                f"project = {k} ORDER BY created DESC", maxResults=100
            )
            if not issues:
                print(f"No issues found in project {k}", file=sys.stderr)
                continue
            seen_types: set[str] = set()
            for issue in issues:
                itype = issue.fields.issuetype.name
                if itype not in seen_types:
                    seen_types.add(itype)
                    print(f"Resolved {k}/{itype} -> {issue.key}")
                    keys.append(issue.key)

    if not keys:
        return

    # Group by (project, issue_type) and learn each
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for key in keys:
        project = key.split("-")[0]
        print(f"\nLearning from {key}...")

        # Get issue type
        try:
            issue = jira.issue(key, fields="issuetype")
            issue_type = issue.fields.issuetype.name
        except Exception as e:
            print(f"Error fetching issue {key}: {e}", file=sys.stderr)
            continue

        try:
            resp = jira._session.get(f"{server}/rest/api/3/issue/{key}/editmeta")
            resp.raise_for_status()
        except Exception as e:
            print(f"Error fetching editmeta for {key}: {e}", file=sys.stderr)
            continue

        all_fields = _parse_editmeta_response(resp.json())

        editmeta: EditmetaSchema = {
            "project": project,
            "issueType": issue_type,
            "learnedFrom": [key],
            "fields": all_fields,
        }

        path = get_editmeta_path(project, issue_type)
        path.write_text(yaml.dump(editmeta, default_flow_style=False, sort_keys=False))

        print(f"  {issue_type}: {len(all_fields)} fields -> {path.name}")

        # Print summary table
        print(f"  {'Field':<40} {'Type':<12} {'Info':<20}")
        print(f"  {'-' * 72}")
        for name in sorted(all_fields, key=str.lower):
            f = all_fields[name]
            ftype = f.get("type", "")
            if f.get("required"):
                info = "required"
            elif f.get("allowedValues"):
                info = f"{len(f['allowedValues'])} values"
            else:
                info = ""
            print(f"    {name:<38} {ftype:<12} {info:<20}")


def _iter_editmeta() -> list[tuple[str, str, EditmetaSchema]]:
    """Load all cached editmeta files.

    Returns list of (project, issue_type, editmeta) tuples.
    """
    results = []
    for path in sorted(CACHE_DIR.glob("editmeta_*.yaml")):
        data = yaml.safe_load(path.read_text())
        if data and "fields" in data:
            results.append((data.get("project", ""), data.get("issueType", ""), data))
    return results


def field_command(args: argparse.Namespace) -> None:
    """Look up editmeta for named fields across all cached issue types."""
    names = args.names
    all_editmeta = _iter_editmeta()
    if not all_editmeta:
        print("No editmeta cached. Run 'zaira learn <KEY>' first.", file=sys.stderr)
        sys.exit(1)

    descriptions = load_field_descriptions()

    for name in names:
        name_lower = name.lower()
        # Collect matches: group by field ID, merge allowed values and locations
        matches: dict[str, dict] = {}  # field_id -> merged info
        for project, issue_type, editmeta in all_editmeta:
            fields = editmeta["fields"]
            hit = None
            for fname, fdef in fields.items():
                if fname.lower() == name_lower or fdef.get("id", "").lower() == name_lower:
                    hit = (fname, fdef)
                    break
            if not hit:
                continue
            fname, fdef = hit
            fid = fdef.get("id", "")
            if fid not in matches:
                matches[fid] = {
                    "name": fname,
                    "fdef": dict(fdef),
                    "locations": [],
                }
            merged_fdef = matches[fid]["fdef"]
            matches[fid]["locations"].append(f"{project}/{issue_type}")
            # Merge allowed values (union, preserving order)
            new_vals = fdef.get("allowedValues", [])
            existing = merged_fdef.get("allowedValues", [])
            if new_vals:
                seen = set(existing)
                for v in new_vals:
                    if v not in seen:
                        existing.append(v)
                        seen.add(v)
                merged_fdef["allowedValues"] = existing

        if not matches:
            print(f"{name}: not found in any editmeta cache\n")
            continue

        for fid, info in matches.items():
            fdef = info["fdef"]
            fname = info["name"]
            locs = ", ".join(info["locations"])
            print(f"{fname}  ({locs})")
            print(f"  id:         {fid}")
            print(f"  type:       {fdef.get('type', '')}")
            print(f"  required:   {fdef.get('required', False)}")
            allowed = fdef.get("allowedValues", [])
            if allowed:
                print(f"  values:     {', '.join(str(v) for v in allowed)}")
            desc = descriptions.get(fname)
            if desc:
                print(f"  description: {desc}")
            print()


def info_command(args: argparse.Namespace) -> None:
    """Handle info subcommand."""
    if hasattr(args, "info_func"):
        args.info_func(args)
    else:
        print("Usage: zaira info <subcommand>")
        print("Subcommands: link-types, statuses, issue-types, fields, field")
        sys.exit(1)
