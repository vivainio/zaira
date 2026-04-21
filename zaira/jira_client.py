"""Jira client wrapper using the jira library."""

import sys
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import cast

import keyring
from jira import JIRA
from platformdirs import user_cache_dir, user_config_dir

from zaira.types import Credentials

CONFIG_DIR = Path(user_config_dir("zaira", appauthor=False))
CACHE_DIR = Path(user_cache_dir("zaira", appauthor=False))


CREDENTIALS_FILE = CONFIG_DIR / "credentials.toml"
CONFIG_FILE = CONFIG_DIR / "config.toml"

KEYRING_SERVICE = "zaira"


def get_schema_path() -> Path:
    """Get path to instance schema file (~/.cache/zaira/schema.json)."""
    return CACHE_DIR / "schema.json"


def get_editmeta_path(project: str, issue_type: str) -> Path:
    """Get path to editmeta cache file (~/.cache/zaira/editmeta_PROJECT_ISSUETYPE.yaml)."""
    safe_type = issue_type.replace(" ", "-").lower()
    return CACHE_DIR / f"editmeta_{project}_{safe_type}.yaml"


def get_project_schema_path(project: str) -> Path:
    """Get path to project schema file (~/.cache/zaira/zproject_PROJECT.json)."""
    return CACHE_DIR / f"zproject_{project}.json"


def get_server_from_config() -> str | None:
    """Get Jira server URL from credentials."""
    creds = load_credentials()
    site = creds.get("site")

    if site:
        if not site.startswith("https://"):
            site = f"https://{site}"
        return site
    return None


def _read_credentials_file() -> Credentials:
    """Read credentials.toml without consulting the keyring."""
    if not CREDENTIALS_FILE.exists():
        return {}

    with open(CREDENTIALS_FILE, "rb") as f:
        return cast(Credentials, tomllib.load(f))


def load_credentials() -> Credentials:
    """Load credentials, preferring the OS keyring for api_token.

    site/email come from credentials.toml; api_token comes from the keyring
    (service='zaira', username=email), falling back to the file if present.
    """
    creds = _read_credentials_file()

    if not creds.get("api_token"):
        email = creds.get("email")
        if email:
            token = keyring.get_password(KEYRING_SERVICE, email)
            if token:
                creds["api_token"] = token

    return creds


def save_token_to_keyring(email: str, api_token: str) -> None:
    """Store the Jira API token in the OS keyring."""
    keyring.set_password(KEYRING_SERVICE, email, api_token)


def delete_token_from_keyring(email: str) -> None:
    """Remove the Jira API token from the OS keyring (if present)."""
    try:
        keyring.delete_password(KEYRING_SERVICE, email)
    except keyring.errors.PasswordDeleteError:
        pass


def strip_token_from_credentials_file() -> bool:
    """Remove any `api_token = ...` line from credentials.toml.

    Returns True if a line was removed.
    """
    if not CREDENTIALS_FILE.exists():
        return False
    original = CREDENTIALS_FILE.read_text()
    kept = [
        line
        for line in original.splitlines()
        if not line.lstrip().startswith("api_token")
    ]
    new = "\n".join(kept)
    if kept and not new.endswith("\n"):
        new += "\n"
    if new == original:
        return False
    CREDENTIALS_FILE.write_text(new)
    CREDENTIALS_FILE.chmod(0o600)
    return True


def save_credentials(email: str, api_token: str) -> None:
    """Save email to credentials.toml and api_token to the OS keyring."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    existing = _read_credentials_file()
    site = existing.get("site", "")
    lines = []
    if site:
        lines.append(f'site = "{site}"')
    lines.append(f'email = "{email}"')
    CREDENTIALS_FILE.write_text("\n".join(lines) + "\n")
    CREDENTIALS_FILE.chmod(0o600)

    save_token_to_keyring(email, api_token)


def get_credentials() -> tuple[str, str, str]:
    """Get Jira credentials from config files.

    Server comes from zproject.toml, credentials from the platform config directory.

    Returns:
        Tuple of (server_url, email, api_token)
    """
    server = get_server_from_config()
    creds = load_credentials()
    email = creds.get("email")
    token = creds.get("api_token")

    if not server or not email or not token:
        print(
            f"Error: Credentials not configured in {CREDENTIALS_FILE}", file=sys.stderr
        )
        print("\nRun 'zaira init' to set up credentials.", file=sys.stderr)
        sys.exit(1)

    return server, email, token


# Injected client for testing
_jira_client: JIRA | None = None


def get_jira() -> JIRA:
    """Get the JIRA client instance (cached or injected).

    Returns:
        Authenticated JIRA client
    """
    global _jira_client
    if _jira_client is not None:
        return _jira_client
    return _get_default_jira()


@lru_cache(maxsize=1)
def _get_default_jira() -> JIRA:
    """Create the default JIRA client from credentials.

    Returns:
        Authenticated JIRA client
    """
    server, email, token = get_credentials()
    return JIRA(server=server, basic_auth=(email, token))


def set_jira(client: JIRA | None) -> None:
    """Inject a JIRA client for testing. Pass None to reset."""
    global _jira_client
    _jira_client = client


def reset_jira() -> None:
    """Reset to default client and clear cache."""
    global _jira_client
    _jira_client = None
    _get_default_jira.cache_clear()


def get_server_url() -> str:
    """Get the Jira server URL."""
    server, _, _ = get_credentials()
    return server


def get_jira_site() -> str:
    """Get Jira site name (without https://)."""
    creds = load_credentials()
    site = creds.get("site", "")
    return site.replace("https://", "").replace("http://", "")


def format_jira_error(e: Exception) -> str:
    """Extract a clean error message from a JIRAError, stripping headers/response noise."""
    from jira.exceptions import JIRAError

    msg = ""
    status = None
    if isinstance(e, JIRAError):
        status = getattr(e, "status_code", None)
        if e.response is not None and hasattr(e.response, "json"):
            try:
                data = e.response.json()
                msgs = data.get("errorMessages", [])
                errs = data.get("errors", {})
                parts = [m for m in msgs if m]
                parts += [f"{k}: {v}" for k, v in errs.items()]
                if parts:
                    msg = "; ".join(parts)
            except Exception:
                pass
        if not msg and e.text:
            msg = e.text
    if not msg:
        msg = str(e)

    if status in (401, 403):
        msg += (
            " (auth failed - API token may be expired; run 'zaira init' to update it)"
        )
    elif status == 404 and "do not have permission" in msg:
        msg += " (or your API token is expired - try 'zaira init' to update it)"
    return msg
