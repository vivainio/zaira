"""Shared pytest fixtures for zaira tests."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zaira import activity_log, confluence_api, jira_client


@pytest.fixture(autouse=True)
def isolated_activity_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Redirect the activity log to a temp dir so tests never write to the real one.

    The real log is an audit trail stamped with the user's token fingerprint;
    test entries there would be indistinguishable from genuine activity.
    """
    log_dir = tmp_path / "activity-log"
    monkeypatch.setattr(activity_log, "CACHE_DIR", log_dir)
    monkeypatch.setattr(activity_log, "LOG_FILE", log_dir / "activity.log")
    monkeypatch.setattr(activity_log, "_token_fp", lambda: "test0000")
    yield log_dir / "activity.log"


@pytest.fixture
def mock_jira() -> Iterator[MagicMock]:
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
def mock_confluence() -> Iterator[None]:
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
