"""Zaira configuration."""

import tomllib
from pathlib import Path


def find_project_root() -> Path | None:
    """Search up the directory tree for zproject.toml."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "zproject.toml").exists():
            return parent
    return None


def get_project_dir(subdir: str) -> Path:
    """Get project subdirectory, falling back to cwd if no project found."""
    root = find_project_root()
    if root:
        return root / subdir
    return Path.cwd() / subdir


def get_tickets_dir() -> Path:
    """Get tickets directory, respecting tickets_dir in zproject.toml."""
    root = find_project_root()
    if root:
        config_path = root / "zproject.toml"
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        configured = config.get("tickets_dir")
        if configured:
            return root / configured
        return root / "tickets"
    return Path.cwd() / "tickets"


def load_project_config() -> dict:
    """Load zproject.toml from the project root, or {} outside a project."""
    root = find_project_root()
    if not root:
        return {}
    with open(root / "zproject.toml", "rb") as f:
        return tomllib.load(f)


def get_db_path() -> Path:
    """Get the snapshot database path, respecting [db] path in zproject.toml."""
    root = find_project_root()
    if not root:
        return Path.cwd() / "zaira.db"
    configured = load_project_config().get("db", {}).get("path")
    return root / (configured or "zaira.db")


def get_db_scopes() -> list[str]:
    """Get default scope (query) names from [db] scopes in zproject.toml."""
    return list(load_project_config().get("db", {}).get("scopes", []))


def get_project_query(name: str) -> str | None:
    """Get a named query from [queries] in the project's zproject.toml."""
    return load_project_config().get("queries", {}).get(name)


def get_reports_dir() -> Path:
    """Get the reports directory for the project active at call time."""
    return get_project_dir("reports")


# Default directories - relative to project root if found, else cwd
TICKETS_DIR = get_project_dir("tickets")
REPORTS_DIR = get_reports_dir()
