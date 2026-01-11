"""Sync reports by re-running their generation command."""

import argparse
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from zaira.config import REPORTS_DIR, TICKETS_DIR


def parse_front_matter(content: str) -> dict:
    """Parse YAML front matter from markdown content."""
    if not content.startswith("---"):
        return {}

    # Find closing ---
    end = content.find("---", 3)
    if end == -1:
        return {}

    yaml_content = content[3:end].strip()
    result = {}

    for line in yaml_content.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            value = value.strip()
            # Only strip quotes if value is fully wrapped in them
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            result[key.strip()] = value

    return result


def extract_ticket_keys(report_content: str) -> list[str]:
    """Extract ticket keys from report markdown."""
    # Match ticket links like [AC-1234](https://...)
    pattern = r"\[([A-Z]+-\d+)\]\(https://"
    return list(set(re.findall(pattern, report_content)))


def find_ticket_file(key: str) -> Path | None:
    """Find existing ticket file by key."""
    if not TICKETS_DIR.exists():
        return None
    for f in TICKETS_DIR.glob(f"{key}-*.md"):
        return f
    return None


def get_local_synced_time(ticket_file: Path) -> datetime | None:
    """Get the synced timestamp from a local ticket file."""
    content = ticket_file.read_text()
    meta = parse_front_matter(content)
    synced_str = meta.get("synced", "")

    if not synced_str:
        return None

    try:
        return datetime.fromisoformat(synced_str)
    except ValueError:
        return None


def ticket_needs_export(ticket_file: Path, jira_updated: str) -> bool:
    """Check if ticket needs export by comparing Jira updated vs local synced."""
    local_synced = get_local_synced_time(ticket_file)
    if not local_synced:
        return True  # No synced timestamp, needs export

    try:
        # Parse Jira timestamp (format: 2026-01-11T14:30:00.000+0000)
        updated_str = jira_updated.replace("+0000", "+00:00")
        jira_time = datetime.fromisoformat(updated_str)
        # Make local_synced offset-aware if jira_time is
        if jira_time.tzinfo and not local_synced.tzinfo:
            local_synced = local_synced.replace(tzinfo=jira_time.tzinfo)
        return jira_time > local_synced
    except ValueError:
        return True  # Can't parse, assume needs export


def sync_command(args: argparse.Namespace) -> None:
    """Handle sync subcommand."""
    from zaira.export import export_ticket

    # Find report file
    report_path = Path(args.report)
    if not report_path.exists():
        # Try in reports directory
        report_path = REPORTS_DIR / args.report
        if not report_path.exists():
            # Try with .md extension
            report_path = REPORTS_DIR / f"{args.report}.md"

    if not report_path.exists():
        print(f"Error: Report not found: {args.report}")
        sys.exit(1)

    # Parse front matter
    content = report_path.read_text()
    front_matter = parse_front_matter(content)

    if not front_matter:
        print(f"Error: No front matter found in {report_path}")
        sys.exit(1)

    sync_cmd = front_matter.get("sync")
    if not sync_cmd:
        print("Error: No sync command in front matter")
        sys.exit(1)

    print(f"Syncing: {report_path.name}")

    try:
        cmd_parts = shlex.split(sync_cmd)
    except ValueError:
        print("Error: Could not parse sync command")
        sys.exit(1)

    # Add output path
    cmd_parts.extend(["-o", str(report_path)])

    print(f"Running: {' '.join(cmd_parts)}")
    result = subprocess.run(cmd_parts)

    if result.returncode != 0:
        sys.exit(result.returncode)

    # Full sync: also export tickets
    if getattr(args, "full", False):
        from zaira.report import search_tickets
        from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
        from zaira.project import get_query, get_board

        # Re-read front matter after sync
        front_matter = parse_front_matter(report_path.read_text())

        # Build JQL from front matter
        jql = front_matter.get("jql")
        if front_matter.get("query"):
            jql = get_query(front_matter["query"])
        elif front_matter.get("board"):
            board_id = front_matter["board"]
            try:
                board_id = int(board_id)
            except ValueError:
                board_id = get_board(board_id)
            if board_id:
                jql = get_board_issues_jql(board_id)
        elif front_matter.get("sprint"):
            jql = get_sprint_issues_jql(int(front_matter["sprint"]))

        if not jql:
            print("Warning: Could not determine JQL for ticket export")
        else:
            # Add label filter if present
            if front_matter.get("label"):
                jql = f'{jql} AND labels = "{front_matter["label"]}"'

            print("\nExporting tickets...")
            tickets = search_tickets(jql)
            print(f"Found {len(tickets)} tickets")

            exported = 0
            skipped = 0
            force = getattr(args, "force", False)

            for t in sorted(tickets, key=lambda x: x["key"]):
                key = t["key"]
                updated = t.get("updated", "")
                ticket_file = find_ticket_file(key)

                if ticket_file:
                    if force:
                        print(f"  {key}: forcing refresh...")
                        if export_ticket(key, TICKETS_DIR):
                            exported += 1
                    elif ticket_needs_export(ticket_file, updated):
                        print(f"  {key}: changed, refreshing...")
                        if export_ticket(key, TICKETS_DIR):
                            exported += 1
                    else:
                        print(f"  {key}: unchanged, skipping")
                        skipped += 1
                else:
                    print(f"  {key}: new, exporting...")
                    if export_ticket(key, TICKETS_DIR):
                        exported += 1

            print(f"\nExported {exported} tickets, {skipped} unchanged")
