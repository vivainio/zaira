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


# Default directories - relative to project root if found, else cwd
TICKETS_DIR = get_project_dir("tickets")
REPORTS_DIR = get_project_dir("reports")
