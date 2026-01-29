"""Initialize project configuration."""

import argparse
import json
import sys
from pathlib import Path

from zaira.jira_client import (
    CACHE_DIR,
    CREDENTIALS_FILE,
    get_jira,
    get_jira_site,
    get_project_schema_path,
    load_credentials,
)
from zaira.info import fetch_and_save_schema


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


def slugify(name: str) -> str:
    """Convert name to slug for config keys."""
    return name.lower().replace(" ", "-").replace("(", "").replace(")", "")


def generate_config(
    projects: list[str],
    site: str,
    all_boards: dict[str, list[dict]],
    all_components: dict[str, list[str]],
) -> str:
    """Generate zproject.toml content.

    Args:
        projects: List of project keys
        site: Jira site URL
        all_boards: Dict mapping project key to list of boards
        all_components: Dict mapping project key to list of components
    """
    lines = ["[project]", f'site = "{site}"', ""]

    # Boards - collect from all projects
    lines.append("[boards]")
    has_boards = False
    for project in projects:
        boards = all_boards.get(project, [])
        for board in boards:
            has_boards = True
            lines.append(f"# {board['name']} ({board['type']})")
            lines.append(f"{slugify(board['name'])} = {board['id']}")
    if not has_boards:
        lines.append("# No boards found")
        lines.append("# kanban = 1789")
    lines.append("")

    # Queries - per project
    lines.append("[queries]")
    lines.append("# Named JQL queries for quick access")
    project_list = ", ".join(projects)
    lines.append(
        f'my-tickets = "assignee = currentUser() AND project IN ({project_list}) AND status NOT IN (Done, Disposal)"'
    )
    for project in projects:
        prefix = f"{project.lower()}-" if len(projects) > 1 else ""
        lines.append(
            f'# {prefix}bugs = "project = {project} AND type = Bug AND status != Done"'
        )
    lines.append("")

    # Reports - named report definitions
    lines.append("[reports]")
    lines.append('my-tickets = { query = "my-tickets", group_by = "status" }')

    for project in projects:
        prefix = f"{project.lower()}-" if len(projects) > 1 else ""
        boards = all_boards.get(project, [])
        if boards:
            board = boards[0]
            lines.append(
                f'{slugify(board["name"])} = {{ board = {board["id"]}, group_by = "status" }}'
            )
        components = all_components.get(project, [])
        for comp in components:
            lines.append(
                f'{prefix}{slugify(comp)} = {{ jql = "project = {project} AND component = \\"{comp}\\"", group_by = "status" }}'
            )
        lines.append(
            f'# {prefix}bugs = {{ jql = "project = {project} AND type = Bug", group_by = "priority" }}'
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
    """Handle init subcommand - credentials setup only."""
    if check_credentials():
        print("Credentials configured.")
        print(f"  Site: {get_jira_site()}")
        print(f"  Credentials: {CREDENTIALS_FILE}")
    else:
        setup_credentials()
        sys.exit(1)


def init_project_command(args: argparse.Namespace) -> None:
    """Handle init-project subcommand - generate zproject.toml."""
    config_path = Path("zproject.toml")

    # Check credentials first
    if not check_credentials():
        print("Error: credentials not configured. Run 'zaira init' first.")
        sys.exit(1)

    if config_path.exists() and not args.force:
        print(f"Error: {config_path} already exists. Use --force to overwrite.")
        sys.exit(1)

    projects = args.projects
    site = args.site or get_jira_site()

    if not projects:
        print("Error: at least one project is required")
        print("Usage: zaira init-project PROJECT [PROJECT ...]")
        sys.exit(1)

    # Discover metadata for all projects
    all_boards: dict[str, list[dict]] = {}
    all_components: dict[str, list[str]] = {}
    all_labels: dict[str, list[str]] = {}

    for project in projects:
        print(f"Discovering {project}...")

        print("  Finding components...")
        components = discover_components(project)
        all_components[project] = components
        print(f"    Found {len(components)} components")

        print("  Finding labels...")
        labels = discover_labels(project)
        all_labels[project] = labels
        print(f"    Found {len(labels)} labels")

        print("  Finding boards...")
        boards = discover_boards(project)
        all_boards[project] = boards
        print(f"    Found {len(boards)} boards")

    content = generate_config(projects, site, all_boards, all_components)
    config_path.write_text(content)
    print(f"\nCreated {config_path}\n")

    # Cache instance schema (once) and project metadata (per project)
    fetch_and_save_schema()
    for project in projects:
        project_schema = {
            "components": all_components.get(project, []),
            "labels": all_labels.get(project, []),
        }
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        project_file = get_project_schema_path(project)
        project_file.write_text(json.dumps(project_schema, indent=2))
        print(f"Saved project schema to {project_file}")
