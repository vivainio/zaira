"""Tests for jira_client module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zaira import jira_client


class TestGetProfile:
    """Tests for get_profile function."""

    def test_returns_profile_from_config(self, tmp_path, monkeypatch):
        """Returns profile name from zproject.toml."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[project]
profile = "production"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = jira_client.get_profile()
        assert result == "production"

    def test_returns_default_when_no_profile(self, tmp_path, monkeypatch):
        """Returns 'default' when no profile specified."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "zproject.toml").write_bytes(b"[project]")

        result = jira_client.get_profile()
        assert result == "default"

    def test_returns_default_when_no_config(self, tmp_path, monkeypatch):
        """Returns 'default' when no config file."""
        monkeypatch.chdir(tmp_path)

        result = jira_client.get_profile()
        assert result == "default"


class TestGetSchemaPath:
    """Tests for get_schema_path function."""

    def test_returns_path_with_profile(self):
        """Returns schema path with profile name."""
        result = jira_client.get_schema_path("myprofile")

        assert "zschema_myprofile.json" in str(result)
        assert result.name == "zschema_myprofile.json"

    def test_uses_current_profile_when_none(self, tmp_path, monkeypatch):
        """Uses current profile when profile is None."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[project]
profile = "test"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = jira_client.get_schema_path(None)
        assert "zschema_test.json" in str(result)


class TestGetProjectSchemaPath:
    """Tests for get_project_schema_path function."""

    def test_returns_path_with_project_and_profile(self):
        """Returns schema path with project and profile."""
        result = jira_client.get_project_schema_path("PROJ", "staging")

        assert "zproject_staging_PROJ.json" in str(result)
        assert result.name == "zproject_staging_PROJ.json"

    def test_uses_current_profile_when_none(self, tmp_path, monkeypatch):
        """Uses current profile when profile is None."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[project]
profile = "dev"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        result = jira_client.get_project_schema_path("TEST", None)
        assert "zproject_dev_TEST.json" in str(result)


class TestGetServerFromConfig:
    """Tests for get_server_from_config function."""

    def test_returns_site_from_credentials(self, tmp_path, monkeypatch):
        """Returns site from credentials file."""
        with patch.object(jira_client, "load_credentials", return_value={"site": "example.atlassian.net"}):
            result = jira_client.get_server_from_config()

        assert result == "https://example.atlassian.net"

    def test_adds_https_prefix(self, tmp_path, monkeypatch):
        """Adds https:// prefix when missing."""
        with patch.object(jira_client, "load_credentials", return_value={"site": "jira.example.com"}):
            result = jira_client.get_server_from_config()

        assert result == "https://jira.example.com"

    def test_preserves_https_prefix(self, tmp_path, monkeypatch):
        """Preserves https:// prefix when present."""
        with patch.object(jira_client, "load_credentials", return_value={"site": "https://jira.example.com"}):
            result = jira_client.get_server_from_config()

        assert result == "https://jira.example.com"

    def test_falls_back_to_zproject(self, tmp_path, monkeypatch):
        """Falls back to zproject.toml when credentials don't have site."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[project]
site = "project.atlassian.net"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        with patch.object(jira_client, "load_credentials", return_value={}):
            result = jira_client.get_server_from_config()

        assert result == "https://project.atlassian.net"

    def test_returns_none_when_no_site(self, tmp_path, monkeypatch):
        """Returns None when no site configured."""
        monkeypatch.chdir(tmp_path)

        with patch.object(jira_client, "load_credentials", return_value={}):
            result = jira_client.get_server_from_config()

        assert result is None


class TestLoadCredentials:
    """Tests for load_credentials function."""

    def test_loads_credentials_file(self, tmp_path, monkeypatch):
        """Loads and parses credentials file."""
        creds_dir = tmp_path / "config"
        creds_dir.mkdir()
        creds_file = creds_dir / "credentials.toml"
        creds_file.write_text('email = "user@example.com"\napi_token = "secret"\n')

        with patch.object(jira_client, "CREDENTIALS_FILE", creds_file):
            result = jira_client.load_credentials()

        assert result["email"] == "user@example.com"
        assert result["api_token"] == "secret"

    def test_returns_empty_dict_when_missing(self, tmp_path, monkeypatch):
        """Returns empty dict when credentials file doesn't exist."""
        creds_file = tmp_path / "nonexistent.toml"

        with patch.object(jira_client, "CREDENTIALS_FILE", creds_file):
            result = jira_client.load_credentials()

        assert result == {}


class TestGetJiraSite:
    """Tests for get_jira_site function."""

    def test_returns_site_without_protocol(self, tmp_path, monkeypatch):
        """Returns site name without https://."""
        with patch.object(jira_client, "load_credentials", return_value={"site": "https://example.atlassian.net"}):
            result = jira_client.get_jira_site()

        assert result == "example.atlassian.net"

    def test_strips_http_protocol(self, tmp_path, monkeypatch):
        """Strips http:// from site."""
        with patch.object(jira_client, "load_credentials", return_value={"site": "http://jira.example.com"}):
            result = jira_client.get_jira_site()

        assert result == "jira.example.com"

    def test_returns_site_as_is_without_protocol(self, tmp_path, monkeypatch):
        """Returns site as-is when no protocol."""
        with patch.object(jira_client, "load_credentials", return_value={"site": "jira.example.com"}):
            result = jira_client.get_jira_site()

        assert result == "jira.example.com"

    def test_falls_back_to_zproject(self, tmp_path, monkeypatch):
        """Falls back to zproject.toml when credentials don't have site."""
        monkeypatch.chdir(tmp_path)
        config_content = b"""
[project]
site = "project.atlassian.net"
"""
        (tmp_path / "zproject.toml").write_bytes(config_content)

        with patch.object(jira_client, "load_credentials", return_value={}):
            result = jira_client.get_jira_site()

        assert result == "project.atlassian.net"


class TestJiraClientInjection:
    """Tests for JIRA client injection (mock support)."""

    def test_set_jira_injects_client(self):
        """set_jira injects a mock client."""
        mock = MagicMock()
        jira_client.set_jira(mock)

        try:
            result = jira_client.get_jira()
            assert result is mock
        finally:
            jira_client.reset_jira()

    def test_reset_jira_clears_injection(self):
        """reset_jira clears the injected client."""
        mock = MagicMock()
        jira_client.set_jira(mock)
        jira_client.reset_jira()

        # Can't test get_jira() without credentials, but we can verify the global is None
        assert jira_client._jira_client is None

    def test_set_jira_none_clears_injection(self):
        """set_jira(None) clears the injected client."""
        mock = MagicMock()
        jira_client.set_jira(mock)
        jira_client.set_jira(None)

        assert jira_client._jira_client is None
