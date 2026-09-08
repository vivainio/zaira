"""Sync-state computation for wiki put: sync properties, hashing, and diffing
local content/images against the last-recorded remote state."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from zaira import confluence_api
from zaira.mdconv import extract_local_images

# Property key for sync metadata
SYNC_PROPERTY_KEY = "zaira-sync"


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


@dataclass
class SyncState:
    """Comparison of a local file's content against its last-synced state.

    Pure given its inputs: computed entirely from the already-fetched
    remote_version and sync_meta plus local file reads (for image
    hashing) -- it makes no Confluence API calls itself.
    """

    local_hash: str
    local_changed: bool
    remote_changed: bool
    stored_version: int
    stored_image_hashes: dict[str, str] = field(default_factory=dict)


def compute_sync_state(
    filepath: Path,
    body_only: str,
    remote_version: int,
    sync_meta: dict | None,
) -> SyncState:
    """Compare local file content/images against the last-recorded sync state."""
    local_hash = hashlib.sha256(body_only.encode()).hexdigest()

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

    return SyncState(
        local_hash=local_hash,
        local_changed=local_changed,
        remote_changed=remote_changed,
        stored_version=stored_version,
        stored_image_hashes=stored_image_hashes,
    )
