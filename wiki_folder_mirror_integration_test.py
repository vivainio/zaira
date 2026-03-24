#!/usr/bin/env python3
"""Integration tests for zaira wiki put --mirror with folder structure.

Tests that directory structure is mirrored to Confluence folders with --prefix.

Run with: uv run wiki_folder_mirror_integration_test.py

Example:
    zaira wiki put example/ --space basspec --mirror --parent <folder-id> --prefix "Demo - "
"""

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Test configuration
WIKI_TEST_ROOT_FOLDER = "1792999571"  # Parent folder ID in Confluence
WIKI_SPACE = "~anttiste"  # Space key (personal space)

# Track created pages/folders for cleanup
created_items: list[str] = []


def run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a zaira CLI command."""
    full_cmd = f"python -m zaira {cmd}"
    print(f"  $ zaira {cmd}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().split("\n")[:10]:
            print(f"    {line}")
        if result.stdout.count("\n") > 10:
            print("    ...")
    if result.stderr and result.returncode != 0:
        print(f"    stderr: {result.stderr[:200]}")
    if result.returncode != 0:
        if check:
            print(f"  FAILED: {result.stderr}")
            sys.exit(1)
        else:
            print(f"  (exit {result.returncode})")
    return result


def create_test_structure(base_dir: Path) -> None:
    """Create nested markdown files for testing mirror functionality."""
    # Root level file
    (base_dir / "overview.md").write_text(
        """# Project Overview

This is the main overview page at the root level.

## Contents

- Backend API documentation
- Frontend components
""",
        encoding="utf-8",
    )

    # Backend folder
    backend = base_dir / "backend"
    backend.mkdir()
    (backend / "architecture.md").write_text(
        """# Backend Architecture

## Overview

The backend uses a microservices architecture.

## Components

| Service | Port | Description |
|---------|------|-------------|
| API Gateway | 8080 | Main entry point |
| Auth Service | 8081 | Authentication |
| Data Service | 8082 | Data processing |
""",
        encoding="utf-8",
    )

    # Backend/api subfolder
    api = backend / "api"
    api.mkdir()
    (api / "endpoints.md").write_text(
        """# API Endpoints

## REST API

### GET /users
Returns list of users.

### POST /users
Creates a new user.

```json
{
  "name": "John Doe",
  "email": "john@example.com"
}
```
""",
        encoding="utf-8",
    )

    # Frontend folder
    frontend = base_dir / "frontend"
    frontend.mkdir()
    (frontend / "setup.md").write_text(
        """# Frontend Setup

## Prerequisites

- Node.js 18+
- npm or yarn

## Installation

```bash
npm install
npm run dev
```
""",
        encoding="utf-8",
    )

    # Frontend/components subfolder
    components = frontend / "components"
    components.mkdir()
    (components / "buttons.md").write_text(
        """# Button Components

## Primary Button

Used for main actions.

## Secondary Button

Used for secondary actions.

## Icon Button

Button with icon only.
""",
        encoding="utf-8",
    )

    (components / "forms.md").write_text(
        """# Form Components

## Text Input

Standard text input field.

## Select

Dropdown selection component.

## Checkbox

Boolean toggle component.
""",
        encoding="utf-8",
    )


def verify_confluence_structure(
    prefix: str,
) -> dict[str, list[str]]:
    """Verify the created structure in Confluence.

    Returns dict mapping folder paths to list of page titles.
    """
    result = run(f"wiki get {WIKI_TEST_ROOT_FOLDER} --list")
    return {"output": result.stdout}


def extract_created_ids(output: str) -> list[str]:
    """Extract page/folder IDs from command output."""
    ids = []
    # Match "Created page NNNN" or "Created folder NNNN"
    for match in re.finditer(r"Created (?:page|folder) (\d+)", output):
        ids.append(match.group(1))
    return ids


def test_mirror_with_prefix():
    """Test mirroring a directory structure with prefix."""
    print("\n" + "=" * 60)
    print("TEST: Mirror directory with prefix")
    print("=" * 60)

    timestamp = int(time.time())
    prefix = f"Test{timestamp} - "

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "docs"
        base_dir.mkdir()

        print("\n--- Creating test structure ---")
        create_test_structure(base_dir)

        # List created files
        for f in sorted(base_dir.rglob("*.md")):
            rel = f.relative_to(base_dir)
            print(f"  {rel}")

        print(f"\n--- Mirroring to Confluence with prefix '{prefix}' ---")
        result = run(
            f'wiki put "{base_dir}" --space {WIKI_SPACE} --mirror '
            f'--parent {WIKI_TEST_ROOT_FOLDER} --prefix "{prefix}"'
        )

        # Track created items for cleanup
        ids = extract_created_ids(result.stdout)
        created_items.extend(ids)
        print(f"\n  Created {len(ids)} items")

        # Verify correct number of items created
        # Expected: 6 pages + 4 folders = 10 items
        expected_count = 10
        assert len(ids) >= expected_count, (
            f"Expected at least {expected_count} items, got {len(ids)}"
        )
        print(
            f"  OK: Created expected number of items ({len(ids)} >= {expected_count})"
        )

        # Verify front matter was updated in local files
        print("\n--- Verifying front matter updates ---")
        all_have_ids = True
        for md_file in base_dir.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            rel_path = md_file.relative_to(base_dir)

            if "confluence:" not in content:
                print(f"  FAIL: {rel_path} missing confluence: front matter")
                all_have_ids = False
            else:
                print(f"  OK: {rel_path} has confluence ID")

        assert all_have_ids, "Some files missing confluence ID in front matter"

        print("\n--- Test completed ---")
        return True


def cleanup():
    """Delete created test pages/folders."""
    if not created_items:
        print("\nNo items to clean up")
        return

    print(f"\n--- Cleaning up {len(created_items)} items ---")
    for item_id in reversed(created_items):  # Delete children first
        result = run(f"wiki delete {item_id} --yes", check=False)
        if result.returncode == 0:
            print(f"  Deleted {item_id}")
        else:
            print(f"  Failed to delete {item_id}")


def main():
    print("=" * 60)
    print("Wiki Folder Mirror Integration Test")
    print("=" * 60)
    print(f"Space: {WIKI_SPACE}")
    print(f"Parent folder: {WIKI_TEST_ROOT_FOLDER}")

    try:
        test_mirror_with_prefix()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        # Ask before cleanup
        if created_items:
            print(f"\nCreated {len(created_items)} items during test.")
            response = input("Clean up created items? [y/N] ").strip().lower()
            if response == "y":
                cleanup()
            else:
                print("Skipping cleanup. Items left in Confluence.")


if __name__ == "__main__":
    main()
