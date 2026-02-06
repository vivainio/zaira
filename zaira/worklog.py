"""Log work hours to Jira tickets."""

import argparse
import sys
from datetime import datetime

from zaira.jira_client import get_jira, get_jira_site
from zaira.types import Worklog, get_user_identifier


def list_worklogs(key: str) -> list[Worklog]:
    """Get worklogs for a ticket.

    Args:
        key: Ticket key (e.g., PROJ-123)

    Returns:
        List of Worklog entries
    """
    jira = get_jira()
    try:
        entries = jira.worklogs(key)
        return [
            Worklog(
                author=get_user_identifier(entry.author) or "Unknown",
                time_spent=entry.timeSpent,
                started=entry.started,
                comment=getattr(entry, "comment", None),
            )
            for entry in entries
        ]
    except Exception as e:
        print(f"Error getting worklogs for {key}: {e}", file=sys.stderr)
        return []


def add_worklog(
    key: str,
    time_spent: str,
    comment: str | None = None,
    started: datetime | None = None,
) -> bool:
    """Add a worklog entry to a Jira ticket.

    Args:
        key: Ticket key (e.g., PROJ-123)
        time_spent: Time spent string (e.g., "2h", "30m", "1d")
        comment: Optional worklog comment
        started: Optional start date/time (defaults to now)

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        kwargs: dict = {"issue": key, "timeSpent": time_spent}
        if comment:
            kwargs["comment"] = comment
        if started:
            kwargs["started"] = started
        worklog = jira.add_worklog(**kwargs)
        return worklog is not None
    except Exception as e:
        print(f"Error logging work to {key}: {e}", file=sys.stderr)
        return False


def log_command(args: argparse.Namespace) -> None:
    """Handle log subcommand."""
    key = args.key.upper()
    jira_site = get_jira_site()

    if args.list:
        entries = list_worklogs(key)
        if not entries:
            print(f"No worklogs found for {key}")
            return
        total_h = 0.0
        print(f"Worklogs for {key}:")
        for entry in entries:
            comment_str = f"  ({entry.comment})" if entry.comment else ""
            date = entry.started[:10] if len(entry.started) >= 10 else entry.started
            print(f"  {date}  {entry.time_spent:<8} {entry.author}{comment_str}")
            # Parse time_spent for total (best-effort)
            total_h += _parse_time_to_hours(entry.time_spent)
        if total_h > 0:
            print(f"\nTotal: {total_h:.1f}h")
        return

    if not args.time:
        print("Error: Specify time spent or use --list", file=sys.stderr)
        sys.exit(1)

    started = None
    if args.date:
        try:
            started = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(
                f"Error: Invalid date '{args.date}'. Use YYYY-MM-DD format.",
                file=sys.stderr,
            )
            sys.exit(1)

    print(f"Logging {args.time} to {key}...")

    if add_worklog(key, args.time, comment=args.comment, started=started):
        print(f"Logged {args.time} to {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
    else:
        sys.exit(1)


def _parse_time_to_hours(time_spent: str) -> float:
    """Best-effort parse of Jira time string to hours.

    Handles formats like "2h", "30m", "1d", "1h 30m", "2h 15m".
    """
    hours = 0.0
    parts = time_spent.lower().split()
    for part in parts:
        if part.endswith("d"):
            try:
                hours += float(part[:-1]) * 8
            except ValueError:
                pass
        elif part.endswith("h"):
            try:
                hours += float(part[:-1])
            except ValueError:
                pass
        elif part.endswith("m"):
            try:
                hours += float(part[:-1]) / 60
            except ValueError:
                pass
        elif part.endswith("w"):
            try:
                hours += float(part[:-1]) * 40
            except ValueError:
                pass
    return hours
