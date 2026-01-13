#!/usr/bin/env python3
"""Integration tests for zaira CLI targeting sandbox project SAN.

These tests create real tickets in Jira and perform various operations on them.
Run with: python integration_test.py
"""

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a zaira CLI command."""
    full_cmd = f"python -m zaira {cmd}"
    print(f"  $ zaira {cmd}")
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().split("\n")[:3]:
            print(f"    {line}")
        if result.stdout.count("\n") > 3:
            print("    ...")
    if result.returncode != 0 and check:
        print(f"  FAILED: {result.stderr}")
        sys.exit(1)
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


def extract_key(output: str) -> str:
    """Extract SAN-### ticket key from output."""
    match = re.search(r"SAN-\d+", output)
    return match.group(0) if match else ""


def test_create_ticket() -> str:
    """Create a test ticket and return its key."""
    print("\n=== Create ticket ===")
    content = f"""\
---
project: SAN
summary: "Integration test {int(time.time())}"
type: Task
priority: Medium
labels: [integration-test, automated]
---

Automated integration test ticket created by zaira.
Created at: {time.strftime("%Y-%m-%d %H:%M:%S")}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        ticket_file = f.name

    result = run(f"create {ticket_file}")
    Path(ticket_file).unlink()

    key = extract_key(result.stdout)
    if not key:
        print("ERROR: Could not extract ticket key")
        sys.exit(1)
    return key


def test_export(key: str):
    """Export and verify ticket."""
    print("\n=== Export ticket ===")
    result = run(f"export {key}")
    assert key in result.stdout
    assert "Integration test" in result.stdout


def test_edit_title(key: str):
    """Edit title."""
    print("\n=== Edit title ===")
    run(f'edit {key} -t "[MODIFIED] Integration test {int(time.time())}"')
    result = run(f"export {key}")
    assert "MODIFIED" in result.stdout


def test_edit_description(key: str):
    """Edit description via stdin."""
    print("\n=== Edit description ===")
    desc = f"Updated description at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    run_stdin(f"edit {key} -d -", desc)


def test_edit_field(key: str):
    """Edit field with -F."""
    print("\n=== Edit field ===")
    run(f'edit {key} -F "Priority=High"')


def test_comments(key: str):
    """Add comments and verify in export."""
    print("\n=== Add comments ===")
    marker1 = f"COMMENT1-{int(time.time())}"
    run(f'comment {key} "Test comment {marker1}"')

    marker2 = f"COMMENT2-{int(time.time())}"
    run_stdin(f"comment {key} -", f"Multiline comment\nMarker: {marker2}")

    print("\n=== Verify comments in export ===")
    result = run(f"export {key}")
    assert marker1 in result.stdout, "Comment 1 not in export"
    assert marker2 in result.stdout, "Comment 2 not in export"


def test_transitions(key: str) -> list[str]:
    """List and test transitions."""
    print("\n=== List transitions ===")
    result = run(f"transition {key} --list")

    statuses = []
    for line in result.stdout.split("\n"):
        if "→" in line:
            target = line.split("→")[-1].strip()
            if target:
                statuses.append(target)

    print("\n=== Transition ticket ===")
    for target in ["In Progress", "To Do", "Open"]:
        if target in statuses:
            run(f'transition {key} "{target}"')
            break

    return statuses


def test_create_link_target() -> str:
    """Create second ticket for linking."""
    print("\n=== Create link target ===")
    content = f"""\
---
project: SAN
summary: "Link target {int(time.time())}"
type: Task
labels: [integration-test, link-target]
---

Link target ticket.
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        ticket_file = f.name

    result = run(f"create {ticket_file}")
    Path(ticket_file).unlink()
    return extract_key(result.stdout)


def test_links(key1: str, key2: str):
    """Test various link types."""
    if not key2:
        print("\n=== Links: skipped (no target) ===")
        return

    print("\n=== Create links ===")
    for link_type in ["Relates", "Blocks", "Cloners"]:
        result = run(f'link {key1} {key2} -t "{link_type}"', check=False)
        status = "OK" if result.returncode == 0 else "skipped"
        print(f"  {link_type}: {status}")

    print("\n=== Verify links in export ===")
    result = run(f"export {key1}")
    assert key2 in result.stdout, "Link target not in export"


def test_export_formats(key: str):
    """Test export to file in different formats."""
    print("\n=== Export formats ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        run(f"export {key} -o {tmpdir}/out.md")
        run(f"export {key} -o {tmpdir}/out.json --format json")


def test_export_jql(key: str):
    """Test JQL export."""
    print("\n=== Export with JQL ===")
    result = run(f'export --jql "project = SAN AND labels = integration-test" --format json')
    assert key in result.stdout


def test_my():
    """Test my command."""
    print("\n=== My tickets ===")
    run("my", check=False)


def test_info():
    """Test info subcommands."""
    print("\n=== Info commands ===")
    for subcmd in ["statuses", "priorities", "issue-types", "link-types"]:
        run(f"info {subcmd}", check=False)


def test_edit_multiple(key: str):
    """Test editing multiple fields."""
    print("\n=== Edit multiple fields ===")
    run(f'edit {key} -F "Priority=Low" -F "Labels=integration-test,multi-edit"', check=False)


def test_edit_yaml(key: str):
    """Test editing from YAML."""
    print("\n=== Edit from YAML ===")
    yaml = "priority: Medium\nlabels: [integration-test, yaml-edit]\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml)
        yaml_file = f.name
    run(f"edit {key} --from {yaml_file}", check=False)
    Path(yaml_file).unlink()


def test_init():
    """Test init command in temp directory."""
    print("\n=== Init command ===")
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir = os.getcwd()
        try:
            os.chdir(tmpdir)
            result = run("init -p SAN --force", check=False)
            config = Path("zproject.toml")
            if config.exists():
                content = config.read_text()
                assert "[project]" in content
                assert "[boards]" in content
                assert "[queries]" in content
                assert "[reports]" in content
                print("  Config created and validated")
            else:
                print("  Warning: config not created (may need credentials)")
        finally:
            os.chdir(orig_dir)


def cleanup(keys: list[str]):
    """Dispose test tickets."""
    print("\n=== Cleanup ===")
    for key in keys:
        if not key:
            continue
        result = run(f"transition {key} --list", check=False)
        if result.returncode != 0:
            continue

        available = [line.split("→")[-1].strip() for line in result.stdout.split("\n") if "→" in line]
        for status in ["Disposal", "Closed", "Done"]:
            if status in available:
                run(f'transition {key} "{status}"', check=False)
                print(f"  {key}: {status}")
                break


def main():
    print("=" * 50)
    print("ZAIRA INTEGRATION TESTS - SAN")
    print("=" * 50)

    key1 = test_create_ticket()
    key2 = ""

    try:
        test_export(key1)
        test_edit_title(key1)
        test_edit_description(key1)
        test_edit_field(key1)
        test_comments(key1)
        test_transitions(key1)

        key2 = test_create_link_target()
        test_links(key1, key2)

        test_export_formats(key1)
        test_export_jql(key1)
        test_my()
        test_info()
        test_edit_multiple(key1)
        test_edit_yaml(key1)
        test_init()

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED")
        print("=" * 50)

    except AssertionError as e:
        print(f"\nFAILED: {e}")
        return 1
    except Exception as e:
        print(f"\nERROR: {e}")
        return 1
    finally:
        cleanup([key1, key2])

    return 0


if __name__ == "__main__":
    sys.exit(main())
