"""Refresh reports by re-running their generation command."""

import argparse
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from zaira.config import REPORTS_DIR, TICKETS_DIR
from zaira.types import FrontMatter


def parse_front_matter(content: str) -> FrontMatter:
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
    # Match ticket links like [PROJ-123](https://...)
    pattern = r"\[([A-Z]+-\d+)\]\(https://"
    return list(set(re.findall(pattern, report_content)))


def find_ticket_file(key: str, search_dir: Path | None = None) -> Path | None:
    """Find existing ticket file by key."""
    d = search_dir or TICKETS_DIR
    if not d.exists():
        return None
    for f in d.glob(f"{key}-*.md"):
        return f
    return None


def get_local_synced_time(ticket_file: Path) -> datetime | None:
    """Get the synced timestamp from a local ticket file."""
    content = ticket_file.read_text(encoding="utf-8")
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


def _build_command(front_matter: FrontMatter) -> list[str] | None:
    """Build refresh command from structured front matter fields.

    Reconstructs the command from jql/query/board/sprint fields rather than
    parsing the refresh string, which can break with nested quotes in JQL.
    """
    # If generated from a named report, use that directly
    if front_matter.get("report"):
        return ["zaira", "report", front_matter["report"]]

    cmd = ["zaira", "report"]
    has_source = False

    if front_matter.get("query"):
        cmd.extend(["--query", front_matter["query"]])
        has_source = True
    elif front_matter.get("jql"):
        cmd.extend(["--jql", front_matter["jql"]])
        has_source = True
    if front_matter.get("board"):
        cmd.extend(["--board", front_matter["board"]])
        has_source = True
    if front_matter.get("sprint"):
        cmd.extend(["--sprint", front_matter["sprint"]])
        has_source = True
    if front_matter.get("label"):
        cmd.extend(["--label", front_matter["label"]])
    if front_matter.get("group_by"):
        cmd.extend(["--group-by", front_matter["group_by"]])
    if front_matter.get("title"):
        cmd.extend(["--title", front_matter["title"]])
    if not has_source and not front_matter.get("refresh"):
        return None

    # Fall back to parsing refresh string if no structured fields found
    if not has_source:
        try:
            return shlex.split(front_matter["refresh"])
        except ValueError:
            return None

    return cmd


def refresh_command(args: argparse.Namespace) -> None:
    """Handle refresh subcommand."""
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
    content = report_path.read_text(encoding="utf-8")
    front_matter = parse_front_matter(content)

    if not front_matter:
        print(f"Error: No front matter found in {report_path}")
        sys.exit(1)

    # Rebuild command from structured front matter fields (more reliable
    # than parsing the refresh string which can have nested-quote issues)
    cmd_parts = _build_command(front_matter)
    if not cmd_parts:
        print("Error: No refresh command or query/board/jql in front matter")
        sys.exit(1)

    print(f"Refreshing: {report_path.name}")

    # Add output path
    cmd_parts.extend(["-o", str(report_path)])

    print(f"Running: {' '.join(cmd_parts)}")
    result = subprocess.run(cmd_parts)

    if result.returncode != 0:
        sys.exit(result.returncode)

    # Full refresh: also export tickets
    if getattr(args, "full", False):
        from zaira.report import search_tickets
        from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
        from zaira.project import get_query, get_board, get_report

        # Re-read front matter after refresh
        front_matter = parse_front_matter(report_path.read_text(encoding="utf-8"))

        # Resolve report definition if named report
        fm = dict(front_matter)
        if fm.get("report"):
            report_def = get_report(fm["report"]) or {}
            for k in ("query", "jql", "board", "sprint", "label"):
                if k in report_def and k not in fm:
                    fm[k] = str(report_def[k])

        # Build JQL from front matter
        jql = fm.get("jql")
        if fm.get("query"):
            jql = get_query(fm["query"])
        elif fm.get("board"):
            board_id = fm["board"]
            try:
                board_id = int(board_id)
            except ValueError:
                board_id = get_board(board_id)
            if board_id:
                jql = get_board_issues_jql(board_id)
        elif fm.get("sprint"):
            jql = get_sprint_issues_jql(int(fm["sprint"]))

        if not jql:
            print("Warning: Could not determine JQL for ticket export")
        else:
            # Add label filter if present
            if fm.get("label"):
                jql = f'{jql} AND labels = "{fm["label"]}"'

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
