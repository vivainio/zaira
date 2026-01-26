#!/usr/bin/env python3
"""Integration tests for zaira wiki commands.

These tests create real pages in Confluence and perform various operations.
Run with: python wiki_integration_test.py
"""

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Test configuration - space inferred from parent
WIKI_TEST_ROOT_PAGE = "1549893693"  # "Created via zaira" page in ~villevai

# Track created pages for cleanup
created_pages: list[str] = []


def run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a zaira CLI command."""
    full_cmd = f"python -m zaira {cmd}"
    print(f"  $ zaira {cmd}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().split("\n")[:4]:
            print(f"    {line}")
        if result.stdout.count("\n") > 4:
            print("    ...")
    if result.returncode != 0:
        if check:
            print(f"  FAILED: {result.stderr}")
            sys.exit(1)
        else:
            print(f"  (exit {result.returncode})")
    return result


def run_stdin(cmd: str, stdin: str) -> subprocess.CompletedProcess:
    """Run a zaira CLI command with stdin input."""
    full_cmd = f"python -m zaira {cmd}"
    print(f"  $ zaira {cmd} (stdin)")
    result = subprocess.run(full_cmd, shell=True, input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAILED: {result.stderr}")
        sys.exit(1)
    return result


def extract_page_id(output: str) -> str:
    """Extract page ID from 'Created page NNNN' output."""
    match = re.search(r"Created page (\d+)", output)
    return match.group(1) if match else ""


def test_wiki_get_formats():
    """Test wiki get with different output formats."""
    print("\n=== Get page (markdown) ===")
    result = run(f"wiki get {WIKI_TEST_ROOT_PAGE}")
    assert "confluence:" in result.stdout, "Missing confluence front matter"
    assert "title:" in result.stdout, "Missing title in front matter"

    print("\n=== Get page (JSON) ===")
    result = run(f"wiki get {WIKI_TEST_ROOT_PAGE} --format json")
    data = json.loads(result.stdout)
    assert data["id"] == WIKI_TEST_ROOT_PAGE, "Wrong page ID in JSON"
    assert "title" in data, "Missing title in JSON"

    print("\n=== Get page (HTML) ===")
    result = run(f"wiki get {WIKI_TEST_ROOT_PAGE} --format html")
    assert "Title:" in result.stdout, "Missing title in HTML output"


def test_wiki_search():
    """Test wiki search command."""
    print("\n=== Search pages ===")
    result = run('wiki search "zaira" --limit 3')
    assert "zaira" in result.stdout.lower(), "Search results missing expected content"

    print("\n=== Search (URL format) ===")
    result = run('wiki search "zaira" --limit 2 --format url')
    assert "atlassian.net/wiki" in result.stdout, "Missing wiki URL"

    print("\n=== Search (ID format) ===")
    result = run('wiki search "zaira" --limit 2 --format id')
    # Should be just numbers
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            assert line.strip().isdigit(), f"Expected page ID, got: {line}"


def test_wiki_create() -> str:
    """Test creating a new page."""
    print("\n=== Create page ===")
    timestamp = int(time.time())
    title = f"Integration Test {timestamp}"

    result = run(f'wiki create -t "{title}" -b "Test content created at {timestamp}" -p {WIKI_TEST_ROOT_PAGE} -m')

    page_id = extract_page_id(result.stdout)
    assert page_id, "Failed to extract page ID from create output"
    created_pages.append(page_id)
    print(f"  Created page: {page_id}")

    # Verify page exists
    result = run(f"wiki get {page_id}")
    assert title in result.stdout, "Created page title not found"

    return page_id


def test_wiki_edit_title(page_id: str):
    """Test editing page title."""
    print("\n=== Edit title ===")
    new_title = f"Modified Title {int(time.time())}"
    run(f'wiki edit {page_id} -t "{new_title}"')

    result = run(f"wiki get {page_id}")
    assert new_title in result.stdout, "Title not updated"


def test_wiki_edit_labels(page_id: str):
    """Test editing page labels."""
    print("\n=== Edit labels ===")
    run(f'wiki edit {page_id} -l "test,integration,zaira-test"')

    result = run(f"wiki get {page_id}")
    assert "labels:" in result.stdout, "Labels not in front matter"
    assert "integration" in result.stdout, "Label 'integration' not found"


def test_wiki_put_roundtrip(page_id: str):
    """Test put command with status, diff, and update."""
    print("\n=== Put status ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Export page to file
        outfile = Path(tmpdir) / "test.md"
        run(f"wiki get {page_id} -o {tmpdir}")

        # Find the exported file
        md_files = list(Path(tmpdir).glob("*.md"))
        assert md_files, "No markdown file exported"
        outfile = md_files[0]
        print(f"  Exported to: {outfile.name}")

        # Check status (should be in sync)
        result = run(f"wiki put {outfile} --status")
        assert "In sync" in result.stdout or "already in sync" in result.stdout.lower(), \
            "Expected in-sync status after fresh export"

        # Modify the file
        content = outfile.read_text()
        modified = content + f"\n\nModified at {time.time()}\n"
        outfile.write_text(modified)

        print("\n=== Put status (after modify) ===")
        result = run(f"wiki put {outfile} --status")
        assert "Local ahead" in result.stdout or "local" in result.stdout.lower(), \
            "Expected local-ahead status after modification"

        print("\n=== Put diff ===")
        result = run(f"wiki put {outfile} --diff")
        assert "Modified at" in result.stdout or "@@" in result.stdout, \
            "Expected diff output"

        print("\n=== Put (push changes) ===")
        result = run(f"wiki put {outfile}")
        assert "Pushed" in result.stdout or "version" in result.stdout.lower(), \
            "Expected push confirmation"


def test_wiki_put_pull(page_id: str):
    """Test pulling remote changes."""
    print("\n=== Put pull ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Export page
        run(f"wiki get {page_id} -o {tmpdir}")
        md_files = list(Path(tmpdir).glob("*.md"))
        outfile = md_files[0]

        # Modify remote via edit
        run(f'wiki edit {page_id} -t "Pull Test {int(time.time())}"')

        # Pull changes
        result = run(f"wiki put {outfile} --pull")
        assert "Pulled" in result.stdout, "Expected pull confirmation"

        # Verify local file updated
        content = outfile.read_text()
        assert "Pull Test" in content, "Local file not updated with pulled title"


def test_wiki_put_create() -> str:
    """Test creating page via put --create."""
    print("\n=== Put create ===")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        timestamp = int(time.time())
        f.write(f"# New Page via Put {timestamp}\n\n")
        f.write("This page was created using `wiki put --create`.\n")
        tmpfile = Path(f.name)

    try:
        result = run(f"wiki put {tmpfile} --create --parent {WIKI_TEST_ROOT_PAGE}")

        # Extract page ID from output
        match = re.search(r"Created page (\d+)", result.stdout)
        assert match, "Failed to extract page ID from put --create output"
        page_id = match.group(1)
        created_pages.append(page_id)
        print(f"  Created page: {page_id}")

        # Verify front matter was added to file
        content = tmpfile.read_text()
        assert "confluence:" in content, "Front matter not added to file"

        return page_id
    finally:
        tmpfile.unlink()


def test_wiki_list_children():
    """Test listing child pages."""
    print("\n=== List children ===")
    result = run(f"wiki get {WIKI_TEST_ROOT_PAGE} --list")
    # Should show tree structure
    assert WIKI_TEST_ROOT_PAGE in result.stdout or "Created via zaira" in result.stdout, \
        "Root page not in list output"


def test_wiki_get_children():
    """Test exporting with children."""
    print("\n=== Get with children ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run(f"wiki get {WIKI_TEST_ROOT_PAGE} --children -o {tmpdir}")

        # Should have exported multiple files
        md_files = list(Path(tmpdir).glob("*.md"))
        print(f"  Exported {len(md_files)} file(s)")
        assert len(md_files) >= 1, "Expected at least one exported file"


def test_wiki_attach(page_id: str):
    """Test uploading attachments."""
    print("\n=== Attach file ===")

    # Create a simple test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(f"Test attachment content {time.time()}\n")
        tmpfile = Path(f.name)

    try:
        result = run(f"wiki attach {page_id} {tmpfile}")
        assert "Uploaded" in result.stdout or "test" in result.stdout.lower(), \
            "Expected upload confirmation"

        # Test replace
        print("\n=== Attach replace ===")
        tmpfile.write_text(f"Updated content {time.time()}\n")
        result = run(f"wiki attach {page_id} {tmpfile} --replace")
        assert "Updated" in result.stdout or "Uploaded" in result.stdout, \
            "Expected update confirmation"
    finally:
        tmpfile.unlink()


def test_wiki_conflict(page_id: str):
    """Test conflict detection."""
    print("\n=== Conflict detection ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Export page
        run(f"wiki get {page_id} -o {tmpdir}")
        md_files = list(Path(tmpdir).glob("*.md"))
        outfile = md_files[0]

        # Modify local
        content = outfile.read_text()
        outfile.write_text(content + "\nLocal change\n")

        # Modify remote
        run(f'wiki edit {page_id} -t "Conflict Test {int(time.time())}"')

        # Try to push - should detect conflict (message goes to stderr)
        result = run(f"wiki put {outfile}", check=False)
        has_conflict = (
            result.returncode != 0
            or "conflict" in result.stdout.lower()
            or "conflict" in result.stderr.lower()
        )
        assert has_conflict, f"Expected conflict detection, got: stdout={result.stdout!r}, stderr={result.stderr!r}"

        print("\n=== Force push ===")
        result = run(f"wiki put {outfile} --force")
        assert "Pushed" in result.stdout or "version" in result.stdout.lower(), \
            "Expected force push to succeed"


def test_wiki_delete():
    """Test delete command (used in cleanup)."""
    print("\n=== Delete page ===")
    # Create a page specifically for deletion test
    timestamp = int(time.time())
    result = run(f'wiki create -t "Delete Test {timestamp}" -b "To be deleted" -p {WIKI_TEST_ROOT_PAGE} -m')
    page_id = extract_page_id(result.stdout)
    assert page_id, "Failed to create page for delete test"

    result = run(f"wiki delete {page_id} --yes")
    assert "Deleted" in result.stdout, "Expected deletion confirmation"

    # Verify page is gone
    result = run(f"wiki get {page_id}", check=False)
    assert result.returncode != 0, "Page should not exist after deletion"


def cleanup():
    """Delete all created test pages."""
    print("\n=== Cleanup ===")
    for page_id in reversed(created_pages):
        result = run(f"wiki delete {page_id} --yes", check=False)
        if result.returncode == 0:
            print(f"  Deleted {page_id}")
        else:
            print(f"  Failed to delete {page_id} (may already be deleted)")


def main():
    print("=" * 50)
    print("ZAIRA WIKI INTEGRATION TESTS")
    print("=" * 50)
    print(f"Root page: {WIKI_TEST_ROOT_PAGE}")

    try:
        # Basic operations
        test_wiki_get_formats()
        test_wiki_search()

        # Create and modify
        page_id = test_wiki_create()
        test_wiki_edit_title(page_id)
        test_wiki_edit_labels(page_id)

        # Put operations
        test_wiki_put_roundtrip(page_id)
        test_wiki_put_pull(page_id)
        test_wiki_put_create()

        # Hierarchy
        test_wiki_list_children()
        test_wiki_get_children()

        # Attachments
        test_wiki_attach(page_id)

        # Conflict handling
        test_wiki_conflict(page_id)

        # Delete (creates and deletes its own page)
        test_wiki_delete()

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED")
        print("=" * 50)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
