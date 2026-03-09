"""Transition Jira tickets between statuses."""

import argparse
import sys
from typing import Any

from zaira.jira_client import format_jira_error, get_jira, get_jira_site


def get_transitions(key: str) -> list[dict]:
    """Get available transitions for a ticket."""
    jira = get_jira()
    try:
        return jira.transitions(key)
    except Exception as e:
        print(
            f"Error getting transitions for {key}: {format_jira_error(e)}",
            file=sys.stderr,
        )
        return []


def transition_ticket(
    key: str,
    status: str,
    fields: dict[str, Any] | None = None,
    comment: str | None = None,
) -> bool:
    """Transition a ticket to a new status.

    Args:
        key: Ticket key (e.g., PROJ-123)
        status: Target status name or transition name
        fields: Optional dict of field_id -> value to set during transition
        comment: Optional comment to include with the transition

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        transitions = jira.transitions(key)

        # Find matching transition (case-insensitive)
        status_lower = status.lower()
        match = None
        for t in transitions:
            if t["name"].lower() == status_lower:
                match = t
                break
            if t["to"]["name"].lower() == status_lower:
                match = t
                break

        if not match:
            print(f"Error: No transition to '{status}' available", file=sys.stderr)
            print("\nAvailable transitions:", file=sys.stderr)
            for t in transitions:
                print(f"  - {t['name']} → {t['to']['name']}", file=sys.stderr)
            return False

        jira.transition_issue(key, match["id"], fields=fields or {}, comment=comment)
        return True
    except Exception as e:
        print(f"Error transitioning {key}: {format_jira_error(e)}", file=sys.stderr)
        return False


def transition_command(args: argparse.Namespace) -> None:
    """Handle transition subcommand."""
    key = args.key.upper()
    jira_site = get_jira_site()

    if args.list:
        transitions = get_transitions(key)
        if transitions:
            print(f"Available transitions for {key}:")
            for t in transitions:
                print(f"  - {t['name']} → {t['to']['name']}")
        return

    if not args.status:
        print("Error: Specify a status or use --list", file=sys.stderr)
        sys.exit(1)

    status = args.status

    # Check allowed_fields whitelist for raw field names BEFORE parsing (unless --no-check is set)
    # This must happen BEFORE mapping field names to IDs
    field_args = getattr(args, "field", None) or []
    project = key.split("-")[0]
    if field_args and not getattr(args, "no_check", False):
        from zaira.rules import check_field_allowed, load_allowed_fields

        allowed_fields = load_allowed_fields(project=project)
        if allowed_fields:
            field_errors = []
            # Extract field names from arguments
            for arg in field_args:
                if "=" in arg:
                    name = arg.split("=", 1)[0].strip()
                    error = check_field_allowed(name, allowed_fields)
                    if error:
                        field_errors.append(error)

            if field_errors:
                print("Error: The following fields are not allowed:", file=sys.stderr)
                for err in field_errors:
                    field_name = err.field
                    suggestions = err.suggestions
                    print(f"  - {field_name}", file=sys.stderr)
                    if suggestions:
                        print("    Did you mean:", file=sys.stderr)
                        for s in suggestions:
                            print(f"      {s}", file=sys.stderr)
                print("\nUse --no-check to skip validation.", file=sys.stderr)
                sys.exit(1)

    # Parse --field arguments
    fields = {}
    if field_args:
        from zaira.edit import parse_field_args
        from zaira.jira_client import get_jira
        from zaira.info import ensure_editmeta

        jira = get_jira()
        issue = jira.issue(key, fields="issuetype")
        issue_type = issue.fields.issuetype.name
        ensure_editmeta(key, issue_type)
        fields = parse_field_args(field_args, project=project, issue_type=issue_type)

    # Validate against rules.yaml before transitioning
    if not getattr(args, "no_check", False):
        from zaira.rules import (
            try_load_rules,
            validate_transition,
        )
        from zaira.export import get_ticket

        all_rules = try_load_rules()
        violations = []

        if all_rules:
            ticket = get_ticket(key, full=True, include_custom=True)
            if ticket:
                violations.extend(validate_transition(ticket, all_rules, status))

        if violations:
            from collections import namedtuple

            print(
                f"Blocked: {key} fails rules for '{status}':",
                file=sys.stderr,
            )
            for v in violations:
                print(f"  FAIL  {v.check:<11s} {v.field}", file=sys.stderr)
                if v.check in (
                    "contains",
                    "not_contains",
                    "matches",
                    "not_matches",
                    "subtask_types",
                    "one_of",
                    "not_one_of",
                    "allowed_fields",
                ):
                    print(f"        {v.message}", file=sys.stderr)
            print("\nUse --no-check to skip validation.", file=sys.stderr)
            sys.exit(1)

    comment = getattr(args, "comment", None)

    # Handle dry-run
    if getattr(args, "dry_run", False):
        print(f"Would transition {key} to '{status}'")
        if fields:
            print("  With fields:")
            for field_id, value in fields.items():
                print(f"    {field_id} = {value}")
        if comment:
            print(f"  With comment: {comment}")
        return

    if transition_ticket(key, status, fields=fields, comment=comment):
        print(f"Transitioned {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record

        record("transition", key, f"→ {status}")
    else:
        sys.exit(1)
