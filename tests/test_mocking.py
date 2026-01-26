"""Tests to verify API mocking works correctly."""

from unittest.mock import MagicMock

from zaira import jira_client
from zaira import confluence_api


class TestJiraMocking:
    """Tests for JIRA client mocking."""

    def test_mock_jira_injection(self, mock_jira):
        """Test that mock JIRA client is properly injected."""
        # Configure mock
        mock_jira.search_issues.return_value = [
            MagicMock(key="TEST-1", fields=MagicMock(summary="Test issue"))
        ]

        # Get client and verify it's the mock
        client = jira_client.get_jira()
        assert client is mock_jira

        # Verify mock behavior
        issues = client.search_issues("project = TEST")
        assert len(issues) == 1
        assert issues[0].key == "TEST-1"

    def test_jira_reset_after_test(self):
        """Test that JIRA client is reset after test using fixture."""
        # After a test using mock_jira, get_jira should try to get real client
        # We can't actually test this without credentials, but we can verify
        # the _jira_client is None
        assert jira_client._jira_client is None


class TestConfluenceMocking:
    """Tests for Confluence API mocking."""

    def test_mock_confluence_fetch_page(self, mock_confluence):
        """Test mocking fetch_page function."""
        # Set up mock
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand="": {"id": page_id, "title": "Mocked Page"},
        )

        # Call function
        result = confluence_api.fetch_page("12345")

        # Verify mock was used
        assert result == {"id": "12345", "title": "Mocked Page"}

    def test_mock_confluence_multiple_functions(self, mock_confluence):
        """Test mocking multiple Confluence functions."""
        # Set up mocks
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand="": {"id": page_id, "title": "Test"},
        )
        confluence_api.set_api(
            "get_page_labels",
            lambda page_id: ["label1", "label2"],
        )

        # Test both mocks
        page = confluence_api.fetch_page("123")
        labels = confluence_api.get_page_labels("123")

        assert page["title"] == "Test"
        assert labels == ["label1", "label2"]

    def test_confluence_reset_after_test(self):
        """Test that Confluence API is reset after test using fixture."""
        # After a test using mock_confluence, overrides should be cleared
        assert len(confluence_api._api_overrides) == 0
