"""Create links between Jira tickets."""

import argparse
import sys

from zaira.jira_client import get_jira, get_jira_site


def get_link_types() -> list[str]:
    """Get available link type names."""
    jira = get_jira()
    return [lt.name for lt in jira.issue_link_types()]


def create_link(from_key: str, to_key: str, link_type: str) -> bool:
    """Create a link between two Jira tickets.

    Args:
        from_key: Source ticket key (e.g., PROJ-123)
        to_key: Target ticket key (e.g., PROJ-456)
        link_type: Link type name (e.g., "Blocks", "Relates")

    Returns:
        True if successful, False otherwise
    """
    jira = get_jira()
    try:
        jira.create_issue_link(link_type, from_key, to_key)
        return True
    except Exception as e:
        err = str(e)
        if "No issue link type with name" in err:
            print(f"Error: Unknown link type '{link_type}'", file=sys.stderr)
            print(f"\nValid link types:", file=sys.stderr)
            for name in sorted(get_link_types()):
                print(f"  {name}", file=sys.stderr)
        else:
            print(f"Error creating link: {e}", file=sys.stderr)
        return False


def link_command(args: argparse.Namespace) -> None:
    """Handle link subcommand."""
    from_key = args.from_key.upper()
    to_key = args.to_key.upper()
    link_type = args.type

    jira_site = get_jira_site()
    print(f"Linking {from_key} --[{link_type}]--> {to_key}...")

    if create_link(from_key, to_key, link_type):
        print(f"Link created: {from_key} {link_type} {to_key}")
        print(f"View at: https://{jira_site}/browse/{from_key}")
    else:
        sys.exit(1)
