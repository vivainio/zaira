"""Tests for dashboard module."""

from unittest.mock import MagicMock

import pytest

from zaira.dashboard import (
    _get_owner_name,
    _dict_to_dashboard,
    _extract_gadget_type,
    generate_dashboard_markdown,
    get_dashboards,
    get_my_dashboards,
    get_dashboard,
    get_dashboard_raw,
    _get_gadget_config,
    _get_filter,
)
from zaira.types import Dashboard, DashboardGadget


class TestGetOwnerName:
    """Tests for _get_owner_name function."""

    def test_none_owner(self):
        """Returns empty string for None owner."""
        assert _get_owner_name(None) == ""

    def test_display_name(self):
        """Returns displayName when available."""
        owner = {"displayName": "John Doe", "name": "jdoe"}
        assert _get_owner_name(owner) == "John Doe"

    def test_name_fallback(self):
        """Falls back to name when no displayName."""
        owner = {"name": "jdoe", "accountId": "123"}
        assert _get_owner_name(owner) == "jdoe"

    def test_account_id_fallback(self):
        """Falls back to accountId when no name."""
        owner = {"accountId": "123456"}
        assert _get_owner_name(owner) == "123456"

    def test_empty_dict(self):
        """Returns empty string for empty dict."""
        assert _get_owner_name({}) == ""


class TestDictToDashboard:
    """Tests for _dict_to_dashboard function."""

    def test_converts_full_dict(self):
        """Converts complete API response to Dashboard."""
        api_response = {
            "id": "12345",
            "name": "My Dashboard",
            "description": "A test dashboard",
            "owner": {"displayName": "Jane Smith"},
            "view": "https://jira.example.com/dashboard/12345",
            "isFavourite": True,
        }

        result = _dict_to_dashboard(api_response)

        assert isinstance(result, Dashboard)
        assert result.id == 12345
        assert result.name == "My Dashboard"
        assert result.description == "A test dashboard"
        assert result.owner == "Jane Smith"
        assert result.view_url == "https://jira.example.com/dashboard/12345"
        assert result.is_favourite is True

    def test_handles_missing_fields(self):
        """Handles missing optional fields."""
        api_response = {"id": "999"}

        result = _dict_to_dashboard(api_response)

        assert result.id == 999
        assert result.name == ""
        assert result.description == ""
        assert result.owner == ""
        assert result.view_url == ""
        assert result.is_favourite is False


class TestGetDashboards:
    """Tests for get_dashboards function with mocked Jira."""

    def test_returns_dashboards(self, mock_jira):
        """Returns list of Dashboard objects."""
        mock_jira._get_json.return_value = {
            "values": [
                {"id": "1", "name": "Dashboard One"},
                {"id": "2", "name": "Dashboard Two"},
            ]
        }

        result = get_dashboards()

        assert len(result) == 2
        assert all(isinstance(d, Dashboard) for d in result)
        assert result[0].name == "Dashboard One"

    def test_passes_filter_params(self, mock_jira):
        """Passes filter parameters to API."""
        mock_jira._get_json.return_value = {"values": []}

        get_dashboards(filter_text="test", owner="user123", max_results=10)

        mock_jira._get_json.assert_called_once()
        call_args = mock_jira._get_json.call_args
        params = call_args[1]["params"]
        assert params["filter"] == "test"
        assert params["owner"] == "user123"
        assert params["maxResults"] == 10

    def test_handles_error(self, mock_jira, capsys):
        """Returns empty list on error."""
        mock_jira._get_json.side_effect = Exception("API Error")

        result = get_dashboards()

        assert result == []
        captured = capsys.readouterr()
        assert "Error fetching dashboards" in captured.err


class TestGetMyDashboards:
    """Tests for get_my_dashboards function with mocked Jira."""

    def test_returns_my_dashboards(self, mock_jira):
        """Returns dashboards owned by current user."""
        mock_jira._get_json.return_value = {
            "values": [{"id": "10", "name": "My Dashboard"}]
        }

        result = get_my_dashboards()

        assert len(result) == 1
        mock_jira._get_json.assert_called_with(
            "dashboard/search", params={"owner": "me"}
        )

    def test_handles_error(self, mock_jira, capsys):
        """Returns empty list on error."""
        mock_jira._get_json.side_effect = Exception("API Error")

        result = get_my_dashboards()

        assert result == []


class TestGetDashboard:
    """Tests for get_dashboard function with mocked Jira."""

    def test_returns_dashboard(self, mock_jira):
        """Returns Dashboard object for valid ID."""
        mock_jira._get_json.return_value = {
            "id": "42",
            "name": "Specific Dashboard",
            "description": "Details",
        }

        result = get_dashboard(42)

        assert result is not None
        assert result.id == 42
        assert result.name == "Specific Dashboard"
        mock_jira._get_json.assert_called_with("dashboard/42")

    def test_returns_none_on_error(self, mock_jira, capsys):
        """Returns None when dashboard not found."""
        mock_jira._get_json.side_effect = Exception("Not found")

        result = get_dashboard(999)

        assert result is None
        captured = capsys.readouterr()
        assert "Error fetching dashboard" in captured.err


class TestGetDashboardRaw:
    """Tests for get_dashboard_raw function with mocked Jira."""

    def test_returns_raw_data(self, mock_jira):
        """Returns raw API response."""
        mock_jira._get_json.return_value = {"id": "123", "raw": "data"}

        result = get_dashboard_raw(123)

        assert result == {"id": "123", "raw": "data"}
        mock_jira._get_json.assert_called_with("dashboard/123")

    def test_returns_none_on_error(self, mock_jira):
        """Returns None on error."""
        mock_jira._get_json.side_effect = Exception("Error")

        result = get_dashboard_raw(999)

        assert result is None


class TestGetGadgetConfig:
    """Tests for _get_gadget_config function with mocked Jira."""

    def test_returns_config_value(self, mock_jira):
        """Returns value from config response."""
        mock_jira._get_json.return_value = {"value": {"filterId": "123"}}

        result = _get_gadget_config(100, "gadget1")

        assert result == {"filterId": "123"}

    def test_returns_none_on_error(self, mock_jira):
        """Returns None on error."""
        mock_jira._get_json.side_effect = Exception("Error")

        result = _get_gadget_config(100, "gadget1")

        assert result is None


class TestGetFilter:
    """Tests for _get_filter function with mocked Jira."""

    def test_returns_filter_data(self, mock_jira):
        """Returns filter data."""
        mock_jira._get_json.return_value = {"name": "My Filter", "jql": "project = TEST"}

        result = _get_filter("123")

        assert result == {"name": "My Filter", "jql": "project = TEST"}

    def test_returns_none_on_error(self, mock_jira):
        """Returns None on error."""
        mock_jira._get_json.side_effect = Exception("Error")

        result = _get_filter("999")

        assert result is None


class TestExtractGadgetType:
    """Tests for _extract_gadget_type function (pure)."""

    def test_extracts_from_uri(self):
        """Extracts gadget type from URI format."""
        uri = "rest/gadgets/1.0/g/com.atlassian.jira.gadgets:filter-results-gadget/more"
        result = _extract_gadget_type(uri)

        assert result == "Filter Results"

    def test_extracts_from_module_key(self):
        """Extracts gadget type from module key format."""
        key = "com.atlassian.jira.gadgets:pie-chart-gadget"
        result = _extract_gadget_type(key)

        assert result == "Pie Chart"

    def test_handles_empty_string(self):
        """Returns 'unknown' for empty string."""
        assert _extract_gadget_type("") == "unknown"
        assert _extract_gadget_type(None) == "unknown"

    def test_handles_simple_string(self):
        """Handles simple string without colon."""
        result = _extract_gadget_type("simple-gadget")
        assert "Simple" in result


class TestGenerateDashboardMarkdown:
    """Tests for generate_dashboard_markdown function (pure)."""

    def test_generates_basic_markdown(self):
        """Generates markdown with dashboard info."""
        dashboard = Dashboard(
            id=123,
            name="Test Dashboard",
            description="A test dashboard",
            owner="John Doe",
            view_url="https://jira.example.com/dashboard/123",
            is_favourite=True,
        )
        gadgets = []

        result = generate_dashboard_markdown(dashboard, gadgets)

        assert "title: Test Dashboard" in result
        assert "dashboard_id: 123" in result
        assert "# Test Dashboard" in result
        assert "_A test dashboard_" in result
        assert "**Owner:** John Doe" in result
        assert "**Favourite:** Yes" in result

    def test_includes_gadgets(self):
        """Includes gadget information."""
        dashboard = Dashboard(
            id=456,
            name="With Gadgets",
            description="",
            owner="Jane",
            view_url="https://example.com",
            is_favourite=False,
        )
        gadgets = [
            DashboardGadget(
                id="g1",
                title="Filter Results",
                gadget_type="Filter Results",
                position=(0, 0),
                filter_id="100",
                filter_name="My Filter",
                jql="project = TEST",
            ),
        ]

        result = generate_dashboard_markdown(dashboard, gadgets)

        assert "## Gadgets" in result
        assert "Filter Results" in result
        assert "project = TEST" in result

    def test_no_description(self):
        """Handles dashboard without description."""
        dashboard = Dashboard(
            id=789,
            name="No Desc",
            description="",
            owner="User",
            view_url="https://example.com",
            is_favourite=False,
        )

        result = generate_dashboard_markdown(dashboard, [])

        assert "# No Desc" in result
        assert "**Favourite:** No" in result
