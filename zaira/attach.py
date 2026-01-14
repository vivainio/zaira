"""Upload attachments to Jira tickets."""

import argparse
import sys
from pathlib import Path

from zaira.jira_client import get_jira, get_jira_site


def attach_file(key: str, filepath: Path) -> bool:
    """Upload a file as an attachment to a Jira ticket.

    Args:
        key: Ticket key (e.g., PROJ-123)
        filepath: Path to the file to upload

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        with open(filepath, "rb") as f:
            jira.add_attachment(key, f, filename=filepath.name)
        return True
    except Exception as e:
        print(f"  Error uploading {filepath.name}: {e}", file=sys.stderr)
        return False


def attach_command(args: argparse.Namespace) -> None:
    """Handle attach subcommand."""
    key = args.key.upper()
    files = [Path(f) for f in args.files]

    # Validate files exist
    for f in files:
        if not f.exists():
            print(f"Error: File not found: {f}", file=sys.stderr)
            sys.exit(1)

    jira_site = get_jira_site()
    print(f"Uploading {len(files)} file(s) to {key}...")

    success = 0
    for f in files:
        print(f"  {f.name}...", end=" ")
        if attach_file(key, f):
            print("done")
            success += 1
        else:
            print("failed")

    print(f"\nUploaded {success}/{len(files)} files")
    print(f"View at: https://{jira_site}/browse/{key}")

    if success < len(files):
        sys.exit(1)
