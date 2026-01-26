"""Confluence API commands."""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

from zaira.jira_client import load_credentials, get_server_from_config
from zaira.mdconv import (
    markdown_to_storage,
    storage_to_markdown,
    extract_local_images,
)


# Property key for sync metadata
SYNC_PROPERTY_KEY = "zaira-sync"


def parse_front_matter(content: str) -> tuple[dict, str]:
    """Parse YAML front matter from markdown content.

    Args:
        content: Markdown content with optional front matter

    Returns:
        Tuple of (front_matter_dict, body_content)
    """
    import yaml

    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end_match = re.search(r'\n---\s*\n', content[3:])
    if not end_match:
        return {}, content

    end_pos = end_match.end() + 3
    front_matter_str = content[4:end_match.start() + 3]
    body = content[end_pos:]

    try:
        front_matter = yaml.safe_load(front_matter_str) or {}
    except yaml.YAMLError:
        return {}, content

    return front_matter, body


def write_front_matter(front_matter: dict, body: str) -> str:
    """Write YAML front matter to markdown content.

    Args:
        front_matter: Front matter dict
        body: Markdown body content

    Returns:
        Combined content with front matter
    """
    import yaml

    if not front_matter:
        return body

    fm_str = yaml.safe_dump(front_matter, default_flow_style=False, sort_keys=False)
    return f"---\n{fm_str}---\n\n{body.lstrip()}"


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


def get_sync_property(base_url: str, auth: HTTPBasicAuth, page_id: str) -> dict | None:
    """Get sync metadata from page properties.

    Returns:
        Sync metadata dict or None if not found
    """
    r = requests.get(
        f"{base_url}/content/{page_id}/property/{SYNC_PROPERTY_KEY}",
        auth=auth,
    )
    if r.ok:
        return r.json().get("value", {})
    return None


def set_sync_property(
    base_url: str, auth: HTTPBasicAuth, page_id: str, metadata: dict
) -> bool:
    """Set sync metadata in page properties.

    Returns:
        True if successful
    """
    # Check if property exists
    r = requests.get(
        f"{base_url}/content/{page_id}/property/{SYNC_PROPERTY_KEY}",
        auth=auth,
    )

    if r.ok:
        # Update existing property
        prop = r.json()
        prop_version = prop["version"]["number"]
        r = requests.put(
            f"{base_url}/content/{page_id}/property/{SYNC_PROPERTY_KEY}",
            json={
                "key": SYNC_PROPERTY_KEY,
                "value": metadata,
                "version": {"number": prop_version + 1},
            },
            auth=auth,
        )
    else:
        # Create new property
        r = requests.post(
            f"{base_url}/content/{page_id}/property",
            json={
                "key": SYNC_PROPERTY_KEY,
                "value": metadata,
            },
            auth=auth,
        )

    return r.ok


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of file contents."""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def sync_images(
    base_url: str,
    auth: HTTPBasicAuth,
    page_id: str,
    md_file: Path,
    body_content: str,
    stored_image_hashes: dict[str, str],
) -> dict[str, str]:
    """Upload local images as Confluence attachments.

    Args:
        base_url: Confluence API base URL
        auth: Authentication
        page_id: Page ID
        md_file: Path to markdown file (for resolving relative paths)
        body_content: Markdown body content
        stored_image_hashes: Previously stored image hashes

    Returns:
        Dict of {filename: hash} for all synced images
    """
    images = extract_local_images(body_content)
    if not images:
        return {}

    # Get existing attachments
    r = requests.get(
        f"{base_url}/content/{page_id}/child/attachment",
        auth=auth,
    )
    existing = {}
    if r.ok:
        for att in r.json().get("results", []):
            existing[att["title"]] = att["id"]

    image_hashes = {}
    md_dir = md_file.parent

    for alt, rel_path in images:
        img_path = md_dir / rel_path
        if not img_path.exists():
            print(f"  Warning: Image not found: {img_path}", file=sys.stderr)
            continue

        filename = img_path.name
        current_hash = compute_file_hash(img_path)
        image_hashes[filename] = current_hash

        # Check if upload needed
        if stored_image_hashes.get(filename) == current_hash:
            continue  # Image unchanged

        headers = {"X-Atlassian-Token": "nocheck"}

        if filename in existing:
            # Update existing attachment
            att_id = existing[filename]
            with open(img_path, "rb") as f:
                r = requests.post(
                    f"{base_url}/content/{page_id}/child/attachment/{att_id}/data",
                    files={"file": (filename, f)},
                    headers=headers,
                    auth=auth,
                )
            action = "Updated"
        else:
            # Upload new attachment
            with open(img_path, "rb") as f:
                r = requests.post(
                    f"{base_url}/content/{page_id}/child/attachment",
                    files={"file": (filename, f)},
                    headers=headers,
                    auth=auth,
                )
            action = "Uploaded"

        if r.ok:
            print(f"  {action} image: {filename}")
        else:
            print(f"  Error uploading {filename}: {r.status_code}", file=sys.stderr)

    return image_hashes


def download_images(
    base_url: str,
    auth: HTTPBasicAuth,
    page_id: str,
    md_file: Path,
    image_dir: str = "images",
) -> None:
    """Download Confluence attachments to local directory.

    Args:
        base_url: Confluence API base URL
        auth: Authentication
        page_id: Page ID
        md_file: Path to markdown file
        image_dir: Subdirectory for images relative to md file
    """
    # Get attachments
    r = requests.get(
        f"{base_url}/content/{page_id}/child/attachment",
        params={"expand": "version"},
        auth=auth,
    )
    if not r.ok:
        return

    attachments = r.json().get("results", [])
    if not attachments:
        return

    # Create images directory
    img_path = md_file.parent / image_dir
    img_path.mkdir(exist_ok=True)

    server = get_server_from_config()

    for att in attachments:
        filename = att["title"]
        # Only download image files
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
            continue

        download_url = server + att["_links"]["download"]
        r = requests.get(download_url, auth=auth)
        if r.ok:
            (img_path / filename).write_bytes(r.content)
            print(f"  Downloaded image: {filename}")


def sync_one_file(
    filepath: Path,
    base_url: str,
    auth: HTTPBasicAuth,
    push: bool,
    pull: bool,
    status: bool,
    force: bool,
) -> bool:
    """Sync a single markdown file with its Confluence page.

    Returns:
        True if successful, False otherwise
    """
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return False

    # Read file and parse front matter
    file_content = filepath.read_text()
    front_matter, body_content = parse_front_matter(file_content)

    # Get page ID from front matter
    page_id = None
    if front_matter.get("confluence"):
        page_id = str(front_matter["confluence"])

    if not page_id:
        print(f"Skipping {filepath}: no 'confluence:' in front matter", file=sys.stderr)
        return False

    # Get current page info
    r = requests.get(
        f"{base_url}/content/{page_id}",
        params={"expand": "body.storage,version"},
        auth=auth,
    )

    if not r.ok:
        print(f"Error syncing {filepath}: {r.status_code} - {r.reason}", file=sys.stderr)
        if r.status_code == 404:
            print(f"Page not found: {page_id}", file=sys.stderr)
        else:
            print(r.text, file=sys.stderr)
        return False

    page = r.json()
    remote_version = page["version"]["number"]
    remote_body = page["body"]["storage"]["value"]

    # Get sync metadata
    sync_meta = get_sync_property(base_url, auth, page_id)

    # Compute hash of body content only (excluding front matter)
    local_hash = hashlib.sha256(body_content.encode()).hexdigest()

    # Determine sync status
    if sync_meta:
        stored_hash = sync_meta.get("source_hash", "")
        stored_version = sync_meta.get("uploaded_version", 0)

        local_changed = local_hash != stored_hash
        remote_changed = remote_version != stored_version
    else:
        # No sync metadata - first sync
        local_changed = True
        remote_changed = True
        stored_version = 0

    # Handle --status flag
    if status:
        print(f"Page ID: {page_id}")
        print(f"File: {filepath}")
        print(f"Remote version: {remote_version}")
        if sync_meta:
            print(f"Last synced version: {sync_meta.get('uploaded_version', 'N/A')}")
            print(f"Last synced: {sync_meta.get('uploaded_at', 'N/A')}")
            print(f"Local changed: {'Yes' if local_changed else 'No'}")
            print(f"Remote changed: {'Yes' if remote_changed else 'No'}")
            if local_changed and remote_changed:
                print("Status: CONFLICT (both changed)")
            elif local_changed:
                print("Status: Local ahead (safe to push)")
            elif remote_changed:
                print("Status: Remote ahead (safe to pull)")
            else:
                print("Status: In sync")
        else:
            print("Status: Not synced (no metadata)")
        return True

    # Handle --pull flag
    if pull:
        # Download images first
        download_images(base_url, auth, page_id, filepath)

        md_content = storage_to_markdown(remote_body)

        # Preserve/update front matter with confluence page ID
        front_matter["confluence"] = int(page_id)
        new_content = write_front_matter(front_matter, md_content)
        filepath.write_text(new_content)

        new_hash = hashlib.sha256(md_content.encode()).hexdigest()

        # Update sync metadata
        set_sync_property(base_url, auth, page_id, {
            "source_hash": new_hash,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_version": remote_version,
            "source_file": str(filepath),
        })

        print(f"Pulled version {remote_version} to {filepath}")
        return True

    # Handle --push flag or default sync
    if push or (not pull and not status):
        # Check for conflicts unless --force
        if not force and local_changed and remote_changed and sync_meta:
            print(f"Error: Conflict in {filepath}!", file=sys.stderr)
            print(f"  Local file changed since last sync", file=sys.stderr)
            print(f"  Remote changed: version {stored_version} -> {remote_version}", file=sys.stderr)
            print("Use --force to overwrite, or --pull to get remote changes", file=sys.stderr)
            return False

        # Check if there's anything to push
        if not local_changed and not force:
            print(f"{filepath}: already in sync")
            return True

        # Upload images first (before content references them)
        stored_image_hashes = sync_meta.get("images", {}) if sync_meta else {}
        image_hashes = sync_images(
            base_url, auth, page_id, filepath, body_content, stored_image_hashes
        )

        # Convert and push (body only, without front matter)
        storage_content = markdown_to_storage(body_content)

        update_payload = {
            "version": {"number": remote_version + 1},
            "title": page["title"],
            "type": page["type"],
            "body": {
                "storage": {
                    "value": storage_content,
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
            print(f"Error syncing {filepath}: {r.status_code} - {r.reason}", file=sys.stderr)
            print(r.text, file=sys.stderr)
            return False

        result = r.json()
        new_version = result["version"]["number"]

        # Update sync metadata including image hashes
        set_sync_property(base_url, auth, page_id, {
            "source_hash": local_hash,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_version": new_version,
            "source_file": str(filepath),
            "images": image_hashes,
        })

        print(f"Pushed {filepath} to page {page_id} (version {remote_version} -> {new_version})")
        return True

    return True


def sync_command(args: argparse.Namespace) -> None:
    """Sync markdown files with Confluence pages."""
    import glob as glob_module

    base_url, auth = get_confluence_auth()

    # Expand file arguments (globs, directories)
    files_to_sync = []
    for pattern in args.files:
        path = Path(pattern)
        if path.is_dir():
            # Sync all .md files in directory
            files_to_sync.extend(path.glob("*.md"))
        elif "*" in pattern or "?" in pattern:
            # Glob pattern
            files_to_sync.extend(Path(p) for p in glob_module.glob(pattern))
        else:
            files_to_sync.append(path)

    if not files_to_sync:
        print("No markdown files found", file=sys.stderr)
        sys.exit(1)

    # Sync each file
    success_count = 0
    fail_count = 0

    for filepath in files_to_sync:
        success = sync_one_file(
            filepath=filepath,
            base_url=base_url,
            auth=auth,
            push=args.push,
            pull=args.pull,
            status=args.status,
            force=args.force,
        )
        if success:
            success_count += 1
        else:
            fail_count += 1

    # Summary for multiple files
    if len(files_to_sync) > 1:
        print(f"\nSynced {success_count} file(s), {fail_count} failed")

    if fail_count > 0:
        sys.exit(1)


def wiki_command(args: argparse.Namespace) -> None:
    """Handle wiki subcommand."""
    if hasattr(args, "wiki_func"):
        args.wiki_func(args)
    else:
        print("Usage: zaira wiki <subcommand>")
        print("Subcommands: get, search, create, put, attach, sync")
        sys.exit(1)
