"""Log work hours to Jira tickets."""

import argparse
import re
import sys
from datetime import datetime, timedelta

from zaira.hours import query_hours
from zaira.jira_client import format_jira_error, get_jira, get_jira_site
from zaira.project import get_max_hours_per_day
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
        print(f"Error getting worklogs for {key}: {format_jira_error(e)}", file=sys.stderr)
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
        print(f"Error logging work to {key}: {format_jira_error(e)}", file=sys.stderr)
        return False


def _round_half_hour(hours: float) -> float:
    """Round hours to nearest 0.5h."""
    return round(hours * 2) / 2


def _distribute_rounded(total_hours: float, num_days: int) -> list[float]:
    """Split total_hours across num_days, rounding each to 0.5h.

    Distributes evenly, rounds each slot, then adjusts slots to keep the
    total correct (adds/removes 0.5h from the slots furthest from their
    unrounded values).
    """
    if num_days <= 0:
        return []
    base = total_hours / num_days
    rounded = [_round_half_hour(base)] * num_days

    diff = round((total_hours - sum(rounded)) * 2) / 2  # in 0.5h increments

    # Compute how far each slot was rounded (positive = rounded down)
    errors = [(base - rounded[i], i) for i in range(num_days)]

    if diff > 0:
        # Need to add 0.5h to some slots — prefer those rounded down most
        errors.sort(reverse=True)  # largest positive error first
        steps = int(diff / 0.5)
        for s in range(steps):
            idx = errors[s % num_days][1]
            rounded[idx] += 0.5
    elif diff < 0:
        # Need to remove 0.5h from some slots — prefer those rounded up most
        errors.sort()  # largest negative error (rounded up most) first
        steps = int(-diff / 0.5)
        for s in range(steps):
            idx = errors[s % num_days][1]
            rounded[idx] = max(0, rounded[idx] - 0.5)

    return rounded


def _collect_workdays(
    num_days: int,
    start_date: datetime | None = None,
    skip_weekends: bool = True,
) -> list[datetime]:
    """Collect workdays going backwards from start_date (default: today)."""
    if start_date is None:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days: list[datetime] = []
    current = start_date
    while len(days) < num_days:
        if not skip_weekends or current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    days.reverse()
    return days


def _collect_date_range(
    start: str,
    end: str,
    skip_weekends: bool = True,
) -> list[datetime]:
    """Collect workdays in an inclusive date range."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    days: list[datetime] = []
    current = start_dt
    while current <= end_dt:
        if not skip_weekends or current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _parse_spread(spread: str) -> int | tuple[str, str]:
    """Parse --spread value: '5d' for day count, 'YYYY-MM-DD,YYYY-MM-DD' for range."""
    m = re.match(r"^(\d+)d$", spread)
    if m:
        return int(m.group(1))
    parts = spread.split(",")
    if len(parts) == 2:
        # Validate date format
        for p in parts:
            datetime.strptime(p.strip(), "%Y-%m-%d")
        return (parts[0].strip(), parts[1].strip())
    raise ValueError(
        f"Invalid --spread value '{spread}'. Use '5d' or 'YYYY-MM-DD,YYYY-MM-DD'."
    )


def _format_duration(hrs: float) -> str:
    """Format hours as Jira duration string like '3h', '2h 30m', '30m'."""
    whole = int(hrs)
    frac = hrs - whole
    if whole and frac:
        return f"{whole}h 30m"
    elif whole:
        return f"{whole}h"
    else:
        return "30m"


def spread_hours(
    total: str,
    days: int | tuple[str, str],
    skip_weekends: bool = True,
    existing_hours: dict[str, float] | None = None,
) -> list[tuple[str, str]]:
    """Distribute total time across workdays, respecting 8h/day cap.

    Args:
        total: Time string (e.g., "16h", "2d", "4h 30m")
        days: Number of days (int) or (start, end) date range
        skip_weekends: Whether to skip Sat/Sun
        existing_hours: Dict of date (YYYY-MM-DD) -> hours already logged

    Returns:
        List of (YYYY-MM-DD, duration_str) tuples
    """
    total_hours = _parse_time_to_hours(total)
    if total_hours <= 0:
        return []

    if isinstance(days, int):
        workdays = _collect_workdays(days, skip_weekends=skip_weekends)
    else:
        workdays = _collect_date_range(days[0], days[1], skip_weekends=skip_weekends)

    if not workdays:
        return []

    existing = existing_hours or {}
    max_per_day = get_max_hours_per_day()

    # Compute available capacity per day (rounded to 0.5h)
    caps = []
    for dt in workdays:
        date_str = dt.strftime("%Y-%m-%d")
        used = existing.get(date_str, 0.0)
        avail = _round_half_hour(max(0.0, max_per_day - used))
        caps.append(avail)

    total_capacity = sum(caps)
    if total_capacity < total_hours:
        raise ValueError(
            f"Cannot fit {total_hours:.1f}h into {len(workdays)} days "
            f"(only {total_capacity:.1f}h available after existing worklogs). "
            f"Add more days."
        )

    # Distribute: try even split first, capped per day
    num_days = len(workdays)
    amounts = _distribute_rounded(total_hours, num_days)

    # Clamp to caps and redistribute overflow
    for _ in range(num_days):  # iterate until stable
        overflow = 0.0
        underfilled = []
        for i in range(num_days):
            if amounts[i] > caps[i]:
                overflow += amounts[i] - caps[i]
                amounts[i] = caps[i]
            elif amounts[i] < caps[i]:
                underfilled.append(i)
        if overflow <= 0:
            break
        if not underfilled:
            break
        # Spread overflow across underfilled days
        extra = _distribute_rounded(overflow, len(underfilled))
        for idx, add in zip(underfilled, extra):
            amounts[idx] = _round_half_hour(amounts[idx] + add)

    result: list[tuple[str, str]] = []
    for dt, hrs in zip(workdays, amounts):
        if hrs > 0:
            result.append((dt.strftime("%Y-%m-%d"), _format_duration(hrs)))
    return result


def _format_hours(hours: float) -> str:
    """Format hours as display string like '3.5h'."""
    if hours == int(hours):
        return f"{int(hours)}.0h"
    return f"{hours:.1f}h"


class _ExistingHours:
    """Existing worklog hours per day with ticket details."""

    def __init__(
        self,
        totals: dict[str, float],
        details: dict[str, list[tuple[str, float]]],
    ):
        self.totals = totals
        self.details = details  # date -> [(ticket_key, hours), ...]

    def get(self, date_str: str, default: float = 0.0) -> float:
        return self.totals.get(date_str, default)


def _fetch_existing_hours(
    spread_spec: int | tuple[str, str],
    skip_weekends: bool,
) -> _ExistingHours:
    """Query Jira for existing hours per day in the spread range."""
    if isinstance(spread_spec, int):
        workdays = _collect_workdays(spread_spec, skip_weekends=skip_weekends)
        date_from = workdays[0].strftime("%Y-%m-%d")
        date_to = workdays[-1].strftime("%Y-%m-%d")
    else:
        date_from, date_to = spread_spec
        if date_from > date_to:
            date_from, date_to = date_to, date_from

    daily, _ = query_hours(date_from, date_to)
    totals: dict[str, float] = {}
    details: dict[str, list[tuple[str, float]]] = {}
    for date_str, entries in daily.items():
        totals[date_str] = sum(hours for _, _, hours, _ in entries)
        # Aggregate hours per ticket for the day
        by_ticket: dict[str, float] = {}
        for key, _, hours, _ in entries:
            by_ticket[key] = by_ticket.get(key, 0) + hours
        details[date_str] = sorted(by_ticket.items())
    return _ExistingHours(totals, details)


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

    # Spread mode
    spread = getattr(args, "spread", None)
    if spread:
        try:
            parsed = _parse_spread(spread)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        include_weekends = getattr(args, "include_weekends", False)

        # Query existing worklogs to avoid exceeding max hours/day
        try:
            existing = _fetch_existing_hours(parsed, not include_weekends)
        except Exception:
            existing = _ExistingHours({}, {})

        try:
            entries = spread_hours(
                args.time, parsed,
                skip_weekends=not include_weekends,
                existing_hours=existing.totals,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if not entries:
            print("Error: No workdays in the specified range.", file=sys.stderr)
            sys.exit(1)

        total_hours = sum(_parse_time_to_hours(dur) for _, dur in entries)
        print(f"\nSpreading {args.time} across {len(entries)} workdays for {key}:\n")
        for date_str, dur in entries:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_name = dt.strftime("%a")
            hrs = _parse_time_to_hours(dur)
            day_details = existing.details.get(date_str, [])
            if day_details:
                tickets = ", ".join(
                    f"{k} {h:.1f}h" for k, h in day_details
                )
                note = f"  ({tickets})"
            else:
                note = ""
            print(f"  {date_str} ({day_name})  {_format_hours(hrs)}{note}")
        print(f"  Total: {_format_hours(total_hours)}\n")

        yes = getattr(args, "yes", False)
        if not yes:
            print("This is a preview. Run again with --yes to confirm.")
            return

        comment = getattr(args, "comment", None)
        failed = 0
        for date_str, dur in entries:
            started = datetime.strptime(date_str, "%Y-%m-%d")
            if add_worklog(key, dur, comment=comment, started=started):
                print(f"  Logged {dur} on {date_str}")
            else:
                failed += 1

        if failed:
            print(f"\n{failed} of {len(entries)} entries failed.", file=sys.stderr)
            sys.exit(1)
        print(f"\nDone. View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record
        record("worklog", key, f"{args.time} spread:{spread}")
        return

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
        from zaira.activity_log import record
        record("worklog", key, args.time)
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
