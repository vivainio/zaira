"""Query worklog hours across tickets."""

import argparse
import sys
from datetime import datetime, timedelta

from zaira.jira_client import format_jira_error, get_jira
from zaira.project import get_max_hours_per_day
from zaira.types import get_user_identifier


def _days_range(days: int) -> tuple[str, str]:
    """Get date range for the last N days (ending today).

    Args:
        days: Number of days to look back

    Returns:
        Tuple of (start_date, end_date) as YYYY-MM-DD strings
    """
    today = datetime.now()
    start = today - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


def query_hours(
    date_from: str, date_to: str
) -> tuple[dict[str, list[tuple[str, str, float, str | None]]], dict[str, float]]:
    """Query worklogs for current user in a date range.

    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)

    Returns:
        Tuple of (daily_entries, ticket_totals) where:
        - daily_entries maps date -> list of (key, summary, hours, comment)
        - ticket_totals maps key -> total hours
    """
    jira = get_jira()
    jql = (
        f"worklogAuthor = currentUser() "
        f'AND worklogDate >= "{date_from}" '
        f'AND worklogDate <= "{date_to}"'
    )
    issues = jira.search_issues(jql, maxResults=50)

    if not issues:
        return {}, {}

    me = jira.myself().get("emailAddress", "")
    daily: dict[str, list[tuple[str, str, float, str | None]]] = {}
    ticket_totals: dict[str, float] = {}

    for issue in issues:
        worklogs = jira.worklogs(issue.key)
        summary = str(issue.fields.summary)[:50]
        for wl in worklogs:
            started = wl.started[:10]
            if started < date_from or started > date_to:
                continue
            author = get_user_identifier(wl.author) or ""
            if author != me:
                continue
            hours = wl.timeSpentSeconds / 3600
            comment = getattr(wl, "comment", None)
            daily.setdefault(started, []).append((issue.key, summary, hours, comment))
            ticket_totals[issue.key] = ticket_totals.get(issue.key, 0) + hours

    return daily, ticket_totals


def query_ticket_hours(
    keys: list[str],
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, dict[str, float]]:
    """Query worklogs for specific tickets, grouped by person.

    Args:
        keys: Ticket keys to query
        date_from: Optional start date filter (YYYY-MM-DD)
        date_to: Optional end date filter (YYYY-MM-DD)

    Returns:
        Dict mapping ticket key -> {author: total_hours}
    """
    jira = get_jira()
    result: dict[str, dict[str, float]] = {}

    for key in keys:
        try:
            worklogs = jira.worklogs(key)
        except Exception as e:
            print(
                f"Error getting worklogs for {key}: {format_jira_error(e)}",
                file=sys.stderr,
            )
            continue

        author_hours: dict[str, float] = {}
        for wl in worklogs:
            started = wl.started[:10]
            if date_from and started < date_from:
                continue
            if date_to and started > date_to:
                continue
            author = get_user_identifier(wl.author) or "Unknown"
            hours = wl.timeSpentSeconds / 3600
            author_hours[author] = author_hours.get(author, 0) + hours

        if author_hours:
            result[key] = author_hours

    return result


def format_ticket_hours(
    ticket_hours: dict[str, dict[str, float]],
    summaries: dict[str, str],
) -> str:
    """Format per-ticket worklog data for display.

    Args:
        ticket_hours: Dict from query_ticket_hours
        summaries: Dict mapping ticket key -> summary text

    Returns:
        Formatted string
    """
    if not ticket_hours:
        return "No worklogs found"

    lines: list[str] = []
    grand_total = 0.0

    for key in ticket_hours:
        author_hours = ticket_hours[key]
        summary = summaries.get(key, "")
        subtotal = sum(author_hours.values())
        grand_total += subtotal

        lines.append(f"\n{key}: {summary}")
        for author, hours in sorted(author_hours.items(), key=lambda x: -x[1]):
            lines.append(f"  {author:<40} {hours:.1f}h")
        lines.append(f"  {'Subtotal:':<40} {subtotal:.1f}h")

    lines.append(f"\n{'=' * 50}")
    lines.append(f"Total: {grand_total:.1f}h across {len(ticket_hours)} ticket(s)")

    return "\n".join(lines)


def format_ticket_hours_csv(
    ticket_hours: dict[str, dict[str, float]],
    summaries: dict[str, str],
) -> str:
    """Format per-ticket worklog data as CSV.

    Args:
        ticket_hours: Dict from query_ticket_hours
        summaries: Dict mapping ticket key -> summary text

    Returns:
        CSV string with header
    """
    lines = ["ticket,summary,author,hours"]
    for key in ticket_hours:
        summary = summaries.get(key, "").replace('"', '""')
        for author, hours in sorted(ticket_hours[key].items(), key=lambda x: -x[1]):
            lines.append(f'{key},"{summary}",{author},{hours:.1f}')
    return "\n".join(lines)


def _workdays_in_range(date_from: str, date_to: str) -> list[str]:
    """Return list of weekday date strings (Mon-Fri) between date_from and date_to inclusive."""
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    days: list[str] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def format_hours(
    daily: dict[str, list[tuple[str, str, float, str | None]]],
    ticket_totals: dict[str, float],
    date_from: str,
    date_to: str,
    summary_only: bool = False,
    show_missing: bool = False,
) -> str:
    """Format worklog data for display.

    Args:
        daily: Daily entries from query_hours
        ticket_totals: Ticket totals from query_hours
        date_from: Start date
        date_to: End date
        summary_only: Show only ticket totals, no daily breakdown
        show_missing: Show workdays with missing hours

    Returns:
        Formatted string
    """
    if not daily and not show_missing:
        return f"No worklogs found for {date_from} to {date_to}"

    lines: list[str] = []

    if not summary_only:
        for date in sorted(daily):
            day_name = datetime.strptime(date, "%Y-%m-%d").strftime("%a")
            day_total = sum(h for _, _, h, _ in daily[date])
            lines.append(f"\n{date} ({day_name})  [{day_total:.1f}h]")
            for key, summary, hours, comment in daily[date]:
                comment_str = f"  ({comment})" if comment else ""
                lines.append(f"  {key:<12} {hours:.1f}h  {summary}{comment_str}")

    grand_total = sum(ticket_totals.values())
    lines.append(f"\n{'=' * 50}")
    lines.append(f"Total: {grand_total:.1f}h  ({date_from} to {date_to})")
    if ticket_totals:
        lines.append("\nBy ticket:")
        for key, hours in sorted(ticket_totals.items(), key=lambda x: -x[1]):
            lines.append(f"  {key:<12} {hours:.1f}h")

    if show_missing:
        max_hours = get_max_hours_per_day()
        workdays = _workdays_in_range(date_from, date_to)
        missing_lines: list[str] = []
        total_missing = 0.0
        for day in workdays:
            logged = sum(h for _, _, h, _ in daily.get(day, []))
            if logged < max_hours:
                gap = max_hours - logged
                total_missing += gap
                day_name = datetime.strptime(day, "%Y-%m-%d").strftime("%a")
                missing_lines.append(
                    f"  {day} ({day_name})   {logged:.1f}h logged, {gap:.1f}h missing"
                )
        if missing_lines:
            lines.append("\nMissing hours:")
            lines.extend(missing_lines)
            lines.append(
                f"  Total missing: {total_missing:.1f}h across {len(missing_lines)} day(s)"
            )

    return "\n".join(lines)


def fill_missing(
    ticket: str,
    date_from: str,
    date_to: str,
    daily: dict[str, list[tuple[str, str, float, str | None]]],
    yes: bool = False,
) -> None:
    """Fill missing hours by logging worklogs for gap days.

    Args:
        ticket: Ticket key to log hours against
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        daily: Daily entries from query_hours
        yes: If True, actually log the hours; otherwise preview only
    """
    from zaira.worklog import _format_duration, add_worklog

    max_hours = get_max_hours_per_day()
    workdays = _workdays_in_range(date_from, date_to)
    gaps: list[tuple[str, float]] = []

    for day in workdays:
        logged = sum(h for _, _, h, _ in daily.get(day, []))
        if logged < max_hours:
            gaps.append((day, max_hours - logged))

    if not gaps:
        print("No missing hours to fill.")
        return

    total_fill = sum(h for _, h in gaps)
    print(f"\nFilling missing hours on {ticket}:\n")
    for day, gap in gaps:
        day_name = datetime.strptime(day, "%Y-%m-%d").strftime("%a")
        print(f"  {day} ({day_name})  {_format_duration(gap)}")
    print(f"  Total: {total_fill:.1f}h across {len(gaps)} day(s)\n")

    if not yes:
        print("This is a preview. Run again with --yes to confirm.")
        return

    failed = 0
    for day, gap in gaps:
        started = datetime.strptime(day, "%Y-%m-%d")
        duration = _format_duration(gap)
        if add_worklog(ticket, duration, started=started):
            print(f"  Logged {duration} on {day}")
        else:
            failed += 1

    if failed:
        print(f"\n{failed} of {len(gaps)} entries failed.", file=sys.stderr)
        sys.exit(1)
    print(f"\nDone. Filled {total_fill:.1f}h across {len(gaps)} day(s).")


def hours_command(args: argparse.Namespace) -> None:
    """Handle hours subcommand."""
    tickets = getattr(args, "tickets", None) or []

    # Ticket mode: show hours by person per ticket
    if tickets:
        keys = [k.upper() for k in tickets]
        date_from = args.date_from
        date_to = args.date_to

        if date_from or date_to:
            for d, label in [(date_from, "--from"), (date_to, "--to")]:
                if d:
                    try:
                        datetime.strptime(d, "%Y-%m-%d")
                    except ValueError:
                        print(
                            f"Error: Invalid date '{d}' for {label}. Use YYYY-MM-DD format.",
                            file=sys.stderr,
                        )
                        sys.exit(1)

        # Fetch summaries
        jira = get_jira()
        summaries: dict[str, str] = {}
        for key in keys:
            try:
                issue = jira.issue(key, fields="summary")
                summaries[key] = str(issue.fields.summary)[:50]
            except Exception:
                summaries[key] = ""

        ticket_hours = query_ticket_hours(keys, date_from, date_to)
        fmt = getattr(args, "format", None)
        if fmt == "csv":
            print(format_ticket_hours_csv(ticket_hours, summaries))
        else:
            print(format_ticket_hours(ticket_hours, summaries))
        return

    # My hours mode: show my worklogs by day
    if args.days is not None:
        date_from, date_to = _days_range(args.days)
    elif args.date_from and args.date_to:
        date_from, date_to = args.date_from, args.date_to
    elif args.date_from or args.date_to:
        print("Error: --from and --to must be used together", file=sys.stderr)
        sys.exit(1)
    else:
        date_from, date_to = _days_range(7)

    # Validate date format
    for d, label in [(date_from, "--from"), (date_to, "--to")]:
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            print(
                f"Error: Invalid date '{d}' for {label}. Use YYYY-MM-DD format.",
                file=sys.stderr,
            )
            sys.exit(1)

    daily, ticket_totals = query_hours(date_from, date_to)

    show_missing = getattr(args, "missing", False)
    fill_ticket = getattr(args, "fill", None)

    print(
        format_hours(
            daily,
            ticket_totals,
            date_from,
            date_to,
            args.summary,
            show_missing=show_missing or bool(fill_ticket),
        )
    )

    if fill_ticket:
        fill_missing(
            fill_ticket.upper(),
            date_from,
            date_to,
            daily,
            yes=getattr(args, "yes", False),
        )
