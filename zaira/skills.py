"""Install Claude Code skills bundled with zaira."""

import argparse
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path

import yaml

from zaira.jira_client import CACHE_DIR

STALE_CHECK_MARKER = CACHE_DIR / "skill-check.txt"
INSTALLED_SKILL_MD = Path.home() / ".claude" / "skills" / "zaira" / "SKILL.md"


def install_skills_command(args: argparse.Namespace) -> None:
    skills_dir = (
        Path(args.skills_dir) if args.skills_dir else Path.home() / ".claude" / "skills"
    )
    src = files("zaira") / "skills" / "zaira"
    dest = skills_dir / "zaira"
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        dest_file = dest / item.name
        with item.open("rb") as f:
            dest_file.write_bytes(f.read())
        print(f"Installed {dest_file}")
    print(f"Skills installed to {dest}")


def _frontmatter_updated(text: str) -> str | None:
    """Extract the `updated:` frontmatter field from a skill markdown file, if present."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    front_matter = yaml.safe_load(text[4:end]) or {}
    updated = front_matter.get("updated")
    return str(updated) if updated else None


def check_skill_staleness() -> None:
    """Print a one-line stderr nudge if the installed skill is older than the bundled one.

    Throttled to once per day via a cache marker, since this runs on every CLI invocation.
    """
    today = date.today().isoformat()
    if STALE_CHECK_MARKER.exists() and STALE_CHECK_MARKER.read_text().strip() == today:
        return
    STALE_CHECK_MARKER.parent.mkdir(parents=True, exist_ok=True)
    STALE_CHECK_MARKER.write_text(today)

    if not INSTALLED_SKILL_MD.exists():
        return

    bundled = (files("zaira") / "skills" / "zaira" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    bundled_updated = _frontmatter_updated(bundled)
    installed_updated = _frontmatter_updated(
        INSTALLED_SKILL_MD.read_text(encoding="utf-8")
    )
    if bundled_updated and (
        not installed_updated or installed_updated < bundled_updated
    ):
        print(
            f"note: installed zaira skill is outdated (installed: {installed_updated or 'unknown'}, "
            f"latest: {bundled_updated}) — run 'zaira install-skills' to update",
            file=sys.stderr,
        )
