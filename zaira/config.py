"""Zaira configuration."""

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


# Default directories - relative to project root if found, else cwd
TICKETS_DIR = get_project_dir("tickets")
REPORTS_DIR = get_project_dir("reports")
