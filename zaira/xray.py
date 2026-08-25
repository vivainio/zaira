"""Xray Cloud API integration and credential storage."""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import keyring
import requests

from zaira import wincred

XRAY_BASE_URL = "https://xray.cloud.getxray.app/api/v2"
XRAY_CLIENT_ID_TARGET = "zaira-xray-client-id"
XRAY_CLIENT_SECRET_TARGET = "zaira-xray-client-secret"
XRAY_CREDENTIAL_USER = "xray"


class XrayCredentialsNotConfigured(RuntimeError):
    """Raised when Xray Cloud credentials have not been stored."""


def _get_secret(target: str) -> str | None:
    """Read a value from the platform secret store."""
    if wincred.is_wsl():
        return wincred.get_password(target, XRAY_CREDENTIAL_USER)
    return keyring.get_password(target, XRAY_CREDENTIAL_USER)


def _set_secret(target: str, value: str) -> None:
    """Write a value to the platform secret store."""
    if wincred.is_wsl():
        wincred.set_password(target, XRAY_CREDENTIAL_USER, value)
        return
    keyring.set_password(target, XRAY_CREDENTIAL_USER, value)


def load_credentials() -> tuple[str, str]:
    """Load the Xray Client ID and Client Secret from the secret store."""
    client_id = _get_secret(XRAY_CLIENT_ID_TARGET)
    client_secret = _get_secret(XRAY_CLIENT_SECRET_TARGET)
    if not client_id or not client_secret:
        raise XrayCredentialsNotConfigured(
            "Xray Cloud credentials are not configured. Run 'zaira init-xray'."
        )
    return client_id, client_secret


def save_credentials(client_id: str, client_secret: str) -> None:
    """Store the Xray Client ID and Client Secret in the secret store."""
    _set_secret(XRAY_CLIENT_ID_TARGET, client_id)
    _set_secret(XRAY_CLIENT_SECRET_TARGET, client_secret)


def authenticate(client_id: str, client_secret: str) -> str:
    """Exchange an Xray API key pair for a bearer token."""
    response = requests.post(
        f"{XRAY_BASE_URL}/authenticate",
        json={"client_id": client_id, "client_secret": client_secret},
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()
    if not isinstance(token, str) or not token:
        raise RuntimeError("Xray authentication returned an invalid token")
    return token


def fetch_test_definition(test_key: str, token: str) -> dict[str, Any]:
    """Fetch the Xray-specific definition for one Test issue."""
    query = """
    query TestDefinition($jql: String!) {
      getTests(jql: $jql, limit: 1) {
        results {
          testType { name kind }
          steps { id data action result }
          gherkin
          unstructured
        }
      }
    }
    """
    response = requests.post(
        f"{XRAY_BASE_URL}/graphql",
        json={"query": query, "variables": {"jql": f'key = "{test_key}"'}},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"Xray GraphQL errors: {errors}")
    results = payload.get("data", {}).get("getTests", {}).get("results", [])
    if not results:
        raise RuntimeError(f"Xray Test not found: {test_key}")
    result = results[0]
    if not isinstance(result, dict):
        raise RuntimeError(f"Xray returned an invalid Test definition: {test_key}")
    return result


def fetch_test_steps(test_key: str, token: str) -> list[dict[str, Any]]:
    """Fetch manual test steps for one Xray Test issue."""
    definition = fetch_test_definition(test_key, token)
    steps = definition.get("steps") or []
    return [step for step in steps if isinstance(step, dict)]


def add_steps(tests: list[dict[str, Any]]) -> None:
    """Enrich linked Xray tests in place with their manual steps."""
    if not tests:
        return
    client_id, client_secret = load_credentials()
    token = authenticate(client_id, client_secret)
    for test in tests:
        test["steps"] = fetch_test_steps(str(test["key"]), token)


def fetch_test_run(
    test_issue_id: str, exec_issue_id: str, token: str
) -> dict[str, Any]:
    """Fetch the Test Run (actual per-step results) for one Test within one Test Execution."""
    query = """
    query TestRun($testIssueId: String!, $testExecIssueId: String!) {
      getTestRun(testIssueId: $testIssueId, testExecIssueId: $testExecIssueId) {
        status { name }
        steps { status { name } actualResult comment }
      }
    }
    """
    response = requests.post(
        f"{XRAY_BASE_URL}/graphql",
        json={
            "query": query,
            "variables": {
                "testIssueId": test_issue_id,
                "testExecIssueId": exec_issue_id,
            },
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"Xray GraphQL errors: {errors}")
    result = payload.get("data", {}).get("getTestRun")
    if not isinstance(result, dict):
        raise RuntimeError("Xray Test Run not found")
    return result


def add_test_run_results(tests: list[dict[str, Any]]) -> None:
    """Enrich linked Xray Test Executions in place with actual per-step results.

    A Test's `steps` (from add_steps) are the expected procedure; a Test Run's
    steps carry what actually happened when that test was executed.
    """
    pending = [
        (test, execution)
        for test in tests
        for execution in test.get("executions", [])
        if test.get("id") and execution.get("id")
    ]
    if not pending:
        return
    client_id, client_secret = load_credentials()
    token = authenticate(client_id, client_secret)
    for test, execution in pending:
        try:
            run = fetch_test_run(str(test["id"]), str(execution["id"]), token)
        except Exception:
            continue
        execution["runStatus"] = str((run.get("status") or {}).get("name") or "")
        execution["steps"] = run.get("steps") or []


def _secret_store_name() -> str:
    return "Windows Credential Manager" if wincred.is_wsl() else "OS keyring"


def _prompt(label: str) -> str:
    value = input(f"{label}: ").strip()
    if not value:
        print(f"Error: empty {label}", file=sys.stderr)
        raise SystemExit(1)
    return value


def init_xray_command(args: argparse.Namespace) -> None:
    """Prompt for and store an Xray Cloud API key pair."""
    del args
    if wincred.is_wsl() and wincred.backend_info() is None:
        print(
            "wincred.exe is not installed. Run `zaira init --install-wincred` first.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(f"Store Xray Cloud credentials in the {_secret_store_name()}.")
    client_id = _prompt("Xray Client ID")
    client_secret = _prompt("Xray Client Secret")
    save_credentials(client_id, client_secret)
    print(f"Xray Cloud credentials stored in the {_secret_store_name()}.")
    print(f"  Client ID target: {XRAY_CLIENT_ID_TARGET}")
    print(f"  Client Secret target: {XRAY_CLIENT_SECRET_TARGET}")


def _table_cell(value: Any) -> str:
    """Format an Xray step value for a Markdown table cell."""
    return (
        str(value or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("|", "\\|")
        .replace("\n", "<br>")
    )


def format_test_markdown(
    ticket: dict[str, Any],
    definition: dict[str, Any],
    synced: str,
    comments: list[Any] | None = None,
) -> str:
    """Format a Jira/Xray Test as standalone Markdown.

    Jira comments are always included: manual tests with no formal Xray
    steps often have their actual test procedure written up as a comment
    instead, so omitting comments would silently drop that content.
    """
    from zaira.export import yaml_quote
    from zaira.jira_client import get_jira_site

    key = str(ticket.get("key") or "")
    summary = str(ticket.get("summary") or "No summary")
    test_type = definition.get("testType") or {}
    type_name = str(test_type.get("name") or "Unknown")
    kind = str(test_type.get("kind") or "").lower()
    description = str(ticket.get("description") or "No description")

    markdown = f"""---
key: {key}
summary: {yaml_quote(summary)}
test_type: {yaml_quote(type_name)}
status: {yaml_quote(str(ticket.get("status") or "Unknown"))}
assignee: {yaml_quote(str(ticket.get("assignee") or "Unassigned"))}
reporter: {yaml_quote(str(ticket.get("reporter") or "Unknown"))}
synced: {synced}
url: https://{get_jira_site()}/browse/{key}
---

# {key}: {summary}

## Description

{description}
"""

    if kind == "gherkin":
        gherkin = str(definition.get("gherkin") or "").strip()
        markdown += f"\n## Scenario\n\n```gherkin\n{gherkin}\n```\n"
    elif kind == "unstructured":
        unstructured = str(definition.get("unstructured") or "").strip()
        markdown += f"\n## Definition\n\n{unstructured or '_No definition._'}\n"
    else:
        markdown += "\n## Steps\n\n"
        steps = definition.get("steps") or []
        if not steps:
            markdown += "_No manual steps._\n"
        else:
            markdown += "| # | Action | Data | Expected Result |\n"
            markdown += "|---|---|---|---|\n"
            for number, step in enumerate(steps, 1):
                markdown += (
                    f"| {number} | {_table_cell(step.get('action'))} | "
                    f"{_table_cell(step.get('data'))} | "
                    f"{_table_cell(step.get('result'))} |\n"
                )

    markdown += "\n## Comments\n\n"
    if comments:
        for comment in comments:
            markdown += (
                f"### {comment.author} ({comment.created})\n\n{comment.body}\n\n"
            )
    else:
        markdown += "_No comments_\n"
    return markdown


def extract_command(args: argparse.Namespace) -> None:
    """Extract Xray Tests as standalone Markdown documents."""
    from zaira.export import get_comments, get_ticket

    client_id, client_secret = load_credentials()
    token = authenticate(client_id, client_secret)
    output = Path(args.output) if args.output else None
    if output:
        output.mkdir(parents=True, exist_ok=True)

    failures = 0
    for index, key_arg in enumerate(args.keys):
        key = key_arg.upper()
        ticket = get_ticket(key)
        if not ticket:
            print(f"Error: could not fetch Jira Test {key}", file=sys.stderr)
            failures += 1
            continue
        if ticket.get("issuetype") not in ("Test", "Test Case", "Test Case 2"):
            print(f"Error: {key} is not a Jira Test issue", file=sys.stderr)
            failures += 1
            continue
        try:
            definition = fetch_test_definition(key, token)
        except Exception as error:
            print(f"Error: could not fetch Xray Test {key}: {error}", file=sys.stderr)
            failures += 1
            continue

        try:
            comments = get_comments(key)
        except Exception:
            comments = []

        synced = datetime.now().isoformat(timespec="seconds")
        markdown = format_test_markdown(ticket, definition, synced, comments)
        if output:
            path = output / f"{key}.md"
            path.write_text(markdown, encoding="utf-8")
            print(f"Saved: {path}")
        else:
            if index:
                print()
            print(markdown, end="")

    if failures:
        raise SystemExit(1)
