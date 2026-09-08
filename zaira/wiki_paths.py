"""Page ID parsing and filesystem/folder path helpers for wiki commands."""

import re


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


def _build_folder_path(ancestors: list[dict]) -> str | None:
    """Build a folder path from a page's ancestors.

    Skips the first ancestor (space homepage) and filters to folder-type
    ancestors only, joining their titles with '/'.

    Returns:
        Folder path like 'dochub/docs', or None if no folder ancestors
    """
    if not ancestors:
        return None

    # Skip homepage (first ancestor), keep only folders
    folder_ancestors = [a for a in ancestors[1:] if a.get("type") == "folder"]
    if not folder_ancestors:
        return None

    return "/".join(a["title"] for a in folder_ancestors)


def _append_section_slug(section: str) -> str:
    """Sanitize a user-supplied section id into a safe content-property key suffix."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", section.strip()).strip("-") or "default"
