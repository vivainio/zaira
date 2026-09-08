"""Confluence API commands."""

import argparse
import json
import re
import sys
from pathlib import Path

from zaira import confluence_api
from zaira.jira_client import get_server_from_config
from zaira.mdconv import markdown_to_storage, storage_to_markdown
from zaira.wiki_create import _create_page_for_file as _create_page_for_file
from zaira.wiki_create import _export_page_to_file
from zaira.wiki_frontmatter import parse_front_matter as parse_front_matter
from zaira.wiki_frontmatter import write_front_matter
from zaira.wiki_paths import _append_section_slug, _build_folder_path, parse_page_id
from zaira.wiki_paths import slugify as slugify
from zaira.wiki_put import _put_one_file as _put_one_file
from zaira.wiki_put import put_command as put_command
from zaira.wiki_remote import (
    _extract_attachment_names,
    _fetch_labels,
    _fetch_page,
    _get_children,
    _get_page_info,
    _print_page_tree,
)
from zaira.wiki_remote import (
    _resolve_parent_from_front_matter as _resolve_parent_from_front_matter,
)
from zaira.wiki_sync import check_images_changed as check_images_changed
from zaira.wiki_sync import compute_file_hash as compute_file_hash
from zaira.wiki_sync import compute_sync_state as compute_sync_state
from zaira.wiki_sync import get_sync_property as get_sync_property
from zaira.wiki_sync import set_sync_property as set_sync_property

# Property key prefix for idempotent append sections (one property per section id)
APPEND_PROPERTY_PREFIX = "zaira-append-"


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
                "space": space_key,
            }
            folder_path = _build_folder_path(page.get("ancestors", []))
            if folder_path:
                front_matter["folder"] = folder_path
            # Add labels if any
            labels = _fetch_labels(page_id)
            if labels:
                front_matter["labels"] = labels
            # Add attachments if any
            attachments = _extract_attachment_names(page)
            if attachments:
                front_matter["attachments"] = attachments
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
    if args.cql:
        cql = args.cql
    else:
        cql_parts = []

        # Text search - search in title and body (optional if creator specified)
        query = args.query
        if query:
            cql_parts.append(f'text ~ "{query}"')

        # Optional space filter
        if args.space:
            space = args.space
            if space.lower() == "my":
                space = confluence_api.get_personal_space_key()
                if not space:
                    print(
                        "Error: Could not determine personal space key.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            cql_parts.append(f'space = "{space}"')

        # Optional creator filter
        if args.creator:
            cql_parts.append(f'creator.fullname ~ "{args.creator}"')

        # Optional label filter — the value must be quoted or Confluence's
        # CQL parser fails silently on hyphenated label names (e.g.
        # "aws-services" without quotes returns a "could not parse cql" error)
        if args.label:
            cql_parts.append(f'label = "{args.label}"')

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

    if args.format == "toon":
        try:
            import toon_format
        except ImportError:
            print(
                "Error: toon-format package not installed. Run: pip install toon-format",
                file=sys.stderr,
            )
            sys.exit(1)
        print(toon_format.encode(data))
        return

    if not results:
        print("No results found.", file=sys.stderr)
        sys.exit(0)

    # Get base wiki URL for building links
    server = get_server_from_config()
    wiki_base = (server or "") + "/wiki"

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
            # Default: YAML-ish output
            print(f"- title: {title}")
            print(f"  space: {space_key}")
            print(f'  id: "{page_id}"')
            print(f"  url: {url}")
            excerpt = page.get("excerpt", "")
            if excerpt:
                # Strip HTML tags and Confluence highlight markers
                clean = re.sub(r"@@@(end)?hl@@@", "", excerpt)
                clean = re.sub(r"<[^>]+>", "", clean).strip()
                clean = clean[:200]
                if clean:
                    lines = clean.split("\n")
                    if len(lines) > 1:
                        print("  excerpt: |")
                        for line in lines:
                            print(f"    {line}")
                    else:
                        print(f"  excerpt: {clean}")


def get_attachment_command(args: argparse.Namespace) -> None:
    """Download attachments from a Confluence page by filename pattern."""
    from fnmatch import fnmatch

    page_id = parse_page_id(args.page)
    pattern = args.pattern
    output_dir = Path(getattr(args, "output", None) or ".")

    data = confluence_api.get_attachments(page_id, expand="version")
    attachments = data.get("results", [])
    if not attachments:
        print(f"No attachments on page {page_id}")
        return

    matched = [a for a in attachments if fnmatch(a["title"], pattern)]
    if not matched:
        print(f"No attachments matching '{pattern}' on page {page_id}")
        print("Available attachments:")
        for a in attachments:
            size_kb = (a.get("extensions", {}).get("fileSize") or 0) // 1024
            print(f"  {a['title']} ({size_kb} KB)")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    download_base = data.get("_links", {}).get("base") or get_server_from_config()

    print(f"Downloading {len(matched)} attachment(s) from page {page_id}...")
    success = 0
    for att in matched:
        size_kb = (att.get("extensions", {}).get("fileSize") or 0) // 1024
        name = att["title"]
        download_url = download_base + att["_links"]["download"]
        dest = output_dir / name
        print(f"  {name} ({size_kb} KB)...", end=" ")
        if confluence_api.download_attachment(download_url, dest):
            print("done")
            success += 1
        else:
            print("failed")

    print(f"\nDownloaded {success}/{len(matched)} files to {output_dir}/")
    if success < len(matched):
        sys.exit(1)


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
    """Create a new Confluence page from stdin (markdown)."""
    body_content = sys.stdin.read()

    if not body_content.strip():
        print(
            "Error: No content on stdin. Pipe markdown content to this command.",
            file=sys.stderr,
        )
        sys.exit(1)

    body_content = markdown_to_storage(body_content)

    # Optional parent page
    parent_id = parse_page_id(args.parent) if args.parent else None

    # Determine space: from --space flag, or infer from parent
    space_key = args.space
    if space_key and space_key.lower() == "my":
        space_key = confluence_api.get_personal_space_key()
        if not space_key:
            print("Error: Could not determine personal space key.", file=sys.stderr)
            sys.exit(1)
    if not space_key:
        if not parent_id:
            print("Error: Either --space or --parent is required", file=sys.stderr)
            sys.exit(1)
        info = _get_page_info(parent_id)
        if not info or not info.space_key:
            print(
                f"Error: Could not get space from parent page {parent_id}",
                file=sys.stderr,
            )
            sys.exit(1)
        space_key = info.space_key

    result = confluence_api.create_page(space_key, args.title, body_content, parent_id)

    if not result:
        print("Error creating page", file=sys.stderr)
        sys.exit(1)

    page_id = result["id"]
    server = get_server_from_config()
    url = f"{server}/wiki/spaces/{space_key}/pages/{page_id}"
    print(f"Created page {page_id}: {url}")


def append_command(args: argparse.Namespace) -> None:
    """Append to a Confluence page, optionally tracked for idempotent replacement.

    Without --section, always appends to the end of the page (plain append,
    no tracking). With --section, the previously-appended block for that
    section id is tracked in a hidden page property (not visible in the
    rendered page or the page source): on re-runs, if that previous block is
    still present verbatim in the page body it is replaced in place;
    otherwise the new content is appended to the end.
    """
    page_id = parse_page_id(args.page)
    section = getattr(args, "section", None)
    section_key = (
        APPEND_PROPERTY_PREFIX + _append_section_slug(section) if section else None
    )

    if args.file == "-":
        content = sys.stdin.read()
    else:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        content = path.read_text(encoding="utf-8")

    if not content.strip():
        print("Error: empty content", file=sys.stderr)
        sys.exit(1)

    raw = getattr(args, "raw", False)
    new_block = content if raw else markdown_to_storage(content)

    page = confluence_api.fetch_page(page_id, expand="version,body.storage")
    if not page:
        print(f"Error fetching page {page_id}", file=sys.stderr)
        sys.exit(1)

    remote_body = page["body"]["storage"]["value"]
    version = page["version"]["number"]
    title = page["title"]

    previous_block = None
    if section_key:
        prop = confluence_api.get_page_property(page_id, section_key)
        previous_block = prop.get("value", {}).get("content") if prop else None

    if previous_block and previous_block in remote_body:
        new_body = remote_body.replace(previous_block, new_block, 1)
        action = "Replaced"
    else:
        new_body = remote_body + new_block
        action = "Appended"

    result = confluence_api.update_page(page_id, title, new_body, version, page["type"])
    if not result:
        print(f"Error updating page {page_id}", file=sys.stderr)
        sys.exit(1)

    if section_key:
        confluence_api.set_page_property(page_id, section_key, {"content": new_block})

    new_version = result["version"]["number"]
    detail = f"section '{section}' on" if section else "to"
    print(f"{action} {detail} page {page_id} (version {version} -> {new_version})")


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
        parent_arg = args.parent
        if "/" in parent_arg:
            # Folder path — resolve to ID
            space_for_resolve = args.space if args.space else current_space
            resolved = confluence_api.resolve_folder_path(
                space_for_resolve, parent_arg, create_missing=False
            )
            if not resolved:
                print(
                    f"Error: Could not resolve folder path '{parent_arg}' in space '{space_for_resolve}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            new_parent = resolved
        else:
            new_parent = parse_page_id(parent_arg)
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
        confirm = input("Type 'yes' to confirm deletion (or use --yes to skip): ")
        if confirm.lower() != "yes":
            print("Deletion cancelled.")
            sys.exit(0)

    # Delete the page
    if not confluence_api.delete_page(page_id):
        print("Error deleting page", file=sys.stderr)
        sys.exit(1)

    print(f"Deleted page {page_id}: {title}")


def ls_command(args: argparse.Namespace) -> None:
    """List pages and folders in a Confluence space."""
    space_key = confluence_api.parse_space_key(args.space)

    if space_key.lower() == "my":
        space_key = confluence_api.get_personal_space_key()
        if not space_key:
            print("Error: Could not determine personal space key.", file=sys.stderr)
            sys.exit(1)

    server = get_server_from_config() or ""
    depth = args.depth

    # Get root pages and folders
    root_pages = confluence_api.get_space_root_pages(space_key)
    root_folders = confluence_api.get_space_root_folders(space_key)

    if not root_pages and not root_folders:
        print(
            f"No content in space '{space_key}' (or space does not exist).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Collect root folder IDs to avoid duplicating them under the homepage
    root_folder_ids = {f["id"] for f in root_folders}

    total = 0
    for folder in root_folders:
        total += _print_content_tree(
            folder, space_key, server, 0, depth, root_folder_ids
        )
    for page in root_pages:
        total += _print_content_tree(page, space_key, server, 0, depth, root_folder_ids)

    print(f"\n{total} item(s) in {space_key}")


def _print_content_tree(
    item: dict,
    space_key: str,
    server: str,
    indent: int,
    max_depth: int,
    skip_folder_ids: set[str] | None = None,
) -> int:
    """Print a page or folder and its children as a tree.

    Args:
        skip_folder_ids: Folder IDs to skip (avoids duplicating root folders
            that also appear as children of the homepage)

    Returns:
        Count of items printed
    """
    item_id = item["id"]
    title = item["title"]
    item_type = item.get("type", "page")
    is_folder = item_type == "folder"

    if is_folder:
        prefix = "[folder] "
        url = f"{server}/wiki/spaces/{space_key}/folder/{item_id}"
    else:
        prefix = ""
        url = f"{server}/wiki/spaces/{space_key}/pages/{item_id}"

    print(f"{'  ' * indent}{prefix}{title} ({item_id})")
    print(f"{'  ' * indent}  {url}")

    count = 1

    if max_depth != 0:
        next_depth = max_depth - 1 if max_depth > 0 else -1

        # Get child folders and pages
        child_folders = confluence_api.get_child_folders(item_id)
        child_pages = confluence_api.get_child_pages(item_id)

        for child in child_folders:
            if skip_folder_ids and child["id"] in skip_folder_ids:
                continue
            child["type"] = "folder"
            count += _print_content_tree(
                child, space_key, server, indent + 1, next_depth
            )
        for child in child_pages:
            count += _print_content_tree(
                child, space_key, server, indent + 1, next_depth
            )

    return count


def wiki_command(args: argparse.Namespace) -> None:
    """Handle wiki subcommand."""
    if hasattr(args, "wiki_func"):
        args.wiki_func(args)
    else:
        print("Usage: zaira wiki <subcommand>")
        print("Subcommands: ls, get, search, create, put, attach, edit, delete")
        sys.exit(1)
