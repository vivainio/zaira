"""Generate reports from Jira queries in markdown, JSON, or CSV format."""

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from zaira.config import REPORTS_DIR
from zaira.jira_client import get_jira
from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
from zaira.dashboard import get_dashboard, get_dashboard_gadgets
from zaira.types import ReportTicket, get_user_identifier


def humanize_age(iso_timestamp: str) -> str:
    """Convert ISO timestamp to human-readable age like '2d' or '3w'."""
    if not iso_timestamp:
        return "-"
    try:
        # Parse ISO timestamp (Jira format: 2026-01-11T14:30:00.000+0000)
        dt = datetime.fromisoformat(iso_timestamp.replace("+0000", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt

        seconds = delta.total_seconds()
        if seconds < 60:
            return "now"
        minutes = seconds / 60
        if minutes < 60:
            return f"{int(minutes)}m"
        hours = minutes / 60
        if hours < 24:
            return f"{int(hours)}h"
        days = hours / 24
        if days < 7:
            return f"{int(days)}d"
        weeks = days / 7
        if weeks < 4:
            return f"{int(weeks)}w"
        months = days / 30
        if months < 12:
            return f"{int(months)}mo"
        years = days / 365
        return f"{int(years)}y"
    except (ValueError, TypeError):
        return "-"


def get_ticket_dates(key: str) -> dict:
    """Fetch created and updated timestamps for a ticket."""
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="created,updated")
        return {
            "created": issue.fields.created or "",
            "updated": issue.fields.updated or "",
        }
    except Exception:
        return {"created": "", "updated": ""}


def search_tickets(jql: str) -> list[ReportTicket]:
    """Search for tickets and return list of ticket data."""
    jira = get_jira()
    try:
        issues = jira.search_issues(jql, maxResults=False)
        tickets = []
        for issue in issues:
            fields = issue.fields
            labels = fields.labels or []

            # Get parent info if available
            parent = None
            if hasattr(fields, "parent") and fields.parent:
                parent = {
                    "key": fields.parent.key,
                    "summary": fields.parent.fields.summary
                    if hasattr(fields.parent, "fields")
                    else "",
                }

            ticket = {
                "key": issue.key,
                "summary": fields.summary or "",
                "issuetype": fields.issuetype.name if fields.issuetype else "?",
                "status": fields.status.name if fields.status else "?",
                "statusCategory": fields.status.statusCategory.name
                if fields.status and fields.status.statusCategory
                else None,
                "priority": fields.priority.name if fields.priority else "-",
                "assignee": get_user_identifier(fields.assignee) or "-",
                "assigneeDisplayName": fields.assignee.displayName
                if fields.assignee
                else None,
                "reporter": get_user_identifier(fields.reporter),
                "reporterDisplayName": fields.reporter.displayName
                if fields.reporter
                else None,
                "labels": labels,
                "components": [c.name for c in (fields.components or [])],
                "project": fields.project.key if fields.project else None,
                "resolution": fields.resolution.name if fields.resolution else None,
                "fixVersions": [
                    v.name for v in (getattr(fields, "fixVersions", None) or [])
                ],
                "duedate": getattr(fields, "duedate", None),
                "created": fields.created or "",
                "updated": fields.updated or "",
                "parent": parent,
            }
            tickets.append(ticket)
        return tickets
    except Exception as e:
        print(f"Error searching: {e}")
        return []


def generate_front_matter(
    title: str,
    jql: str | None = None,
    query: str | None = None,
    board: int | None = None,
    sprint: int | None = None,
    group_by: str | None = None,
    label: str | None = None,
) -> str:
    """Generate YAML front matter with refresh info."""
    lines = ["---"]
    lines.append(f"title: {title}")
    lines.append(f"generated: {datetime.now().isoformat(timespec='seconds')}")

    # Refresh command
    cmd_parts = ["zaira report"]
    if query:
        lines.append(f"query: {query}")
        cmd_parts.append(f"--query {query}")
    elif jql and not board and not sprint:
        lines.append(f'jql: "{jql}"')
        cmd_parts.append(f'--jql "{jql}"')
    if board:
        lines.append(f"board: {board}")
        cmd_parts.append(f"--board {board}")
    if sprint:
        lines.append(f"sprint: {sprint}")
        cmd_parts.append(f"--sprint {sprint}")
    if label:
        lines.append(f"label: {label}")
        cmd_parts.append(f'--label "{label}"')
    if group_by:
        lines.append(f"group_by: {group_by}")
        cmd_parts.append(f"--group-by {group_by}")

    cmd_parts.append(f'--title "{title}"')
    lines.append(f"refresh: {' '.join(cmd_parts)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def generate_report(
    tickets: list[ReportTicket],
    title: str,
    group_by: str | None = None,
    jql: str | None = None,
    query: str | None = None,
    board: int | None = None,
    sprint: int | None = None,
    label: str | None = None,
) -> str:
    """Generate markdown report from tickets."""
    md = generate_front_matter(title, jql, query, board, sprint, group_by, label)
    md += f"# {title}\n\n"
    md += f"**Total:** {len(tickets)} tickets\n\n"

    if not tickets:
        md += "_No tickets found._\n"
        return md

    if group_by:
        if group_by == "labels":
            # Special handling for labels - tickets can have multiple
            groups = {}
            for t in tickets:
                ticket_labels = t.get("labels", [])
                if not ticket_labels:
                    ticket_labels = ["(no label)"]
                for lbl in ticket_labels:
                    if lbl not in groups:
                        groups[lbl] = []
                    groups[lbl].append(t)
        elif group_by == "parent":
            # Special handling for parent - it's a dict
            groups = {}
            for t in tickets:
                parent = t.get("parent")
                if parent:
                    group_key = f"{parent['key']}: {parent['summary']}"
                else:
                    group_key = "(no parent)"
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(t)
        else:
            # Group tickets by field
            groups = {}
            for t in tickets:
                key = t.get(group_by, "Unknown")
                if key not in groups:
                    groups[key] = []
                groups[key].append(t)

        for group_name, group_tickets in sorted(groups.items()):
            md += f"## {group_name} ({len(group_tickets)})\n\n"
            md += generate_table(group_tickets, group_by=group_by)
            md += "\n"
    else:
        md += generate_table(tickets)

    return md


def generate_table(tickets: list[ReportTicket], group_by: str | None = None) -> str:
    """Generate markdown table from tickets.

    Args:
        tickets: List of ticket data
        group_by: Field used for grouping (will be excluded from table)
    """
    if not tickets:
        return "_No tickets_\n"

    # Check if any tickets have parents
    has_parents = any(t.get("parent") for t in tickets)

    # Build columns, excluding the group_by field
    columns = ["Key", "Type", "Status", "Age"]
    if has_parents and group_by != "parent":
        columns.append("Parent")
    columns.append("Summary")

    # Remove grouped column
    if group_by == "status":
        columns.remove("Status")
    elif group_by == "issuetype":
        columns.remove("Type")

    md = "| " + " | ".join(columns) + " |\n"
    md += "|" + "|".join(["-----"] * len(columns)) + "|\n"

    for t in tickets:
        key = t.get("key", "?")
        issue_type = t.get("issuetype", "?")
        status = t.get("status", "?")
        age = humanize_age(t.get("updated", ""))
        summary = t.get("summary", "")
        parent = t.get("parent")

        # Truncate long summaries
        if len(summary) > 200:
            summary = summary[:197] + "..."

        # Escape pipes in summary
        summary = summary.replace("|", "\\|")

        # Build row based on columns
        row = [key, issue_type, status, age]
        if has_parents and group_by != "parent":
            row.append(parent["key"] if parent else "-")
        row.append(summary)

        # Remove grouped column value
        if group_by == "status":
            row.pop(2)  # status is at index 2
        elif group_by == "issuetype":
            row.pop(1)  # type is at index 1

        md += "| " + " | ".join(row) + " |\n"

    return md


def generate_json_report(
    tickets: list[ReportTicket],
    title: str,
    jql: str | None = None,
    query: str | None = None,
    board: int | None = None,
    sprint: int | None = None,
    group_by: str | None = None,
    label: str | None = None,
) -> str:
    """Generate JSON report from tickets."""
    data = {
        "title": title,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "total": len(tickets),
        "tickets": tickets,
    }
    if jql:
        data["jql"] = jql
    if query:
        data["query"] = query
    if board:
        data["board"] = board
    if sprint:
        data["sprint"] = sprint
    if group_by:
        data["group_by"] = group_by
    if label:
        data["label"] = label
    return json.dumps(data, indent=2)


def generate_csv_report(tickets: list[ReportTicket]) -> str:
    """Generate CSV report from tickets."""
    if not tickets:
        return ""

    output = io.StringIO()
    fieldnames = [
        "key",
        "summary",
        "issuetype",
        "status",
        "priority",
        "assignee",
        "labels",
        "parent",
        "created",
        "updated",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for t in tickets:
        row = {**t}
        # Convert labels list to comma-separated string
        row["labels"] = ",".join(t.get("labels", []))
        # Convert parent dict to key
        parent = t.get("parent")
        row["parent"] = parent["key"] if parent else ""
        writer.writerow(row)

    return output.getvalue()


def generate_dashboard_report(
    dashboard_id: int,
    group_by: str | None = None,
    to_stdout: bool = False,
) -> tuple[str, int]:
    """Generate a combined report from all JQL queries in a dashboard.

    Args:
        dashboard_id: The dashboard ID
        group_by: Optional field to group tickets by within each section
        to_stdout: Whether output is going to stdout (suppresses progress)

    Returns:
        Tuple of (markdown report, total ticket count)
    """
    dashboard = get_dashboard(dashboard_id)
    if not dashboard:
        return "", 0

    if not to_stdout:
        print(f"Fetching gadgets from dashboard: {dashboard.name}")

    gadgets = get_dashboard_gadgets(dashboard_id, resolve_jql=True)
    jql_gadgets = [g for g in gadgets if g.jql]

    if not jql_gadgets:
        return f"# {dashboard.name}\n\n_No gadgets with JQL queries found._\n", 0

    if not to_stdout:
        print(f"Found {len(jql_gadgets)} gadgets with JQL queries")

    # Build front matter
    lines = ["---"]
    lines.append(f"title: {dashboard.name}")
    lines.append(f"dashboard_id: {dashboard_id}")
    lines.append(f"generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"refresh: zaira report --dashboard {dashboard_id}")
    lines.append("---")
    lines.append("")

    # Header
    lines.append(f"# {dashboard.name}")
    lines.append("")
    if dashboard.description:
        lines.append(f"_{dashboard.description}_")
        lines.append("")
    lines.append(f"**Dashboard URL:** {dashboard.view_url}")
    lines.append("")

    total_tickets = 0

    # Run each gadget's JQL and generate a section
    for gadget in sorted(jql_gadgets, key=lambda x: x.position):
        title = gadget.filter_name or gadget.title or f"Query {gadget.id}"
        if not to_stdout:
            print(f"  Running: {title}")

        tickets = search_tickets(gadget.jql)
        total_tickets += len(tickets)

        if not to_stdout:
            print(f"    Found {len(tickets)} tickets")

        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"**JQL:** `{gadget.jql}`")
        lines.append("")
        lines.append(f"**Results:** {len(tickets)} tickets")
        lines.append("")

        if tickets:
            if group_by:
                # Group tickets
                if group_by == "labels":
                    groups = {}
                    for t in tickets:
                        ticket_labels = t.get("labels", [])
                        if not ticket_labels:
                            ticket_labels = ["(no label)"]
                        for lbl in ticket_labels:
                            if lbl not in groups:
                                groups[lbl] = []
                            groups[lbl].append(t)
                elif group_by == "parent":
                    groups = {}
                    for t in tickets:
                        parent = t.get("parent")
                        if parent:
                            group_key = f"{parent['key']}: {parent['summary']}"
                        else:
                            group_key = "(no parent)"
                        if group_key not in groups:
                            groups[group_key] = []
                        groups[group_key].append(t)
                else:
                    groups = {}
                    for t in tickets:
                        key = t.get(group_by, "Unknown")
                        if key not in groups:
                            groups[key] = []
                        groups[key].append(t)

                for group_name, group_tickets in sorted(groups.items()):
                    lines.append(f"### {group_name} ({len(group_tickets)})")
                    lines.append("")
                    lines.append(generate_table(group_tickets, group_by=group_by))
            else:
                lines.append(generate_table(tickets))
        else:
            lines.append("_No tickets found._")

        lines.append("")

    # Summary
    lines.append("---")
    lines.append("")
    lines.append(f"**Total across all queries:** {total_tickets} tickets")
    lines.append("")

    return "\n".join(lines), total_tickets


def report_command(args: argparse.Namespace) -> None:
    """Handle report subcommand."""
    from zaira.project import get_query, get_board, get_report, list_reports

    # Check if no arguments provided - list available reports
    report_name = getattr(args, "name", None)
    dashboard_arg = getattr(args, "dashboard", None)
    has_args = report_name or args.query or args.jql or args.board or args.sprint or dashboard_arg

    if not has_args:
        reports = list_reports()
        if not reports:
            print("No reports defined in zproject.toml")
            print("\nUse --jql, --query, --board, or --sprint to generate a report")
            sys.exit(0)

        print("Available reports:\n")
        for name, config in reports.items():
            # Build description from config
            desc_parts = []
            if "dashboard" in config:
                desc_parts.append(f"dashboard={config['dashboard']}")
            if "query" in config:
                desc_parts.append(f"query={config['query']}")
            if "jql" in config:
                desc_parts.append(f'jql="{config["jql"]}"')
            if "board" in config:
                desc_parts.append(f"board={config['board']}")
            if "sprint" in config:
                desc_parts.append(f"sprint={config['sprint']}")
            if "group_by" in config:
                desc_parts.append(f"group_by={config['group_by']}")
            if "label" in config:
                desc_parts.append(f"label={config['label']}")

            desc = ", ".join(desc_parts) if desc_parts else "(no config)"
            print(f"  {name}")
            print(f"    {desc}")
        print("\nRun: zaira report <name>")
        sys.exit(0)

    # Default to stdout if no zproject.toml, otherwise files
    has_project = Path("zproject.toml").exists()
    if args.output == "-":
        to_stdout = True
    elif args.output:
        to_stdout = False
    else:
        to_stdout = not has_project

    # Handle named report from project.toml
    if report_name:
        report_def = get_report(report_name)
        if not report_def:
            print(f"Error: Report '{report_name}' not found in project.toml")
            sys.exit(1)
        if not to_stdout:
            print(f"Using report '{report_name}'")
        # Apply report settings as defaults (CLI args override)
        if not dashboard_arg and "dashboard" in report_def:
            dashboard_arg = report_def["dashboard"]
        if not args.query and "query" in report_def:
            args.query = report_def["query"]
        if not args.jql and "jql" in report_def:
            args.jql = report_def["jql"]
        if not args.board and "board" in report_def:
            args.board = str(report_def["board"])
        if not args.sprint and "sprint" in report_def:
            args.sprint = report_def["sprint"]
        if not args.group_by and "group_by" in report_def:
            args.group_by = report_def["group_by"]
        if not getattr(args, "label", None) and "label" in report_def:
            args.label = report_def["label"]
        if not args.title and "title" in report_def:
            args.title = report_def["title"]
        if "full" in report_def:
            args.full = report_def["full"]

    # Handle dashboard report (special case - runs multiple queries)
    if dashboard_arg:
        # Extract ID from URL if needed
        if "/" in str(dashboard_arg):
            parts = str(dashboard_arg).rstrip("/").split("/")
            dashboard_id = int(parts[-1])
        else:
            dashboard_id = int(dashboard_arg)

        report, total = generate_dashboard_report(
            dashboard_id,
            group_by=args.group_by,
            to_stdout=to_stdout,
        )

        if not report:
            print(f"Dashboard {dashboard_id} not found.")
            sys.exit(1)

        if to_stdout:
            print(report)
        else:
            if args.output:
                output_path = Path(args.output)
            else:
                # Use report name for filename if available
                filename = f"{report_name}.md" if report_name else f"dashboard-{dashboard_id}.md"
                output_path = REPORTS_DIR / filename

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report)
            print(f"Saved to {output_path}")

        sys.exit(0)

    # Build JQL from options
    jql = args.jql
    board_id = None

    # Handle named query
    if args.query:
        jql = get_query(args.query)
        if not jql:
            print(f"Error: Query '{args.query}' not found in project.toml")
            sys.exit(1)
        if not to_stdout:
            print(f"Using query '{args.query}'")

    # Handle board (ID or name)
    if args.board:
        # Try as integer first
        try:
            board_id = int(args.board)
        except ValueError:
            # Try as name from project.toml
            board_id = get_board(args.board)
            if not board_id:
                print(f"Error: Board '{args.board}' not found in project.toml")
                sys.exit(1)
        jql = get_board_issues_jql(board_id)
        if not to_stdout:
            print(f"Using board {board_id}")
    elif args.sprint:
        jql = get_sprint_issues_jql(args.sprint)
        if not to_stdout:
            print(f"Using sprint {args.sprint}")

    if not jql:
        print("Error: --query, --jql, --board, or --sprint is required")
        sys.exit(1)

    # Add label filter if specified
    label = getattr(args, "label", None)

    if label:
        jql = f'{jql} AND labels = "{label}"'
        if not to_stdout:
            print(f"Filtering by label: {label}")

    if not to_stdout:
        print(f"Searching: {jql}")
    tickets = search_tickets(jql)
    if not to_stdout:
        print(f"Found {len(tickets)} tickets")

    if not tickets:
        print("No tickets found.")
        sys.exit(0)

    # Default title from report name, query name, board name, or generic
    title = args.title
    if not title:
        if report_name:
            title = report_name.replace("-", " ").title()
        elif args.query:
            title = args.query.replace("-", " ").title()
        elif args.board:
            title = str(args.board).replace("-", " ").title()
        else:
            title = "Jira Report"

    # Generate report in requested format
    fmt = getattr(args, "format", "md")
    if fmt == "json":
        report = generate_json_report(
            tickets,
            title,
            jql=args.jql,
            query=getattr(args, "query", None),
            board=board_id,
            sprint=args.sprint,
            group_by=args.group_by,
            label=label,
        )
        ext = "json"
    elif fmt == "csv":
        report = generate_csv_report(tickets)
        ext = "csv"
    else:
        report = generate_report(
            tickets,
            title,
            group_by=args.group_by,
            jql=args.jql,
            query=getattr(args, "query", None),
            board=board_id,
            sprint=args.sprint,
            label=label,
        )
        ext = "md"

    if to_stdout:
        # Output to stdout
        print(report)
    else:
        if args.output:
            output_path = Path(args.output)
        else:
            # Generate filename from title
            slug = title.lower().replace(" ", "-")
            output_path = REPORTS_DIR / f"{slug}.{ext}"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        print(f"Saved to {output_path}")

    # Full mode: also export tickets
    if getattr(args, "full", False):
        from zaira.export import export_ticket
        from zaira.config import TICKETS_DIR
        from zaira.refresh import find_ticket_file, ticket_needs_export

        print("\nExporting tickets...")
        exported = 0
        skipped = 0
        force = getattr(args, "force", False)

        for t in tickets:
            key = t.get("key")
            if not key:
                continue
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

        print(f"Exported {exported} tickets, {skipped} unchanged")
