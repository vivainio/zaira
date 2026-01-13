"""Zaira - Jira CLI tool for offline ticket management."""

from importlib.metadata import version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jira import JIRA

__version__ = version("zaira")


def client() -> "JIRA":
    """Get an authenticated Jira client.

    Returns an authenticated jira.JIRA instance using credentials
    from $XDG_CONFIG_HOME/zaira/credentials.toml.

    Usage:
        import zaira
        jira = zaira.client()
        issue = jira.issue("FOO-123")

    Returns:
        jira.JIRA: Authenticated Jira client
    """
    from zaira.jira_client import get_jira

    return get_jira()


def schema() -> dict | None:
    """Get cached instance schema.

    Returns Jira instance metadata including fields, statuses,
    priorities, issue types, and link types.

    Usage:
        import zaira
        s = zaira.schema()
        print(s["statuses"])  # {'Open': 'To Do', 'In Progress': 'In Progress', ...}
        print(s["fields"])    # {'customfield_10001': 'Epic Link', ...}

    Returns:
        Schema dict or None if not cached. Run 'zaira init' to populate.
    """
    from zaira.info import load_schema

    return load_schema()


def project_schema(project: str) -> dict | None:
    """Get cached project schema.

    Returns project-specific metadata including components and labels.

    Usage:
        import zaira
        s = zaira.project_schema("FOO")
        print(s["components"])  # ['Backend', 'Frontend', ...]
        print(s["labels"])      # ['bug', 'feature', ...]

    Args:
        project: Project key (e.g., "FOO")

    Returns:
        Project schema dict or None if not cached. Run 'zaira init' to populate.
    """
    from zaira.info import load_project_schema

    return load_project_schema(project)
