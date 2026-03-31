"""Get Jira tickets."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
from zaira.export import (
    PendingAttachment,
    export_ticket,
    export_to_stdout,
    search_tickets,
)


def get_command(args: argparse.Namespace) -> None:
    """Handle get subcommand."""
    fmt = getattr(args, "format", "md")
    include_custom = getattr(args, "all_fields", False)
    with_prs = getattr(args, "with_prs", False)
    with_tests = getattr(args, "with_tests", False)
    with_props = getattr(args, "with_props", False)
    minimal = getattr(args, "min", False)
    raw = getattr(args, "raw", False)
    output = getattr(args, "output", None)
    parallel = getattr(args, "parallel", False)
    if not output:
        from zaira.project import load_config

        if load_config().get("tickets_dir"):
            from zaira.config import get_tickets_dir

            output = str(get_tickets_dir())
    to_stdout = not output

    keys = list(args.keys or [])

    # Build JQL from options
    jql = getattr(args, "jql", None)
    if getattr(args, "board", None):
        jql = get_board_issues_jql(args.board)
        if not to_stdout:
            print(f"Using board {args.board}")
    elif getattr(args, "sprint", None):
        jql = get_sprint_issues_jql(args.sprint)
        if not to_stdout:
            print(f"Using sprint {args.sprint}")

    if jql:
        if not to_stdout:
            print(f"Searching: {jql}")
        found = search_tickets(jql)
        if not to_stdout:
            print(f"Found {len(found)} tickets")
        keys.extend(found)

    if not keys:
        print("No tickets specified. Use ticket keys, --jql, --board, or --sprint.")
        sys.exit(1)

    if to_stdout:
        for key in keys:
            export_to_stdout(
                key,
                fmt=fmt,
                with_prs=with_prs,
                with_tests=with_tests,
                with_props=with_props,
                include_custom=include_custom,
                minimal=minimal,
                raw=raw,
            )
    else:
        assert output is not None
        output_dir = Path(output)
        all_pending: list[PendingAttachment] = []

        export_kwargs = dict(
            fmt=fmt,
            with_prs=with_prs,
            with_tests=with_tests,
            include_custom=include_custom,
            with_attachments=True,
            defer_attachments=True,
        )

        if parallel:
            from zaira.info import ensure_fields_cached

            ensure_fields_cached()
            success = 0
            with ThreadPoolExecutor() as pool:
                futures = {
                    pool.submit(export_ticket, key, output_dir, **export_kwargs): key
                    for key in keys
                }
                for future in as_completed(futures):
                    result = future.result()
                    if result is not False:
                        success += 1
                        if isinstance(result, list):
                            all_pending.extend(result)
        else:
            success = 0
            for key in keys:
                result = export_ticket(key, output_dir, **export_kwargs)
                if result is not False:
                    success += 1
                    if isinstance(result, list):
                        all_pending.extend(result)

        if all_pending:
            print(f"\nDownloading {len(all_pending)} attachment(s)...")
            if parallel:
                with ThreadPoolExecutor() as pool:
                    list(pool.map(lambda p: p.download(), all_pending))
            else:
                for p in all_pending:
                    p.download()

        print(f"\nExported {success}/{len(keys)} tickets to {output_dir}/")
