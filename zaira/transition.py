"""Transition Jira tickets between statuses."""

import argparse
import sys
from typing import Any

from zaira.jira_client import get_jira, get_jira_site


def get_transitions(key: str) -> list[dict]:
    """Get available transitions for a ticket."""
    jira = get_jira()
    try:
        return jira.transitions(key)
    except Exception as e:
        print(f"Error getting transitions for {key}: {e}", file=sys.stderr)
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
        print(f"Error transitioning {key}: {e}", file=sys.stderr)
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

    # Parse --field arguments
    fields = {}
    field_args = getattr(args, "field", None) or []
    if field_args:
        from zaira.edit import parse_field_args

        project = key.split("-")[0]
        from zaira.jira_client import get_jira
        from zaira.info import ensure_editmeta
        jira = get_jira()
        issue = jira.issue(key, fields="issuetype")
        issue_type = issue.fields.issuetype.name
        ensure_editmeta(key, issue_type)
        fields = parse_field_args(field_args, project=project, issue_type=issue_type)

    # Validate against rules.yaml before transitioning
    if not getattr(args, "no_check", False):
        from zaira.rules import try_load_rules, validate_transition
        from zaira.export import get_ticket

        all_rules = try_load_rules()
        if all_rules:
            ticket = get_ticket(key, full=True, include_custom=True)
            if ticket:
                violations = validate_transition(ticket, all_rules, status)
                if violations:
                    print(f"Blocked: {key} fails rules for '{status}':", file=sys.stderr)
                    for v in violations:
                        print(f"  FAIL  {v.check:<11s} {v.field}", file=sys.stderr)
                        if v.check in ("contains", "not_contains", "matches", "not_matches", "subtask_types", "one_of", "not_one_of"):
                            print(f"        {v.message}", file=sys.stderr)
                    print("\nUse --no-check to skip validation.", file=sys.stderr)
                    sys.exit(1)

    comment = getattr(args, "comment", None)

    if transition_ticket(key, status, fields=fields, comment=comment):
        print(f"Transitioned {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
        from zaira.activity_log import record
        record("transition", key, f"→ {status}")
    else:
        sys.exit(1)
