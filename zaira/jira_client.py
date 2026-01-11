"""Jira client wrapper using the jira library."""

import sys
import tomllib
from functools import lru_cache
from pathlib import Path

from jira import JIRA

from zaira.project import load_config

CONFIG_DIR = Path.home() / ".config" / "zaira"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.toml"


def get_server_from_config() -> str | None:
    """Get Jira server URL from credentials or zproject.toml."""
    # First check credentials file
    creds = load_credentials()
    site = creds.get("site")

    # Fall back to zproject.toml
    if not site:
        config = load_config()
        site = config.get("project", {}).get("site")

    if site:
        if not site.startswith("https://"):
            site = f"https://{site}"
        return site
    return None


def load_credentials() -> dict:
    """Load credentials from ~/.config/zaira/credentials.toml."""
    if not CREDENTIALS_FILE.exists():
        return {}

    with open(CREDENTIALS_FILE, "rb") as f:
        return tomllib.load(f)


def save_credentials(email: str, api_token: str) -> None:
    """Save credentials to ~/.config/zaira/credentials.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    content = f'email = "{email}"\napi_token = "{api_token}"\n'
    CREDENTIALS_FILE.write_text(content)

    # Secure the file
    CREDENTIALS_FILE.chmod(0o600)


def get_credentials() -> tuple[str, str, str]:
    """Get Jira credentials from config files.

    Server comes from zproject.toml, credentials from ~/.config/zaira/credentials.toml.

    Returns:
        Tuple of (server_url, email, api_token)
    """
    server = get_server_from_config()
    creds = load_credentials()
    email = creds.get("email")
    token = creds.get("api_token")

    if not server or not email or not token:
        print(f"Error: Credentials not configured in {CREDENTIALS_FILE}", file=sys.stderr)
        print("\nRun 'zaira init' to set up credentials.", file=sys.stderr)
        sys.exit(1)

    return server, email, token


@lru_cache(maxsize=1)
def get_jira() -> JIRA:
    """Get a cached JIRA client instance.

    Returns:
        Authenticated JIRA client
    """
    server, email, token = get_credentials()
    return JIRA(server=server, basic_auth=(email, token))


def get_server_url() -> str:
    """Get the Jira server URL."""
    server, _, _ = get_credentials()
    return server


def get_jira_site() -> str:
    """Get Jira site name (without https://)."""
    # First check credentials file
    creds = load_credentials()
    site = creds.get("site", "")

    # Fall back to zproject.toml
    if not site:
        config = load_config()
        site = config.get("project", {}).get("site", "")

    return site.replace("https://", "").replace("http://", "")
