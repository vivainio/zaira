"""Fetch and display Jira issue changelog with optional diffs."""

import argparse
import difflib
import sys
from datetime import datetime
from typing import Any

from zaira.export import _format_timestamp
from zaira.info import get_field_name
from zaira.jira_client import format_jira_error, get_jira
from zaira.types import get_user_identifier


def _extract_value(raw: Any) -> str:
    """Extract a display string from a changelog value."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for attr in ("name", "displayName", "value", "key"):
            if attr in raw:
                return str(raw[attr])
    return str(raw)


def _is_long_text(value: str) -> bool:
    """Check if a value is long enough to warrant a diff view."""
    return "\n" in value or len(value) > 120


def _format_diff(old: str, new: str) -> str:
    """Format a unified diff between two text values."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, lineterm="")
    result = []
    for line in diff:
        # Skip the --- / +++ header lines
        if line.startswith("---") or line.startswith("+++"):
            continue
        result.append(line.rstrip("\n"))
    return "\n".join(result) if result else "(no visible changes)"


def fetch_changelog(key: str) -> list[dict]:
    """Fetch the changelog for a Jira issue.

    Returns a list of history entries sorted oldest-first, each with:
        author, created, items: [{field, from, to}]
    """
    jira = get_jira()
    try:
        issue = jira.issue(key, expand="changelog")
    except Exception as e:
        print(f"Error fetching {key}: {format_jira_error(e)}", file=sys.stderr)
        sys.exit(1)

    entries: list[dict] = []
    changelog = issue.changelog
    for history in changelog.histories:
        author = get_user_identifier(history.author) or "Unknown"
        created = getattr(history, "created", "")
        items = []
        for item in history.items:
            field_id = getattr(item, "fieldId", None)
            field_name = getattr(item, "field", field_id or "?")
            # Try to resolve custom field IDs to human names
            if field_id and field_id.startswith("customfield_"):
                resolved = get_field_name(field_id)
                if resolved:
                    field_name = resolved
            items.append(
                {
                    "field": field_name,
                    "from": _extract_value(getattr(item, "fromString", None)),
                    "to": _extract_value(getattr(item, "toString", None)),
                }
            )
        entries.append(
            {
                "author": author,
                "created": created,
                "items": items,
            }
        )
    return entries


def extract_field_revisions(
    entries: list[dict],
    field: str,
) -> list[dict]:
    """Build a list of revisions for a specific field from changelog entries.

    Returns revisions oldest-first, each with:
        rev (1-based), author, created, value
    The first revision is the oldest "from" value, subsequent revisions
    are the "to" values of each change.
    """
    changes = []
    for entry in entries:
        for item in entry["items"]:
            if item["field"].lower() == field.lower():
                changes.append(
                    {
                        "author": entry["author"],
                        "created": entry["created"],
                        "from": item["from"],
                        "to": item["to"],
                    }
                )
    if not changes:
        return []

    revisions: list[dict] = []
    # Rev 1 = the "from" value of the earliest change (state before any change)
    revisions.append(
        {
            "rev": 1,
            "author": "(before first edit)",
            "created": changes[0]["created"],
            "value": changes[0]["from"],
        }
    )
    for i, ch in enumerate(changes):
        revisions.append(
            {
                "rev": i + 2,
                "author": ch["author"],
                "created": ch["created"],
                "value": ch["to"],
            }
        )
    return revisions


def format_revisions(revisions: list[dict]) -> str:
    """Format revision list for display."""
    if not revisions:
        return "(no revisions found)"
    lines = []
    for r in revisions:
        ts = _format_timestamp(r["created"])
        preview = r["value"][:80].replace("\n", " ")
        if len(r["value"]) > 80:
            preview += "..."
        lines.append(f"  {r['rev']:>3}  {ts}  {r['author']}")
        lines.append(f"       {preview}")
    return "\n".join(lines)


def format_changelog(
    entries: list[dict],
    *,
    full: bool = False,
    field_filter: str | None = None,
) -> str:
    """Format changelog entries as readable text.

    Long text fields show diffs by default. Use full=True to show complete
    old → new values instead.

    Args:
        entries: Changelog entries from fetch_changelog()
        full: Show full old/new values instead of diffs for long text
        field_filter: Only show changes to this field (case-insensitive)
    """
    if not entries:
        return "(no changelog entries)"

    lines: list[str] = []
    for entry in entries:
        items = entry["items"]
        if field_filter:
            ff = field_filter.lower()
            items = [i for i in items if i["field"].lower() == ff]
        if not items:
            continue

        ts = _format_timestamp(entry["created"])
        author = entry["author"]
        lines.append(f"## {ts}  {author}")
        lines.append("")

        for item in items:
            field = item["field"]
            old = item["from"]
            new = item["to"]

            if not full and (_is_long_text(old) or _is_long_text(new)):
                lines.append(f"**{field}**:")
                lines.append("```diff")
                lines.append(_format_diff(old, new))
                lines.append("```")
            else:
                if not old:
                    lines.append(f"- **{field}**: → {new}")
                elif not new:
                    lines.append(f"- **{field}**: {old} → *(cleared)*")
                else:
                    lines.append(f"- **{field}**: {old} → {new}")
        lines.append("")

    return "\n".join(lines).rstrip() if lines else "(no matching changes)"


def changelog_command(args: argparse.Namespace) -> None:
    """Handle changelog subcommand."""
    key = args.key.upper()
    rev = getattr(args, "rev", None)
    revisions_mode = getattr(args, "revisions", False)

    # --revisions and --rev require --field
    if (rev is not None or revisions_mode) and not getattr(args, "field", None):
        print("Error: --revisions and --rev require --field", file=sys.stderr)
        sys.exit(1)

    entries = fetch_changelog(key)

    if revisions_mode:
        revisions = extract_field_revisions(entries, args.field)
        print(format_revisions(revisions))
        return

    if rev is not None:
        revisions = extract_field_revisions(entries, args.field)
        match = [r for r in revisions if r["rev"] == rev]
        if not match:
            total = len(revisions)
            print(
                f"Error: revision {rev} not found (have {total} revisions)",
                file=sys.stderr,
            )
            sys.exit(1)
        print(match[0]["value"])
        return

    tail = getattr(args, "tail", None)
    if tail:
        entries = entries[-tail:]

    output = format_changelog(
        entries,
        full=getattr(args, "full", False),
        field_filter=getattr(args, "field", None),
    )
    print(output)
