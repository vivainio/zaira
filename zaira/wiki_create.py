"""Creating new Confluence pages from local markdown files."""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from zaira import confluence_api
from zaira.mdconv import (
    cleanup_render_temps,
    markdown_to_storage,
    render_diagram_blocks,
    storage_to_markdown,
)
from zaira.wiki_frontmatter import parse_front_matter, write_front_matter
from zaira.wiki_images import download_images, sync_images
from zaira.wiki_paths import _build_folder_path, slugify
from zaira.wiki_remote import _extract_attachment_names, _fetch_labels
from zaira.wiki_sync import set_sync_property


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
    space_key = page.get("space", {}).get("key")
    ancestors = page.get("ancestors", [])

    # Convert to markdown
    md_body = storage_to_markdown(body_html)
    front_matter = {
        "confluence": int(page_id),
        "title": title,
    }
    if space_key:
        front_matter["space"] = space_key
    folder_path = _build_folder_path(ancestors)
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

    content = write_front_matter(front_matter, md_body)

    # Write file (create subdirs from folder path)
    file_dir = output_dir
    if folder_path:
        file_dir = output_dir / folder_path
        file_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{slugify(title)}.md"
    filepath = file_dir / filename
    filepath.write_text(content, encoding="utf-8")

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


def _create_page_for_file(
    filepath: Path,
    parent_id: str | None,
    space_key: str,
    renderers: list[str] | None = None,
    title_prefix: str = "",
) -> bool:
    """Create a new Confluence page for a markdown file.

    Args:
        filepath: Path to markdown file
        parent_id: Parent page/folder ID
        space_key: Space key
        renderers: Optional list of diagram renderers
        title_prefix: Prefix to add to page title (for --prefix flag)

    Returns:
        True if successful, False otherwise
    """
    body_content = filepath.read_text(encoding="utf-8")
    front_matter, body_only = parse_front_matter(body_content)

    # Title priority: front matter > first heading > filename
    title = front_matter.get("title")
    if not title:
        for line in body_only.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if not title:
        title = filepath.stem.replace("-", " ").replace("_", " ").title()

    # Apply prefix to title
    if title_prefix:
        title = f"{title_prefix}{title}"

    # Render diagram blocks to PNG (if requested and tools available)
    body_only, render_temps = render_diagram_blocks(body_only, renderers)

    # Convert to storage format
    storage_content = markdown_to_storage(body_only)

    # Create page
    result = confluence_api.create_page(space_key, title, storage_content, parent_id)

    if not result:
        cleanup_render_temps(render_temps)
        print(f"Error creating page for {filepath}", file=sys.stderr)
        return False

    new_page_id = result["id"]
    new_version = result["version"]["number"]

    # Update file with front matter
    front_matter["confluence"] = int(new_page_id)
    new_content = write_front_matter(front_matter, body_only)
    filepath.write_text(new_content, encoding="utf-8")

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

    # Upload images if any (including rendered diagram PNGs)
    stored_image_hashes: dict[str, str] = {}
    sync_images(new_page_id, filepath, body_only, stored_image_hashes)
    cleanup_render_temps(render_temps)

    print(f"Created page {new_page_id} for {filepath}")
    return True
