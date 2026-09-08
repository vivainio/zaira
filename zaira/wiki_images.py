"""Image sync between local markdown files and Confluence attachments."""

import sys
from pathlib import Path

from zaira import confluence_api
from zaira.jira_client import get_server_from_config
from zaira.mdconv import extract_local_images
from zaira.wiki_sync import compute_file_hash


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
    download_base = data.get("_links", {}).get("base") or get_server_from_config()

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
