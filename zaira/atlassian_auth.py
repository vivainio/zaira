"""Shared Atlassian cloud-ID resolution and auth-mode detection.

Atlassian scoped API tokens (created with specific scopes selected) only
authenticate against the api.atlassian.com/ex/{jira,confluence}/<cloudId>
gateway. Legacy/classic tokens only authenticate directly against the site.
The two are not interchangeable across base URLs, so callers need to know
which mode a given credential requires.
"""

from typing import Literal

import requests
from requests.auth import HTTPBasicAuth

REQUEST_TIMEOUT_SECONDS = 30

AuthMode = Literal["classic", "scoped"]

_cloud_id_cache: dict[str, str | None] = {}


def resolve_cloud_id(server: str) -> str | None:
    """Resolve the Atlassian cloud ID for `server`.

    Calls the public, unauthenticated /_edge/tenant_info endpoint. Cached
    in-process per server so repeated lookups don't re-hit the network.
    """
    if server in _cloud_id_cache:
        return _cloud_id_cache[server]
    cloud_id = None
    try:
        r = requests.get(f"{server}/_edge/tenant_info", timeout=REQUEST_TIMEOUT_SECONDS)
        if r.ok:
            cloud_id = r.json().get("cloudId") or None
    except requests.RequestException:
        cloud_id = None
    _cloud_id_cache[server] = cloud_id
    return cloud_id


def probe_auth_mode(
    server: str, email: str, token: str
) -> tuple[AuthMode, str | None] | None:
    """Determine whether `token` is a classic or scoped Atlassian API token.

    Tries /rest/api/3/myself directly against `server` first (classic). On
    failure, resolves the cloud ID and retries through the
    api.atlassian.com/ex/jira/<cloudId> gateway (scoped).

    Returns (mode, cloud_id) for whichever succeeds - cloud_id is always
    None for "classic". Returns None if both fail (a real credential
    problem, not a mode mismatch).
    """
    auth = HTTPBasicAuth(email, token)
    try:
        r = requests.get(
            f"{server}/rest/api/3/myself",
            auth=auth,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if r.ok:
            return "classic", None
    except requests.RequestException:
        pass

    cloud_id = resolve_cloud_id(server)
    if not cloud_id:
        return None

    gateway = f"https://api.atlassian.com/ex/jira/{cloud_id}"
    try:
        r = requests.get(
            f"{gateway}/rest/api/3/myself",
            auth=auth,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if r.ok:
            return "scoped", cloud_id
    except requests.RequestException:
        pass

    return None


def jira_base_url(server: str, mode: AuthMode, cloud_id: str | None) -> str:
    """Return the Jira REST base URL for the given auth mode."""
    if mode == "scoped" and cloud_id:
        return f"https://api.atlassian.com/ex/jira/{cloud_id}"
    return server


def confluence_base_url(server: str, mode: AuthMode, cloud_id: str | None) -> str:
    """Return the Confluence REST base URL for the given auth mode."""
    if mode == "scoped" and cloud_id:
        return f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/rest/api"
    return server + "/wiki/rest/api"
