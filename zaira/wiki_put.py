"""`wiki put`: status/diff/pull/push orchestration for markdown files."""

import argparse
import difflib
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
from zaira.wiki_create import _create_page_for_file
from zaira.wiki_frontmatter import parse_front_matter, write_front_matter
from zaira.wiki_images import download_images, sync_images
from zaira.wiki_paths import _build_folder_path, parse_page_id
from zaira.wiki_remote import (
    _any_file_has_folder_front_matter,
    _get_page_info,
    _resolve_parent_from_front_matter,
    _resolve_space_alias,
)
from zaira.wiki_sync import compute_sync_state, get_sync_property, set_sync_property


def _print_sync_status(
    page_id: str,
    filepath: Path,
    remote_version: int,
    sync_meta: dict | None,
    local_changed: bool,
    remote_changed: bool,
) -> None:
    """Print sync status for `wiki put --status`."""
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


def _show_diff(
    filepath: Path, remote_body: str, body_only: str, remote_version: int, raw: bool
) -> None:
    """Print a unified diff between local and remote content for `wiki put --diff`."""
    remote_compare = remote_body if raw else storage_to_markdown(remote_body)
    local_lines = body_only.splitlines(keepends=True)
    remote_lines = remote_compare.splitlines(keepends=True)

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


def _pull_page(
    filepath: Path,
    page_id: str,
    page: dict,
    front_matter: dict,
    raw: bool,
) -> None:
    """Pull remote content down to the local file for `wiki put --pull`."""
    remote_version = page["version"]["number"]
    remote_body = page["body"]["storage"]["value"]
    current_title = page["title"]

    download_images(page_id, filepath)
    md_content = remote_body if raw else storage_to_markdown(remote_body)

    # Sync properties from remote
    front_matter["confluence"] = int(page_id)
    front_matter["title"] = current_title
    front_matter["space"] = page["space"]["key"]
    folder_path = _build_folder_path(page.get("ancestors", []))
    if folder_path:
        front_matter["folder"] = folder_path
    elif "folder" in front_matter:
        del front_matter["folder"]

    # Get labels from remote
    labels = confluence_api.get_page_labels(page_id)
    if labels:
        front_matter["labels"] = labels
    elif "labels" in front_matter:
        del front_matter["labels"]

    new_content = write_front_matter(front_matter, md_content)
    filepath.write_text(new_content, encoding="utf-8")

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


def _push_page(
    filepath: Path,
    page_id: str,
    page: dict,
    front_matter: dict,
    body_only: str,
    sync_meta: dict | None,
    local_hash: str,
    local_changed: bool,
    remote_changed: bool,
    stored_version: int,
    stored_image_hashes: dict[str, str],
    title_override: str | None,
    force: bool,
    raw: bool,
    renderers: list[str] | None,
    mirror_parent_id: str | None,
    name_prefix: str,
) -> bool:
    """Push local content to Confluence for `wiki put` (the default action)."""
    remote_version = page["version"]["number"]
    current_title = page["title"]

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

    if raw:
        image_hashes = stored_image_hashes
        storage_content = body_only
    else:
        # Render diagram blocks to PNG (if requested and tools available)
        body_only, render_temps = render_diagram_blocks(body_only, renderers)

        # Upload images (including rendered diagram PNGs)
        image_hashes = sync_images(page_id, filepath, body_only, stored_image_hashes)
        cleanup_render_temps(render_temps)

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

    # Check if folder changed — move page if needed
    local_folder = front_matter.get("folder")
    local_space = front_matter.get("space") or page["space"]["key"]
    remote_folder = _build_folder_path(page.get("ancestors", []))

    # Apply prefix to local folder path for comparison and resolution
    if local_folder and name_prefix:
        segments = [s.strip() for s in local_folder.strip("/").split("/") if s.strip()]
        prefixed_segments = [f"{name_prefix}{seg}" for seg in segments]
        prefixed_local_folder = "/".join(prefixed_segments)
    else:
        prefixed_local_folder = local_folder

    # In mirror mode, strip the mirror parent's folder path from remote_folder
    # so we compare only the path relative to the mirror parent
    effective_remote_folder = remote_folder
    if mirror_parent_id and remote_folder:
        # Get the mirror parent's folder path
        parent_page = confluence_api.fetch_page(mirror_parent_id, expand="ancestors")
        if parent_page:
            parent_ancestors = parent_page.get("ancestors", [])
            parent_folder_path = _build_folder_path(parent_ancestors)
            # Also include the parent folder's own title
            parent_title = parent_page.get("title", "")
            if parent_folder_path:
                mirror_root_path = f"{parent_folder_path}/{parent_title}"
            else:
                mirror_root_path = parent_title
            # Strip the mirror root path from remote_folder
            if remote_folder.startswith(mirror_root_path + "/"):
                effective_remote_folder = remote_folder[len(mirror_root_path) + 1 :]
            elif remote_folder == mirror_root_path:
                effective_remote_folder = ""

    if prefixed_local_folder != effective_remote_folder and (
        prefixed_local_folder or effective_remote_folder
    ):
        if prefixed_local_folder:
            # Use mirror parent resolution if available
            if mirror_parent_id:
                target_parent = confluence_api.resolve_folder_path_from_parent(
                    local_space,
                    mirror_parent_id,
                    prefixed_local_folder,
                    create_missing=True,
                )
            else:
                target_parent = confluence_api.resolve_folder_path(
                    local_space, prefixed_local_folder, create_missing=True
                )
            if not target_parent:
                print(
                    f"Error: Could not resolve folder path '{prefixed_local_folder}' in space '{local_space}'",
                    file=sys.stderr,
                )
                return False
        else:
            # Moving to space root — no parent
            target_parent = None

        move_result = confluence_api.update_page_properties(
            page_id,
            remote_version,
            page["type"],
            title=new_title,
            parent_id=target_parent,
        )
        if not move_result:
            print(
                f"Error moving {filepath} to folder '{local_folder}'", file=sys.stderr
            )
            return False
        remote_version = move_result["version"]["number"]
        property_changes.append(
            f"folder: '{remote_folder}' -> '{prefixed_local_folder}'"
        )

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


def _put_one_file(
    filepath: Path,
    page_id_override: str | None,
    title_override: str | None,
    pull: bool,
    force: bool,
    status: bool,
    diff: bool = False,
    renderers: list[str] | None = None,
    mirror_parent_id: str | None = None,
    name_prefix: str = "",
    raw: bool = False,
) -> bool:
    """Process a single markdown file for wiki put.

    Fetches the remote page and its sync state, then dispatches to
    whichever of --status/--diff/--pull/(default push) was requested.

    Args:
        filepath: Path to markdown file
        page_id_override: Override page ID from -p flag
        title_override: Override title from -t flag
        pull: Pull remote changes instead of pushing
        force: Force overwrite on conflict
        status: Just show sync status
        diff: Just show diff
        renderers: Diagram renderers
        mirror_parent_id: Parent folder ID for mirror mode
        name_prefix: Prefix for folder names in mirror mode
        raw: Treat file content as literal Confluence storage format (skip markdown conversion)

    Returns:
        True if successful, False otherwise
    """
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return False

    body_content = filepath.read_text(encoding="utf-8")
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

    # Get sync metadata and compare against local file/image state
    sync_meta = get_sync_property(page_id)
    sync_state = compute_sync_state(filepath, body_only, remote_version, sync_meta)

    if status:
        _print_sync_status(
            page_id,
            filepath,
            remote_version,
            sync_meta,
            sync_state.local_changed,
            sync_state.remote_changed,
        )
        return True

    if diff:
        _show_diff(
            filepath, page["body"]["storage"]["value"], body_only, remote_version, raw
        )
        return True

    if pull:
        _pull_page(filepath, page_id, page, front_matter, raw)
        return True

    return _push_page(
        filepath,
        page_id,
        page,
        front_matter,
        body_only,
        sync_meta,
        sync_state.local_hash,
        sync_state.local_changed,
        sync_state.remote_changed,
        sync_state.stored_version,
        sync_state.stored_image_hashes,
        title_override,
        force,
        raw,
        renderers,
        mirror_parent_id,
        name_prefix,
    )


def _parse_renderers(value: str | None) -> list[str] | None:
    """Parse --render flag value into a list of renderer names."""
    if not value:
        return None
    return [r.strip() for r in value.split(",") if r.strip()]


def put_command(args: argparse.Namespace) -> None:
    """Update Confluence page(s) from markdown files."""
    import glob as glob_module

    renderers = _parse_renderers(getattr(args, "render", None))
    mirror_mode = getattr(args, "mirror", False)

    # Collect files to process
    files_to_process: list[Path] = []
    mirror_roots: list[Path] = []

    # Handle positional files argument
    if args.files:
        for pattern in args.files:
            path = Path(pattern)
            if path.is_dir():
                if mirror_mode:
                    files_to_process.extend(path.rglob("*.md"))
                    mirror_roots.append(path.resolve())
                else:
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

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, encoding="utf-8"
            ) as f:
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
                    renderers,
                    raw=getattr(args, "raw", False),
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

    # Mirror mode variables (used later for folder resolution and page creation)
    mirror_parent_id: str | None = None
    mirror_prefix: str = ""

    # Mirror preprocessing: inject space:/folder: into front matter based on path
    if mirror_mode:
        args.create = True  # --mirror implies --create

        mirror_space = getattr(args, "space", None)
        mirror_parent_id = getattr(args, "parent", None)  # This is a folder ID
        mirror_prefix = getattr(args, "prefix", None) or ""

        for filepath in files_to_process:
            if not filepath.exists():
                continue

            # Find matching mirror root
            resolved = filepath.resolve()
            root = None
            for mr in mirror_roots:
                try:
                    resolved.relative_to(mr)
                    root = mr
                    break
                except ValueError:
                    continue

            if root is None:
                # File was specified directly (not from a directory), skip mirror logic
                continue

            # Compute relative folder path (just the subdirectory structure)
            # Use as_posix() to ensure forward slashes on all platforms
            rel_folder = resolved.relative_to(root).parent.as_posix()
            if rel_folder == ".":
                rel_folder = ""

            content = filepath.read_text(encoding="utf-8")
            fm, body = parse_front_matter(content)

            changed = False

            if mirror_space and fm.get("space") != mirror_space:
                fm["space"] = mirror_space
                changed = True

            # Store just the relative folder path (prefix applied during resolution)
            if rel_folder and fm.get("folder") != rel_folder:
                fm["folder"] = rel_folder
                changed = True
            elif not rel_folder and "folder" in fm:
                del fm["folder"]
                changed = True

            if changed:
                filepath.write_text(write_front_matter(fm, body), encoding="utf-8")

        # Validate that all files have a space
        if not mirror_space:
            for filepath in files_to_process:
                if not filepath.exists():
                    continue
                content = filepath.read_text(encoding="utf-8")
                fm, _ = parse_front_matter(content)
                if not fm.get("space") and not fm.get("confluence"):
                    print(
                        "Error: --mirror requires --space (or space: in every file's front matter)",
                        file=sys.stderr,
                    )
                    sys.exit(1)

    # Separate files into linked (have confluence: front matter) and unlinked
    linked_files: list[tuple[Path, str]] = []  # (filepath, page_id)
    unlinked_files: list[Path] = []

    for filepath in files_to_process:
        if not filepath.exists():
            print(f"Warning: File not found: {filepath}", file=sys.stderr)
            continue
        content = filepath.read_text(encoding="utf-8")
        fm, _ = parse_front_matter(content)
        if fm.get("confluence"):
            linked_files.append((filepath, str(fm["confluence"])))
        else:
            unlinked_files.append(filepath)

    # Handle --create for unlinked files
    create_mode = getattr(args, "create", False)
    parent_id = None
    space_key = None
    # Whether each unlinked file resolves its own parent from front matter
    per_file_resolve = False

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
            # Determine parent: mirror mode > --parent flag > front matter > siblings
            if mirror_mode:
                # In mirror mode, use per-file resolution with the mirror parent
                per_file_resolve = True
                space_key = _resolve_space_alias(getattr(args, "space", None))
            elif args.parent:
                parent_id = parse_page_id(args.parent)
                info = _get_page_info(parent_id)
                if info:
                    space_key = info.space_key
                else:
                    print(
                        f"Error: Could not get info for parent page {parent_id}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            elif _any_file_has_folder_front_matter(unlinked_files):
                # Files have space:/folder: in front matter — resolve per-file
                per_file_resolve = True
                space_key = _resolve_space_alias(getattr(args, "space", None))
            elif linked_files:
                # Get parent from linked files - verify they all have same parent
                parents_seen: dict[
                    str | None, str | None
                ] = {}  # parent_id -> space_key
                for _, page_id in linked_files:
                    info = _get_page_info(page_id)
                    if info:
                        parents_seen[info.parent_id] = info.space_key

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
                    "Error: No linked files to determine parent from. Use --parent, --space, or add space:/folder: to front matter.",
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
            renderers,
            mirror_parent_id=mirror_parent_id if mirror_mode else None,
            name_prefix=mirror_prefix if mirror_mode else "",
            raw=getattr(args, "raw", False),
        )
        if success:
            success_count += 1
        else:
            fail_count += 1

    # Create pages for unlinked files
    for filepath in unlinked_files:
        if per_file_resolve:
            file_parent_id, file_space = _resolve_parent_from_front_matter(
                filepath,
                default_space=space_key,
                mirror_parent_id=mirror_parent_id,
                name_prefix=mirror_prefix,
            )
            if file_space is None:
                fail_count += 1
                continue
            success = _create_page_for_file(
                filepath,
                file_parent_id,
                file_space,
                renderers,
                title_prefix=mirror_prefix,
            )
        else:
            assert space_key is not None, (
                "space_key must be set for non-per-file-resolve path"
            )
            success = _create_page_for_file(filepath, parent_id, space_key, renderers)
        if success:
            success_count += 1
        else:
            fail_count += 1

    # Summary for batch operations
    if len(files_to_process) > 1:
        print(f"\nProcessed {success_count} file(s), {fail_count} failed")
