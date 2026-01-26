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
from zaira.export import export_command
from zaira.link import link_command
from zaira.transition import transition_command
from zaira.wiki import wiki_command, get_command as wiki_get_command, search_command as wiki_search_command, create_command as wiki_create_command, put_command as wiki_put_command, attach_command as wiki_attach_command, sync_command as wiki_sync_command
from zaira.info import (
    info_command,
    link_types_command,
    statuses_command,
    priorities_command,
    issue_types_command,
    fields_command,
    components_command,
    labels_command,
)
from zaira.init import init_command
from zaira.my import my_command
from zaira.report import report_command
from zaira.refresh import refresh_command


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

    # Export command
    export_parser = subparsers.add_parser(
        "export",
        help="Export Jira tickets to markdown",
    )
    export_parser.add_argument(
        "tickets",
        nargs="*",
        help="Ticket keys (e.g., PROJ-123)",
    )
    export_parser.add_argument(
        "--jql",
        help="JQL query to find tickets",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        help="Output directory (default: tickets/)",
    )
    export_parser.add_argument(
        "--board",
        type=int,
        help="Export tickets from board ID",
    )
    export_parser.add_argument(
        "--sprint",
        type=int,
        help="Export tickets from sprint ID",
    )
    export_parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output format (default: md)",
    )
    export_parser.add_argument(
        "--with-prs",
        action="store_true",
        help="Include linked GitHub pull requests (extra API call per ticket)",
    )
    export_parser.add_argument(
        "-a",
        "--all-fields",
        action="store_true",
        help="Include custom fields (uses cached schema for name lookup)",
    )
    export_parser.add_argument(
        "-f",
        "--files",
        action="store_true",
        help="Force file output to tickets/ (even without zproject.toml)",
    )
    export_parser.set_defaults(func=export_command)

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
        choices=["status", "priority", "issuetype", "assignee", "labels", "components", "parent"],
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

    # Init command
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize project configuration",
    )
    init_parser.add_argument(
        "projects",
        nargs="*",
        help="Project keys (e.g., FOO BAR)",
    )
    init_parser.add_argument(
        "-s",
        "--site",
        help="Jira site (e.g., company.atlassian.net)",
    )
    init_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing project.toml",
    )
    init_parser.set_defaults(func=init_command)

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
    transition_parser.set_defaults(func=transition_command)

    # Info command with subcommands
    info_parser = subparsers.add_parser(
        "info",
        help="Query Jira instance metadata",
    )
    info_parser.add_argument(
        "-s",
        "--save",
        action="store_true",
        help="Refresh cached instance schema",
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

    info_priorities = info_subparsers.add_parser("priorities", help="List priorities")
    info_priorities.add_argument("-r", "--refresh", **refresh_args)
    info_priorities.set_defaults(info_func=priorities_command)

    info_issue_types = info_subparsers.add_parser("issue-types", help="List issue types")
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

    info_components = info_subparsers.add_parser(
        "components", help="List components for a project"
    )
    info_components.add_argument("project", help="Project key (e.g., PROJ)")
    info_components.set_defaults(info_func=components_command)

    info_labels = info_subparsers.add_parser(
        "labels", help="List labels for a project"
    )
    info_labels.add_argument("project", help="Project key (e.g., PROJ)")
    info_labels.set_defaults(info_func=labels_command)

    # Wiki (Confluence) command with subcommands
    wiki_parser = subparsers.add_parser(
        "wiki",
        help="Confluence wiki commands",
    )
    wiki_parser.set_defaults(func=wiki_command)
    wiki_subparsers = wiki_parser.add_subparsers(dest="wiki_command")

    wiki_get = wiki_subparsers.add_parser(
        "get",
        help="Get a Confluence page by ID or URL",
    )
    wiki_get.add_argument(
        "page",
        help="Page ID or Confluence URL",
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
        "-s", "--space",
        required=True,
        help="Space key (e.g., PROJ, ~username)",
    )
    wiki_create.add_argument(
        "-t", "--title",
        required=True,
        help="Page title",
    )
    wiki_create.add_argument(
        "-b", "--body",
        required=True,
        help="Page body in Confluence storage format (use '-' to read from stdin)",
    )
    wiki_create.add_argument(
        "-p", "--parent",
        help="Parent page ID or URL (optional)",
    )
    wiki_create.add_argument(
        "-m", "--markdown",
        action="store_true",
        help="Convert body from Markdown to Confluence storage format",
    )
    wiki_create.set_defaults(wiki_func=wiki_create_command)

    wiki_put = wiki_subparsers.add_parser(
        "put",
        help="Update a Confluence page",
    )
    wiki_put.add_argument(
        "page",
        help="Page ID or Confluence URL",
    )
    wiki_put.add_argument(
        "-b", "--body",
        required=True,
        help="Page body in Confluence storage format (use '-' to read from stdin)",
    )
    wiki_put.add_argument(
        "-t", "--title",
        help="New page title (optional, keeps existing if not specified)",
    )
    wiki_put.add_argument(
        "-m", "--markdown",
        action="store_true",
        help="Convert body from Markdown to Confluence storage format",
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
        "-r", "--replace",
        action="store_true",
        help="Replace existing attachments with same filename",
    )
    wiki_attach.set_defaults(wiki_func=wiki_attach_command)

    wiki_sync = wiki_subparsers.add_parser(
        "sync",
        help="Sync markdown files with Confluence pages",
    )
    wiki_sync.add_argument(
        "files",
        nargs="+",
        help="Markdown files to sync (glob patterns supported, or directory)",
    )
    wiki_sync.add_argument(
        "--push",
        action="store_true",
        help="Push local changes to Confluence",
    )
    wiki_sync.add_argument(
        "--pull",
        action="store_true",
        help="Pull remote changes to local file",
    )
    wiki_sync.add_argument(
        "--status",
        action="store_true",
        help="Show sync status without making changes",
    )
    wiki_sync.add_argument(
        "--force",
        action="store_true",
        help="Force push even if remote has changed (overwrite conflicts)",
    )
    wiki_sync.set_defaults(wiki_func=wiki_sync_command)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
