"""Project configuration handling."""

import tomllib
from pathlib import Path


def load_config() -> dict:
    """Load zproject.toml if it exists."""
    config_path = Path("zproject.toml")
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    return {}


def get_query(name: str) -> str | None:
    """Get a named query from zproject.toml."""
    config = load_config()
    queries = config.get("queries", {})
    return queries.get(name)


def get_board(name: str) -> int | None:
    """Get a board ID by name from zproject.toml."""
    config = load_config()
    boards = config.get("boards", {})
    value = boards.get(name)
    if isinstance(value, int):
        return value
    return None


def list_queries() -> dict[str, str]:
    """List all named queries."""
    config = load_config()
    return config.get("queries", {})


def list_boards() -> dict[str, int]:
    """List all named boards."""
    config = load_config()
    return {k: v for k, v in config.get("boards", {}).items() if isinstance(v, int)}


def get_report(name: str) -> dict | None:
    """Get a named report definition from zproject.toml."""
    config = load_config()
    reports = config.get("reports", {})
    return reports.get(name)


def list_reports() -> dict[str, dict]:
    """List all named reports."""
    config = load_config()
    return config.get("reports", {})


def get_max_hours_per_day() -> float:
    """Get max hours per day from config.toml, default 7.5."""
    from zaira.jira_client import CONFIG_FILE

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "rb") as f:
            config = tomllib.load(f)
        value = config.get("worklog", {}).get("max_hours_per_day")
        if value is not None:
            return float(value)
    return 7.5
