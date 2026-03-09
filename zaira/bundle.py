"""Bundle install/update commands for distributing rules files."""

import datetime
import io
import urllib.request
import zipfile
from pathlib import Path

import yaml

from zaira.jira_client import CONFIG_DIR
from zaira.types import BundleChanges

BUNDLE_META = CONFIG_DIR / "bundle.yaml"
ALLOWED_DIRS = {"rules"}


def _install_from_directory(
    path: Path, source: str, dry_run: bool = False
) -> BundleChanges:
    """Copy rules files from a local directory to config dir.

    Returns:
        Dict with 'added', 'modified', 'removed' file lists
    """
    rules_src = path / "rules"
    if not rules_src.exists():
        raise SystemExit(f"Directory does not contain 'rules/': {path}")
    if not rules_src.is_dir():
        raise SystemExit(f"Expected directory, got file: {rules_src}")

    changes = BundleChanges(added=[], modified=[], removed=[])

    # Track which files we're installing
    installed_files = set()

    # Copy all files from rules/ to CONFIG_DIR/rules/
    for file in rules_src.rglob("*"):
        if file.is_file():
            rel = file.relative_to(rules_src)
            dest = CONFIG_DIR / "rules" / rel
            installed_files.add(dest)

            # Check if file is new or modified
            if not dest.exists():
                changes.added.append(str(rel))
            else:
                if dest.read_bytes() != file.read_bytes():
                    changes.modified.append(str(rel))

            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(file.read_bytes())

    # Check for removed files (only in dry-run or update scenarios)
    if (CONFIG_DIR / "rules").exists():
        for existing in (CONFIG_DIR / "rules").rglob("*"):
            if existing.is_file() and existing not in installed_files:
                rel = existing.relative_to(CONFIG_DIR / "rules")
                # Only report as removed if it looks like a bundle file
                # (skip user customizations by only flagging known bundle files)
                if rel.name in (
                    "rules.yaml",
                    "allowed_fields.txt",
                ) or rel.name.startswith("allowed_fields_"):
                    changes.removed.append(str(rel))

    if not dry_run:
        # Write bundle metadata with source path
        BUNDLE_META.write_text(
            yaml.dump(
                {
                    "source": source,
                    "installed_at": datetime.datetime.utcnow().isoformat(),
                }
            )
        )

    return changes


def _install_from_zip(
    data: bytes, source_url: str | None, dry_run: bool = False
) -> BundleChanges:
    """Validate zip contents, extract to config dir, write bundle.yaml.

    Returns:
        Dict with 'added', 'modified', 'removed' file lists
    """
    changes = BundleChanges(added=[], modified=[], removed=[])

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()

        # Strip single top-level wrapper dir (GitHub convention)
        top_dirs = {n.split("/")[0] for n in names if n.strip("/")}
        if len(top_dirs) == 1:
            wrapper = top_dirs.pop() + "/"
            if all(n.startswith(wrapper) for n in names):
                names = [n[len(wrapper) :] for n in names]

        # Determine actual top-level dirs in (possibly stripped) listing
        actual_top = {n.split("/")[0] for n in names if "/" in n and n.split("/")[0]}
        unknown = actual_top - ALLOWED_DIRS
        if unknown:
            raise SystemExit(
                f"Bundle contains unexpected directories: {unknown!r}. Only {ALLOWED_DIRS} is allowed."
            )

    # Extract, stripping wrapper prefix if present
    installed_files = set()
    with zipfile.ZipFile(io.BytesIO(data)) as zf2:
        all_names = zf2.namelist()
        top_dirs2 = {n.split("/")[0] for n in all_names if n.strip("/")}
        prefix = ""
        if len(top_dirs2) == 1:
            candidate = top_dirs2.pop() + "/"
            if all(n.startswith(candidate) for n in all_names):
                prefix = candidate

        for member in zf2.infolist():
            rel = member.filename
            if prefix:
                if not rel.startswith(prefix):
                    continue
                rel = rel[len(prefix) :]
            if not rel or rel.endswith("/"):
                continue  # skip dirs
            dest = CONFIG_DIR / rel
            installed_files.add(dest)

            member_data = zf2.read(member.filename)

            # Check if file is new or modified
            if not dest.exists():
                changes.added.append(rel)
            else:
                if dest.read_bytes() != member_data:
                    changes.modified.append(rel)

            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(member_data)

    # Check for removed files
    if (CONFIG_DIR / "rules").exists():
        for existing in (CONFIG_DIR / "rules").rglob("*"):
            if existing.is_file() and existing not in installed_files:
                rel = existing.relative_to(CONFIG_DIR / "rules")
                # Only report as removed if it looks like a bundle file
                if rel.name in (
                    "rules.yaml",
                    "allowed_fields.txt",
                ) or rel.name.startswith("allowed_fields_"):
                    changes.removed.append(str(rel))

    if not dry_run and source_url:
        BUNDLE_META.write_text(
            yaml.dump(
                {
                    "source": source_url,
                    "installed_at": datetime.datetime.utcnow().isoformat(),
                }
            )
        )

    return changes


def _print_changes(changes: dict) -> None:
    """Print file changes in a readable format."""
    if changes.added:
        for f in sorted(changes.added):
            print(f"  + {f}")
    if changes.modified:
        for f in sorted(changes.modified):
            print(f"  ~ {f}")
    if changes.removed:
        for f in sorted(changes.removed):
            print(f"  - {f}")

    total = len(changes.added) + len(changes.modified) + len(changes.removed)
    if total == 0:
        print("  (no changes)")


def bundle_install_command(args) -> None:
    source = args.source
    dry_run = getattr(args, "dry_run", False)

    if source.startswith("http://") or source.startswith("https://"):
        print(f"Downloading {source} ...")
        with urllib.request.urlopen(source) as resp:
            data = resp.read()
        changes = _install_from_zip(data, source_url=source, dry_run=dry_run)
        if dry_run:
            print("Would install from:", source)
        else:
            print("Installed from:", source)
    else:
        path = Path(source)
        if not path.exists():
            raise SystemExit(f"Path not found: {path}")
        if path.is_dir():
            print(f"Installing from directory {path} ...")
            changes = _install_from_directory(
                path, source=str(path.resolve()), dry_run=dry_run
            )
            if not dry_run:
                print(f"Bundle installed from {path}")
        else:
            print(f"Installing from zip {path} ...")
            data = path.read_bytes()
            changes = _install_from_zip(data, source_url=None, dry_run=dry_run)
            if not dry_run:
                print(f"Bundle installed from {path}")

    if changes.added or changes.modified or changes.removed:
        _print_changes(changes)
    if dry_run:
        print("\nUse without --dry-run to install.")


def bundle_update_command(args) -> None:
    if not BUNDLE_META.exists():
        raise SystemExit(
            "No bundle installed. Run 'zaira bundle install <source>' first."
        )
    meta = yaml.safe_load(BUNDLE_META.read_text())
    source = meta.get("source")
    if not source:
        raise SystemExit("Installed bundle has no recorded source.")

    dry_run = getattr(args, "dry_run", False)

    if source.startswith("http://") or source.startswith("https://"):
        print(f"Re-fetching {source} ...")
        with urllib.request.urlopen(source) as resp:
            data = resp.read()
        changes = _install_from_zip(data, source_url=source, dry_run=dry_run)
        if dry_run:
            print("Would update from:", source)
        else:
            print("Updated from:", source)
    else:
        path = Path(source)
        if not path.exists():
            raise SystemExit(f"Source directory not found: {path}")
        print(f"Re-copying from {path} ...")
        changes = _install_from_directory(path, source=source, dry_run=dry_run)
        if not dry_run:
            print(f"Bundle updated from {path}")

    if changes.added or changes.modified or changes.removed:
        _print_changes(changes)
    if dry_run:
        print("\nUse without --dry-run to update.")
