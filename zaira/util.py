"""Utility functions."""

import difflib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def fuzzy_match(query: str, choices: list[str], n: int = 5) -> list[str]:
    """Fuzzy match a query string against a list of choices.

    Uses difflib.get_close_matches for similarity matching with a cutoff of 0.6.

    Args:
        query: String to search for
        choices: List of choices to match against
        n: Maximum number of matches to return (default: 5)

    Returns:
        List of matching choices, ordered by similarity
    """
    return difflib.get_close_matches(query, choices, n=n, cutoff=0.6)


def humanize_age(iso_timestamp: str | None) -> str:
    """Convert an ISO timestamp to a compact human-readable age."""
    if not iso_timestamp:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("+0000", "+00:00"))
        delta = datetime.now(timezone.utc) - dt

        seconds = delta.total_seconds()
        if seconds < 60:
            return "now"
        minutes = seconds / 60
        if minutes < 60:
            return f"{int(minutes)}m"
        hours = minutes / 60
        if hours < 24:
            return f"{int(hours)}h"
        days = hours / 24
        if days < 7:
            return f"{int(days)}d"
        weeks = days / 7
        if weeks < 4:
            return f"{int(weeks)}w"
        months = days / 30
        if months < 12:
            return f"{int(months)}mo"
        years = days / 365
        return f"{int(years)}y"
    except (ValueError, TypeError):
        return "-"


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text to `path` atomically.

    Writes to a temporary file in the same directory, then renames it into
    place. A failure partway through (encoding error, disk full, etc.)
    leaves the previous contents of `path` untouched instead of a
    truncated or partially written file, since `path` itself is never
    opened for writing.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
