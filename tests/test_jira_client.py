"""Tests for jira_client module."""

from unittest.mock import MagicMock, patch

import pytest

from zaira import jira_client
from zaira.errors import CredentialsNotConfigured


class TestGetSchemaPath:
    """Tests for get_schema_path function."""

    def test_returns_path(self) -> None:
        """Returns schema path."""
        result = jira_client.get_schema_path()

        assert result.name == "schema.json"


class TestGetProjectSchemaPath:
    """Tests for get_project_schema_path function."""

    def test_returns_path_with_project(self) -> None:
        """Returns schema path with project."""
        result = jira_client.get_project_schema_path("PROJ")

        assert result.name == "zproject_PROJ.json"


class TestGetServerFromConfig:
    """Tests for get_server_from_config function."""

    def test_returns_site_from_credentials(self, tmp_path, monkeypatch) -> None:
        """Returns site from credentials file."""
        with patch.object(
            jira_client,
            "load_credentials",
            return_value={"site": "example.atlassian.net"},
        ):
            result = jira_client.get_server_from_config()

        assert result == "https://example.atlassian.net"

    def test_adds_https_prefix(self, tmp_path, monkeypatch) -> None:
        """Adds https:// prefix when missing."""
        with patch.object(
            jira_client, "load_credentials", return_value={"site": "jira.example.com"}
        ):
            result = jira_client.get_server_from_config()

        assert result == "https://jira.example.com"

    def test_preserves_https_prefix(self, tmp_path, monkeypatch) -> None:
        """Preserves https:// prefix when present."""
        with patch.object(
            jira_client,
            "load_credentials",
            return_value={"site": "https://jira.example.com"},
        ):
            result = jira_client.get_server_from_config()

        assert result == "https://jira.example.com"

    def test_returns_none_when_no_site(self, tmp_path, monkeypatch) -> None:
        """Returns None when no site configured."""
        monkeypatch.chdir(tmp_path)

        with patch.object(jira_client, "load_credentials", return_value={}):
            result = jira_client.get_server_from_config()

        assert result is None


class TestLoadCredentials:
    """Tests for load_credentials function."""

    def test_loads_credentials_file(self, tmp_path, monkeypatch) -> None:
        """Loads and parses credentials file."""
        creds_dir = tmp_path / "config"
        creds_dir.mkdir()
        creds_file = creds_dir / "credentials.toml"
        creds_file.write_text('email = "user@example.com"\napi_token = "secret"\n')

        with patch.object(jira_client, "CREDENTIALS_FILE", creds_file):
            result = jira_client.load_credentials()

        assert result["email"] == "user@example.com"
        assert result["api_token"] == "secret"

    def test_returns_empty_dict_when_missing(self, tmp_path, monkeypatch) -> None:
        """Returns empty dict when credentials file doesn't exist."""
        creds_file = tmp_path / "nonexistent.toml"

        with patch.object(jira_client, "CREDENTIALS_FILE", creds_file):
            result = jira_client.load_credentials()

        assert result == {}


class TestGetCredentials:
    """Tests for complete credential loading."""

    def test_raises_application_error_when_credentials_are_missing(self) -> None:
        """Missing credentials do not terminate programmatic callers."""
        with (
            patch.object(jira_client, "get_server_from_config", return_value=None),
            patch.object(jira_client, "load_credentials", return_value={}),
            pytest.raises(CredentialsNotConfigured) as exc_info,
        ):
            jira_client.get_credentials()

        assert "Credentials not configured" in str(exc_info.value)
        assert exc_info.value.exit_code == 1


class TestGetJiraSite:
    """Tests for get_jira_site function."""

    def test_returns_site_without_protocol(self, tmp_path, monkeypatch) -> None:
        """Returns site name without https://."""
        with patch.object(
            jira_client,
            "load_credentials",
            return_value={"site": "https://example.atlassian.net"},
        ):
            result = jira_client.get_jira_site()

        assert result == "example.atlassian.net"

    def test_strips_http_protocol(self, tmp_path, monkeypatch) -> None:
        """Strips http:// from site."""
        with patch.object(
            jira_client,
            "load_credentials",
            return_value={"site": "http://jira.example.com"},
        ):
            result = jira_client.get_jira_site()

        assert result == "jira.example.com"

    def test_returns_site_as_is_without_protocol(self, tmp_path, monkeypatch) -> None:
        """Returns site as-is when no protocol."""
        with patch.object(
            jira_client, "load_credentials", return_value={"site": "jira.example.com"}
        ):
            result = jira_client.get_jira_site()

        assert result == "jira.example.com"


class TestLoadAuthMode:
    """Tests for load_auth_mode function."""

    def test_returns_none_when_file_missing(self, tmp_path) -> None:
        """Returns None when config.toml doesn't exist."""
        with patch.object(jira_client, "CONFIG_FILE", tmp_path / "nonexistent.toml"):
            assert jira_client.load_auth_mode() is None

    def test_returns_none_when_no_auth_table(self, tmp_path) -> None:
        """Returns None when config.toml has no [auth] table."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[worklog]\nmax_hours_per_day = 7.5\n")

        with patch.object(jira_client, "CONFIG_FILE", config_file):
            assert jira_client.load_auth_mode() is None

    def test_returns_cached_mode_and_cloud_id(self, tmp_path) -> None:
        """Returns (mode, cloud_id) from the [auth] table."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[auth]\nmode = "scoped"\ncloud_id = "cloud-123"\n')

        with patch.object(jira_client, "CONFIG_FILE", config_file):
            assert jira_client.load_auth_mode() == ("scoped", "cloud-123")

    def test_returns_classic_mode_without_cloud_id(self, tmp_path) -> None:
        """Returns (mode, None) when cloud_id is absent."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[auth]\nmode = "classic"\n')

        with patch.object(jira_client, "CONFIG_FILE", config_file):
            assert jira_client.load_auth_mode() == ("classic", None)


class TestSaveAuthMode:
    """Tests for save_auth_mode function."""

    def test_creates_file_with_auth_table(self, tmp_path) -> None:
        """Creates config.toml with an [auth] table if missing."""
        config_file = tmp_path / "config.toml"
        config_dir = tmp_path

        with (
            patch.object(jira_client, "CONFIG_FILE", config_file),
            patch.object(jira_client, "CONFIG_DIR", config_dir),
        ):
            jira_client.save_auth_mode("scoped", "cloud-123")
            assert jira_client.load_auth_mode() == ("scoped", "cloud-123")

    def test_preserves_existing_tables(self, tmp_path) -> None:
        """Appends [auth] without clobbering other tables."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("[worklog]\nmax_hours_per_day = 7.5\n")

        with (
            patch.object(jira_client, "CONFIG_FILE", config_file),
            patch.object(jira_client, "CONFIG_DIR", tmp_path),
        ):
            jira_client.save_auth_mode("classic", None)

        text = config_file.read_text()
        assert "max_hours_per_day = 7.5" in text
        assert 'mode = "classic"' in text
        assert "cloud_id" not in text

    def test_replaces_existing_auth_table(self, tmp_path) -> None:
        """Overwrites a stale [auth] table rather than duplicating it."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[auth]\nmode = "classic"\n')

        with (
            patch.object(jira_client, "CONFIG_FILE", config_file),
            patch.object(jira_client, "CONFIG_DIR", tmp_path),
        ):
            jira_client.save_auth_mode("scoped", "cloud-456")
            assert jira_client.load_auth_mode() == ("scoped", "cloud-456")
        assert config_file.read_text().count("[auth]") == 1


class TestClearAuthMode:
    """Tests for clear_auth_mode function."""

    def test_removes_auth_table(self, tmp_path) -> None:
        """Strips the [auth] table, preserving other tables."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[worklog]\nmax_hours_per_day = 7.5\n\n[auth]\nmode = "scoped"\ncloud_id = "cloud-123"\n'
        )

        with patch.object(jira_client, "CONFIG_FILE", config_file):
            jira_client.clear_auth_mode()

        text = config_file.read_text()
        assert "[auth]" not in text
        assert "max_hours_per_day = 7.5" in text

    def test_noop_when_file_missing(self, tmp_path) -> None:
        """Does nothing when config.toml doesn't exist."""
        with patch.object(jira_client, "CONFIG_FILE", tmp_path / "nonexistent.toml"):
            jira_client.clear_auth_mode()  # Should not raise


class TestGetOrDetectAuthMode:
    """Tests for get_or_detect_auth_mode function."""

    def test_returns_cached_mode_without_probing(self) -> None:
        """Uses the cached value and never calls probe_auth_mode."""
        with (
            patch.object(
                jira_client, "load_auth_mode", return_value=("scoped", "cloud-123")
            ),
            patch.object(jira_client, "probe_auth_mode") as mock_probe,
        ):
            result = jira_client.get_or_detect_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("scoped", "cloud-123")
        mock_probe.assert_not_called()

    def test_probes_and_persists_when_not_cached(self) -> None:
        """Probes and saves the result when nothing is cached yet."""
        with (
            patch.object(jira_client, "load_auth_mode", return_value=None),
            patch.object(
                jira_client, "probe_auth_mode", return_value=("scoped", "cloud-123")
            ),
            patch.object(jira_client, "save_auth_mode") as mock_save,
        ):
            result = jira_client.get_or_detect_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("scoped", "cloud-123")
        mock_save.assert_called_once_with("scoped", "cloud-123")

    def test_falls_back_to_classic_without_caching_when_probe_fails(self) -> None:
        """Falls back to classic (uncached) when both endpoints reject the token."""
        with (
            patch.object(jira_client, "load_auth_mode", return_value=None),
            patch.object(jira_client, "probe_auth_mode", return_value=None),
            patch.object(jira_client, "save_auth_mode") as mock_save,
        ):
            result = jira_client.get_or_detect_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("classic", None)
        mock_save.assert_not_called()


class TestGetDefaultJira:
    """Tests for _get_default_jira constructing the right server URL."""

    def test_uses_classic_server_url(self) -> None:
        """Constructs JIRA client with the site URL unchanged for classic mode."""
        with (
            patch.object(
                jira_client,
                "get_credentials",
                return_value=(
                    "https://example.atlassian.net",
                    "user@example.com",
                    "tok",
                ),
            ),
            patch.object(
                jira_client, "get_or_detect_auth_mode", return_value=("classic", None)
            ),
            patch("zaira.jira_client.JIRA") as mock_jira_cls,
        ):
            jira_client._get_default_jira.cache_clear()
            jira_client._get_default_jira()

        mock_jira_cls.assert_called_once_with(
            server="https://example.atlassian.net",
            basic_auth=("user@example.com", "tok"),
        )
        jira_client._get_default_jira.cache_clear()

    def test_uses_gateway_server_url_for_scoped(self) -> None:
        """Constructs JIRA client with the api.atlassian.com gateway for scoped mode."""
        with (
            patch.object(
                jira_client,
                "get_credentials",
                return_value=(
                    "https://example.atlassian.net",
                    "user@example.com",
                    "tok",
                ),
            ),
            patch.object(
                jira_client,
                "get_or_detect_auth_mode",
                return_value=("scoped", "cloud-123"),
            ),
            patch("zaira.jira_client.JIRA") as mock_jira_cls,
        ):
            jira_client._get_default_jira.cache_clear()
            jira_client._get_default_jira()

        mock_jira_cls.assert_called_once_with(
            server="https://api.atlassian.com/ex/jira/cloud-123",
            basic_auth=("user@example.com", "tok"),
        )
        jira_client._get_default_jira.cache_clear()


class TestJiraClientInjection:
    """Tests for JIRA client injection (mock support)."""

    def test_set_jira_injects_client(self) -> None:
        """set_jira injects a mock client."""
        mock = MagicMock()
        jira_client.set_jira(mock)

        try:
            result = jira_client.get_jira()
            assert result is mock
        finally:
            jira_client.reset_jira()

    def test_reset_jira_clears_injection(self) -> None:
        """reset_jira clears the injected client."""
        mock = MagicMock()
        jira_client.set_jira(mock)
        jira_client.reset_jira()

        # Can't test get_jira() without credentials, but we can verify the global is None
        assert jira_client._jira_client is None

    def test_set_jira_none_clears_injection(self) -> None:
        """set_jira(None) clears the injected client."""
        mock = MagicMock()
        jira_client.set_jira(mock)
        jira_client.set_jira(None)

        assert jira_client._jira_client is None
