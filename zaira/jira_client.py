"""Jira client wrapper using the jira library."""

import hashlib
import json
import socket
import sys
import tomllib
from datetime import datetime, timezone
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import cast

import keyring
from jira import JIRA
from keyring.errors import PasswordDeleteError
from platformdirs import user_cache_dir, user_config_dir

from zaira import wincred
from zaira.atlassian_auth import AuthMode, jira_base_url
from zaira.errors import CredentialsNotConfigured
from zaira.types import Credentials, TokenRecord

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


# Record behind the token most recently returned by load_credentials(); None
# when the token came from credentials.toml or no token is stored.
_token_record: TokenRecord | None = None
_warned_record_mismatch = False

RECORD_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _zaira_version() -> str:
    try:
        return metadata.version("zaira")
    except metadata.PackageNotFoundError:
        return "unknown"


def parse_token_secret(secret: str) -> TokenRecord:
    """Parse a secret-store value into a TokenRecord.

    A JSON object with a `token` field is a v1+ record. Anything else is a
    bare token written before the record format existed (or by another
    tool) and comes back flagged `legacy`.
    """
    text = secret.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("token"), str):
            if data["token"]:
                return cast(TokenRecord, data)
    return {"token": text, "legacy": True}


def encode_token_record(record: TokenRecord) -> str:
    """Serialize a TokenRecord for the secret store (drops runtime-only flags)."""
    data = {k: v for k, v in record.items() if k != "legacy"}
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def _normalize_site(site: str) -> str:
    return site.replace("https://", "").replace("http://", "").rstrip("/").lower()


def _warn_on_record_mismatch(record: TokenRecord, creds: Credentials) -> None:
    """Warn (once per process) when the stored token record looks misplaced."""
    global _warned_record_mismatch
    if _warned_record_mismatch:
        return
    problems: list[str] = []
    rec_email, email = record.get("email"), creds.get("email")
    if rec_email and email and rec_email.lower() != email.lower():
        problems.append(f"token was stored for {rec_email}, but email is {email}")
    rec_site, site = record.get("site"), creds.get("site")
    if rec_site and site and _normalize_site(rec_site) != _normalize_site(site):
        problems.append(f"token was stored for {rec_site}, but site is {site}")
    stored_fp = record.get("fingerprint")
    if stored_fp and stored_fp != token_fingerprint(record["token"]):
        problems.append(
            f"stored token fingerprint {stored_fp} does not match the token "
            "(record edited or corrupted)"
        )
    expires = record.get("expires_at")
    if expires and expires < _utc_now():
        problems.append(f"token expired on {expires}")
    if problems:
        _warned_record_mismatch = True
        print(f"Warning: {'; '.join(problems)}.", file=sys.stderr)


def load_credentials() -> Credentials:
    """Load credentials, preferring the OS keyring for api_token.

    site/email come from credentials.toml; api_token comes from the secret
    store (service='zaira', username=email), falling back to the file if
    present. The store holds a JSON TokenRecord (see parse_token_secret);
    the record itself is available via get_token_record().
    """
    global _token_record
    creds = _read_credentials_file()
    _token_record = None

    if not creds.get("api_token"):
        email = creds.get("email")
        if email:
            secret = _get_token(email)
            if secret:
                record = parse_token_secret(secret)
                creds["api_token"] = record["token"]
                _token_record = record
                _warn_on_record_mismatch(record, creds)

    return creds


def get_token_record() -> TokenRecord | None:
    """Record behind the token last returned by load_credentials(), if any."""
    return _token_record


def token_fingerprint(token: str) -> str:
    """Return a short, non-reversible identifier for an API token.

    First 8 hex chars of the SHA-256 digest of the token string. Support
    can verify it by hashing the token themselves
    (`printf %s "$TOKEN" | sha256sum | cut -c1-8`), while the secret itself
    never reaches the log.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def current_token_fingerprint() -> str | None:
    """Fingerprint of the currently configured API token, or None if unset."""
    token = load_credentials().get("api_token")
    return token_fingerprint(token) if token else None


def _wincred_target(email: str) -> str:
    """Build the Windows Credential Manager target name for a Jira token.

    wincred.exe's `get` only takes a bare target (no username), so the
    email has to be folded into the target itself.

    Deliberately NOT the `{email}@zaira` name Python `keyring` uses on native
    Windows: something outside this zaira kept overwriting that entry with an
    old legacy bare token. A distinct name keeps other writers away from it.
    """
    return f"zaira-jira-token:{email}"


def _get_token(email: str) -> str | None:
    if wincred.is_wsl():
        try:
            return wincred.get_password(_wincred_target(email), email)
        except wincred.WslInteropUnavailable as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    return keyring.get_password(KEYRING_SERVICE, email)


def _store_secret(email: str, secret: str) -> None:
    if wincred.is_wsl():
        wincred.set_password(_wincred_target(email), email, secret)
        return
    keyring.set_password(KEYRING_SERVICE, email, secret)


def save_token_to_keyring(
    email: str,
    api_token: str,
    *,
    site: str | None = None,
    mode: AuthMode = "classic",
    cloud_id: str | None = None,
    stored_by: str = "zaira",
    expires_at: str | None = None,
) -> None:
    """Store the Jira API token plus debugging metadata as a JSON record.

    Goes to the OS keyring, or to Windows Credential Manager on WSL.
    """
    fingerprint = token_fingerprint(api_token)
    record: TokenRecord = {
        "v": RECORD_VERSION,
        "email": email,
        "token": api_token,
        "fingerprint": fingerprint,
        "mode": mode,
        "cloud_id": cloud_id,
        "stored_at": _utc_now(),
        "stored_by": stored_by,
        "zaira_version": _zaira_version(),
        "host": socket.gethostname(),
        "expires_at": expires_at,
    }
    if site:
        record["site"] = site

    previous = _existing_record(email)
    previous_fp = token_fingerprint(previous["token"]) if previous else None
    if previous and previous_fp != fingerprint:
        record["previous_fingerprint"] = cast(str, previous_fp)
        record["replaced_at"] = record["stored_at"]
    elif previous:
        # Same token stored again: keep the earlier rotation history.
        for key in ("previous_fingerprint", "replaced_at"):
            if previous.get(key):
                record[key] = previous[key]  # type: ignore[literal-required]

    _store_secret(email, encode_token_record(record))
    _log_token_set(previous_fp, fingerprint, stored_by)


def _existing_record(email: str) -> TokenRecord | None:
    """Currently stored record for `email`, or None if absent/unreadable."""
    try:
        secret = _get_token(email)
    except Exception:
        return None
    return parse_token_secret(secret) if secret else None


def _log_token_set(old_fp: str | None, new_fp: str, stored_by: str) -> None:
    """Record a token write (and the fingerprint it replaced) in the activity log."""
    from zaira.activity_log import record

    change = f"{old_fp} -> {new_fp}" if old_fp else f"(none) -> {new_fp}"
    record("token-set", "-", f"{change} [{stored_by}]")


def persist_auth_mode(mode: AuthMode, cloud_id: str | None) -> bool:
    """Record the detected auth mode in the stored token record.

    Returns False when there is no stored record to update (the token comes
    from credentials.toml), so the caller can tell the user to migrate.
    """
    record = _token_record
    email = _read_credentials_file().get("email")
    if record is None or not email:
        return False
    updated: TokenRecord = {**record, "v": RECORD_VERSION}
    updated.pop("legacy", None)
    updated["mode"] = mode
    updated["cloud_id"] = cloud_id
    updated.setdefault("email", email)
    updated.setdefault("fingerprint", token_fingerprint(record["token"]))
    if record.get("legacy"):
        updated["stored_by"] = "migrated-legacy"
        updated["migrated_at"] = _utc_now()
        updated["zaira_version"] = _zaira_version()
        updated["host"] = socket.gethostname()
    _store_secret(email, encode_token_record(updated))
    return True


def delete_token_from_keyring(email: str) -> None:
    """Remove the Jira API token from the secret store (if present)."""
    if wincred.is_wsl():
        wincred.delete_password(_wincred_target(email), email)
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, email)
    except PasswordDeleteError:
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

    save_token_to_keyring(
        email, api_token, site=site or None, stored_by="save_credentials"
    )


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
        raise CredentialsNotConfigured(
            f"Credentials not configured in {CREDENTIALS_FILE}\n"
            "Run 'zaira init' to set up credentials."
        )

    return server, email, token


def get_or_detect_auth_mode(
    server: str, email: str, token: str
) -> tuple[AuthMode, str | None]:
    """Return the auth mode recorded with the stored token.

    Tokens without a recorded mode (legacy entries, credentials.toml) are
    assumed classic. `zaira init` probes and records the mode, so scoped
    tokens must be set up through it.
    """
    record = _token_record
    if record and record.get("token") == token and record.get("mode") == "scoped":
        return "scoped", record.get("cloud_id")
    return "classic", None


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
    mode, cloud_id = get_or_detect_auth_mode(server, email, token)
    effective_server = jira_base_url(server, mode, cloud_id)
    return JIRA(server=effective_server, basic_auth=(email, token))


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


def describe_token_record(record: TokenRecord | None) -> str:
    """One-line, secret-free summary of the stored token record for logs."""
    if record is None:
        return "source=credentials.toml"
    if record.get("legacy"):
        return "format=legacy (bare token; not written by this zaira version)"
    parts = [f"format=v{record.get('v', '?')}", f"mode={record.get('mode', '?')}"]
    stored_at = record.get("stored_at")
    if stored_at:
        parts.append(f"stored_at={stored_at}")
    if record.get("previous_fingerprint"):
        parts.append(
            f"replaced={record['previous_fingerprint']}@{record.get('replaced_at', '?')}"
        )
    for key in ("stored_by", "zaira_version", "host", "expires_at"):
        if record.get(key):
            parts.append(f"{key}={record[key]}")
    return " ".join(parts)


def _report_token_expiry(status: int | None, msg: str) -> None:
    """Write a token-expiry entry to the activity log."""
    from zaira.activity_log import record

    detail = f"HTTP {status}: {msg[:200]} [{describe_token_record(_token_record)}]"
    record("token-expired", "-", detail)


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

    if status in (401, 403) and "permission" not in msg.lower():
        _report_token_expiry(status, msg)
        msg += " (auth failed - API token may be expired; create a new one at https://id.atlassian.com/manage-profile/security/api-tokens then run 'zaira init --set-token' to update it)"
    elif status == 404 and "do not have permission" in msg:
        _report_token_expiry(status, msg)
        msg += " (or your API token is expired - create a new one at https://id.atlassian.com/manage-profile/security/api-tokens then run 'zaira init --set-token' to update it)"
    return msg
