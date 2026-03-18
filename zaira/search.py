"""Search Jira tickets."""

import argparse
import sys

from zaira.export import extract_custom_field_value
from zaira.info import get_field_id
from zaira.jira_client import get_jira
from zaira.report import humanize_age


PAGE_SIZE = 50

# Standard fields accessible as attributes on issue.fields
STANDARD_FIELD_ATTRS = {
    "assignee": lambda f: _user_display(f.assignee),
    "reporter": lambda f: _user_display(f.reporter),
    "priority": lambda f: f.priority.name if f.priority else "",
    "issuetype": lambda f: f.issuetype.name if f.issuetype else "",
    "components": lambda f: ", ".join(c.name for c in (f.components or [])),
    "labels": lambda f: ", ".join(f.labels or []),
    "fixversions": lambda f: ", ".join(v.name for v in (f.fixVersions or [])),
    "duedate": lambda f: f.duedate or "",
    "created": lambda f: (f.created or "")[:10],
    "updated": lambda f: (f.updated or "")[:10],
    "resolution": lambda f: f.resolution.name if f.resolution else "",
    "status": lambda f: f.status.name if f.status else "",
}

# Aliases for user convenience
FIELD_ALIASES = {
    "fix versions": "fixversions",
    "fix version": "fixversions",
    "fixversion": "fixversions",
    "issue type": "issuetype",
    "type": "issuetype",
    "due date": "duedate",
    "due": "duedate",
}


def _user_display(user) -> str:
    if not user:
        return ""
    if hasattr(user, "displayName"):
        return user.displayName
    if hasattr(user, "name"):
        return user.name
    return str(user)


def _resolve_extra_field(name: str) -> tuple[str, str | None]:
    """Resolve a field name to (display_name, field_id_or_attr).

    Returns (display_name, key) where key is either a STANDARD_FIELD_ATTRS key
    or a Jira field ID (customfield_*), or None if not found.
    """
    lower = name.lower().strip()

    # Check aliases first
    if lower in FIELD_ALIASES:
        lower = FIELD_ALIASES[lower]

    # Check standard fields
    if lower in STANDARD_FIELD_ATTRS:
        return name, lower

    # Try schema lookup by human name
    field_id = get_field_id(name)
    if field_id:
        return name, field_id

    return name, None


def _extract_field_value(issue, key: str) -> str:
    """Extract a display value for a field from an issue."""
    lower = key.lower()

    # Standard field via lambda
    if lower in STANDARD_FIELD_ATTRS:
        try:
            return str(STANDARD_FIELD_ATTRS[lower](issue.fields))
        except Exception:
            return ""

    # Custom field by ID
    raw = issue.raw.get("fields", {}).get(key)
    if raw is None:
        return ""
    extracted = extract_custom_field_value(raw)
    if isinstance(extracted, list):
        return ", ".join(str(v) for v in extracted)
    return str(extracted) if extracted is not None else ""


def print_row(
    key: str, status: str, created: str, summary: str, key_width: int
) -> None:
    """Print a single search result row."""
    age = humanize_age(created)
    if len(summary) > 90:
        summary = summary[:87] + "..."
    status_short = status[:15]
    print(f"{key:<{key_width}}  {status_short:<15}  {age:>5}  {summary}")


def print_row_with_fields(
    key: str,
    status: str,
    created: str,
    summary: str,
    key_width: int,
    extra_values: list[str],
    col_widths: list[int],
) -> None:
    """Print a search result row with extra field columns."""
    age = humanize_age(created)
    status_short = status[:15]
    parts = [f"{key:<{key_width}}", f"{status_short:<15}", f"{age:>5}"]
    for val, width in zip(extra_values, col_widths):
        if len(val) > width:
            val = val[: width - 3] + "..."
        parts.append(f"{val:<{width}}")
    # Summary last, no truncation needed since it's the final column
    if len(summary) > 80:
        summary = summary[:77] + "..."
    parts.append(summary)
    print("  ".join(parts))


def search_command(args: argparse.Namespace) -> None:
    """Handle search subcommand."""
    jql = build_jql(args)
    limit = args.limit
    jira = get_jira()

    output_format = getattr(args, "format", "default")

    if output_format in ("json", "toon"):
        # Resolve extra fields for structured output
        extra_field_specs = []
        field_args = getattr(args, "fields", None)
        if field_args:
            for name in field_args.split(","):
                name = name.strip()
                if not name:
                    continue
                display, key = _resolve_extra_field(name)
                if key is None:
                    print(f"Warning: unknown field '{name}', skipping", file=sys.stderr)
                    continue
                extra_field_specs.append((display, key))

        max_results = limit if limit else False
        issues = jira.search_issues(jql, startAt=0, maxResults=max_results)
        data = []
        for issue in issues:
            f = issue.fields
            item = {
                "key": issue.key,
                "summary": f.summary or "",
                "status": f.status.name if f.status else "?",
                "type": f.issuetype.name if f.issuetype else "",
                "priority": f.priority.name if f.priority else "",
                "assignee": str(f.assignee) if f.assignee else "",
                "created": f.created or "",
            }
            for display, fkey in extra_field_specs:
                item[display] = _extract_field_value(issue, fkey)
            data.append(item)
            if limit and len(data) >= limit:
                break
        if output_format == "json":
            import json

            print(json.dumps(data, indent=2, default=str))
        else:
            try:
                import toon_format
            except ImportError:
                print(
                    "Error: toon-format package not installed. Run: pip install toon-format",
                    file=sys.stderr,
                )
                import sys

                sys.exit(1)
            print(toon_format.encode(data))
        return

    # Resolve extra fields
    extra_fields = []  # list of (display_name, field_key)
    field_args = getattr(args, "fields", None)
    if field_args:
        for name in field_args.split(","):
            name = name.strip()
            if not name:
                continue
            display, key = _resolve_extra_field(name)
            if key is None:
                print(f"Warning: unknown field '{name}', skipping", file=sys.stderr)
                continue
            extra_fields.append((display, key))

    total_printed = 0
    key_width = 10  # reasonable default, adjusts if needed

    # For extra fields, collect all rows first to calculate column widths
    if extra_fields:
        all_rows = []

    # Let the library handle pagination (uses token-based pagination on Cloud)
    max_results = limit if limit else False
    issues = jira.search_issues(jql, startAt=0, maxResults=max_results)

    for issue in issues:
        fields = issue.fields
        key = issue.key
        if len(key) > key_width:
            key_width = len(key)

        if extra_fields:
            extra_values = [
                _extract_field_value(issue, fkey) for _, fkey in extra_fields
            ]
            all_rows.append(
                (
                    key,
                    fields.status.name if fields.status else "?",
                    fields.created or "",
                    fields.summary or "",
                    extra_values,
                )
            )
        else:
            print_row(
                key,
                fields.status.name if fields.status else "?",
                fields.created or "",
                fields.summary or "",
                key_width,
            )
        total_printed += 1
        if limit and total_printed >= limit:
            break

    # Print rows with extra fields (need all rows to calculate column widths)
    if extra_fields and all_rows:
        col_widths = []
        for i, (display, _) in enumerate(extra_fields):
            max_val = max(len(row[4][i]) for row in all_rows)
            col_widths.append(max(len(display), min(max_val, 30)))

        # Print header
        header_parts = [f"{'KEY':<{key_width}}", f"{'STATUS':<15}", f"{'AGE':>5}"]
        for (display, _), width in zip(extra_fields, col_widths):
            header_parts.append(f"{display.upper():<{width}}")
        header_parts.append("SUMMARY")
        print("  ".join(header_parts))

        for key, status, created, summary, extra_values in all_rows:
            print_row_with_fields(
                key, status, created, summary, key_width, extra_values, col_widths
            )

    if total_printed == 0:
        print("No tickets found.")


def _looks_like_jql(text: str) -> bool:
    """Detect if text looks like JQL (heuristic check)."""
    if not text:
        return False
    text_upper = text.upper()
    # Check for JQL keywords and operators
    jql_indicators = [
        "=",
        " AND ",
        " OR ",
        " NOT ",
        "ORDER BY",
        "PROJECT",
        "TYPE",
        "STATUS",
        "ASSIGNEE",
        "PRIORITY",
        "LABEL",
        "COMPONENT",
    ]
    return any(indicator in text_upper for indicator in jql_indicators)


def build_jql(args: argparse.Namespace) -> str:
    """Build JQL from search arguments."""
    if args.jql:
        return args.jql

    # Auto-detect if text argument looks like JQL
    if args.text and _looks_like_jql(args.text):
        return args.text

    clauses = []
    if args.text:
        clauses.append(f'text ~ "{args.text}"')
    if args.project:
        clauses.append(f"project = {args.project}")
    if args.status:
        clauses.append(f'status = "{args.status}"')
    if args.assignee:
        clauses.append(f'assignee = "{args.assignee}"')

    if not clauses:
        print("Provide search text, --jql, or filters (-p, -s, -a).")
        sys.exit(1)

    return " AND ".join(clauses) + " ORDER BY updated DESC"
