"""Zaira CLI - Main entry point."""

import argparse
import sys

from zaira import __version__
from zaira.attach import attach_command
from zaira.boards import boards_command
from zaira.comment import comment_command
from zaira.create import create_command
from zaira.dashboard import dashboard_command, dashboards_command
from zaira.edit import edit_command
from zaira.export import get_attachment_command
from zaira.hours import hours_command
from zaira.link import link_command
from zaira.transition import transition_command
from zaira.worklog import log_command
from zaira.wiki import (
    wiki_command,
    get_command as wiki_get_command,
    search_command as wiki_search_command,
    create_command as wiki_create_command,
    put_command as wiki_put_command,
    attach_command as wiki_attach_command,
    edit_command as wiki_edit_command,
    delete_command as wiki_delete_command,
)
from zaira.info import (
    info_command,
    learn_command,
    link_types_command,
    statuses_command,
    issue_types_command,
    fields_command,
    field_command,
)
from zaira.init import init_command, init_project_command
from zaira.my import my_command
from zaira.report import report_command
from zaira.refresh import refresh_command
from zaira.search import search_command
from zaira.get import get_command
from zaira.rules import check_command
from zaira.activity_log import read_entries, format_entries


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="zaira",
        description="Jira CLI tool for offline ticket management",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Report command
    report_parser = subparsers.add_parser(
        "report",
        help="Generate markdown report from JQL query",
    )
    report_parser.add_argument(
        "name",
        nargs="?",
        help="Named report from project.toml",
    )
    report_parser.add_argument(
        "-q",
        "--query",
        help="Named query from project.toml",
    )
    report_parser.add_argument(
        "--jql",
        help="JQL query to find tickets",
    )
    report_parser.add_argument(
        "--board",
        help="Board ID or name from project.toml",
    )
    report_parser.add_argument(
        "--sprint",
        type=int,
        help="Generate report from sprint ID",
    )
    report_parser.add_argument(
        "--dashboard",
        help="Generate reports from dashboard ID (runs all JQL queries from gadgets)",
    )
    report_parser.add_argument(
        "-o",
        "--output",
        help="Output file path (default: reports/{title}.md)",
    )
    report_parser.add_argument(
        "-t",
        "--title",
        help="Report title (default: 'Jira Report')",
    )
    report_parser.add_argument(
        "-g",
        "--group-by",
        choices=[
            "status",
            "priority",
            "issuetype",
            "assignee",
            "labels",
            "components",
            "parent",
        ],
        help="Group tickets by field",
    )
    report_parser.add_argument(
        "-l",
        "--label",
        help="Filter tickets by label",
    )
    report_parser.add_argument(
        "-f",
        "--full",
        action="store_true",
        help="Also export tickets to tickets/",
    )
    report_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-export tickets even if unchanged (requires --full)",
    )
    report_parser.add_argument(
        "--format",
        choices=["md", "json", "csv"],
        default="md",
        help="Output format (default: md)",
    )
    report_parser.add_argument(
        "--files",
        action="store_true",
        help="Force file output to reports/ (even without zproject.toml)",
    )
    report_parser.set_defaults(func=report_command)

    # Boards command
    boards_parser = subparsers.add_parser(
        "boards",
        help="List Jira boards",
    )
    boards_parser.add_argument(
        "-p",
        "--project",
        help="Filter boards by project key (e.g., PROJ)",
    )
    boards_parser.set_defaults(func=boards_command)

    # Dashboards command
    dashboards_parser = subparsers.add_parser(
        "dashboards",
        help="List Jira dashboards",
    )
    dashboards_parser.add_argument(
        "-f",
        "--filter",
        help="Filter dashboards by name",
    )
    dashboards_parser.add_argument(
        "-m",
        "--mine",
        action="store_true",
        help="Show only my dashboards",
    )
    dashboards_parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=50,
        help="Maximum number of dashboards to return (default: 50)",
    )
    dashboards_parser.set_defaults(func=dashboards_command)

    # Dashboard command (single dashboard)
    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Show or export a specific dashboard",
    )
    dashboard_parser.add_argument(
        "id",
        help="Dashboard ID or URL (e.g., 16148 or https://company.atlassian.net/jira/dashboards/16148)",
    )
    dashboard_parser.add_argument(
        "-o",
        "--output",
        help="Output file path (default: stdout)",
    )
    dashboard_parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output format (default: md)",
    )
    dashboard_parser.set_defaults(func=dashboard_command)

    # Refresh command
    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Refresh a report from its front matter",
    )
    refresh_parser.add_argument(
        "report",
        help="Report file path or name (e.g., my-report.md)",
    )
    refresh_parser.add_argument(
        "-f",
        "--full",
        action="store_true",
        help="Also export tickets from the report",
    )
    refresh_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-export tickets even if they already exist",
    )
    refresh_parser.set_defaults(func=refresh_command)

    # Init command - credentials only
    init_parser = subparsers.add_parser(
        "init",
        help="Setup Jira credentials",
    )
    init_parser.set_defaults(func=init_command)

    # Init-project command - generate zproject.toml
    init_project_parser = subparsers.add_parser(
        "init-project",
        help="Generate zproject.toml with discovered boards, queries, reports",
    )
    init_project_parser.add_argument(
        "projects",
        nargs="*",
        help="Project keys (e.g., FOO BAR)",
    )
    init_project_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing zproject.toml",
    )
    init_project_parser.set_defaults(func=init_project_command)

    # My command
    my_parser = subparsers.add_parser(
        "my",
        help="Show my open tickets",
    )
    my_parser.add_argument(
        "-r",
        "--reported",
        action="store_true",
        help="Show tickets I reported (created) instead of assigned to me",
    )
    my_parser.set_defaults(func=my_command)

    # Search command
    search_parser = subparsers.add_parser(
        "search",
        help="Search Jira tickets",
    )
    search_parser.add_argument(
        "text",
        nargs="?",
        help="Text to search for",
    )
    search_parser.add_argument(
        "--jql",
        help="Raw JQL query",
    )
    search_parser.add_argument(
        "-p",
        "--project",
        help="Filter by project key",
    )
    search_parser.add_argument(
        "-s",
        "--status",
        help="Filter by status",
    )
    search_parser.add_argument(
        "-a",
        "--assignee",
        help="Filter by assignee",
    )
    search_parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=0,
        help="Maximum results (default: unlimited)",
    )
    search_parser.set_defaults(func=search_command)

    # Get command
    get_parser = subparsers.add_parser(
        "get",
        help="Get ticket(s) by key, JQL, board, or sprint",
    )
    get_parser.add_argument(
        "keys",
        nargs="*",
        help="Ticket key(s) (e.g., PROJ-123)",
    )
    get_parser.add_argument(
        "--jql",
        help="JQL query to find tickets",
    )
    get_parser.add_argument(
        "-o",
        "--output",
        help="Output directory (writes files instead of stdout)",
    )
    get_parser.add_argument(
        "--board",
        type=int,
        help="Get tickets from board ID",
    )
    get_parser.add_argument(
        "--sprint",
        type=int,
        help="Get tickets from sprint ID",
    )
    get_parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output format (default: md)",
    )
    get_parser.add_argument(
        "--with-prs",
        action="store_true",
        help="Include linked GitHub pull requests",
    )
    get_parser.add_argument(
        "--with-tests",
        action="store_true",
        help="Include linked Xray tests and test executions",
    )
    get_parser.add_argument(
        "-a",
        "--all-fields",
        action="store_true",
        help="Include custom fields",
    )
    get_parser.set_defaults(func=get_command)

    # Check command
    check_parser = subparsers.add_parser(
        "check",
        help="Validate tickets against rules.yaml",
    )
    check_parser.add_argument(
        "keys",
        nargs="+",
        help="Ticket key(s) to check (e.g., PROJ-123)",
    )
    check_parser.add_argument(
        "--rules",
        default="rules.yaml",
        help="Path to rules YAML file (default: rules.yaml)",
    )
    check_parser.set_defaults(func=check_command)

    # Comment command
    comment_parser = subparsers.add_parser(
        "comment",
        help="Add a comment to a ticket",
    )
    comment_parser.add_argument(
        "key",
        help="Ticket key (e.g., PROJ-123)",
    )
    comment_parser.add_argument(
        "body",
        help="Comment text (use '-' to read from stdin)",
    )
    comment_parser.set_defaults(func=comment_command)

    # Log (worklog) command
    log_parser = subparsers.add_parser(
        "log",
        help="Log work hours to a ticket",
    )
    log_parser.add_argument(
        "key",
        help="Ticket key (e.g., PROJ-123)",
    )
    log_parser.add_argument(
        "time",
        nargs="?",
        help="Time spent (e.g., 2h, 30m, 1d, '1h 30m')",
    )
    log_parser.add_argument(
        "-c",
        "--comment",
        help="Worklog comment",
    )
    log_parser.add_argument(
        "-d",
        "--date",
        help="Start date (YYYY-MM-DD, default: today)",
    )
    log_parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List existing worklogs",
    )
    log_parser.add_argument(
        "--spread",
        help="Spread hours across days: '5d' (last 5 workdays) or 'YYYY-MM-DD,YYYY-MM-DD' (date range)",
    )
    log_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (for --spread)",
    )
    log_parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="Include weekends when spreading hours",
    )
    log_parser.set_defaults(func=log_command)

    # Hours command
    hours_parser = subparsers.add_parser(
        "hours",
        help="Show logged hours across tickets",
    )
    hours_parser.add_argument(
        "tickets",
        nargs="*",
        help="Ticket keys to query (shows hours by person). Omit for personal timesheet.",
    )
    hours_parser.add_argument(
        "--from",
        dest="date_from",
        help="Start date (YYYY-MM-DD)",
    )
    hours_parser.add_argument(
        "--to",
        dest="date_to",
        help="End date (YYYY-MM-DD)",
    )
    hours_parser.add_argument(
        "-d",
        "--days",
        type=int,
        help="Number of days to look back (default: 7)",
    )
    hours_parser.add_argument(
        "-s",
        "--summary",
        action="store_true",
        help="Show only ticket totals (no daily breakdown)",
    )
    hours_parser.add_argument(
        "--format",
        choices=["default", "csv"],
        default="default",
        help="Output format (csv only for ticket mode)",
    )
    hours_parser.add_argument(
        "-m", "--missing",
        action="store_true",
        help="Show workdays with missing hours",
    )
    hours_parser.add_argument(
        "--fill",
        metavar="TICKET",
        help="Fill missing hours on TICKET (preview; add --yes to confirm)",
    )
    hours_parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Confirm filling missing hours (requires --fill)",
    )
    hours_parser.set_defaults(func=hours_command)

    # Attach command
    attach_parser = subparsers.add_parser(
        "attach",
        help="Upload attachments to a ticket",
    )
    attach_parser.add_argument(
        "key",
        help="Ticket key (e.g., PROJ-123)",
    )
    attach_parser.add_argument(
        "files",
        nargs="+",
        help="Files to upload",
    )
    attach_parser.set_defaults(func=attach_command)

    # Get-attachment command
    get_att_parser = subparsers.add_parser(
        "get-attachment",
        help="Download attachments by filename pattern",
    )
    get_att_parser.add_argument(
        "key",
        help="Ticket key (e.g., PROJ-123)",
    )
    get_att_parser.add_argument(
        "pattern",
        help="Filename pattern (e.g., '*.pdf', 'report*')",
    )
    get_att_parser.add_argument(
        "-o",
        "--output",
        help="Output directory (default: current directory)",
    )
    get_att_parser.set_defaults(func=get_attachment_command)

    # Edit command
    edit_parser = subparsers.add_parser(
        "edit",
        help="Edit a ticket's title and/or description",
    )
    edit_parser.add_argument(
        "key",
        help="Ticket key (e.g., PROJ-123)",
    )
    edit_parser.add_argument(
        "-t",
        "--title",
        help="New title/summary",
    )
    edit_parser.add_argument(
        "-d",
        "--description",
        help="New description (use '-' to read from stdin). Supports Jira wiki syntax.",
    )
    edit_parser.add_argument(
        "-F",
        "--field",
        action="append",
        metavar="NAME=VALUE",
        help="Set field value (repeatable). Custom fields looked up via schema.",
    )
    edit_parser.add_argument(
        "--from",
        dest="from_file",
        metavar="FILE",
        help="Read fields from YAML file (use '-' for stdin)",
    )
    edit_parser.set_defaults(func=edit_command)

    # Create command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a ticket from a YAML front matter file",
    )
    create_parser.add_argument(
        "file",
        help="Path to ticket file with YAML front matter (use '-' for stdin)",
    )
    create_parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show what would be created without actually creating",
    )
    create_parser.set_defaults(func=create_command)

    # Link command
    link_parser = subparsers.add_parser(
        "link",
        help="Create a link between two tickets",
    )
    link_parser.add_argument(
        "from_key",
        help="Source ticket key (e.g., PROJ-123)",
    )
    link_parser.add_argument(
        "to_key",
        help="Target ticket key (e.g., PROJ-456)",
    )
    link_parser.add_argument(
        "-t",
        "--type",
        default="Relates",
        help="Link type (default: Relates). Use 'zaira info link-types' to list",
    )
    link_parser.set_defaults(func=link_command)

    # Transition command
    transition_parser = subparsers.add_parser(
        "transition",
        help="Transition a ticket to a new status",
    )
    transition_parser.add_argument(
        "key",
        help="Ticket key (e.g., PROJ-123)",
    )
    transition_parser.add_argument(
        "status",
        nargs="?",
        help="Target status (e.g., 'In Progress', 'Done')",
    )
    transition_parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List available transitions",
    )
    transition_parser.add_argument(
        "-F",
        "--field",
        action="append",
        metavar="NAME=VALUE",
        help="Set field value during transition (repeatable). E.g., Resolution=Done",
    )
    transition_parser.add_argument(
        "-c",
        "--comment",
        metavar="TEXT",
        help="Comment to include with the transition",
    )
    transition_parser.add_argument(
        "--no-check",
        action="store_true",
        help="Skip rules.yaml validation before transitioning",
    )
    transition_parser.set_defaults(func=transition_command)

    # Learn command
    learn_parser = subparsers.add_parser(
        "learn",
        help="Learn editable fields from an issue's editmeta",
    )
    learn_parser.add_argument(
        "keys",
        nargs="+",
        help="Issue key(s) or YAML file(s) to learn from",
    )
    learn_parser.set_defaults(func=learn_command)

    # Info command with subcommands
    info_parser = subparsers.add_parser(
        "info",
        help="Query Jira instance metadata",
    )
    info_parser.set_defaults(func=info_command)
    info_subparsers = info_parser.add_subparsers(dest="info_command")

    # Common --refresh argument for all info subcommands
    refresh_args = {"action": "store_true", "help": "Fetch live from Jira API"}

    info_link_types = info_subparsers.add_parser("link-types", help="List link types")
    info_link_types.add_argument("-r", "--refresh", **refresh_args)
    info_link_types.set_defaults(info_func=link_types_command)

    info_statuses = info_subparsers.add_parser("statuses", help="List statuses")
    info_statuses.add_argument("-r", "--refresh", **refresh_args)
    info_statuses.set_defaults(info_func=statuses_command)

    info_issue_types = info_subparsers.add_parser(
        "issue-types", help="List issue types"
    )
    info_issue_types.add_argument("-r", "--refresh", **refresh_args)
    info_issue_types.set_defaults(info_func=issue_types_command)

    info_fields = info_subparsers.add_parser("fields", help="List custom fields")
    info_fields.add_argument("-r", "--refresh", **refresh_args)
    info_fields.add_argument(
        "-f",
        "--filter",
        help="Filter fields by name or ID",
    )
    info_fields.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show all fields, not just custom fields",
    )
    info_fields.set_defaults(info_func=fields_command)

    info_field = info_subparsers.add_parser("field", help="Look up editmeta for a field")
    info_field.add_argument(
        "names",
        nargs="+",
        help="Field name(s) or ID(s) to look up",
    )
    info_field.set_defaults(info_func=field_command)

    # Wiki (Confluence) command with subcommands
    wiki_parser = subparsers.add_parser(
        "wiki",
        help="Confluence wiki commands",
    )
    wiki_parser.set_defaults(func=wiki_command)
    wiki_subparsers = wiki_parser.add_subparsers(dest="wiki_command")

    wiki_get = wiki_subparsers.add_parser(
        "get",
        help="Get Confluence page(s) by ID or URL",
    )
    wiki_get.add_argument(
        "pages",
        nargs="*",
        help="Page ID(s) or Confluence URL(s)",
    )
    wiki_get.add_argument(
        "-o",
        "--output",
        help="Output directory (writes files instead of stdout)",
    )
    wiki_get.add_argument(
        "--children",
        action="store_true",
        help="Also export all child pages recursively",
    )
    wiki_get.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List page(s) and children without exporting",
    )
    wiki_get.add_argument(
        "--format",
        choices=["md", "html", "json"],
        default="md",
        help="Output format (default: md)",
    )
    wiki_get.set_defaults(wiki_func=wiki_get_command)

    wiki_search = wiki_subparsers.add_parser(
        "search",
        help="Search Confluence pages",
    )
    wiki_search.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search query text (optional if --creator specified)",
    )
    wiki_search.add_argument(
        "--space",
        help="Limit search to a specific space key",
    )
    wiki_search.add_argument(
        "--creator",
        help="Filter by page creator name",
    )
    wiki_search.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum results to return (default: 25)",
    )
    wiki_search.add_argument(
        "--format",
        choices=["default", "url", "id", "json"],
        default="default",
        help="Output format (default: title/space/url)",
    )
    wiki_search.set_defaults(wiki_func=wiki_search_command)

    wiki_create = wiki_subparsers.add_parser(
        "create",
        help="Create a new Confluence page",
    )
    wiki_create.add_argument(
        "-s",
        "--space",
        help="Space key (e.g., PROJ, ~username). Inferred from --parent if not specified.",
    )
    wiki_create.add_argument(
        "-t",
        "--title",
        required=True,
        help="Page title",
    )
    wiki_create.add_argument(
        "-b",
        "--body",
        required=True,
        help="Page body: file path, '-' for stdin, or literal content",
    )
    wiki_create.add_argument(
        "-p",
        "--parent",
        help="Parent page ID or URL (optional)",
    )
    wiki_create.add_argument(
        "-m",
        "--markdown",
        action="store_true",
        help="Convert body from Markdown to Confluence storage format",
    )
    wiki_create.set_defaults(wiki_func=wiki_create_command)

    wiki_put = wiki_subparsers.add_parser(
        "put",
        help="Update Confluence page(s) from markdown files",
    )
    wiki_put.add_argument(
        "files",
        nargs="*",
        help="Markdown files, glob patterns, or directories (page ID from front matter)",
    )
    wiki_put.add_argument(
        "-p",
        "--page",
        help="Page ID or URL (for single file without front matter)",
    )
    wiki_put.add_argument(
        "-b",
        "--body",
        help="Body content: '-' for stdin, or literal (legacy, prefer positional files)",
    )
    wiki_put.add_argument(
        "-t",
        "--title",
        help="New page title (single file only)",
    )
    wiki_put.add_argument(
        "-m",
        "--markdown",
        action="store_true",
        help="Treat input as Markdown (auto-enabled for .md files)",
    )
    wiki_put.add_argument(
        "--pull",
        action="store_true",
        help="Pull remote changes to local file(s) instead of pushing",
    )
    wiki_put.add_argument(
        "--force",
        action="store_true",
        help="Force push even if remote has changed (overwrite conflicts)",
    )
    wiki_put.add_argument(
        "--status",
        action="store_true",
        help="Show sync status without making changes",
    )
    wiki_put.add_argument(
        "--diff",
        action="store_true",
        help="Show diff between local and remote content",
    )
    wiki_put.add_argument(
        "--create",
        action="store_true",
        help="Create new pages for files without 'confluence:' front matter",
    )
    wiki_put.add_argument(
        "--parent",
        help="Parent page for new pages (auto-detected from siblings if not specified)",
    )
    wiki_put.set_defaults(wiki_func=wiki_put_command)

    wiki_attach = wiki_subparsers.add_parser(
        "attach",
        help="Upload attachments to a Confluence page",
    )
    wiki_attach.add_argument(
        "page",
        help="Page ID or Confluence URL",
    )
    wiki_attach.add_argument(
        "files",
        nargs="+",
        help="Files to upload (supports glob patterns)",
    )
    wiki_attach.add_argument(
        "-r",
        "--replace",
        action="store_true",
        help="Replace existing attachments with same filename",
    )
    wiki_attach.set_defaults(wiki_func=wiki_attach_command)

    wiki_edit = wiki_subparsers.add_parser(
        "edit",
        help="Edit Confluence page properties",
    )
    wiki_edit.add_argument(
        "page",
        help="Page ID or Confluence URL",
    )
    wiki_edit.add_argument(
        "-t",
        "--title",
        help="New page title",
    )
    wiki_edit.add_argument(
        "-p",
        "--parent",
        help="New parent page ID or URL (moves the page)",
    )
    wiki_edit.add_argument(
        "-l",
        "--labels",
        help="Labels (comma-separated, replaces existing)",
    )
    wiki_edit.add_argument(
        "-s",
        "--space",
        help="Move to different space",
    )
    wiki_edit.set_defaults(wiki_func=wiki_edit_command)

    wiki_delete = wiki_subparsers.add_parser(
        "delete",
        help="Delete a Confluence page",
    )
    wiki_delete.add_argument(
        "page",
        help="Page ID or Confluence URL",
    )
    wiki_delete.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    wiki_delete.set_defaults(wiki_func=wiki_delete_command)

    # History command
    history_parser = subparsers.add_parser(
        "history",
        help="Show recent write activity from the local log",
    )
    history_parser.add_argument(
        "-n",
        "--tail",
        type=int,
        default=20,
        metavar="N",
        help="Number of most recent entries to show (default: 20)",
    )
    history_parser.add_argument(
        "-k",
        "--key",
        metavar="TICKET",
        help="Filter by ticket key (e.g., AC-1234)",
    )

    def _history_command(args: argparse.Namespace) -> None:
        entries = read_entries(
            tail=args.tail,
            key_filter=getattr(args, "key", None),
        )
        print(format_entries(entries))

    history_parser.set_defaults(func=_history_command)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
