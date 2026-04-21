"""Initialize project configuration."""

import argparse
import getpass
import json
import sys
from pathlib import Path

from zaira.jira_client import (
    CACHE_DIR,
    CONFIG_FILE,
    CREDENTIALS_FILE,
    get_jira,
    get_jira_site,
    get_project_schema_path,
    load_credentials,
    save_token_to_keyring,
    strip_token_from_credentials_file,
)
from zaira.info import _fetch_and_cache_fields


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
    """Convert name to slug for TOML bare keys (only A-Za-z0-9, -, _)."""
    import re

    slug = name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


def _unique_key(slug: str, seen: set[str]) -> str:
    """Return a unique TOML key, appending -2, -3, etc. if needed."""
    if slug not in seen:
        seen.add(slug)
        return slug
    n = 2
    while f"{slug}-{n}" in seen:
        n += 1
    key = f"{slug}-{n}"
    seen.add(key)
    return key


def generate_config(
    projects: list[str],
    all_boards: dict[str, list[dict]],
    all_components: dict[str, list[str]],
) -> str:
    """Generate zproject.toml content.

    Args:
        projects: List of project keys
        all_boards: Dict mapping project key to list of boards
        all_components: Dict mapping project key to list of components
    """
    lines = []

    # Boards - collect from all projects
    lines.append("[boards]")
    has_boards = False
    seen_boards: set[str] = set()
    for project in projects:
        boards = all_boards.get(project, [])
        for board in boards:
            has_boards = True
            key = _unique_key(slugify(board["name"]), seen_boards)
            lines.append(f"# {board['name']} ({board['type']})")
            lines.append(f"{key} = {board['id']}")
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
    seen_reports: set[str] = set()
    lines.append('my-tickets = { query = "my-tickets", group_by = "status" }')
    seen_reports.add("my-tickets")

    for project in projects:
        prefix = f"{project.lower()}-" if len(projects) > 1 else ""
        boards = all_boards.get(project, [])
        if boards:
            board = boards[0]
            key = _unique_key(slugify(board["name"]), seen_reports)
            lines.append(f'{key} = {{ board = {board["id"]}, group_by = "status" }}')
        components = all_components.get(project, [])
        for comp in components:
            key = _unique_key(f"{prefix}{slugify(comp)}", seen_reports)
            lines.append(
                f'{key} = {{ jql = "project = {project} AND component = \\"{comp}\\"", group_by = "status" }}'
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


def _create_config_file() -> None:
    """Create config.toml with defaults if it doesn't exist."""
    if CONFIG_FILE.exists():
        return
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    template = """# Zaira configuration

[worklog]
# Max hours per day for 'zaira log --spread'
max_hours_per_day = 7.5
"""
    CONFIG_FILE.write_text(template)


def _ensure_credentials_file() -> bool:
    """Make sure credentials.toml has a real site and email.

    Returns True if the file is ready (site + email set), False if the user
    still needs to edit it.
    """
    if not CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        template = """# Jira credentials
# The API token is stored in the OS keyring; 'zaira init' will prompt for it.
# Get your API token from: https://id.atlassian.com/manage-profile/security/api-tokens

site = "your-company.atlassian.net"
email = "your-email@example.com"
"""
        CREDENTIALS_FILE.write_text(template)
        CREDENTIALS_FILE.chmod(0o600)
        _create_config_file()
        print(f"Created {CREDENTIALS_FILE}\n")
        print(
            "Please edit this file with your Jira site and email, then run 'zaira init' again."
        )
        return False

    creds = load_credentials()
    site = creds.get("site")
    email = creds.get("email")
    if (
        not site
        or not email
        or site == "your-company.atlassian.net"
        or email == "your-email@example.com"
    ):
        print(f"Credentials file needs to be configured: {CREDENTIALS_FILE}\n")
        print("Please set 'site' and 'email', then run 'zaira init' again.")
        return False

    return True


def _prompt_for_token(email: str) -> str:
    """Prompt the user for an API token (hidden input)."""
    print(
        f"No API token found for {email} in the OS keyring.\n"
        "Get one from https://id.atlassian.com/manage-profile/security/api-tokens"
    )
    token = getpass.getpass("Jira API token: ").strip()
    if not token:
        print("Error: empty token", file=sys.stderr)
        sys.exit(1)
    return token


def init_command(args: argparse.Namespace) -> None:
    """Handle init subcommand - credentials setup only."""
    if not _ensure_credentials_file():
        sys.exit(1)

    creds = load_credentials()
    email = creds["email"]

    reset = getattr(args, "set_token", False)
    if reset or not creds.get("api_token"):
        token = _prompt_for_token(email)
        save_token_to_keyring(email, token)
        print(f"Stored API token for {email} in the OS keyring.\n")
        if reset and strip_token_from_credentials_file():
            print(
                f"Removed stale api_token from {CREDENTIALS_FILE} "
                "so the keyring value takes effect.\n"
            )

    _create_config_file()
    print("Credentials configured.")
    print(f"  Site: {get_jira_site()}")
    print(f"  Credentials: {CREDENTIALS_FILE}")
    print(f"  Config: {CONFIG_FILE}")
    print("  Token: stored in OS keyring")


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

    content = generate_config(projects, all_boards, all_components)
    config_path.write_text(content)
    print(f"\nCreated {config_path}\n")

    # Cache fields (for field name lookups in export)
    print("Fetching fields...")
    try:
        _fetch_and_cache_fields()
        print("Cached field metadata.")
    except Exception as e:
        print(f"  Warning: Could not fetch fields: {e}", file=sys.stderr)

    for project in projects:
        project_schema = {
            "components": all_components.get(project, []),
            "labels": all_labels.get(project, []),
        }
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        project_file = get_project_schema_path(project)
        project_file.write_text(json.dumps(project_schema, indent=2))
        print(f"Saved project schema to {project_file}")
