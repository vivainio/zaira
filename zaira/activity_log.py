"""Activity log: append-only record of write operations."""

import json
from datetime import datetime, timezone

from zaira.jira_client import CACHE_DIR

LOG_FILE = CACHE_DIR / "activity.log"


def record(op: str, key: str, detail: str | None = None) -> None:
    """Append one entry to the activity log.

    Args:
        op:     Operation name (transition, edit, comment, create, worklog, link)
        key:    Primary ticket key (e.g., AC-1234)
        detail: Short human-readable detail string (e.g., "→ Done", "1h30m")
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        entry: dict = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "op": op,
            "key": key,
        }
        if detail:
            entry["detail"] = detail
        with LOG_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let logging break the main operation


def read_entries(
    tail: int | None = None,
    key_filter: str | None = None,
) -> list[dict]:
    """Read log entries, optionally filtered and limited.

    Args:
        tail:       Return at most this many entries (most recent first)
        key_filter: Only return entries whose key matches (case-insensitive)

    Returns:
        List of entry dicts, oldest-first.
    """
    if not LOG_FILE.exists():
        return []

    entries: list[dict] = []
    with LOG_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if key_filter:
        kf = key_filter.upper()
        entries = [e for e in entries if e.get("key", "").upper() == kf]

    if tail is not None:
        entries = entries[-tail:]

    return entries


def format_entries(entries: list[dict]) -> str:
    """Format log entries for display."""
    if not entries:
        return "(no entries)"

    lines = []
    for e in entries:
        ts = e.get("ts", "")
        # Convert "2026-02-20T14:32:01Z" → "2026-02-20 14:32:01"
        ts_display = ts.replace("T", " ").rstrip("Z")
        op = e.get("op", "?")
        key = e.get("key", "?")
        detail = e.get("detail", "")
        detail_str = f"  {detail}" if detail else ""
        lines.append(f"{ts_display}  {op:<12s}  {key}{detail_str}")

    return "\n".join(lines)
