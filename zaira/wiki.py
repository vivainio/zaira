"""Confluence API commands."""

import argparse
import re
import sys

import requests
from requests.auth import HTTPBasicAuth

from zaira.jira_client import load_credentials, get_server_from_config
from zaira.mdconv import markdown_to_storage, storage_to_markdown


def get_confluence_auth() -> tuple[str, HTTPBasicAuth]:
    """Get Confluence base URL and auth.

    Returns:
        Tuple of (base_url, auth)
    """
    creds = load_credentials()
    server = get_server_from_config()

    if not server or not creds.get("email") or not creds.get("api_token"):
        print("Error: Credentials not configured", file=sys.stderr)
        print("Run 'zaira init' to set up credentials.", file=sys.stderr)
        sys.exit(1)

    base_url = server + "/wiki/rest/api"
    auth = HTTPBasicAuth(creds["email"], creds["api_token"])
    return base_url, auth


def parse_page_id(page_ref: str) -> str:
    """Parse page ID from URL or return as-is if numeric.

    Args:
        page_ref: Page ID or Confluence URL

    Returns:
        Page ID string
    """
    # If it's just a number, return it
    if page_ref.isdigit():
        return page_ref

    # Try to extract from URL patterns:
    # https://site.atlassian.net/wiki/spaces/SPACE/pages/123456/Title
    # https://site.atlassian.net/wiki/pages/viewpage.action?pageId=123456
    match = re.search(r"/pages/(\d+)", page_ref)
    if match:
        return match.group(1)

    match = re.search(r"pageId=(\d+)", page_ref)
    if match:
        return match.group(1)

    # Assume it's already an ID
    return page_ref


def get_command(args: argparse.Namespace) -> None:
    """Get a Confluence page by ID or URL."""
    base_url, auth = get_confluence_auth()
    page_id = parse_page_id(args.page)

    r = requests.get(
        f"{base_url}/content/{page_id}",
        params={"expand": "body.storage,version,space"},
        auth=auth,
    )

    if not r.ok:
        print(f"Error: {r.status_code} - {r.reason}", file=sys.stderr)
        if r.status_code == 404:
            print(f"Page not found: {page_id}", file=sys.stderr)
        else:
            print(r.text, file=sys.stderr)
        sys.exit(1)

    page = r.json()
    title = page["title"]
    space_key = page["space"]["key"]
    space_name = page["space"]["name"]
    version = page["version"]["number"]
    body_html = page["body"]["storage"]["value"]

    if args.format == "json":
        import json
        print(json.dumps(page, indent=2))
    elif args.format == "html":
        print(f"Title: {title}")
        print(f"Space: {space_name} ({space_key})")
        print(f"Version: {version}")
        print(f"Page ID: {page_id}")
        print()
        print(body_html)
    else:
        # Default: md - convert storage format to markdown
        print(f"Title: {title}")
        print(f"Space: {space_name} ({space_key})")
        print(f"Version: {version}")
        print(f"Page ID: {page_id}")
        print()
        print(storage_to_markdown(body_html))


def search_command(args: argparse.Namespace) -> None:
    """Search Confluence pages using CQL."""
    base_url, auth = get_confluence_auth()

    # Build CQL query
    cql_parts = []

    # Text search - search in title and body (optional if creator specified)
    query = args.query
    if query:
        cql_parts.append(f'text ~ "{query}"')

    # Optional space filter
    if args.space:
        cql_parts.append(f'space = "{args.space}"')

    # Optional creator filter
    if args.creator:
        cql_parts.append(f'creator.fullname ~ "{args.creator}"')

    # Only search pages (not attachments, comments, etc.)
    cql_parts.append("type = page")

    cql = " AND ".join(cql_parts)

    r = requests.get(
        f"{base_url}/content/search",
        params={
            "cql": cql,
            "limit": args.limit,
            "expand": "space,version",
        },
        auth=auth,
    )

    if not r.ok:
        print(f"Error: {r.status_code} - {r.reason}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        sys.exit(1)

    data = r.json()
    results = data.get("results", [])

    if args.format == "json":
        import json
        print(json.dumps(data, indent=2))
        return

    if not results:
        print("No results found.", file=sys.stderr)
        sys.exit(0)

    # Get base wiki URL for building links
    server = get_server_from_config()
    wiki_base = server + "/wiki"

    for page in results:
        page_id = page["id"]
        title = page["title"]
        space_key = page["space"]["key"]

        # Build URL from _links if available, otherwise construct it
        if "_links" in page and "webui" in page["_links"]:
            url = wiki_base + page["_links"]["webui"]
        else:
            url = f"{wiki_base}/spaces/{space_key}/pages/{page_id}"

        if args.format == "url":
            print(url)
        elif args.format == "id":
            print(page_id)
        else:
            # Default: show title, space, and URL
            print(f"{title}")
            print(f"  Space: {space_key} | ID: {page_id}")
            print(f"  {url}")
            print()


def attach_command(args: argparse.Namespace) -> None:
    """Upload attachments to a Confluence page."""
    base_url, auth = get_confluence_auth()
    page_id = parse_page_id(args.page)

    # Expand glob patterns and collect files
    import glob
    from pathlib import Path

    files_to_upload = []
    for pattern in args.files:
        matches = glob.glob(pattern)
        if matches:
            files_to_upload.extend(matches)
        else:
            # Treat as literal filename if no glob match
            files_to_upload.append(pattern)

    if not files_to_upload:
        print("Error: No files to upload", file=sys.stderr)
        sys.exit(1)

    # Get existing attachments to check for duplicates
    existing = {}
    if args.replace:
        r = requests.get(
            f"{base_url}/content/{page_id}/child/attachment",
            auth=auth,
        )
        if r.ok:
            for att in r.json().get("results", []):
                existing[att["title"]] = att["id"]

    # Upload each file
    uploaded = []
    for filepath in files_to_upload:
        path = Path(filepath)
        if not path.exists():
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            continue

        # Confluence attachment API requires multipart form data
        # The header X-Atlassian-Token: nocheck is required to bypass XSRF protection
        headers = {"X-Atlassian-Token": "nocheck"}

        # Check if attachment already exists - use POST to data endpoint to update
        if path.name in existing:
            att_id = existing[path.name]
            with open(path, "rb") as f:
                r = requests.post(
                    f"{base_url}/content/{page_id}/child/attachment/{att_id}/data",
                    files={"file": (path.name, f)},
                    headers=headers,
                    auth=auth,
                )
            action = "Updated"
        else:
            with open(path, "rb") as f:
                r = requests.post(
                    f"{base_url}/content/{page_id}/child/attachment",
                    files={"file": (path.name, f)},
                    headers=headers,
                    auth=auth,
                )
            action = "Uploaded"

        if not r.ok:
            # Check for duplicate attachment error
            if r.status_code == 400 and "same file name" in r.text:
                print(f"Error: {path.name} already exists. Use --replace to update.", file=sys.stderr)
            else:
                print(f"Error uploading {path.name}: {r.status_code} - {r.reason}", file=sys.stderr)
                print(r.text, file=sys.stderr)
            continue

        uploaded.append((path.name, action))
        print(f"{action}: {path.name}")

    if uploaded:
        print(f"\nTo reference in page body:")
        for name, _ in uploaded:
            print(f'  <ac:image><ri:attachment ri:filename="{name}"/></ac:image>')
    else:
        sys.exit(1)


def create_command(args: argparse.Namespace) -> None:
    """Create a new Confluence page."""
    base_url, auth = get_confluence_auth()

    # Read body from stdin if '-'
    if args.body == "-":
        body_content = sys.stdin.read()
    else:
        body_content = args.body

    if not body_content.strip():
        print("Error: Body content cannot be empty", file=sys.stderr)
        sys.exit(1)

    # Convert markdown to Confluence storage format if requested
    if args.markdown:
        body_content = markdown_to_storage(body_content)

    # Build create payload
    create_payload = {
        "type": "page",
        "title": args.title,
        "space": {"key": args.space},
        "body": {
            "storage": {
                "value": body_content,
                "representation": "storage",
            }
        },
    }

    # Optional parent page
    if args.parent:
        parent_id = parse_page_id(args.parent)
        create_payload["ancestors"] = [{"id": parent_id}]

    r = requests.post(
        f"{base_url}/content",
        json=create_payload,
        auth=auth,
    )

    if not r.ok:
        print(f"Error: {r.status_code} - {r.reason}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        sys.exit(1)

    result = r.json()
    page_id = result["id"]
    server = get_server_from_config()
    url = f"{server}/wiki/spaces/{args.space}/pages/{page_id}"
    print(f"Created page {page_id}: {url}")


def put_command(args: argparse.Namespace) -> None:
    """Update a Confluence page."""
    base_url, auth = get_confluence_auth()
    page_id = parse_page_id(args.page)

    # Read body from stdin if '-'
    if args.body == "-":
        body_content = sys.stdin.read()
    else:
        body_content = args.body

    if not body_content.strip():
        print("Error: Body content cannot be empty", file=sys.stderr)
        sys.exit(1)

    # Convert markdown to Confluence storage format if requested
    if args.markdown:
        body_content = markdown_to_storage(body_content)

    # Get current page to retrieve version and title
    r = requests.get(
        f"{base_url}/content/{page_id}",
        params={"expand": "version"},
        auth=auth,
    )

    if not r.ok:
        print(f"Error: {r.status_code} - {r.reason}", file=sys.stderr)
        if r.status_code == 404:
            print(f"Page not found: {page_id}", file=sys.stderr)
        else:
            print(r.text, file=sys.stderr)
        sys.exit(1)

    page = r.json()
    current_version = page["version"]["number"]
    current_title = page["title"]

    # Build update payload
    update_payload = {
        "version": {"number": current_version + 1},
        "title": args.title if args.title else current_title,
        "type": page["type"],
        "body": {
            "storage": {
                "value": body_content,
                "representation": "storage",
            }
        },
    }

    r = requests.put(
        f"{base_url}/content/{page_id}",
        json=update_payload,
        auth=auth,
    )

    if not r.ok:
        print(f"Error: {r.status_code} - {r.reason}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        sys.exit(1)

    result = r.json()
    new_version = result["version"]["number"]
    print(f"Updated page {page_id} (version {current_version} -> {new_version})")


def wiki_command(args: argparse.Namespace) -> None:
    """Handle wiki subcommand."""
    if hasattr(args, "wiki_func"):
        args.wiki_func(args)
    else:
        print("Usage: zaira wiki <subcommand>")
        print("Subcommands: get, search, create, put, attach")
        sys.exit(1)
