"""Transition Jira tickets between statuses."""

import argparse
import sys

from zaira.jira_client import get_jira, get_jira_site


def get_transitions(key: str) -> list[dict]:
    """Get available transitions for a ticket."""
    jira = get_jira()
    try:
        return jira.transitions(key)
    except Exception as e:
        print(f"Error getting transitions for {key}: {e}", file=sys.stderr)
        return []


def transition_ticket(key: str, status: str) -> bool:
    """Transition a ticket to a new status.

    Args:
        key: Ticket key (e.g., PROJ-123)
        status: Target status name or transition name

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

        jira.transition_issue(key, match["id"])
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

    if transition_ticket(key, status):
        print(f"Transitioned {key}")
        print(f"View at: https://{jira_site}/browse/{key}")
    else:
        sys.exit(1)
