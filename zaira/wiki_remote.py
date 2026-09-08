"""Remote page fetch/resolution helpers for wiki commands."""

import sys
from pathlib import Path

from zaira import confluence_api
from zaira.jira_client import get_server_from_config
from zaira.types import PageInfo
from zaira.wiki_frontmatter import parse_front_matter


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
        page_id,
        expand="body.storage,version,space,ancestors,children.attachment.version",
    )
    if not page:
        print(f"Error fetching {page_id}", file=sys.stderr)
        return None
    return page


def _extract_attachment_names(page: dict) -> list[str]:
    """Extract attachment filenames from an expanded page response."""
    children = page.get("children") or {}
    attachments = children.get("attachment") or {}
    results = attachments.get("results") or []
    return [a["title"] for a in results if a.get("title")]


def _fetch_labels(page_id: str) -> list[str]:
    """Fetch labels for a page.

    Returns:
        List of label names
    """
    return confluence_api.get_page_labels(page_id)


def _any_file_has_folder_front_matter(files: list[Path]) -> bool:
    """Check if any file has space: or folder: in front matter."""
    for f in files:
        if not f.exists():
            continue
        content = f.read_text(encoding="utf-8")
        fm, _ = parse_front_matter(content)
        if fm.get("space") or fm.get("folder"):
            return True
    return False


def _resolve_space_alias(space_key: str | None) -> str | None:
    """Resolve the 'my' space alias to the personal space key.

    Returns the resolved key, or the input unchanged for non-alias values.
    Exits the process if 'my' cannot be resolved.
    """
    if space_key and space_key.lower() == "my":
        resolved = confluence_api.get_personal_space_key()
        if not resolved:
            print("Error: Could not determine personal space key.", file=sys.stderr)
            sys.exit(1)
        return resolved
    return space_key


def _resolve_parent_from_front_matter(
    filepath: Path,
    default_space: str | None = None,
    mirror_parent_id: str | None = None,
    name_prefix: str = "",
) -> tuple[str | None, str | None]:
    """Resolve parent folder ID and space key from a file's front matter.

    Args:
        filepath: Path to markdown file
        default_space: Fallback space key (from --space flag)
        mirror_parent_id: Base parent folder ID (from --parent in mirror mode)
        name_prefix: Prefix to apply to folder names (from --prefix)

    Returns:
        Tuple of (parent_id, space_key). parent_id is None for space root.
    """
    content = filepath.read_text(encoding="utf-8")
    fm, _ = parse_front_matter(content)

    file_space = _resolve_space_alias(fm.get("space") or default_space)
    folder_path = fm.get("folder")

    if not file_space:
        print(
            f"Error: {filepath} has no 'space:' in front matter and no --space flag",
            file=sys.stderr,
        )
        return None, None

    if not folder_path:
        # No subfolder — use the mirror parent directly or space root
        return mirror_parent_id, file_space

    # Apply prefix to each folder segment
    if name_prefix:
        segments = [s.strip() for s in folder_path.strip("/").split("/") if s.strip()]
        prefixed_segments = [f"{name_prefix}{seg}" for seg in segments]
        folder_path = "/".join(prefixed_segments)

    # Resolve folder path from mirror parent or space root
    if mirror_parent_id:
        parent_id = confluence_api.resolve_folder_path_from_parent(
            file_space, mirror_parent_id, folder_path, create_missing=True
        )
    else:
        parent_id = confluence_api.resolve_folder_path(
            file_space, folder_path, create_missing=True
        )

    if not parent_id:
        print(
            f"Error: Could not resolve folder path '{folder_path}' in space '{file_space}'",
            file=sys.stderr,
        )
        return None, None

    return parent_id, file_space


def _get_page_info(page_id: str) -> PageInfo | None:
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

    return PageInfo(parent_id=parent_id, space_key=space_key)
