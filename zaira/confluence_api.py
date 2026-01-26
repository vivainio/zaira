"""Confluence REST API wrapper functions.

Provides high-level functions for Confluence API calls with test injection support.
"""

from pathlib import Path
from typing import Any, Callable

import requests
from requests.auth import HTTPBasicAuth

from zaira.jira_client import load_credentials, get_server_from_config


# API function overrides for testing
_api_overrides: dict[str, Callable] = {}


def set_api(name: str, func: Callable) -> None:
    """Override an API function for testing."""
    _api_overrides[name] = func


def reset_api() -> None:
    """Reset all API overrides."""
    _api_overrides.clear()


def _get_auth() -> tuple[str, HTTPBasicAuth]:
    """Get Confluence base URL and auth.

    Returns:
        Tuple of (base_url, auth)
    """
    creds = load_credentials()
    server = get_server_from_config()

    if not server or not creds.get("email") or not creds.get("api_token"):
        raise ValueError("Credentials not configured. Run 'zaira init' to set up.")

    base_url = server + "/wiki/rest/api"
    auth = HTTPBasicAuth(creds["email"], creds["api_token"])
    return base_url, auth


def fetch_page(page_id: str, expand: str = "") -> dict | None:
    """Fetch a Confluence page by ID.

    Args:
        page_id: The page ID
        expand: Comma-separated list of expansions (e.g. "body.storage,version")

    Returns:
        Page dict or None on error
    """
    if "fetch_page" in _api_overrides:
        return _api_overrides["fetch_page"](page_id, expand)

    base_url, auth = _get_auth()
    params = {"expand": expand} if expand else {}
    r = requests.get(f"{base_url}/content/{page_id}", params=params, auth=auth)
    if not r.ok:
        return None
    return r.json()


def create_page(
    space_key: str,
    title: str,
    body: str,
    parent_id: str | None = None,
) -> dict | None:
    """Create a new Confluence page.

    Args:
        space_key: Space key
        title: Page title
        body: Page body in storage format
        parent_id: Optional parent page ID

    Returns:
        Created page dict or None on error
    """
    if "create_page" in _api_overrides:
        return _api_overrides["create_page"](space_key, title, body, parent_id)

    base_url, auth = _get_auth()
    payload: dict[str, Any] = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": body,
                "representation": "storage",
            }
        },
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    r = requests.post(f"{base_url}/content", json=payload, auth=auth)
    if not r.ok:
        return None
    return r.json()


def update_page(
    page_id: str,
    title: str,
    body: str,
    version: int,
    page_type: str = "page",
) -> dict | None:
    """Update an existing page.

    Args:
        page_id: Page ID
        title: Page title
        body: Page body in storage format
        version: Current version number (will be incremented)
        page_type: Page type (usually "page")

    Returns:
        Updated page dict or None on error
    """
    if "update_page" in _api_overrides:
        return _api_overrides["update_page"](page_id, title, body, version, page_type)

    base_url, auth = _get_auth()
    payload = {
        "version": {"number": version + 1},
        "title": title,
        "type": page_type,
        "body": {"storage": {"value": body, "representation": "storage"}},
    }
    r = requests.put(f"{base_url}/content/{page_id}", json=payload, auth=auth)
    if not r.ok:
        return None
    return r.json()


def update_page_properties(
    page_id: str,
    version: int,
    page_type: str = "page",
    title: str | None = None,
    space_key: str | None = None,
    parent_id: str | None = None,
) -> dict | None:
    """Update page properties (title, space, parent).

    Args:
        page_id: Page ID
        version: Current version number
        page_type: Page type
        title: New title (required)
        space_key: New space key (optional)
        parent_id: New parent page ID (optional)

    Returns:
        Updated page dict or None on error
    """
    if "update_page_properties" in _api_overrides:
        return _api_overrides["update_page_properties"](
            page_id, version, page_type, title, space_key, parent_id
        )

    base_url, auth = _get_auth()
    payload: dict[str, Any] = {
        "version": {"number": version + 1},
        "type": page_type,
        "title": title,
    }
    if space_key:
        payload["space"] = {"key": space_key}
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    r = requests.put(f"{base_url}/content/{page_id}", json=payload, auth=auth)
    if not r.ok:
        return None
    return r.json()


def delete_page(page_id: str) -> bool:
    """Delete a page.

    Args:
        page_id: Page ID

    Returns:
        True if successful
    """
    if "delete_page" in _api_overrides:
        return _api_overrides["delete_page"](page_id)

    base_url, auth = _get_auth()
    r = requests.delete(f"{base_url}/content/{page_id}", auth=auth)
    return r.ok


def get_child_pages(page_id: str, limit: int = 100) -> list[dict]:
    """Get child pages of a page.

    Args:
        page_id: Parent page ID
        limit: Maximum number of children to return

    Returns:
        List of child page dicts
    """
    if "get_child_pages" in _api_overrides:
        return _api_overrides["get_child_pages"](page_id, limit)

    base_url, auth = _get_auth()
    r = requests.get(
        f"{base_url}/content/{page_id}/child/page",
        params={"limit": limit},
        auth=auth,
    )
    if not r.ok:
        return []
    return r.json().get("results", [])


def search_pages(cql: str, limit: int = 25, expand: str = "") -> dict:
    """Search pages using CQL.

    Args:
        cql: CQL query string
        limit: Maximum results
        expand: Comma-separated expansions

    Returns:
        Search response dict with 'results' key
    """
    if "search_pages" in _api_overrides:
        return _api_overrides["search_pages"](cql, limit, expand)

    base_url, auth = _get_auth()
    params: dict[str, Any] = {"cql": cql, "limit": limit}
    if expand:
        params["expand"] = expand
    r = requests.get(f"{base_url}/content/search", params=params, auth=auth)
    if not r.ok:
        return {"results": [], "error": f"{r.status_code} - {r.reason}", "text": r.text}
    return r.json()


def get_page_labels(page_id: str) -> list[str]:
    """Get labels for a page.

    Args:
        page_id: Page ID

    Returns:
        List of label names
    """
    if "get_page_labels" in _api_overrides:
        return _api_overrides["get_page_labels"](page_id)

    base_url, auth = _get_auth()
    r = requests.get(f"{base_url}/content/{page_id}/label", auth=auth)
    if not r.ok:
        return []
    return [lbl["name"] for lbl in r.json().get("results", [])]


def add_page_labels(page_id: str, labels: list[str]) -> bool:
    """Add labels to a page.

    Args:
        page_id: Page ID
        labels: List of label names to add

    Returns:
        True if successful
    """
    if "add_page_labels" in _api_overrides:
        return _api_overrides["add_page_labels"](page_id, labels)

    if not labels:
        return True

    base_url, auth = _get_auth()
    r = requests.post(
        f"{base_url}/content/{page_id}/label",
        json=[{"name": lbl} for lbl in labels],
        auth=auth,
    )
    return r.ok


def remove_page_label(page_id: str, label: str) -> bool:
    """Remove a label from a page.

    Args:
        page_id: Page ID
        label: Label name to remove

    Returns:
        True if successful
    """
    if "remove_page_label" in _api_overrides:
        return _api_overrides["remove_page_label"](page_id, label)

    base_url, auth = _get_auth()
    r = requests.delete(f"{base_url}/content/{page_id}/label/{label}", auth=auth)
    return r.ok


def set_page_labels(page_id: str, labels: list[str]) -> bool:
    """Set labels on a page (add/remove as needed).

    Args:
        page_id: Page ID
        labels: Desired list of labels

    Returns:
        True if successful
    """
    if "set_page_labels" in _api_overrides:
        return _api_overrides["set_page_labels"](page_id, labels)

    current = set(get_page_labels(page_id))
    desired = set(labels)

    # Remove unwanted labels
    for label in current - desired:
        remove_page_label(page_id, label)

    # Add missing labels
    to_add = list(desired - current)
    if to_add:
        add_page_labels(page_id, to_add)

    return True


def get_attachments(page_id: str, expand: str = "") -> dict:
    """Get attachments for a page.

    Args:
        page_id: Page ID
        expand: Optional expansions

    Returns:
        Attachment response dict with 'results' and '_links'
    """
    if "get_attachments" in _api_overrides:
        return _api_overrides["get_attachments"](page_id, expand)

    base_url, auth = _get_auth()
    params = {"expand": expand} if expand else {}
    r = requests.get(
        f"{base_url}/content/{page_id}/child/attachment",
        params=params,
        auth=auth,
    )
    if not r.ok:
        return {"results": []}
    return r.json()


def upload_attachment(
    page_id: str,
    file_path: Path,
    filename: str | None = None,
) -> dict | None:
    """Upload an attachment to a page.

    Args:
        page_id: Page ID
        file_path: Path to file to upload
        filename: Override filename (defaults to file_path.name)

    Returns:
        Attachment dict or None on error
    """
    if "upload_attachment" in _api_overrides:
        return _api_overrides["upload_attachment"](page_id, file_path, filename)

    base_url, auth = _get_auth()
    name = filename or file_path.name
    headers = {"X-Atlassian-Token": "nocheck"}

    with open(file_path, "rb") as f:
        r = requests.post(
            f"{base_url}/content/{page_id}/child/attachment",
            files={"file": (name, f)},
            headers=headers,
            auth=auth,
        )

    if not r.ok:
        return None
    # Response is a dict with 'results' list containing the attachment
    resp = r.json()
    if "results" in resp and resp["results"]:
        return resp["results"][0]
    return resp


def update_attachment(
    page_id: str,
    attachment_id: str,
    file_path: Path,
    filename: str | None = None,
) -> dict | None:
    """Update an existing attachment.

    Args:
        page_id: Page ID
        attachment_id: Attachment ID
        file_path: Path to new file
        filename: Override filename

    Returns:
        Attachment dict or None on error
    """
    if "update_attachment" in _api_overrides:
        return _api_overrides["update_attachment"](
            page_id, attachment_id, file_path, filename
        )

    base_url, auth = _get_auth()
    name = filename or file_path.name
    headers = {"X-Atlassian-Token": "nocheck"}

    with open(file_path, "rb") as f:
        r = requests.post(
            f"{base_url}/content/{page_id}/child/attachment/{attachment_id}/data",
            files={"file": (name, f)},
            headers=headers,
            auth=auth,
        )

    if not r.ok:
        return None
    return r.json()


def download_attachment(url: str, dest: Path) -> bool:
    """Download an attachment.

    Args:
        url: Full download URL
        dest: Destination file path

    Returns:
        True if successful
    """
    if "download_attachment" in _api_overrides:
        return _api_overrides["download_attachment"](url, dest)

    creds = load_credentials()
    auth = HTTPBasicAuth(creds["email"], creds["api_token"])
    r = requests.get(url, auth=auth)
    if not r.ok:
        return False
    dest.write_bytes(r.content)
    return True


def get_page_property(page_id: str, key: str) -> dict | None:
    """Get a page property.

    Args:
        page_id: Page ID
        key: Property key

    Returns:
        Property dict or None if not found
    """
    if "get_page_property" in _api_overrides:
        return _api_overrides["get_page_property"](page_id, key)

    base_url, auth = _get_auth()
    r = requests.get(f"{base_url}/content/{page_id}/property/{key}", auth=auth)
    if not r.ok:
        return None
    return r.json()


def set_page_property(page_id: str, key: str, value: dict) -> bool:
    """Set a page property (create or update).

    Args:
        page_id: Page ID
        key: Property key
        value: Property value dict

    Returns:
        True if successful
    """
    if "set_page_property" in _api_overrides:
        return _api_overrides["set_page_property"](page_id, key, value)

    base_url, auth = _get_auth()

    # Check if property exists
    existing = get_page_property(page_id, key)

    if existing:
        # Update existing property
        prop_version = existing["version"]["number"]
        r = requests.put(
            f"{base_url}/content/{page_id}/property/{key}",
            json={
                "key": key,
                "value": value,
                "version": {"number": prop_version + 1},
            },
            auth=auth,
        )
    else:
        # Create new property
        r = requests.post(
            f"{base_url}/content/{page_id}/property",
            json={
                "key": key,
                "value": value,
            },
            auth=auth,
        )

    return r.ok
