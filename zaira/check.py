"""Ticket validation via user-defined hooks (see zaira.hooks).

There is no declarative rules file anymore -- all validation comes from
CHECK hooks registered with zaira.hooks. This module is just the thin
`zaira check` CLI surface plus two convenience wrappers used by
zaira.transition.
"""

import argparse
import sys
from typing import Any, Mapping

from zaira.export import get_ticket
from zaira.types import Violation


def check_ticket(
    ticket: Mapping[str, Any], status: str | None = None
) -> list[Violation]:
    """Run CHECK hooks against a ticket, at the given or its current status."""
    from zaira.hooks import run_check_hooks

    if status is None:
        status = str(ticket.get("status", ""))
    return run_check_hooks(ticket, status)


def validate_transition(
    ticket: Mapping[str, Any], target_status: str
) -> list[Violation]:
    """Run CHECK hooks against a ticket for its transition target status.

    Used by `zaira transition` to validate before it happens.
    """
    return check_ticket(ticket, status=target_status)


def check_command(args: argparse.Namespace) -> None:
    """CLI handler: fetch tickets, run CHECK hooks, print a report."""
    from zaira.hooks import drain_notes, hooks_enabled

    keys = args.keys
    any_fail = False

    for key in keys:
        ticket = get_ticket(key, full=True, include_custom=True)
        if not ticket:
            print(f"{key}: could not fetch ticket", file=sys.stderr)
            any_fail = True
            continue

        issue_type = ticket.get("issuetype", "Unknown")
        status = ticket.get("status", "Unknown")
        print(f"{key} ({issue_type} / {status})")

        violations = check_ticket(ticket)
        notes = drain_notes()

        for msg in notes:
            print(f"  NOTE  {msg}")
        if violations:
            any_fail = True
            for v in violations:
                print(f"  FAIL  {v.check:<11s} {v.field}")
                print(f"        {v.message}")
        elif not notes:
            print("  ok" if hooks_enabled() else "  ok (no hooks configured)")

    if any_fail:
        sys.exit(1)
