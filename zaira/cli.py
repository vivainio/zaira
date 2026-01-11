"""Zaira CLI - Main entry point."""

import argparse
import sys

from zaira import __version__
from zaira.boards import boards_command
from zaira.comment import comment_command
from zaira.export import export_command
from zaira.link import link_command
from zaira.info import (
    info_command,
    link_types_command,
    statuses_command,
    priorities_command,
    issue_types_command,
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
        help="Ticket keys (e.g., AC-1409)",
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
        choices=["status", "priority", "issuetype", "assignee", "labels", "parent"],
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
    report_parser.set_defaults(func=report_command)

    # Boards command
    boards_parser = subparsers.add_parser(
        "boards",
        help="List Jira boards",
    )
    boards_parser.add_argument(
        "-p",
        "--project",
        help="Filter boards by project key (e.g., AC)",
    )
    boards_parser.set_defaults(func=boards_command)

    # Refresh command
    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Refresh a report from its front matter",
    )
    refresh_parser.add_argument(
        "report",
        help="Report file path or name (e.g., documenthub-new.md)",
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
        "-p",
        "--project",
        help="Project key (e.g., AC)",
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
    my_parser.set_defaults(func=my_command)

    # Comment command
    comment_parser = subparsers.add_parser(
        "comment",
        help="Add a comment to a ticket",
    )
    comment_parser.add_argument(
        "key",
        help="Ticket key (e.g., AC-1409)",
    )
    comment_parser.add_argument(
        "body",
        help="Comment text (use '-' to read from stdin)",
    )
    comment_parser.set_defaults(func=comment_command)

    # Link command
    link_parser = subparsers.add_parser(
        "link",
        help="Create a link between two tickets",
    )
    link_parser.add_argument(
        "from_key",
        help="Source ticket key (e.g., AC-1409)",
    )
    link_parser.add_argument(
        "to_key",
        help="Target ticket key (e.g., AC-1410)",
    )
    link_parser.add_argument(
        "-t",
        "--type",
        default="Relates",
        help="Link type (default: Relates). Use 'zaira info link-types' to list",
    )
    link_parser.set_defaults(func=link_command)

    # Info command with subcommands
    info_parser = subparsers.add_parser(
        "info",
        help="Query Jira instance metadata",
    )
    info_parser.set_defaults(func=info_command)
    info_subparsers = info_parser.add_subparsers(dest="info_command")

    info_link_types = info_subparsers.add_parser("link-types", help="List link types")
    info_link_types.set_defaults(info_func=link_types_command)

    info_statuses = info_subparsers.add_parser("statuses", help="List statuses")
    info_statuses.set_defaults(info_func=statuses_command)

    info_priorities = info_subparsers.add_parser("priorities", help="List priorities")
    info_priorities.set_defaults(info_func=priorities_command)

    info_issue_types = info_subparsers.add_parser("issue-types", help="List issue types")
    info_issue_types.set_defaults(info_func=issue_types_command)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
