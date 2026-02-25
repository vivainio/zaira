"""Push summary + description from markdown back to Jira."""

import argparse
import re
import sys
from pathlib import Path

from zaira.create import detect_markdown, parse_content
from zaira.edit import edit_ticket
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
    minimal = set(front_matter.keys()) <= {"key", "summary"}
    if minimal and new_description is None and body:
        new_description = body

    # Convert markdown to Jira wiki if needed
    if new_description and detect_markdown(new_description):
        from zaira.mdconv import markdown_to_jira_wiki

        new_description = markdown_to_jira_wiki(new_description)

    # Fetch live ticket to compare
    dry_run = getattr(args, "dry_run", False)
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="summary,description")
    except Exception as e:
        print(f"Error: Could not fetch {key}: {format_jira_error(e)}", file=sys.stderr)
        sys.exit(1)

    live_summary = issue.fields.summary or ""
    live_description = issue.fields.description or ""

    # Compare and build update fields
    fields: dict = {}
    changes: list[str] = []

    if new_summary and new_summary != live_summary:
        fields["summary"] = new_summary
        changes.append("summary")

    if new_description is not None and new_description != live_description:
        fields["description"] = new_description
        changes.append("description")

    if not fields:
        print(f"No changes for {key}")
        return

    # Dry run
    if dry_run:
        print(f"Dry run — would update {key}:")
        if "summary" in fields:
            print(f"  summary: {live_summary!r} → {fields['summary']!r}")
        if "description" in fields:
            print(f"  description: ({len(live_description)} chars → {len(fields['description'])} chars)")
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
