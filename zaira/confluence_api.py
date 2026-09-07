"""Confluence REST API wrapper functions.

Provides high-level functions for Confluence API calls with test injection support.
"""

from pathlib import Path
from typing import Any, Callable

import requests
from requests.auth import HTTPBasicAuth

from zaira.atlassian_auth import confluence_base_url, resolve_cloud_id
from zaira.errors import ResourceFetchFailed
from zaira.jira_client import (
    get_or_detect_auth_mode,
    get_server_from_config,
    load_credentials,
)

REQUEST_TIMEOUT_SECONDS = 30


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

    mode, cloud_id = get_or_detect_auth_mode(server, creds["email"], creds["api_token"])
    base_url = confluence_base_url(server, mode, cloud_id)
    auth = HTTPBasicAuth(creds["email"], creds["api_token"])
    return base_url, auth


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    files: dict[str, Any] | None = None,
) -> requests.Response:
    """Make an authenticated Confluence REST API request.

    Centralizes auth resolution and the request timeout shared by every
    Confluence API call below. Deliberately a thin wrapper around the
    requests.get/post/put/delete module functions (rather than a
    requests.Session) so tests that patch those functions directly keep
    working unchanged.
    """
    base_url, auth = _get_auth()
    url = f"{base_url}{path}"
    kwargs: dict[str, Any] = {"auth": auth, "timeout": REQUEST_TIMEOUT_SECONDS}
    if params is not None:
        kwargs["params"] = params
    if json_body is not None:
        kwargs["json"] = json_body
    if headers is not None:
        kwargs["headers"] = headers
    if files is not None:
        kwargs["files"] = files

    if method == "GET":
        return requests.get(url, **kwargs)
    if method == "POST":
        return requests.post(url, **kwargs)
    if method == "PUT":
        return requests.put(url, **kwargs)
    if method == "DELETE":
        return requests.delete(url, **kwargs)
    raise ValueError(f"Unsupported HTTP method: {method}")


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

    params = {"expand": expand} if expand else {}
    r = _request("GET", f"/content/{page_id}", params=params)
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

    r = _request("POST", "/content", json_body=payload)
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

    payload = {
        "version": {"number": version + 1},
        "title": title,
        "type": page_type,
        "body": {"storage": {"value": body, "representation": "storage"}},
    }
    r = _request("PUT", f"/content/{page_id}", json_body=payload)
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

    payload: dict[str, Any] = {
        "version": {"number": version + 1},
        "type": page_type,
        "title": title,
    }
    if space_key:
        payload["space"] = {"key": space_key}
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    r = _request("PUT", f"/content/{page_id}", json_body=payload)
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

    r = _request("DELETE", f"/content/{page_id}")
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

    r = _request("GET", f"/content/{page_id}/child/page", params={"limit": limit})
    if not r.ok:
        return []
    return r.json().get("results", [])


def search_pages(cql: str, limit: int = 25, expand: str = "") -> dict:
    """Search pages using Confluence CQL via the /content/search endpoint.

    Note: the plain /content endpoint does not honor the `cql` parameter
    (it returns the default content listing regardless of query), and the
    generic /search endpoint returns 500 for CQL queries on this instance.
    /content/search both honors CQL and returns flat page objects in
    'results', so no normalization is needed.

    Args:
        cql: CQL query string
        limit: Maximum results
        expand: Comma-separated expansions

    Returns:
        Search response dict with 'results' key.
    """
    if "search_pages" in _api_overrides:
        return _api_overrides["search_pages"](cql, limit, expand)

    params: dict[str, Any] = {"cql": cql, "limit": limit}
    if expand:
        params["expand"] = expand
    r = _request("GET", "/content/search", params=params)
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

    r = _request("GET", f"/content/{page_id}/label")
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

    r = _request(
        "POST", f"/content/{page_id}/label", json_body=[{"name": lbl} for lbl in labels]
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

    r = _request("DELETE", f"/content/{page_id}/label/{label}")
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

    params = {"expand": expand} if expand else {}
    r = _request("GET", f"/content/{page_id}/child/attachment", params=params)
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

    name = filename or file_path.name
    headers = {"X-Atlassian-Token": "nocheck"}

    with open(file_path, "rb") as f:
        r = _request(
            "POST",
            f"/content/{page_id}/child/attachment",
            files={"file": (name, f)},
            headers=headers,
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

    name = filename or file_path.name
    headers = {"X-Atlassian-Token": "nocheck"}

    with open(file_path, "rb") as f:
        r = _request(
            "POST",
            f"/content/{page_id}/child/attachment/{attachment_id}/data",
            files={"file": (name, f)},
            headers=headers,
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
    r = requests.get(url, auth=auth, timeout=REQUEST_TIMEOUT_SECONDS)
    # The /wiki/download/attachments/... endpoint rejects API-token basic auth
    # directly, but works when routed through the api.atlassian.com gateway,
    # which redirects to the media CDN with a signed token.
    if r.status_code == 401 and "/wiki/download/" in url:
        server = get_server_from_config()
        cloud_id = resolve_cloud_id(server) if server else None
        if cloud_id and server and url.startswith(server):
            gateway_url = (
                f"https://api.atlassian.com/ex/confluence/{cloud_id}"
                + url[len(server) :]
            )
            r = requests.get(gateway_url, auth=auth, timeout=REQUEST_TIMEOUT_SECONDS)
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

    r = _request("GET", f"/content/{page_id}/property/{key}")
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

    # Check if property exists
    existing = get_page_property(page_id, key)

    if existing:
        # Update existing property
        prop_version = existing["version"]["number"]
        r = _request(
            "PUT",
            f"/content/{page_id}/property/{key}",
            json_body={
                "key": key,
                "value": value,
                "version": {"number": prop_version + 1},
            },
        )
    else:
        # Create new property
        r = _request(
            "POST",
            f"/content/{page_id}/property",
            json_body={
                "key": key,
                "value": value,
            },
        )

    return r.ok


def get_space_root_pages(space_key: str, limit: int = 100) -> list[dict]:
    """Get top-level pages in a space.

    Args:
        space_key: Space key (e.g. "ENG")
        limit: Maximum number of pages to return

    Returns:
        List of page dicts
    """
    if "get_space_root_pages" in _api_overrides:
        return _api_overrides["get_space_root_pages"](space_key, limit)

    r = _request(
        "GET",
        "/content",
        params={
            "spaceKey": space_key,
            "depth": "root",
            "limit": limit,
            "expand": "version",
        },
    )
    if not r.ok:
        return []
    return r.json().get("results", [])


def get_space_root_folders(space_key: str, limit: int = 100) -> list[dict]:
    """Get top-level folders in a space via CQL.

    Args:
        space_key: Space key
        limit: Maximum number of folders to return

    Returns:
        List of folder dicts (only root-level, i.e. those whose only ancestor is the homepage)

    Note:
        Returns [] both when the space has no folders and when the request
        fails -- see _fetch_space_root_folders for the distinction available
        internally to callers that need it (e.g. resolve_folder_path).
    """
    if "get_space_root_folders" in _api_overrides:
        return _api_overrides["get_space_root_folders"](space_key, limit)

    try:
        return _fetch_space_root_folders(space_key, limit)
    except ResourceFetchFailed:
        return []


def _fetch_space_root_folders(space_key: str, limit: int = 100) -> list[dict]:
    """Fetch top-level folders in a space via CQL.

    Raises ResourceFetchFailed if the request fails, as distinct from the
    space legitimately having no folders. Does not consult _api_overrides --
    callers wanting test-injected results should use get_space_root_folders.
    """
    r = _request(
        "GET",
        "/content/search",
        params={
            "cql": f'space="{space_key}" AND type=folder',
            "limit": limit,
            "expand": "ancestors",
        },
    )
    if not r.ok:
        raise ResourceFetchFailed(
            f"could not list folders in space {space_key}: {r.status_code} - {r.reason}"
        )

    results = r.json().get("results", [])
    # Filter to root folders: those with only the homepage as ancestor
    root_folders = [f for f in results if len(f.get("ancestors", [])) <= 1]
    return root_folders


def get_child_folders(content_id: str, limit: int = 100) -> list[dict]:
    """Get child folders of a page or folder.

    Args:
        content_id: Parent content ID
        limit: Maximum number of children to return

    Returns:
        List of folder dicts

    Note:
        Returns [] both when there are no child folders and when the
        request fails -- see _fetch_child_folders for the distinction
        available internally to callers that need it (e.g.
        resolve_folder_path).
    """
    if "get_child_folders" in _api_overrides:
        return _api_overrides["get_child_folders"](content_id, limit)

    try:
        return _fetch_child_folders(content_id, limit)
    except ResourceFetchFailed:
        return []


def _fetch_child_folders(content_id: str, limit: int = 100) -> list[dict]:
    """Fetch child folders of a page or folder.

    Raises ResourceFetchFailed if the request fails, as distinct from the
    parent legitimately having no child folders. Does not consult
    _api_overrides -- callers wanting test-injected results should use
    get_child_folders.
    """
    r = _request("GET", f"/content/{content_id}/child/folder", params={"limit": limit})
    if not r.ok:
        raise ResourceFetchFailed(
            f"could not list child folders of {content_id}: {r.status_code} - {r.reason}"
        )
    return r.json().get("results", [])


def create_folder(
    space_key: str,
    title: str,
    parent_id: str | None = None,
) -> dict | None:
    """Create a new Confluence folder.

    Args:
        space_key: Space key
        title: Folder title
        parent_id: Optional parent folder/page ID

    Returns:
        Created folder dict or None on error
    """
    if "create_folder" in _api_overrides:
        return _api_overrides["create_folder"](space_key, title, parent_id)

    payload: dict[str, Any] = {
        "type": "folder",
        "title": title,
        "space": {"key": space_key},
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    r = _request("POST", "/content", json_body=payload)
    if not r.ok:
        return None
    return r.json()


def resolve_folder_path(
    space_key: str,
    folder_path: str,
    create_missing: bool = False,
) -> str | None:
    """Resolve a folder path like 'dochub/docs' to a folder ID.

    Walks segments left-to-right, matching by title at each level.

    Args:
        space_key: Space key
        folder_path: Slash-separated folder path
        create_missing: Create folders that don't exist

    Returns:
        Folder ID of the final segment, or None if not found
    """
    if "resolve_folder_path" in _api_overrides:
        return _api_overrides["resolve_folder_path"](
            space_key, folder_path, create_missing
        )

    segments = [s.strip() for s in folder_path.strip("/").split("/") if s.strip()]
    if not segments:
        return None

    # Start with root-level folders
    current_folders = get_space_root_folders(space_key)
    parent_id = None

    for segment in segments:
        # Find matching folder by title
        match = None
        for f in current_folders:
            if f["title"] == segment:
                match = f
                break

        if not match:
            if create_missing:
                match = create_folder(space_key, segment, parent_id)
                if not match:
                    return None
            else:
                return None

        parent_id = match["id"]
        # Get children for next level
        current_folders = get_child_folders(parent_id)

    return parent_id


def resolve_folder_path_from_parent(
    space_key: str,
    parent_id: str,
    folder_path: str,
    create_missing: bool = False,
) -> str | None:
    """Resolve a folder path starting from a parent folder ID.

    Similar to resolve_folder_path but starts from a given parent folder
    instead of space root.

    Args:
        space_key: Space key
        parent_id: Parent folder ID to start from
        folder_path: Slash-separated folder path relative to parent
        create_missing: Create folders that don't exist

    Returns:
        Folder ID of the final segment, or None if not found
    """
    if "resolve_folder_path_from_parent" in _api_overrides:
        return _api_overrides["resolve_folder_path_from_parent"](
            space_key, parent_id, folder_path, create_missing
        )

    segments = [s.strip() for s in folder_path.strip("/").split("/") if s.strip()]
    if not segments:
        return parent_id

    # Start with children of the parent folder
    current_folders = get_child_folders(parent_id)
    current_parent = parent_id

    for segment in segments:
        # Find matching folder by title
        match = None
        for f in current_folders:
            if f["title"] == segment:
                match = f
                break

        if not match:
            if create_missing:
                match = create_folder(space_key, segment, current_parent)
                if not match:
                    return None
                print(f"Created folder {match['id']} for {segment}")
            else:
                return None

        current_parent = match["id"]
        # Get children for next level
        current_folders = get_child_folders(current_parent)

    return current_parent


def parse_space_key(ref: str) -> str:
    """Extract space key from a space overview URL or return as-is.

    Handles URLs like:
        https://site.atlassian.net/wiki/spaces/SPACE/overview
        https://site.atlassian.net/wiki/spaces/SPACE/pages/...

    Args:
        ref: Space key or Confluence URL

    Returns:
        Space key string
    """
    import re

    match = re.search(r"/wiki/spaces/([^/]+)", ref)
    if match:
        return match.group(1)
    return ref


def get_personal_space_key() -> str | None:
    """Return the current user's personal space key, or None if not found."""
    base_url, auth = _get_auth()
    try:
        r = requests.get(
            f"{base_url}/user/current",
            params={"expand": "personalSpace"},
            auth=auth,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if r.ok:
            return r.json().get("personalSpace", {}).get("key")
    except Exception:
        pass
    return None
