"""Shared pytest fixtures for zaira tests."""

import pytest
from unittest.mock import MagicMock

from zaira import jira_client
from zaira import confluence_api


@pytest.fixture
def mock_jira():
    """Provide a mock JIRA client.

    The mock is injected into jira_client and automatically reset after the test.

    Usage:
        def test_something(mock_jira):
            mock_jira.search_issues.return_value = [...]
            # Test code that calls jira_client.get_jira()
    """
    mock = MagicMock()
    jira_client.set_jira(mock)
    yield mock
    jira_client.reset_jira()


@pytest.fixture
def mock_confluence():
    """Reset confluence API overrides after test.

    This fixture ensures any API overrides set during a test are cleaned up.
    Use confluence_api.set_api() within your test to override specific functions.

    Usage:
        def test_something(mock_confluence):
            confluence_api.set_api("fetch_page", lambda page_id, expand: {"id": page_id})
            # Test code that calls confluence_api.fetch_page()
    """
    yield
    confluence_api.reset_api()
