"""Zaira - Jira CLI tool for offline ticket management."""

from importlib.metadata import version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jira import JIRA
    from zaira.types import ZSchema

__version__ = version("zaira")


def client() -> "JIRA":
    """Get an authenticated Jira client.

    Returns an authenticated jira.JIRA instance using credentials
    from the platform config directory (credentials.toml).

    Usage:
        import zaira
        jira = zaira.client()
        issue = jira.issue("FOO-123")

    Returns:
        jira.JIRA: Authenticated Jira client
    """
    from zaira.jira_client import get_jira

    return get_jira()


def schema() -> "ZSchema | None":
    """Get cached instance schema.

    Returns Jira instance metadata including fields, statuses,
    priorities, issue types, and link types.

    Usage:
        import zaira
        s = zaira.schema()
        print(s["statuses"])  # {'Open': 'To Do', 'In Progress': 'In Progress', ...}
        print(s["fields"])    # {'customfield_10001': {'name': 'Epic Link', 'type': '[option]'}, ...}

    Returns:
        Schema dict or None if not cached. Run 'zaira init' to populate.
    """
    from zaira.info import load_schema

    return load_schema()


