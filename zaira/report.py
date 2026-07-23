"""Generate reports from Jira queries in markdown, JSON, or CSV format."""

import argparse
import csv
import io
import json
import shlex
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from zaira.jira_client import format_jira_error, get_jira, get_jira_site
from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
from zaira.config import get_reports_dir
from zaira.dashboard import get_dashboard, get_dashboard_gadgets
from zaira.types import ReportTicket, get_user_identifier
from zaira.util import humanize_age


def _group_tickets_by(
    tickets: list[ReportTicket], group_by: str
) -> dict[str, list[ReportTicket]]:
    """Group tickets by a field.

    Handles special cases for multi-value fields (labels, components) and parent.

    Args:
        tickets: List of ticket data
        group_by: Field name to group by

    Returns:
        Dict mapping group names to lists of tickets
    """
    groups: dict[str, list[ReportTicket]] = {}

    if group_by == "labels":
        for t in tickets:
            ticket_labels = t.get("labels", []) or ["(no label)"]
            for lbl in ticket_labels:
                groups.setdefault(lbl, []).append(t)
    elif group_by == "components":
        for t in tickets:
            ticket_components = t.get("components", []) or ["(no component)"]
            for comp in ticket_components:
                groups.setdefault(comp, []).append(t)
    elif group_by == "parent":
        for t in tickets:
            parent = t.get("parent")
            group_key = (
                f"{parent['key']}: {parent['summary']}" if parent else "(no parent)"
            )
            groups.setdefault(group_key, []).append(t)
    else:
        for t in tickets:
            key = t.get(group_by, "Unknown")
            groups.setdefault(key, []).append(t)

    return groups


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
        print(f"Error searching: {format_jira_error(e)}")
        return []


def generate_front_matter(
    title: str,
    jql: str | None = None,
    query: str | None = None,
    board: int | None = None,
    sprint: int | None = None,
    group_by: str | None = None,
    label: str | None = None,
    links: bool = False,
    report_name: str | None = None,
) -> str:
    """Generate YAML front matter with refresh info."""
    lines = ["---"]
    lines.append(f"title: {title}")
    lines.append(f"generated: {datetime.now().isoformat(timespec='seconds')}")

    if report_name:
        # Named report — zproject.toml has all the details
        lines.append(f"report: {report_name}")
        lines.append(f"refresh: zaira report {report_name}")
        lines.append("---")
        return "\n".join(lines) + "\n\n"

    # Ad-hoc report — store source fields and build refresh command
    if query:
        lines.append(f"query: {query}")
    elif jql and not board and not sprint:
        lines.append(f'jql: "{jql}"')
    if board:
        lines.append(f"board: {board}")
    if sprint:
        lines.append(f"sprint: {sprint}")
    if label:
        lines.append(f"label: {label}")
    if group_by:
        lines.append(f"group_by: {group_by}")

    cmd_parts = ["zaira report"]
    if query:
        cmd_parts.append(f"--query {query}")
    elif jql and not board and not sprint:
        cmd_parts.append(f"--jql {shlex.quote(jql)}")
    if board:
        cmd_parts.append(f"--board {board}")
    if sprint:
        cmd_parts.append(f"--sprint {sprint}")
    if label:
        cmd_parts.append(f"--label {shlex.quote(label)}")
    if group_by:
        cmd_parts.append(f"--group-by {group_by}")
    if links:
        cmd_parts.append("--links")
    cmd_parts.append(f"--title {shlex.quote(title)}")

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
    links: bool = False,
    report_name: str | None = None,
) -> str:
    """Generate markdown report from tickets."""
    md = generate_front_matter(
        title,
        jql,
        query,
        board,
        sprint,
        group_by,
        label,
        links=links,
        report_name=report_name,
    )
    md += f"# {title}\n\n"
    md += f"**Total:** {len(tickets)} tickets\n\n"

    if not tickets:
        md += "_No tickets found._\n"
        return md

    if group_by:
        groups = _group_tickets_by(tickets, group_by)
        for group_name, group_tickets in sorted(groups.items()):
            md += f"## {group_name} ({len(group_tickets)})\n\n"
            md += generate_table(group_tickets, group_by=group_by, links=links)
            md += "\n"
    else:
        md += generate_table(tickets, links=links)

    return md


def generate_table(
    tickets: list[ReportTicket],
    group_by: str | None = None,
    links: bool = False,
) -> str:
    """Generate markdown table from tickets.

    Args:
        tickets: List of ticket data
        group_by: Field used for grouping (will be excluded from table)
        links: Whether to render ticket keys as markdown links
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

    # Resolve Jira site for links
    if links:
        jira_site = get_jira_site()

    # Build all rows first to calculate column widths
    rows: list[list[str]] = []
    for t in tickets:
        raw_key = t.get("key", "?")
        if links:
            key = f"[{raw_key}](https://{jira_site}/browse/{raw_key})"
        else:
            key = raw_key
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
            if parent:
                pkey = parent["key"]
                row.append(
                    f"[{pkey}](https://{jira_site}/browse/{pkey})" if links else pkey
                )
            else:
                row.append("-")
        row.append(summary)

        # Remove grouped column value
        if group_by == "status":
            row.pop(2)  # status is at index 2
        elif group_by == "issuetype":
            row.pop(1)  # type is at index 1

        rows.append(row)

    # Calculate column widths (min 3 for separator)
    # Cap Status column at 12 chars - longer values will overflow
    max_widths = {"Status": 12}
    col_widths = [max(3, len(h)) for h in columns]
    for row in rows:
        for i, cell in enumerate(row):
            cap = max_widths.get(columns[i], 999)
            col_widths[i] = min(cap, max(col_widths[i], len(cell)))

    # Generate header
    header_cells = [h.ljust(col_widths[i]) for i, h in enumerate(columns)]
    md = "| " + " | ".join(header_cells) + " |\n"

    # Generate separator
    sep_cells = ["-" * col_widths[i] for i in range(len(columns))]
    md += "| " + " | ".join(sep_cells) + " |\n"

    # Generate rows
    for row in rows:
        padded = [cell.ljust(col_widths[i]) for i, cell in enumerate(row)]
        md += "| " + " | ".join(padded) + " |\n"

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


def _format_gadget_section(
    title: str,
    jql: str,
    tickets: list[ReportTicket],
    group_by: str | None,
    links: bool,
) -> list[str]:
    """Format a single dashboard gadget as markdown lines."""
    lines = []
    lines.append(f"## {title}")
    lines.append("")
    lines.append(f"**JQL:** `{jql}`")
    lines.append("")
    lines.append(f"**Results:** {len(tickets)} tickets")
    lines.append("")

    if tickets:
        if group_by:
            groups = _group_tickets_by(tickets, group_by)
            for group_name, group_tickets in sorted(groups.items()):
                lines.append(f"### {group_name} ({len(group_tickets)})")
                lines.append("")
                lines.append(
                    generate_table(group_tickets, group_by=group_by, links=links)
                )
        else:
            lines.append(generate_table(tickets, links=links))
    else:
        lines.append("_No tickets found._")

    lines.append("")
    return lines


def generate_dashboard_report(
    dashboard_id: int,
    group_by: str | None = None,
    to_stdout: bool = False,
    links: bool = False,
    parallel: bool = False,
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
    sorted_gadgets = sorted(jql_gadgets, key=lambda x: x.position)

    if parallel:
        # Fetch all gadget results in parallel
        gadget_results: dict[int, list[ReportTicket]] = {}
        with ThreadPoolExecutor() as pool:
            futures = {
                pool.submit(search_tickets, g.jql or ""): g for g in sorted_gadgets
            }
            for future in as_completed(futures):
                g = futures[future]
                tickets = future.result()
                gadget_results[g.id] = tickets
                if not to_stdout:
                    title = g.filter_name or g.title or f"Query {g.id}"
                    print(f"  {title}: {len(tickets)} tickets")

        for gadget in sorted_gadgets:
            tickets = gadget_results[gadget.id]
            title = gadget.filter_name or gadget.title or f"Query {gadget.id}"
            total_tickets += len(tickets)
            lines += _format_gadget_section(
                title, gadget.jql or "", tickets, group_by, links
            )
    else:
        for gadget in sorted_gadgets:
            title = gadget.filter_name or gadget.title or f"Query {gadget.id}"
            if not to_stdout:
                print(f"  Running: {title}")

            tickets = search_tickets(gadget.jql or "")
            total_tickets += len(tickets)

            if not to_stdout:
                print(f"    Found {len(tickets)} tickets")

            lines += _format_gadget_section(
                title, gadget.jql or "", tickets, group_by, links
            )

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
    has_args = (
        report_name
        or args.query
        or args.jql
        or args.board
        or args.sprint
        or dashboard_arg
    )

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
            if "output" in config:
                desc_parts.append(f"output={config['output']}")

            desc = ", ".join(desc_parts) if desc_parts else "(no config)"
            print(f"  {name}")
            print(f"    {desc}")
        print("\nRun: zaira report <name>")
        sys.exit(0)

    # Default to stdout if no zproject.toml, otherwise files
    has_project = Path("zproject.toml").exists()
    force_files = getattr(args, "files", False)
    if args.output == "-":
        to_stdout = True
    elif args.output or force_files:
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
        if not getattr(args, "links", False) and report_def.get("links"):
            args.links = True
        if not args.output and "output" in report_def:
            from zaira.config import find_project_root

            root = find_project_root() or Path.cwd()
            args.output = str(root / report_def["output"])
        if "tickets_dir" in report_def:
            args.tickets_dir = report_def["tickets_dir"]

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
            links=getattr(args, "links", False),
            parallel=getattr(args, "parallel", False),
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
                filename = (
                    f"{report_name}.md"
                    if report_name
                    else f"dashboard-{dashboard_id}.md"
                )
                output_path = get_reports_dir() / filename

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report, encoding="utf-8")
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
            links=getattr(args, "links", False),
            report_name=report_name,
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
            output_path = get_reports_dir() / f"{slug}.{ext}"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Saved to {output_path}")

    # Full mode: also export tickets
    if getattr(args, "full", False):
        from zaira.export import export_ticket
        from zaira.config import get_tickets_dir
        from zaira.refresh import find_ticket_file, ticket_needs_export

        override = getattr(args, "tickets_dir", None)
        if override:
            from zaira.config import find_project_root

            root = find_project_root() or Path.cwd()
            tickets_dir = root / override
        else:
            tickets_dir = get_tickets_dir()

        print("\nExporting tickets...")
        exported = 0
        skipped = 0
        force = getattr(args, "force", False)
        use_parallel = getattr(args, "parallel", False)

        # Build list of keys that need exporting
        to_export: list[str] = []
        for t in tickets:
            key = t.get("key")
            if not key:
                continue
            updated = t.get("updated", "")
            ticket_file = find_ticket_file(key, tickets_dir)

            if ticket_file:
                if force:
                    to_export.append(key)
                elif ticket_needs_export(ticket_file, updated):
                    to_export.append(key)
                else:
                    skipped += 1
            else:
                to_export.append(key)

        if use_parallel and to_export:
            from zaira.info import ensure_fields_cached

            ensure_fields_cached()
            with ThreadPoolExecutor() as pool:
                futures = {
                    pool.submit(export_ticket, key, tickets_dir): key
                    for key in to_export
                }
                for future in as_completed(futures):
                    key = futures[future]
                    if future.result():
                        exported += 1
        else:
            for key in to_export:
                if export_ticket(key, tickets_dir):
                    exported += 1

        print(f"Exported {exported} tickets, {skipped} unchanged")
