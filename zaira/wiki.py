"""Confluence API commands."""

import argparse
import difflib
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from zaira import confluence_api
from zaira.jira_client import get_server_from_config
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
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}, content

    end_pos = end_match.end() + 3
    front_matter_str = content[4 : end_match.start() + 3]
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

    # Use inline style for lists (e.g., labels: [a, b, c])
    class InlineListDumper(yaml.SafeDumper):
        pass

    def represent_list(dumper, data):
        return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)

    InlineListDumper.add_representer(list, represent_list)

    fm_str = yaml.dump(
        front_matter, Dumper=InlineListDumper, default_flow_style=False, sort_keys=False
    )
    return f"---\n{fm_str}---\n\n{body.lstrip()}"


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


def slugify(title: str) -> str:
    """Convert title to filename-safe slug."""
    # Lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "-", slug).strip("-")
    return slug[:80]  # Limit length


def _get_children(page_id: str) -> list[str]:
    """Get all descendant page IDs recursively.

    Returns:
        List of page IDs (children, grandchildren, etc.)
    """
    children = []
    child_pages = confluence_api.get_child_pages(page_id)

    for child in child_pages:
        child_id = child["id"]
        children.append(child_id)
        # Recurse
        children.extend(_get_children(child_id))

    return children


def _print_page_tree(
    page_id: str,
    indent: int = 0,
) -> int:
    """Print page and its children as a tree.

    Returns:
        Count of pages printed (including children)
    """
    # Get page info
    page = confluence_api.fetch_page(page_id, expand="space")
    if not page:
        print(f"{'  ' * indent}Error: Could not fetch {page_id}", file=sys.stderr)
        return 0

    title = page["title"]
    space_key = page["space"]["key"]

    # Build URL
    server = get_server_from_config()
    url = f"{server}/wiki/spaces/{space_key}/pages/{page_id}"

    print(f"{'  ' * indent}{title} ({page_id})")
    print(f"{'  ' * indent}  {url}")

    count = 1

    # Get and print children
    child_pages = confluence_api.get_child_pages(page_id)
    for child in child_pages:
        count += _print_page_tree(child["id"], indent + 1)

    return count


def _fetch_page(page_id: str) -> dict | None:
    """Fetch a single page with body and metadata.

    Returns:
        Page dict or None on error
    """
    page = confluence_api.fetch_page(
        page_id, expand="body.storage,version,space,ancestors"
    )
    if not page:
        print(f"Error fetching {page_id}", file=sys.stderr)
        return None
    return page


def _fetch_labels(page_id: str) -> list[str]:
    """Fetch labels for a page.

    Returns:
        List of label names
    """
    return confluence_api.get_page_labels(page_id)


def _export_page_to_file(
    page: dict,
    output_dir: Path,
) -> Path | None:
    """Export a page to a markdown file with images.

    Returns:
        Path to created file, or None on error
    """
    page_id = page["id"]
    title = page["title"]
    version = page["version"]["number"]
    body_html = page["body"]["storage"]["value"]

    # Convert to markdown
    md_body = storage_to_markdown(body_html)
    front_matter = {
        "confluence": int(page_id),
        "title": title,
    }

    # Add labels if any
    labels = _fetch_labels(page_id)
    if labels:
        front_matter["labels"] = labels

    content = write_front_matter(front_matter, md_body)

    # Write file
    filename = f"{slugify(title)}.md"
    filepath = output_dir / filename
    filepath.write_text(content)

    # Download images
    download_images(page_id, filepath)

    # Set sync metadata so future puts track properly
    local_hash = hashlib.sha256(md_body.encode()).hexdigest()
    set_sync_property(
        page_id,
        {
            "source_hash": local_hash,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_version": version,
            "source_file": str(filepath),
            "images": {},
        },
    )

    return filepath


def get_command(args: argparse.Namespace) -> None:
    """Get Confluence page(s) by ID or URL."""
    # Collect all page IDs to fetch
    page_ids = [parse_page_id(p) for p in args.pages] if args.pages else []

    if not page_ids:
        print("Error: No pages specified", file=sys.stderr)
        sys.exit(1)

    # Handle --list: just print page tree and exit
    if getattr(args, "list", False):
        total = 0
        for pid in page_ids:
            total += _print_page_tree(pid)
        print(f"\n{total} page(s)")
        return

    # Expand children if requested
    if getattr(args, "children", False):
        expanded = []
        for pid in page_ids:
            expanded.append(pid)
            children = _get_children(pid)
            expanded.extend(children)
            if children:
                print(
                    f"Found {len(children)} child page(s) under {pid}", file=sys.stderr
                )
        page_ids = expanded

    output_dir = Path(args.output) if getattr(args, "output", None) else None

    # Single page to stdout (original behavior)
    if len(page_ids) == 1 and not output_dir:
        page_id = page_ids[0]
        page = _fetch_page(page_id)
        if not page:
            sys.exit(1)

        title = page["title"]
        space_key = page["space"]["key"]
        space_name = page["space"]["name"]
        version = page["version"]["number"]
        body_html = page["body"]["storage"]["value"]

        if args.format == "json":
            print(json.dumps(page, indent=2))
        elif args.format == "html":
            print(f"Title: {title}")
            print(f"Space: {space_name} ({space_key})")
            print(f"Version: {version}")
            print(f"Page ID: {page_id}")
            print()
            print(body_html)
        else:
            md_body = storage_to_markdown(body_html)
            front_matter = {
                "confluence": int(page_id),
                "title": title,
            }
            # Add labels if any
            labels = _fetch_labels(page_id)
            if labels:
                front_matter["labels"] = labels
            print(write_front_matter(front_matter, md_body))
        return

    # Multiple pages or output dir specified - write to files
    if not output_dir:
        print("Error: Multiple pages require -o/--output directory", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for page_id in page_ids:
        page = _fetch_page(page_id)
        if not page:
            continue

        filepath = _export_page_to_file(page, output_dir)
        if filepath:
            print(f"Exported: {filepath}")
            success_count += 1

    print(f"\nExported {success_count} page(s) to {output_dir}")


def search_command(args: argparse.Namespace) -> None:
    """Search Confluence pages using CQL."""
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

    data = confluence_api.search_pages(cql, limit=args.limit, expand="space,version")

    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        print(data.get("text", ""), file=sys.stderr)
        sys.exit(1)

    results = data.get("results", [])

    if args.format == "json":
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
    page_id = parse_page_id(args.page)

    # Expand glob patterns and collect files
    import glob as glob_module

    files_to_upload = []
    for pattern in args.files:
        matches = glob_module.glob(pattern)
        if matches:
            files_to_upload.extend(matches)
        else:
            # Treat as literal filename if no glob match
            files_to_upload.append(pattern)

    if not files_to_upload:
        print("Error: No files to upload", file=sys.stderr)
        sys.exit(1)

    # Get existing attachments to check for duplicates
    existing: dict[str, str] = {}
    if args.replace:
        att_data = confluence_api.get_attachments(page_id)
        for att in att_data.get("results", []):
            existing[att["title"]] = att["id"]

    # Upload each file
    uploaded = []
    for filepath in files_to_upload:
        path = Path(filepath)
        if not path.exists():
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            continue

        # Check if attachment already exists - update or upload
        if path.name in existing:
            att_id = existing[path.name]
            result = confluence_api.update_attachment(page_id, att_id, path)
            action = "Updated"
        else:
            result = confluence_api.upload_attachment(page_id, path)
            action = "Uploaded"

        if not result:
            print(
                f"Error uploading {path.name}. Use --replace to update if it exists.",
                file=sys.stderr,
            )
            continue

        uploaded.append((path.name, action))
        print(f"{action}: {path.name}")

    if uploaded:
        print("\nTo reference in page body:")
        for name, _ in uploaded:
            print(f'  <ac:image><ri:attachment ri:filename="{name}"/></ac:image>')
    else:
        sys.exit(1)


def create_command(args: argparse.Namespace) -> None:
    """Create a new Confluence page."""
    # Read body from stdin, file, or use as literal
    if args.body == "-":
        body_content = sys.stdin.read()
    elif Path(args.body).is_file():
        body_content = Path(args.body).read_text()
    else:
        body_content = args.body

    if not body_content.strip():
        print("Error: Body content cannot be empty", file=sys.stderr)
        sys.exit(1)

    # Convert markdown to Confluence storage format if requested
    if args.markdown:
        body_content = markdown_to_storage(body_content)

    # Optional parent page
    parent_id = parse_page_id(args.parent) if args.parent else None

    # Determine space: from --space flag, or infer from parent
    space_key = args.space
    if not space_key:
        if not parent_id:
            print("Error: Either --space or --parent is required", file=sys.stderr)
            sys.exit(1)
        info = _get_page_info(parent_id)
        if not info or not info.get("space_key"):
            print(
                f"Error: Could not get space from parent page {parent_id}",
                file=sys.stderr,
            )
            sys.exit(1)
        space_key = info["space_key"]

    result = confluence_api.create_page(space_key, args.title, body_content, parent_id)

    if not result:
        print("Error creating page", file=sys.stderr)
        sys.exit(1)

    page_id = result["id"]
    server = get_server_from_config()
    url = f"{server}/wiki/spaces/{space_key}/pages/{page_id}"
    print(f"Created page {page_id}: {url}")


def _get_page_info(page_id: str) -> dict | None:
    """Get page info including parent and space.

    Returns:
        Dict with 'parent_id' and 'space_key', or None on error
    """
    page = confluence_api.fetch_page(page_id, expand="ancestors,space")
    if not page:
        return None

    ancestors = page.get("ancestors", [])
    parent_id = ancestors[-1]["id"] if ancestors else None
    space_key = page.get("space", {}).get("key")

    return {"parent_id": parent_id, "space_key": space_key}


def _create_page_for_file(
    filepath: Path,
    parent_id: str,
    space_key: str,
) -> bool:
    """Create a new Confluence page for a markdown file.

    Returns:
        True if successful, False otherwise
    """
    body_content = filepath.read_text()
    front_matter, body_only = parse_front_matter(body_content)

    # Use first heading as title, or filename
    title = None
    for line in body_only.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break
    if not title:
        title = filepath.stem.replace("-", " ").replace("_", " ").title()

    # Convert to storage format
    storage_content = markdown_to_storage(body_only)

    # Create page
    result = confluence_api.create_page(space_key, title, storage_content, parent_id)

    if not result:
        print(f"Error creating page for {filepath}", file=sys.stderr)
        return False

    new_page_id = result["id"]
    new_version = result["version"]["number"]

    # Update file with front matter
    front_matter["confluence"] = int(new_page_id)
    new_content = write_front_matter(front_matter, body_only)
    filepath.write_text(new_content)

    # Set sync metadata
    local_hash = hashlib.sha256(body_only.encode()).hexdigest()
    set_sync_property(
        new_page_id,
        {
            "source_hash": local_hash,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_version": new_version,
            "source_file": str(filepath),
            "images": {},
        },
    )

    # Upload images if any
    stored_image_hashes: dict[str, str] = {}
    sync_images(new_page_id, filepath, body_only, stored_image_hashes)

    print(f"Created page {new_page_id} for {filepath}")
    return True


def _put_one_file(
    filepath: Path,
    page_id_override: str | None,
    title_override: str | None,
    pull: bool,
    force: bool,
    status: bool,
    diff: bool = False,
) -> bool:
    """Process a single markdown file for wiki put.

    Returns:
        True if successful, False otherwise
    """
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return False

    body_content = filepath.read_text()
    if not body_content.strip():
        print(f"Error: File is empty: {filepath}", file=sys.stderr)
        return False

    # Parse front matter
    front_matter, body_only = parse_front_matter(body_content)
    page_id = page_id_override or (
        str(front_matter["confluence"]) if front_matter.get("confluence") else None
    )

    if not page_id:
        print(f"Skipping {filepath}: no 'confluence:' in front matter", file=sys.stderr)
        return False

    # Get current page
    page = confluence_api.fetch_page(
        page_id, expand="version,body.storage,space,ancestors"
    )

    if not page:
        print(f"Error fetching page {page_id}", file=sys.stderr)
        return False

    remote_version = page["version"]["number"]
    remote_body = page["body"]["storage"]["value"]
    current_title = page["title"]

    # Get sync metadata
    sync_meta = get_sync_property(page_id)

    # Compute local content hash
    local_hash = hashlib.sha256(body_only.encode()).hexdigest()

    # Determine sync status
    if sync_meta:
        stored_hash = sync_meta.get("source_hash", "")
        stored_version = sync_meta.get("uploaded_version", 0)
        stored_image_hashes = sync_meta.get("images", {})

        content_changed = local_hash != stored_hash
        images_changed = check_images_changed(filepath, body_only, stored_image_hashes)
        local_changed = content_changed or images_changed
        remote_changed = remote_version != stored_version
    else:
        stored_version = 0
        stored_image_hashes = {}
        local_changed = True
        remote_changed = False

    # Handle --status
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
                print("Status: Local ahead")
            elif remote_changed:
                print("Status: Remote ahead")
            else:
                print("Status: In sync")
        else:
            print("Status: No sync metadata")
        return True

    # Handle --diff
    if diff:
        remote_md = storage_to_markdown(remote_body)
        local_lines = body_only.splitlines(keepends=True)
        remote_lines = remote_md.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                remote_lines,
                local_lines,
                fromfile=f"remote (v{remote_version})",
                tofile=f"local ({filepath})",
            )
        )

        if diff_lines:
            print(f"Diff for {filepath}:")
            print("".join(diff_lines))
        else:
            print(f"{filepath}: no content differences")
        return True

    # Handle --pull
    if pull:
        download_images(page_id, filepath)
        md_content = storage_to_markdown(remote_body)

        # Sync properties from remote
        front_matter["confluence"] = int(page_id)
        front_matter["title"] = current_title

        # Get labels from remote
        labels = confluence_api.get_page_labels(page_id)
        if labels:
            front_matter["labels"] = labels
        elif "labels" in front_matter:
            del front_matter["labels"]

        new_content = write_front_matter(front_matter, md_content)
        filepath.write_text(new_content)

        new_hash = hashlib.sha256(md_content.encode()).hexdigest()
        set_sync_property(
            page_id,
            {
                "source_hash": new_hash,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "uploaded_version": remote_version,
                "source_file": str(filepath),
            },
        )
        print(f"Pulled version {remote_version} to {filepath}")
        return True

    # Handle push (default)
    if not force and sync_meta and local_changed and remote_changed:
        print(f"Conflict in {filepath}: local and remote both changed", file=sys.stderr)
        print(
            f"  Remote: version {stored_version} -> {remote_version}", file=sys.stderr
        )
        print(
            "  Use --diff to see changes, --force to overwrite, or --pull to discard local",
            file=sys.stderr,
        )
        return False

    if sync_meta and not local_changed and not force:
        print(f"{filepath}: already in sync")
        return True

    # Upload images
    image_hashes = sync_images(page_id, filepath, body_only, stored_image_hashes)

    # Convert and push
    storage_content = markdown_to_storage(body_only)
    property_changes = []

    # Determine title: -t flag > front matter > current remote title
    if title_override:
        new_title = title_override
    elif front_matter.get("title") and front_matter["title"] != current_title:
        new_title = front_matter["title"]
    else:
        new_title = current_title

    if new_title != current_title:
        property_changes.append(f"title: '{new_title}'")

    # Note: parent and space are editable via wiki edit only, not synced from front matter
    result = confluence_api.update_page(
        page_id, new_title, storage_content, remote_version, page["type"]
    )
    if not result:
        print(f"Error updating {filepath}", file=sys.stderr)
        return False

    new_version = result["version"]["number"]

    # Sync labels from front matter (separate API)
    if "labels" in front_matter:
        fm_labels = front_matter["labels"]
        if isinstance(fm_labels, str):
            new_labels = {lbl.strip() for lbl in fm_labels.split(",") if lbl.strip()}
        elif isinstance(fm_labels, list):
            new_labels = {str(lbl).strip() for lbl in fm_labels if str(lbl).strip()}
        else:
            new_labels = set()

        # Get current labels
        current_labels = set(confluence_api.get_page_labels(page_id))

        # Remove labels not in front matter
        for label in current_labels - new_labels:
            confluence_api.remove_page_label(page_id, label)

        # Add new labels
        to_add = list(new_labels - current_labels)
        if to_add:
            confluence_api.add_page_labels(page_id, to_add)

        if new_labels != current_labels:
            property_changes.append(f"labels: {sorted(new_labels)}")

    set_sync_property(
        page_id,
        {
            "source_hash": local_hash,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_version": new_version,
            "source_file": str(filepath),
            "images": image_hashes,
        },
    )

    msg = f"Pushed {filepath} (version {remote_version} -> {new_version})"
    if property_changes:
        msg += " [" + ", ".join(property_changes) + "]"
    print(msg)
    return True


def put_command(args: argparse.Namespace) -> None:
    """Update Confluence page(s) from markdown files."""
    import glob as glob_module

    # Collect files to process
    files_to_process: list[Path] = []

    # Handle positional files argument
    if args.files:
        for pattern in args.files:
            path = Path(pattern)
            if path.is_dir():
                files_to_process.extend(path.glob("*.md"))
            elif "*" in pattern or "?" in pattern:
                files_to_process.extend(Path(p) for p in glob_module.glob(pattern))
            else:
                files_to_process.append(path)

    # Handle legacy -b argument
    elif args.body:
        if args.body == "-":
            # Stdin mode - need page ID
            body_content = sys.stdin.read()
            if not body_content.strip():
                print("Error: Empty input from stdin", file=sys.stderr)
                sys.exit(1)

            front_matter, body_only = parse_front_matter(body_content)
            page_id = args.page or (
                str(front_matter["confluence"])
                if front_matter.get("confluence")
                else None
            )

            if not page_id:
                print(
                    "Error: No page ID. Use -p PAGE or include 'confluence:' in front matter",
                    file=sys.stderr,
                )
                sys.exit(1)

            # For stdin, write to temp file and process
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
                f.write(body_content)
                temp_path = Path(f.name)

            try:
                success = _put_one_file(
                    temp_path,
                    page_id,
                    args.title,
                    getattr(args, "pull", False),
                    getattr(args, "force", False),
                    getattr(args, "status", False),
                    getattr(args, "diff", False),
                )
                sys.exit(0 if success else 1)
            finally:
                temp_path.unlink()

        elif Path(args.body).is_file():
            files_to_process.append(Path(args.body))
        else:
            print(f"Error: Not a file: {args.body}", file=sys.stderr)
            sys.exit(1)

    else:
        print("Error: No files specified. Use positional args or -b", file=sys.stderr)
        sys.exit(1)

    if not files_to_process:
        print("No markdown files found", file=sys.stderr)
        sys.exit(1)

    # Separate files into linked (have confluence: front matter) and unlinked
    linked_files: list[tuple[Path, str]] = []  # (filepath, page_id)
    unlinked_files: list[Path] = []

    for filepath in files_to_process:
        if not filepath.exists():
            print(f"Warning: File not found: {filepath}", file=sys.stderr)
            continue
        content = filepath.read_text()
        fm, _ = parse_front_matter(content)
        if fm.get("confluence"):
            linked_files.append((filepath, str(fm["confluence"])))
        else:
            unlinked_files.append(filepath)

    # Handle --create for unlinked files
    create_mode = getattr(args, "create", False)
    parent_id = None
    space_key = None

    skipped_count = 0
    if unlinked_files:
        if not create_mode:
            for f in unlinked_files:
                print(f"Skipping {f}: no 'confluence:' front matter", file=sys.stderr)
                skipped_count += 1
            unlinked_files = []
            if skipped_count > 0:
                print(
                    f"\nSkipped {skipped_count} file(s) without front matter. Use --create to create new pages.",
                    file=sys.stderr,
                )
        else:
            # Determine parent: from --parent flag or from siblings
            if args.parent:
                parent_id = parse_page_id(args.parent)
                info = _get_page_info(parent_id)
                if info:
                    space_key = info["space_key"]
                else:
                    print(
                        f"Error: Could not get info for parent page {parent_id}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            elif linked_files:
                # Get parent from linked files - verify they all have same parent
                parents_seen: dict[str | None, str] = {}  # parent_id -> space_key
                for _, page_id in linked_files:
                    info = _get_page_info(page_id)
                    if info:
                        parents_seen[info["parent_id"]] = info["space_key"]

                if len(parents_seen) == 0:
                    print(
                        "Error: Could not determine parent from existing pages",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                elif len(parents_seen) > 1:
                    print(
                        "Error: Linked files have different parents. Use --parent to specify.",
                        file=sys.stderr,
                    )
                    for pid in parents_seen:
                        print(f"  Parent: {pid}", file=sys.stderr)
                    sys.exit(1)
                else:
                    parent_id = list(parents_seen.keys())[0]
                    space_key = list(parents_seen.values())[0]
                    if parent_id is None:
                        print(
                            "Error: Linked pages have no parent (are at space root). Use --parent to specify.",
                            file=sys.stderr,
                        )
                        sys.exit(1)
            else:
                print(
                    "Error: No linked files to determine parent from. Use --parent to specify.",
                    file=sys.stderr,
                )
                sys.exit(1)

    # Process files
    success_count = 0
    fail_count = 0

    # Process linked files
    for filepath, page_id in linked_files:
        success = _put_one_file(
            filepath,
            args.page if len(files_to_process) == 1 else None,
            args.title if len(files_to_process) == 1 else None,
            getattr(args, "pull", False),
            getattr(args, "force", False),
            getattr(args, "status", False),
            getattr(args, "diff", False),
        )
        if success:
            success_count += 1
        else:
            fail_count += 1

    # Create pages for unlinked files
    for filepath in unlinked_files:
        success = _create_page_for_file(filepath, parent_id, space_key)
        if success:
            success_count += 1
        else:
            fail_count += 1

    # Summary for batch operations
    if len(files_to_process) > 1:
        print(f"\nProcessed {success_count} file(s), {fail_count} failed")


def get_sync_property(page_id: str) -> dict | None:
    """Get sync metadata from page properties.

    Returns:
        Sync metadata dict or None if not found
    """
    prop = confluence_api.get_page_property(page_id, SYNC_PROPERTY_KEY)
    if prop:
        return prop.get("value", {})
    return None


def set_sync_property(page_id: str, metadata: dict) -> bool:
    """Set sync metadata in page properties.

    Returns:
        True if successful
    """
    return confluence_api.set_page_property(page_id, SYNC_PROPERTY_KEY, metadata)


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of file contents."""
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def check_images_changed(
    md_file: Path,
    body_content: str,
    stored_image_hashes: dict[str, str],
) -> bool:
    """Check if any local images have changed compared to stored hashes.

    Args:
        md_file: Path to markdown file
        body_content: Markdown body content
        stored_image_hashes: Dict of filename -> hash from last sync

    Returns:
        True if any image has changed or is new
    """
    images = extract_local_images(body_content)
    if not images:
        return False

    md_dir = md_file.parent

    for _alt, rel_path in images:
        img_path = md_dir / rel_path
        if not img_path.exists():
            continue

        filename = img_path.name
        current_hash = compute_file_hash(img_path)

        if stored_image_hashes.get(filename) != current_hash:
            return True

    return False


def sync_images(
    page_id: str,
    md_file: Path,
    body_content: str,
    stored_image_hashes: dict[str, str],
) -> dict[str, str]:
    """Upload local images as Confluence attachments.

    Args:
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
    att_data = confluence_api.get_attachments(page_id)
    existing: dict[str, str] = {}
    for att in att_data.get("results", []):
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

        if filename in existing:
            # Update existing attachment
            att_id = existing[filename]
            result = confluence_api.update_attachment(page_id, att_id, img_path)
            action = "Updated"
        else:
            # Upload new attachment
            result = confluence_api.upload_attachment(page_id, img_path)
            action = "Uploaded"

        if result:
            print(f"  {action} image: {filename}")
        else:
            print(f"  Error uploading {filename}", file=sys.stderr)

    return image_hashes


def download_images(
    page_id: str,
    md_file: Path,
    image_dir: str = "images",
) -> None:
    """Download Confluence attachments to local directory.

    Args:
        page_id: Page ID
        md_file: Path to markdown file
        image_dir: Subdirectory for images relative to md file
    """
    # Get attachments
    data = confluence_api.get_attachments(page_id, expand="version")
    attachments = data.get("results", [])
    if not attachments:
        return

    # Create images directory
    img_path = md_file.parent / image_dir
    img_path.mkdir(exist_ok=True)

    # Use base URL from response (includes /wiki context path)
    download_base = data.get("_links", {}).get("base", get_server_from_config())

    for att in attachments:
        filename = att["title"]
        # Only download image files
        if not filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
        ):
            continue

        download_url = download_base + att["_links"]["download"]
        dest_path = img_path / filename
        if confluence_api.download_attachment(download_url, dest_path):
            print(f"  Downloaded image: {filename}")


def edit_command(args: argparse.Namespace) -> None:
    """Edit Confluence page properties."""
    page_id = parse_page_id(args.page)

    # Get current page info
    page = confluence_api.fetch_page(page_id, expand="version,space,ancestors")

    if not page:
        print(f"Error: Page not found: {page_id}", file=sys.stderr)
        sys.exit(1)

    current_title = page["title"]
    current_version = page["version"]["number"]
    current_space = page["space"]["key"]
    current_ancestors = page.get("ancestors", [])
    current_parent = current_ancestors[-1]["id"] if current_ancestors else None

    changes = []

    # Determine what needs to change
    new_title = (
        args.title if args.title and args.title != current_title else current_title
    )
    new_parent = None
    new_space = None

    if args.title and args.title != current_title:
        changes.append(f"title: '{current_title}' -> '{args.title}'")

    if args.parent:
        new_parent = parse_page_id(args.parent)
        if new_parent != current_parent:
            changes.append(f"parent: {current_parent} -> {new_parent}")

    if args.space and args.space != current_space:
        new_space = args.space
        changes.append(f"space: {current_space} -> {args.space}")

    # Apply page property updates if any
    if new_title != current_title or new_parent or new_space:
        result = confluence_api.update_page_properties(
            page_id,
            current_version,
            "page",
            title=new_title,
            space_key=new_space,
            parent_id=new_parent,
        )
        if not result:
            print("Error updating page properties", file=sys.stderr)
            sys.exit(1)

    # Handle --labels (separate API)
    if args.labels is not None:
        # Get current labels
        current_labels = set(confluence_api.get_page_labels(page_id))

        # Parse new labels
        new_labels = set()
        if args.labels.strip():
            new_labels = {lbl.strip() for lbl in args.labels.split(",") if lbl.strip()}

        # Remove labels not in new set
        to_remove = current_labels - new_labels
        for label in to_remove:
            if confluence_api.remove_page_label(page_id, label):
                changes.append(f"label removed: {label}")

        # Add new labels
        to_add = list(new_labels - current_labels)
        if to_add:
            if confluence_api.add_page_labels(page_id, to_add):
                for lbl in to_add:
                    changes.append(f"label added: {lbl}")

    if changes:
        print(f"Updated page {page_id}:")
        for change in changes:
            print(f"  {change}")
    else:
        print(f"No changes made to page {page_id}")


def delete_command(args: argparse.Namespace) -> None:
    """Delete a Confluence page."""
    page_id = parse_page_id(args.page)

    # Get page info first to confirm it exists and show title
    page = confluence_api.fetch_page(page_id, expand="space")

    if not page:
        print(f"Error: Page not found: {page_id}", file=sys.stderr)
        sys.exit(1)

    title = page["title"]
    space_key = page["space"]["key"]

    # Confirm deletion unless --yes is specified
    if not args.yes:
        print(f"About to delete: {title}")
        print(f"  Space: {space_key}")
        print(f"  Page ID: {page_id}")
        confirm = input("Type 'yes' to confirm deletion: ")
        if confirm.lower() != "yes":
            print("Deletion cancelled.")
            sys.exit(0)

    # Delete the page
    if not confluence_api.delete_page(page_id):
        print("Error deleting page", file=sys.stderr)
        sys.exit(1)

    print(f"Deleted page {page_id}: {title}")


def wiki_command(args: argparse.Namespace) -> None:
    """Handle wiki subcommand."""
    if hasattr(args, "wiki_func"):
        args.wiki_func(args)
    else:
        print("Usage: zaira wiki <subcommand>")
        print("Subcommands: get, search, create, put, attach, edit, delete")
        sys.exit(1)
