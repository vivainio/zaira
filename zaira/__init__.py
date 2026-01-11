"""Zaira - Jira CLI tool for offline ticket management."""

from importlib.metadata import version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jira import JIRA

__version__ = version("zaira")


def client() -> "JIRA":
    """Get an authenticated Jira client.

    Returns an authenticated jira.JIRA instance using credentials
    from ~/.config/zaira/credentials.toml.

    Usage:
        import zaira
        jira = zaira.client()
        issue = jira.issue("FOO-123")

    Returns:
        jira.JIRA: Authenticated Jira client
    """
    from zaira.jira_client import get_jira

    return get_jira()
