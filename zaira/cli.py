"""Zaira CLI - Main entry point."""

import argparse
import io
import sys
from pathlib import Path
from typing import Any

from zaira import __version__
from zaira.attach import attach_command
from zaira.boards import boards_command
from zaira.changelog import changelog_command
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
    get_attachment_command as wiki_get_attachment_command,
    edit_command as wiki_edit_command,
    delete_command as wiki_delete_command,
    ls_command as wiki_ls_command,
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
from zaira.goals import (
    goals_command,
    export_command as goals_export_command,
    get_command as goals_get_command,
    updates_command as goals_updates_command,
)
from zaira.init import init_command, init_project_command
from zaira.my import my_command
from zaira.report import report_command
from zaira.refresh import refresh_command
from zaira.search import search_command
from zaira.get import get_command
from zaira.put import put_command
from zaira.bundle import bundle_install_command, bundle_update_command
from zaira.skills import install_skills_command
from zaira.rules import check_command
from zaira.activity_log import read_entries, format_entries


class _SingleValueAction(argparse.Action):
    """Argparse action that errors if the flag is given more than once."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest) is not None:
            parser.error(f"{option_string} can only be specified once")
        setattr(namespace, self.dest, values)


def _migrate_legacy_dirs() -> None:
    """Migrate from old double-nested Windows paths (zaira\\zaira) to new single-level paths.

    TODO: Remove this migration after a few months (added 2026-02).
    """
    if sys.platform != "win32":
        return
    from platformdirs import user_config_dir
    from zaira.jira_client import CONFIG_DIR

    old = Path(user_config_dir("zaira"))  # AppData\Local\zaira\zaira
    if not old.exists():
        return
    for item in old.iterdir():
        dest = CONFIG_DIR / item.name
        if not dest.exists():
            item.rename(dest)
    try:
        old.rmdir()
    except OSError:
        pass  # Directory not empty if some items were skipped
    print(f"Migrated zaira data from {old} to {CONFIG_DIR}", file=sys.stderr)


def main() -> None:
    # Force UTF-8 stdout on Windows to avoid encode/decode errors
    # when Jira content contains characters outside cp1252
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        if hasattr(sys.stdout, "reconfigure"):
            stdout = sys.stdout
            assert isinstance(stdout, io.TextIOWrapper)
            stdout.reconfigure(encoding="utf-8")

    _migrate_legacy_dirs()

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
        "--links",
        action="store_true",
        help="Make ticket keys clickable markdown links",
    )
    report_parser.add_argument(
        "--files",
        action="store_true",
        help="Force file output to reports/ (even without zproject.toml)",
    )
    report_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Fetch tickets in parallel threads (for --full and --dashboard)",
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
    init_parser.add_argument(
        "--set-token",
        action="store_true",
        help="Re-prompt for the API token even if one is already stored in the keyring",
    )
    init_parser.add_argument(
        "--migrate-token",
        action="store_true",
        help="Move the api_token from credentials.toml into the OS keyring (no prompt)",
    )
    init_parser.add_argument(
        "--install-wincred",
        action="store_true",
        help="Download wincred.exe to %%USERPROFILE%%\\.local\\bin so zaira can use the Windows Credential Manager from WSL",
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
    search_parser.add_argument(
        "-f",
        "--fields",
        help="Extra columns to display (comma-separated). E.g. 'fixVersions,assignee,priority'",
    )
    search_parser.add_argument(
        "--format",
        choices=["default", "json", "toon"],
        default="default",
        help="Output format (default: tabular)",
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
        "--with-props",
        action="store_true",
        help="Include issue properties (e.g. ducket grids)",
    )
    get_parser.add_argument(
        "-a",
        "--all-fields",
        action="store_true",
        help="Include custom fields",
    )
    get_parser.add_argument(
        "--field",
        help="Use named field as body instead of description (adds field: to front matter)",
    )
    get_parser.add_argument(
        "--min",
        action="store_true",
        help="Minimal output: key + summary front matter, description as body (symmetric with minimal put)",
    )
    get_parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip wiki-to-markdown conversion (preserve Jira wiki markup)",
    )
    get_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Export tickets and download attachments in parallel threads",
    )
    get_parser.set_defaults(func=get_command)

    # Put command
    put_parser = subparsers.add_parser(
        "put",
        help="Push summary + description from markdown back to Jira",
    )
    put_parser.add_argument(
        "file",
        help="Path to ticket markdown file (use '-' for stdin)",
    )
    put_parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show what would change without pushing",
    )
    put_parser.add_argument(
        "--field",
        help="Override target field for body (default: from front matter 'field:' or description)",
    )
    put_parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip markdown-to-wiki conversion (input is already Jira wiki)",
    )
    put_parser.add_argument(
        "--force",
        action="store_true",
        help="Push even if no changes detected",
    )
    put_parser.set_defaults(func=put_command)

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
        "-m",
        "--missing",
        action="store_true",
        help="Show workdays with missing hours",
    )
    hours_parser.add_argument(
        "--fill",
        metavar="TICKET",
        help="Fill missing hours on TICKET (preview; add --yes to confirm)",
    )
    hours_parser.add_argument(
        "-y",
        "--yes",
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
    edit_parser.add_argument(
        "--no-check",
        action="store_true",
        help="Skip allowed_fields.txt validation",
    )
    edit_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating",
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
    transition_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview transition without executing",
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
    refresh_args: dict[str, Any] = {
        "action": "store_true",
        "help": "Fetch live from Jira API",
    }

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
        help="Show all fields (ignore custom-only and allowed_fields filters)",
    )
    info_fields.set_defaults(info_func=fields_command)

    info_field = info_subparsers.add_parser(
        "field", help="Look up editmeta for a field"
    )
    info_field.add_argument(
        "names",
        nargs="+",
        help="Field name(s) or ID(s) to look up",
    )
    info_field.add_argument(
        "-p",
        "--project",
        metavar="PROJECT",
        action=_SingleValueAction,
        help="Filter to a specific project (shows project-scoped allowed values)",
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
        "--cql",
        help="Raw CQL query (bypasses other filters)",
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
        choices=["default", "url", "id", "json", "toon"],
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
        "-p",
        "--parent",
        help="Parent page ID or URL (optional)",
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
    wiki_put.add_argument(
        "--space",
        help="Space key for new pages (can also be set via space: in front matter)",
    )
    wiki_put.add_argument(
        "--mirror",
        action="store_true",
        help="Mirror directory structure to Confluence folders (implies --create)",
    )
    wiki_put.add_argument(
        "--prefix",
        help="Prefix for folder and page names (e.g., 'Demo - ' for uniqueness in space)",
    )
    wiki_put.add_argument(
        "--render",
        help="Render diagram blocks to PNG and attach (comma-separated: mermaid,dot,plantuml,d2,ditaa)",
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

    wiki_get_att = wiki_subparsers.add_parser(
        "get-attachment",
        help="Download attachments from a Confluence page by filename pattern",
    )
    wiki_get_att.add_argument(
        "page",
        help="Page ID or Confluence URL",
    )
    wiki_get_att.add_argument(
        "pattern",
        help="Filename pattern (e.g., '*.pdf', 'report*')",
    )
    wiki_get_att.add_argument(
        "-o",
        "--output",
        help="Output directory (default: current directory)",
    )
    wiki_get_att.set_defaults(wiki_func=wiki_get_attachment_command)

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

    wiki_ls = wiki_subparsers.add_parser(
        "ls",
        help="List pages in a Confluence space",
    )
    wiki_ls.add_argument(
        "space",
        help="Space key or Confluence space URL (e.g. 'ENG' or full URL)",
    )
    wiki_ls.add_argument(
        "-d",
        "--depth",
        type=int,
        default=1,
        help="Tree depth (-1 for unlimited, 0 for root only, default: 1)",
    )
    wiki_ls.set_defaults(wiki_func=wiki_ls_command)

    # Changelog command (Jira issue history)
    changelog_parser = subparsers.add_parser(
        "changelog",
        help="Show Jira changelog for a ticket (who changed what, when)",
    )
    changelog_parser.add_argument("key", help="Ticket key (e.g., PROJ-123)")
    changelog_parser.add_argument(
        "-n",
        "--tail",
        type=int,
        metavar="N",
        help="Show only the N most recent changes",
    )
    changelog_parser.add_argument(
        "--full",
        action="store_true",
        help="Show full old/new values instead of diffs for long text fields",
    )
    changelog_parser.add_argument(
        "-f",
        "--field",
        metavar="FIELD",
        help="Filter to changes on a specific field (e.g., status, description)",
    )
    changelog_parser.add_argument(
        "--revisions",
        action="store_true",
        help="List numbered revisions for a field (requires --field)",
    )
    changelog_parser.add_argument(
        "--rev",
        type=int,
        metavar="N",
        help="Print revision N of a field to stdout (requires --field)",
    )
    changelog_parser.set_defaults(func=changelog_command)

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

    reset_parser = subparsers.add_parser(
        "reset",
        help="Clear all cached data (editmeta, schema, field descriptions)",
    )
    reset_parser.add_argument(
        "--rules",
        action="store_true",
        help="Disable installed rules bundle (renames rules/ to rules-disabled/)",
    )

    def _reset_command(args: argparse.Namespace) -> None:
        from zaira.jira_client import CACHE_DIR, CONFIG_DIR

        # Handle --rules flag to disable bundle
        if getattr(args, "rules", False):
            rules_dir = CONFIG_DIR / "rules"
            rules_disabled = CONFIG_DIR / "rules-disabled"

            if not rules_dir.exists():
                print(f"No rules directory found at {rules_dir}")
                return

            # Remove existing rules-disabled if present
            if rules_disabled.exists():
                __import__("shutil").rmtree(rules_disabled)
                print(f"Removed existing {rules_disabled}")

            # Rename rules to rules-disabled
            rules_dir.rename(rules_disabled)
            print("Rules disabled (renamed to rules-disabled)")
            print(f"\nRules location: {rules_disabled}")
            print(f"To restore: mv {rules_disabled} {rules_dir}")
            return

        # Normal cache clearing
        cleared = 0
        for f in CACHE_DIR.iterdir():
            if f.name == "activity.log":
                continue
            f.unlink() if f.is_file() else __import__("shutil").rmtree(f)
            print(f"Removed {f.name}")
            cleared += 1
        print(f"Cache cleared ({cleared} files removed).")

    reset_parser.set_defaults(func=_reset_command)

    # Bundle command with subcommands
    def bundle_command(args: argparse.Namespace) -> None:
        if hasattr(args, "bundle_func"):
            args.bundle_func(args)
        else:
            print("Usage: zaira bundle <install|update>")
            sys.exit(1)

    bundle_parser = subparsers.add_parser(
        "bundle", help="Install and update rule bundles"
    )
    bundle_parser.set_defaults(func=bundle_command)
    bundle_subparsers = bundle_parser.add_subparsers(dest="bundle_command")

    bundle_install_p = bundle_subparsers.add_parser(
        "install", help="Install a bundle from a URL or local zip"
    )
    bundle_install_p.add_argument("source", help="URL or local path to a .zip bundle")
    bundle_install_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be installed without making changes",
    )
    bundle_install_p.set_defaults(bundle_func=bundle_install_command)

    bundle_update_p = bundle_subparsers.add_parser(
        "update", help="Re-fetch bundle from recorded source URL"
    )
    bundle_update_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    bundle_update_p.set_defaults(bundle_func=bundle_update_command)

    goals_parser = subparsers.add_parser(
        "goals", help="Atlassian Goals (Townsquare) export and lookup"
    )
    goals_parser.set_defaults(func=goals_command)
    goals_subparsers = goals_parser.add_subparsers(dest="goals_command")

    goals_export_p = goals_subparsers.add_parser(
        "export", help="Export goals matching a TQL query"
    )
    goals_export_p.add_argument(
        "--url",
        help="home.atlassian.com goals URL (cloudId & tql parsed from query string)",
    )
    goals_export_p.add_argument("--cloud-id", help="Atlassian cloud/site ID")
    goals_export_p.add_argument(
        "--tql",
        default=None,
        help='TQL filter (default: "archived = false")',
    )
    goals_export_p.add_argument(
        "--full", action="store_true", help="Include all fields (slower, larger)"
    )
    goals_export_p.add_argument(
        "--with-updates",
        action="store_true",
        help="Include each goal's check-in update history in the export",
    )
    goals_export_p.add_argument(
        "--format",
        choices=["json", "md", "table"],
        default=None,
        help="Output format (table = one row per goal in markdown)",
    )
    goals_export_p.add_argument(
        "-o", "--output", help="Write to file instead of stdout"
    )
    goals_export_p.set_defaults(goals_func=goals_export_command)

    goals_get_p = goals_subparsers.add_parser(
        "get", help="Fetch a single goal by key or ARI"
    )
    goals_get_p.add_argument(
        "keys", nargs="+", help="One or more goal keys (e.g. TEAM-42) or ARIs"
    )
    goals_get_p.add_argument(
        "--cloud-id",
        default=None,
        help="Cloud/site ID (auto-detected from your Jira site if omitted)",
    )
    goals_get_p.add_argument(
        "--minimal", action="store_true", help="Only fetch minimal fields"
    )
    goals_get_p.add_argument(
        "--format",
        choices=["json", "md", "table"],
        default=None,
        help="Output format (table = one row per goal in markdown)",
    )
    goals_get_p.add_argument("-o", "--output", help="Write to file instead of stdout")
    goals_get_p.set_defaults(goals_func=goals_get_command)

    goals_updates_p = goals_subparsers.add_parser(
        "updates", help="Show check-in update history for a goal"
    )
    goals_updates_p.add_argument("key", help="Goal key (e.g. TEAM-42) or ARI")
    goals_updates_p.add_argument(
        "--cloud-id",
        default=None,
        help="Cloud/site ID (auto-detected from your Jira site if omitted)",
    )
    goals_updates_p.add_argument(
        "--limit", type=int, default=50, help="Max updates to fetch (default 50)"
    )
    goals_updates_p.add_argument(
        "--format", choices=["md", "json"], default=None, help="Output format"
    )
    goals_updates_p.add_argument(
        "-o", "--output", help="Write to file instead of stdout"
    )
    goals_updates_p.set_defaults(goals_func=goals_updates_command)

    install_skills_parser = subparsers.add_parser(
        "install-skills",
        help="Install Claude Code skills to ~/.claude/skills/",
    )
    install_skills_parser.add_argument(
        "--skills-dir",
        default=None,
        help="Target directory for skills (default: ~/.claude/skills/)",
    )
    install_skills_parser.set_defaults(func=install_skills_command)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    from zaira.wincred import WincredNotInstalled

    try:
        args.func(args)
    except WincredNotInstalled as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
