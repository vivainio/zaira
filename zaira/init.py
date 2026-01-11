"""Initialize project configuration."""

import argparse
import sys
from pathlib import Path

from zaira.jira_client import (
    get_jira,
    get_jira_site,
    CREDENTIALS_FILE,
    load_credentials,
)


def discover_components(project: str) -> list[str]:
    """Discover components for a project."""
    jira = get_jira()
    try:
        proj = jira.project(project)
        components = jira.project_components(proj)
        return sorted([c.name for c in components if c.name])
    except Exception:
        return []


def discover_labels(project: str) -> list[str]:
    """Discover labels used in a project by sampling recent tickets."""
    jira = get_jira()
    try:
        issues = jira.search_issues(
            f"project = {project} ORDER BY updated DESC",
            maxResults=200,
        )
        labels = set()
        for issue in issues:
            for label in issue.fields.labels or []:
                labels.add(label)
        return sorted(labels)
    except Exception:
        return []


def discover_boards(project: str) -> list[dict]:
    """Discover boards for a project."""
    jira = get_jira()
    try:
        boards = jira.boards(projectKeyOrID=project)
        return [
            {
                "id": b.id,
                "name": b.name,
                "type": b.type,
            }
            for b in boards
        ]
    except Exception:
        return []


def discover_issue_types(project: str) -> list[str]:
    """Discover issue types used in a project."""
    jira = get_jira()
    try:
        issues = jira.search_issues(
            f"project = {project}",
            maxResults=100,
        )
        types = set()
        for issue in issues:
            if issue.fields.issuetype and issue.fields.issuetype.name:
                types.add(issue.fields.issuetype.name)
        return sorted(types)
    except Exception:
        return []


def generate_config(
    project: str,
    site: str,
    components: list[str],
    labels: list[str],
    boards: list[dict],
    issue_types: list[str],
) -> str:
    """Generate zproject.toml content."""
    lines = ["[project]", f'key = "{project}"', f'site = "{site}"', ""]

    # Components
    lines.append("[components]")
    if components:
        comp_list = ", ".join(f'"{c}"' for c in components)
        lines.append(f"available = [{comp_list}]")
    else:
        lines.append("# available = []")
    lines.append("")

    # Labels
    lines.append("[labels]")
    if labels:
        label_list = ", ".join(f'"{label}"' for label in labels)
        lines.append(f"available = [{label_list}]")
    else:
        lines.append("# available = []")
    lines.append("")

    # Issue types
    lines.append("[issue_types]")
    if issue_types:
        types_list = ", ".join(f'"{t}"' for t in issue_types)
        lines.append(f"available = [{types_list}]")
    else:
        lines.append('# available = ["Story", "Bug", "Task"]')
    lines.append("")

    # Boards
    lines.append("[boards]")
    if boards:
        for board in boards:
            name_slug = (
                board["name"]
                .lower()
                .replace(" ", "-")
                .replace("(", "")
                .replace(")", "")
            )
            lines.append(f"# {board['name']} ({board['type']})")
            lines.append(f"{name_slug} = {board['id']}")
    else:
        lines.append("# No boards found")
        lines.append("# kanban = 1789")
    lines.append("")

    # Queries
    lines.append("[queries]")
    lines.append("# Named JQL queries for quick access")
    lines.append(
        f'my-tickets = "assignee = currentUser() AND project = {project} AND status NOT IN (Done, Disposal)"'
    )
    lines.append(f'# bugs = "project = {project} AND type = Bug AND status != Done"')
    lines.append("")

    # Reports - named report definitions
    lines.append("[reports]")
    lines.append('my-tickets = { query = "my-tickets", group_by = "status" }')
    if boards:
        board = boards[0]
        name_slug = (
            board["name"].lower().replace(" ", "-").replace("(", "").replace(")", "")
        )
        lines.append(f'{name_slug} = {{ board = {board["id"]}, group_by = "status" }}')
    for comp in components:
        slug = comp.lower().replace(" ", "-")
        lines.append(
            f'{slug} = {{ jql = "project = {project} AND component = {comp}", group_by = "status" }}'
        )
    lines.append(
        f'# bugs = {{ jql = "project = {project} AND type = Bug", group_by = "priority" }}'
    )
    lines.append("")

    return "\n".join(lines)


def check_credentials() -> bool:
    """Check if credentials are configured."""
    creds = load_credentials()
    return bool(creds.get("site") and creds.get("email") and creds.get("api_token"))


def setup_credentials() -> None:
    """Create or prompt to edit credentials file."""
    if CREDENTIALS_FILE.exists():
        # File exists but has invalid/placeholder values
        print(f"Credentials file exists but is not configured: {CREDENTIALS_FILE}\n")
        print("Please edit this file with your Jira credentials:")
        print("  1. Set your Jira site (e.g., company.atlassian.net)")
        print("  2. Set your email address")
        print(
            "  3. Add your API token from https://id.atlassian.com/manage-profile/security/api-tokens"
        )
    else:
        # Create template
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)

        template = """# Jira credentials
# Get your API token from: https://id.atlassian.com/manage-profile/security/api-tokens

site = "your-company.atlassian.net"
email = "your-email@example.com"
api_token = "your-api-token"
"""
        CREDENTIALS_FILE.write_text(template)
        CREDENTIALS_FILE.chmod(0o600)

        print(f"Created {CREDENTIALS_FILE}\n")
        print("Please edit this file with your Jira credentials:")
        print("  1. Set your Jira site (e.g., company.atlassian.net)")
        print("  2. Set your email address")
        print(
            "  3. Add your API token from https://id.atlassian.com/manage-profile/security/api-tokens"
        )

    print("\nThen run 'zaira init' again.")


def init_command(args: argparse.Namespace) -> None:
    """Handle init subcommand."""
    config_path = Path("zproject.toml")

    # Check credentials first
    if not check_credentials():
        setup_credentials()
        sys.exit(1)

    if config_path.exists() and not args.force:
        print(f"Error: {config_path} already exists. Use --force to overwrite.")
        sys.exit(1)

    project = args.project
    site = args.site or get_jira_site()

    if not project:
        print("Error: --project is required")
        sys.exit(1)

    print(f"Discovering project {project} on {site}...")

    # Discover project metadata
    print("  Finding components...")
    components = discover_components(project)
    print(f"    Found {len(components)} components")

    print("  Finding labels...")
    labels = discover_labels(project)
    print(f"    Found {len(labels)} labels")

    print("  Finding boards...")
    boards = discover_boards(project)
    print(f"    Found {len(boards)} boards")

    print("  Finding issue types...")
    issue_types = discover_issue_types(project)
    print(f"    Found {len(issue_types)} issue types")

    content = generate_config(project, site, components, labels, boards, issue_types)
    config_path.write_text(content)
    print(f"\nCreated {config_path}")
