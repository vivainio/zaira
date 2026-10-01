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


class TestTokenRecord:
    """Tests for the JSON token record stored in the secret store."""

    def test_parses_json_record(self) -> None:
        secret = jira_client.encode_token_record(
            {"v": 1, "token": "tok", "mode": "scoped", "cloud_id": "c1"}
        )

        record = jira_client.parse_token_secret(secret)

        assert record["token"] == "tok"
        assert record["mode"] == "scoped"
        assert "legacy" not in record

    def test_bare_token_is_legacy(self) -> None:
        record = jira_client.parse_token_secret("ATATT3-bare-token\n")

        assert record == {"token": "ATATT3-bare-token", "legacy": True}

    def test_json_without_token_is_treated_as_legacy(self) -> None:
        record = jira_client.parse_token_secret('{"foo": 1}')

        assert record["legacy"] is True

    def test_encode_drops_runtime_legacy_flag(self) -> None:
        secret = jira_client.encode_token_record({"token": "t", "legacy": True})

        assert "legacy" not in secret

    def test_save_token_writes_record_with_metadata(self) -> None:
        with (
            patch.object(jira_client.wincred, "is_wsl", return_value=False),
            patch.object(jira_client, "_get_token", return_value=None),
            patch.object(jira_client.keyring, "set_password") as mock_set,
        ):
            jira_client.save_token_to_keyring(
                "u@example.com",
                "tok",
                site="example.atlassian.net",
                stored_by="test",
                expires_at="2027-01-01",
            )

        service, username, secret = mock_set.call_args.args
        assert (service, username) == ("zaira", "u@example.com")
        record = jira_client.parse_token_secret(secret)
        assert record["token"] == "tok"
        assert record["email"] == "u@example.com"
        assert record["site"] == "example.atlassian.net"
        assert record["mode"] == "classic"
        assert record["stored_by"] == "test"
        assert record["expires_at"] == "2027-01-01"
        assert record["stored_at"].endswith("Z")
        assert record["host"]
        assert record["fingerprint"] == jira_client.token_fingerprint("tok")
        assert "previous_fingerprint" not in record

    def test_save_token_records_replaced_fingerprint(
        self, isolated_activity_log
    ) -> None:
        old = jira_client.encode_token_record({"v": 1, "token": "old-token"})

        with (
            patch.object(jira_client, "_get_token", return_value=old),
            patch.object(jira_client, "_store_secret") as mock_store,
        ):
            jira_client.save_token_to_keyring("u@example.com", "new-token")

        record = jira_client.parse_token_secret(mock_store.call_args.args[1])
        old_fp = jira_client.token_fingerprint("old-token")
        new_fp = jira_client.token_fingerprint("new-token")
        assert record["previous_fingerprint"] == old_fp
        assert record["replaced_at"] == record["stored_at"]
        log = isolated_activity_log.read_text()
        assert "token-set" in log
        assert f"{old_fp} -> {new_fp}" in log

    def test_save_same_token_keeps_rotation_history(self) -> None:
        existing = jira_client.encode_token_record(
            {
                "v": 1,
                "token": "same",
                "previous_fingerprint": "deadbeef",
                "replaced_at": "2026-01-01T00:00:00Z",
            }
        )

        with (
            patch.object(jira_client, "_get_token", return_value=existing),
            patch.object(jira_client, "_store_secret") as mock_store,
        ):
            jira_client.save_token_to_keyring("u@example.com", "same")

        record = jira_client.parse_token_secret(mock_store.call_args.args[1])
        assert record["previous_fingerprint"] == "deadbeef"
        assert record["replaced_at"] == "2026-01-01T00:00:00Z"

    def test_save_over_legacy_bare_token_records_its_fingerprint(self) -> None:
        with (
            patch.object(jira_client, "_get_token", return_value="bare-old"),
            patch.object(jira_client, "_store_secret") as mock_store,
        ):
            jira_client.save_token_to_keyring("u@example.com", "new")

        record = jira_client.parse_token_secret(mock_store.call_args.args[1])
        assert record["previous_fingerprint"] == jira_client.token_fingerprint(
            "bare-old"
        )

    def test_warns_when_stored_fingerprint_does_not_match(
        self, tmp_path, capsys, monkeypatch
    ) -> None:
        monkeypatch.setattr(jira_client, "_warned_record_mismatch", False)
        creds_file = tmp_path / "credentials.toml"
        creds_file.write_text('email = "u@example.com"\n')
        secret = jira_client.encode_token_record(
            {"token": "edited", "fingerprint": "00000000"}
        )

        with (
            patch.object(jira_client, "CREDENTIALS_FILE", creds_file),
            patch.object(jira_client, "_get_token", return_value=secret),
        ):
            jira_client.load_credentials()

        assert "does not match the token" in capsys.readouterr().err

    def test_load_credentials_unwraps_record(self, tmp_path) -> None:
        creds_file = tmp_path / "credentials.toml"
        creds_file.write_text('site = "x.atlassian.net"\nemail = "u@example.com"\n')
        secret = jira_client.encode_token_record(
            {"v": 1, "token": "tok", "mode": "scoped", "cloud_id": "c1"}
        )

        with (
            patch.object(jira_client, "CREDENTIALS_FILE", creds_file),
            patch.object(jira_client, "_get_token", return_value=secret),
        ):
            creds = jira_client.load_credentials()

        assert creds["api_token"] == "tok"
        record = jira_client.get_token_record()
        assert record is not None
        assert record["mode"] == "scoped"

    def test_load_credentials_accepts_legacy_bare_token(self, tmp_path) -> None:
        creds_file = tmp_path / "credentials.toml"
        creds_file.write_text('email = "u@example.com"\n')

        with (
            patch.object(jira_client, "CREDENTIALS_FILE", creds_file),
            patch.object(jira_client, "_get_token", return_value="bare"),
        ):
            creds = jira_client.load_credentials()

        assert creds["api_token"] == "bare"
        record = jira_client.get_token_record()
        assert record is not None
        assert record.get("legacy") is True

    def test_warns_on_email_mismatch(self, tmp_path, capsys, monkeypatch) -> None:
        monkeypatch.setattr(jira_client, "_warned_record_mismatch", False)
        creds_file = tmp_path / "credentials.toml"
        creds_file.write_text('email = "me@example.com"\n')
        secret = jira_client.encode_token_record(
            {"token": "tok", "email": "other@example.com"}
        )

        with (
            patch.object(jira_client, "CREDENTIALS_FILE", creds_file),
            patch.object(jira_client, "_get_token", return_value=secret),
        ):
            jira_client.load_credentials()

        err = capsys.readouterr().err
        assert "other@example.com" in err
        assert "me@example.com" in err

    def test_persist_auth_mode_rewrites_record(self, tmp_path, monkeypatch) -> None:
        creds_file = tmp_path / "credentials.toml"
        creds_file.write_text('email = "u@example.com"\n')
        secret = jira_client.encode_token_record(
            {"v": 1, "token": "tok", "stored_by": "orig"}
        )

        with (
            patch.object(jira_client, "CREDENTIALS_FILE", creds_file),
            patch.object(jira_client, "_get_token", return_value=secret),
            patch.object(jira_client, "_store_secret") as mock_store,
        ):
            jira_client.load_credentials()
            assert jira_client.persist_auth_mode("scoped", "c1") is True

        email, written = mock_store.call_args.args
        assert email == "u@example.com"
        record = jira_client.parse_token_secret(written)
        assert record["mode"] == "scoped"
        assert record["cloud_id"] == "c1"
        assert record["stored_by"] == "orig"

    def test_persist_auth_mode_migrates_legacy_entry(self, tmp_path) -> None:
        creds_file = tmp_path / "credentials.toml"
        creds_file.write_text('email = "u@example.com"\n')

        with (
            patch.object(jira_client, "CREDENTIALS_FILE", creds_file),
            patch.object(jira_client, "_get_token", return_value="bare"),
            patch.object(jira_client, "_store_secret") as mock_store,
        ):
            jira_client.load_credentials()
            jira_client.persist_auth_mode("classic", None)

        record = jira_client.parse_token_secret(mock_store.call_args.args[1])
        assert record["token"] == "bare"
        assert record["stored_by"] == "migrated-legacy"
        assert "migrated_at" in record

    def test_persist_auth_mode_returns_false_for_file_token(self, tmp_path) -> None:
        creds_file = tmp_path / "credentials.toml"
        creds_file.write_text('email = "u@example.com"\napi_token = "t"\n')

        with (
            patch.object(jira_client, "CREDENTIALS_FILE", creds_file),
            patch.object(jira_client, "_store_secret") as mock_store,
        ):
            jira_client.load_credentials()
            assert jira_client.persist_auth_mode("scoped", "c1") is False

        mock_store.assert_not_called()

    def test_expiry_report_includes_record_summary(self, isolated_activity_log) -> None:
        jira_client._token_record = {
            "v": 1,
            "token": "SECRET-VALUE-123",
            "mode": "classic",
            "stored_at": "2026-01-01T00:00:00Z",
            "stored_by": "test",
        }
        try:
            jira_client._report_token_expiry(401, "nope")
        finally:
            jira_client._token_record = None

        text = isolated_activity_log.read_text()
        assert "stored_by=test" in text
        assert "SECRET-VALUE-123" not in text


class TestGetOrDetectAuthMode:
    """Tests for get_or_detect_auth_mode function."""

    def test_defaults_to_classic_without_record(self) -> None:
        with patch.object(jira_client, "_token_record", None):
            result = jira_client.get_or_detect_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("classic", None)

    def test_legacy_record_is_classic(self) -> None:
        record = {"token": "token", "legacy": True}
        with patch.object(jira_client, "_token_record", record):
            result = jira_client.get_or_detect_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("classic", None)

    def test_uses_scoped_mode_from_record(self) -> None:
        record = {"token": "token", "mode": "scoped", "cloud_id": "cloud-123"}
        with patch.object(jira_client, "_token_record", record):
            result = jira_client.get_or_detect_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("scoped", "cloud-123")

    def test_ignores_record_for_a_different_token(self) -> None:
        record = {"token": "other", "mode": "scoped", "cloud_id": "cloud-123"}
        with patch.object(jira_client, "_token_record", record):
            result = jira_client.get_or_detect_auth_mode(
                "https://example.atlassian.net", "user@example.com", "token"
            )

        assert result == ("classic", None)


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
