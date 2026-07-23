"""Push summary + description from markdown back to Jira."""

import argparse
import re
import sys
from pathlib import Path

from zaira.create import detect_markdown, parse_content
from zaira.edit import edit_ticket
from zaira.info import get_field_id
from zaira.jira_client import format_jira_error, get_jira, get_jira_site


def parse_description(body: str) -> str | None:
    """Extract description text from between ## Description and ## Links.

    Returns None if no ## Description section found.
    """
    match = re.search(
        r"^## Description\s*\n(.*?)(?=^## Links\s*$|\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(1).strip()


def put_command(args: argparse.Namespace) -> None:
    """Handle put subcommand."""
    # Read input
    if args.file == "-":
        content = sys.stdin.read()
    else:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        content = path.read_text()

    # Parse front matter + body
    try:
        front_matter, body = parse_content(content)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract key (required)
    key = front_matter.get("key")
    if not key:
        print("Error: 'key' field is required in front matter", file=sys.stderr)
        sys.exit(1)
    key = key.upper()

    # Extract summary and description
    new_summary = front_matter.get("summary")
    new_description = parse_description(body)

    # Minimal format: front matter has only 'key' (or 'key'+'summary'), body is the description
    ignored_keys = {"key", "summary", "field"}
    minimal = set(front_matter.keys()) <= ignored_keys
    if minimal and new_description is None and body:
        new_description = body

    # Determine target field: --field flag > front matter field: > description
    target_field_name = getattr(args, "field", None) or front_matter.get("field")

    # Convert markdown to Jira wiki if needed (skip with --raw)
    raw = getattr(args, "raw", False)
    if not raw and new_description and detect_markdown(new_description):
        from zaira.mdconv import markdown_to_jira_wiki

        new_description = markdown_to_jira_wiki(new_description)

    # Resolve target field to Jira field ID
    target_field_id = None
    if target_field_name:
        target_field_id = get_field_id(target_field_name)
        if not target_field_id:
            print(
                f"Error: Could not resolve field '{target_field_name}' to a Jira field ID",
                file=sys.stderr,
            )
            sys.exit(1)

    # Fetch live ticket to compare
    dry_run = getattr(args, "dry_run", False)
    jira = get_jira()
    fetch_fields = "summary,description"
    if target_field_id:
        fetch_fields += f",{target_field_id}"
    try:
        issue = jira.issue(key, fields=fetch_fields)
    except Exception as e:
        print(f"Error: Could not fetch {key}: {format_jira_error(e)}", file=sys.stderr)
        sys.exit(1)

    live_summary = issue.fields.summary or ""

    # Compare and build update fields
    fields: dict = {}
    changes: list[str] = []

    if new_summary and new_summary != live_summary:
        fields["summary"] = new_summary
        changes.append("summary")

    if new_description is not None:
        if target_field_id:
            assert target_field_name is not None
            # Write body to the named custom field
            live_value = getattr(issue.fields, target_field_id, None) or ""
            if new_description != live_value:
                fields[target_field_id] = new_description
                changes.append(target_field_name)
        else:
            # Default: write body to description
            live_description = issue.fields.description or ""
            if new_description != live_description:
                fields["description"] = new_description
                changes.append("description")

    force = getattr(args, "force", False)
    if not fields and not force:
        print(f"No changes for {key}")
        return
    if not fields and force:
        # Force: push all available fields even if unchanged
        if new_summary:
            fields["summary"] = new_summary
            changes.append("summary")
        if new_description is not None:
            if target_field_id:
                assert target_field_name is not None
                fields[target_field_id] = new_description
                changes.append(target_field_name)
            else:
                fields["description"] = new_description
                changes.append("description")

    # Dry run
    if dry_run:
        print(f"Dry run — would update {key}:")
        if "summary" in fields:
            print(f"  summary: {live_summary!r} → {fields['summary']!r}")
        # Show body field change
        body_key = target_field_id or "description"
        if body_key in fields:
            label = target_field_name or "description"
            live_len = len(
                getattr(issue.fields, body_key, None) or issue.fields.description or ""
            )
            print(f"  {label}: ({live_len} chars → {len(fields[body_key])} chars)")
        return

    # Push update
    if edit_ticket(key, fields):
        jira_site = get_jira_site()
        print(f"Updated {key}: {', '.join(changes)}")
        print(f"View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record

        record("put", key, ", ".join(changes))
    else:
        sys.exit(1)
