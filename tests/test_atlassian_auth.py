"""Tests for atlassian_auth module."""

from unittest.mock import MagicMock, patch

from zaira import atlassian_auth
from zaira.atlassian_auth import (
    confluence_base_url,
    jira_base_url,
    probe_auth_mode,
    resolve_cloud_id,
)


class TestResolveCloudId:
    """Tests for resolve_cloud_id function."""

    def setup_method(self) -> None:
        atlassian_auth._cloud_id_cache.clear()

    def test_returns_cloud_id_on_success(self) -> None:
        """Returns cloudId from tenant_info response."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"cloudId": "abc-123"}

        with patch("requests.get", return_value=mock_response):
            result = resolve_cloud_id("https://example.atlassian.net")

        assert result == "abc-123"

    def test_returns_none_on_failure_response(self) -> None:
        """Returns None when tenant_info returns non-ok."""
        mock_response = MagicMock()
        mock_response.ok = False

        with patch("requests.get", return_value=mock_response):
            result = resolve_cloud_id("https://example.atlassian.net")

        assert result is None

    def test_returns_none_on_request_exception(self) -> None:
        """Returns None when the request raises."""
        import requests

        with patch("requests.get", side_effect=requests.RequestException("boom")):
            result = resolve_cloud_id("https://example.atlassian.net")

        assert result is None

    def test_caches_result_in_process(self) -> None:
        """Only hits the network once per server."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"cloudId": "abc-123"}

        with patch("requests.get", return_value=mock_response) as mock_get:
            resolve_cloud_id("https://example.atlassian.net")
            resolve_cloud_id("https://example.atlassian.net")

        mock_get.assert_called_once()


class TestProbeAuthMode:
    """Tests for probe_auth_mode function."""

    def setup_method(self) -> None:
        atlassian_auth._cloud_id_cache.clear()

    def test_classic_succeeds(self) -> None:
        """Returns ('classic', None) when the direct-site call succeeds."""
        mock_response = MagicMock()
        mock_response.ok = True

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = probe_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("classic", None)
        mock_get.assert_called_once()

    def test_classic_fails_then_gateway_succeeds(self) -> None:
        """Falls back to the api.atlassian.com gateway and returns scoped mode."""
        classic_response = MagicMock()
        classic_response.ok = False

        tenant_response = MagicMock()
        tenant_response.ok = True
        tenant_response.json.return_value = {"cloudId": "cloud-123"}

        gateway_response = MagicMock()
        gateway_response.ok = True

        with patch(
            "requests.get",
            side_effect=[classic_response, tenant_response, gateway_response],
        ) as mock_get:
            result = probe_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("scoped", "cloud-123")
        gateway_call = mock_get.call_args_list[-1]
        assert gateway_call.args[0] == (
            "https://api.atlassian.com/ex/jira/cloud-123/rest/api/3/myself"
        )

    def test_both_fail_returns_none(self) -> None:
        """Returns None when both classic and gateway attempts fail."""
        classic_response = MagicMock()
        classic_response.ok = False

        tenant_response = MagicMock()
        tenant_response.ok = True
        tenant_response.json.return_value = {"cloudId": "cloud-123"}

        gateway_response = MagicMock()
        gateway_response.ok = False

        with patch(
            "requests.get",
            side_effect=[classic_response, tenant_response, gateway_response],
        ):
            result = probe_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result is None

    def test_both_fail_when_cloud_id_unresolvable(self) -> None:
        """Returns None without attempting the gateway if cloud_id can't be resolved."""
        classic_response = MagicMock()
        classic_response.ok = False

        tenant_response = MagicMock()
        tenant_response.ok = False

        with patch(
            "requests.get", side_effect=[classic_response, tenant_response]
        ) as mock_get:
            result = probe_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result is None
        assert mock_get.call_count == 2


class TestJiraBaseUrl:
    """Tests for jira_base_url function."""

    def test_classic_returns_server_unchanged(self) -> None:
        assert (
            jira_base_url("https://example.atlassian.net", "classic", None)
            == "https://example.atlassian.net"
        )

    def test_scoped_returns_gateway_url(self) -> None:
        assert (
            jira_base_url("https://example.atlassian.net", "scoped", "cloud-123")
            == "https://api.atlassian.com/ex/jira/cloud-123"
        )


class TestConfluenceBaseUrl:
    """Tests for confluence_base_url function."""

    def test_classic_returns_site_wiki_api(self) -> None:
        assert (
            confluence_base_url("https://example.atlassian.net", "classic", None)
            == "https://example.atlassian.net/wiki/rest/api"
        )

    def test_scoped_returns_gateway_wiki_api(self) -> None:
        assert (
            confluence_base_url("https://example.atlassian.net", "scoped", "cloud-123")
            == "https://api.atlassian.com/ex/confluence/cloud-123/wiki/rest/api"
        )
