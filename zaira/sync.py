"""Sync reports by re-running their generation command."""

import argparse
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from zaira.config import REPORTS_DIR, TICKETS_DIR

# Default max age for tickets before refresh (in hours)
DEFAULT_MAX_AGE_HOURS = 24


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


def ticket_is_stale(
    ticket_file: Path, max_age_hours: int = DEFAULT_MAX_AGE_HOURS
) -> bool:
    """Check if ticket file is older than max_age_hours based on synced timestamp."""
    content = ticket_file.read_text()
    meta = parse_front_matter(content)
    synced_str = meta.get("synced", "")

    if not synced_str:
        return True  # No synced timestamp, consider stale

    try:
        synced = datetime.fromisoformat(synced_str)
        age = datetime.now() - synced
        return age > timedelta(hours=max_age_hours)
    except ValueError:
        return True  # Can't parse, consider stale


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
        print("\nExporting tickets...")
        report_content = report_path.read_text()
        keys = extract_ticket_keys(report_content)
        print(f"Found {len(keys)} tickets in report")

        exported = 0
        skipped = 0
        force = getattr(args, "force", False)

        for key in sorted(keys):
            ticket_file = find_ticket_file(key)
            if ticket_file:
                if force:
                    print(f"  {key}: forcing refresh...")
                    if export_ticket(key, TICKETS_DIR):
                        exported += 1
                elif ticket_is_stale(ticket_file):
                    print(f"  {key}: stale, refreshing...")
                    if export_ticket(key, TICKETS_DIR):
                        exported += 1
                else:
                    print(f"  {key}: fresh, skipping")
                    skipped += 1
            else:
                print(f"  {key}: new, exporting...")
                if export_ticket(key, TICKETS_DIR):
                    exported += 1

        print(f"\nExported {exported} tickets, {skipped} fresh")
