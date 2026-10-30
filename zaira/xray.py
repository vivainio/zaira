"""Xray Cloud API integration and credential storage."""

import argparse
import base64
import json
import mimetypes
import re
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


def _graphql(query: str, variables: dict[str, Any], token: str) -> dict[str, Any]:
    """Run one Xray GraphQL operation and return its `data`."""
    response = requests.post(
        f"{XRAY_BASE_URL}/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"Xray GraphQL errors: {errors}")
    return payload.get("data") or {}


def _issue_id(key: str) -> str:
    """Resolve a Jira issue key to the numeric issue id Xray expects."""
    from zaira.jira_client import get_jira

    return str(get_jira().issue(key, fields="summary").id)


def fetch_run(test_key: str, exec_key: str, token: str) -> dict[str, Any]:
    """Fetch the Test Run (id, status, steps with ids) for a Test within an Execution."""
    query = """
    query TestRun($testIssueId: String!, $testExecIssueId: String!) {
      getTestRun(testIssueId: $testIssueId, testExecIssueId: $testExecIssueId) {
        id
        status { name }
        steps { id status { name } }
      }
    }
    """
    data = _graphql(
        query,
        {"testIssueId": _issue_id(test_key), "testExecIssueId": _issue_id(exec_key)},
        token,
    )
    run = data.get("getTestRun")
    if not isinstance(run, dict):
        raise RuntimeError(f"{test_key} has no Test Run in {exec_key}")
    return run


def update_run_status(run_id: str, status: str, token: str) -> None:
    """Set the overall status of a Test Run."""
    _graphql(
        "mutation($id: String!, $status: String!) "
        "{ updateTestRunStatus(id: $id, status: $status) }",
        {"id": run_id, "status": status},
        token,
    )


def update_run_step(
    run_id: str,
    step_id: str,
    token: str,
    status: str | None = None,
    actual: str | None = None,
    comment: str | None = None,
) -> None:
    """Update one step of a Test Run (only the fields given)."""
    update = {
        name: value
        for name, value in (
            ("status", status),
            ("actualResult", actual),
            ("comment", comment),
        )
        if value is not None
    }
    _graphql(
        "mutation($runId: String!, $stepId: String!, $update: UpdateTestRunStepInput!) "
        "{ updateTestRunStep(testRunId: $runId, stepId: $stepId, updateData: $update) "
        "{ warnings } }",
        {"runId": run_id, "stepId": step_id, "update": update},
        token,
    )


def create_execution(
    project: str,
    summary: str,
    test_keys: list[str],
    environments: list[str],
    token: str,
) -> str:
    """Create a Test Execution containing the given Tests; return its Jira key."""
    variables: dict[str, Any] = {
        "ids": [_issue_id(key) for key in test_keys],
        "jira": {"fields": {"summary": summary, "project": {"key": project}}},
    }
    env_arg = ""
    if environments:
        variables["envs"] = environments
        env_arg = ", testEnvironments: $envs"
    query = (
        "mutation($ids: [String]!, $jira: JSON!"
        + (", $envs: [String]" if environments else "")
        + ") { createTestExecution(testIssueIds: $ids, jira: $jira"
        + env_arg
        + ') { testExecution { issueId jira(fields: ["key"]) } warnings } }'
    )
    data = _graphql(query, variables, token)
    created = (data.get("createTestExecution") or {}).get("testExecution") or {}
    key = (created.get("jira") or {}).get("key")
    if not key:
        raise RuntimeError("Xray did not return the new Test Execution key")
    return str(key)


def _step_id(run: dict[str, Any], number: int) -> str:
    """Map a 1-based step position to the Test Run step id."""
    steps = run.get("steps") or []
    if not 1 <= number <= len(steps):
        raise RuntimeError(f"step {number} out of range (run has {len(steps)} steps)")
    return str(steps[number - 1]["id"])


def _auth_token() -> str:
    client_id, client_secret = load_credentials()
    return authenticate(client_id, client_secret)


def _apply_result(
    test_key: str,
    exec_key: str,
    token: str,
    status: str | None,
    steps: list[dict[str, Any]],
    dry_run: bool,
) -> None:
    """Apply an overall status and/or per-step results to one Test Run."""
    run = fetch_run(test_key, exec_key, token)
    run_id = str(run["id"])
    if status:
        print(f"{test_key} in {exec_key}: status -> {status}")
        if not dry_run:
            update_run_status(run_id, status, token)
    for step in steps:
        number = int(step["n"])
        step_id = _step_id(run, number)
        print(f"{test_key} in {exec_key}: step {number} -> {step.get('status', '')}")
        if not dry_run:
            update_run_step(
                run_id,
                step_id,
                token,
                status=step.get("status"),
                actual=step.get("actual"),
                comment=step.get("comment"),
            )


def run_status_command(args: argparse.Namespace) -> None:
    """Set the status of one or more Tests within a Test Execution."""
    token = _auth_token()
    failures = 0
    for key in args.keys:
        try:
            _apply_result(
                key.upper(), args.exec.upper(), token, args.status, [], args.dry_run
            )
        except Exception as error:
            print(f"Error: {key}: {error}", file=sys.stderr)
            failures += 1
    if failures:
        raise SystemExit(1)


def run_step_command(args: argparse.Namespace) -> None:
    """Set the result of one step of a Test within a Test Execution."""
    step = {
        "n": args.step,
        "status": args.status,
        "actual": args.actual,
        "comment": args.comment,
    }
    try:
        _apply_result(
            args.key.upper(),
            args.exec.upper(),
            _auth_token(),
            None,
            [step],
            args.dry_run,
        )
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)


def run_import_command(args: argparse.Namespace) -> None:
    """Apply results from a JSON file to a Test Execution."""
    try:
        entries = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("expected a JSON list")
    except Exception as error:
        print(f"Error: cannot read {args.file}: {error}", file=sys.stderr)
        raise SystemExit(1)
    token = _auth_token()
    failures = 0
    for entry in entries:
        key = str(entry.get("test", "")).upper()
        try:
            _apply_result(
                key,
                args.exec.upper(),
                token,
                entry.get("status"),
                entry.get("steps") or [],
                args.dry_run,
            )
        except Exception as error:
            print(f"Error: {key or entry}: {error}", file=sys.stderr)
            failures += 1
    if failures:
        raise SystemExit(1)


def exec_create_command(args: argparse.Namespace) -> None:
    """Create a Test Execution for a set of Tests."""
    tests = [key.upper() for key in args.tests]
    if args.dry_run:
        print(f"Would create execution in {args.project}: {args.summary!r}")
        print(f"  tests: {', '.join(tests)}")
        print(f"  environments: {', '.join(args.env) or '(none)'}")
        return
    try:
        key = create_execution(
            args.project, args.summary, tests, args.env or [], _auth_token()
        )
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Created: {key}")


def add_test_step(issue_id: str, step: dict[str, str], token: str) -> str:
    """Append a manual step (action/data/result) to a Test; returns the step id."""
    data = _graphql(
        "mutation($id: String!, $step: CreateStepInput!) "
        "{ addTestStep(issueId: $id, step: $step) { id } }",
        {"id": issue_id, "step": step},
        token,
    )
    return str(data["addTestStep"]["id"])


def update_test_step(step_id: str, fields: dict[str, str], token: str) -> None:
    """Update the given fields (action/data/result) of one manual step."""
    _graphql(
        "mutation($id: String!, $step: UpdateStepInput!) "
        "{ updateTestStep(stepId: $id, step: $step) { warnings } }",
        {"id": step_id, "step": fields},
        token,
    )


def add_step_attachments(step_id: str, files: list[Path], token: str) -> None:
    """Attach files to one manual step (uploaded base64-encoded)."""
    add = [
        {
            "filename": path.name,
            "mimeType": mimetypes.guess_type(path.name)[0]
            or "application/octet-stream",
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
        for path in files
    ]
    _graphql(
        "mutation($id: String!, $step: UpdateStepInput!) "
        "{ updateTestStep(stepId: $id, step: $step) { warnings } }",
        {"id": step_id, "step": {"attachments": {"add": add}}},
        token,
    )


def remove_test_step(step_id: str, token: str) -> None:
    """Delete one manual step."""
    _graphql(
        "mutation($id: String!) { removeTestStep(stepId: $id) }",
        {"id": step_id},
        token,
    )


def remove_all_test_steps(issue_id: str, token: str) -> None:
    """Delete every manual step of a Test."""
    _graphql(
        "mutation($id: String!) { removeAllTestSteps(issueId: $id) }",
        {"id": issue_id},
        token,
    )


def _existing_step_id(test_key: str, number: int, token: str) -> str:
    """Map a 1-based step position to its Xray step id."""
    steps = fetch_test_steps(test_key, token)
    if not 1 <= number <= len(steps):
        raise RuntimeError(f"step {number} out of range (test has {len(steps)} steps)")
    return str(steps[number - 1]["id"])


def parse_steps_markdown(text: str) -> list[dict[str, str]]:
    """Parse the `## Steps` table written by `zaira xray get` into step dicts."""
    section = re.search(r"^## Steps\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not section:
        raise ValueError("no '## Steps' section found")
    steps: list[dict[str, str]] = []
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [
            cell.strip().replace("\\|", "|").replace("<br>", "\n")
            for cell in re.split(r"(?<!\\)\|", line.strip("|"))
        ]
        if len(cells) != 4 or cells[0] in ("#", "") or set(cells[0]) <= {"-", ":"}:
            continue
        steps.append({"action": cells[1], "data": cells[2], "result": cells[3]})
    return steps


def step_add_command(args: argparse.Namespace) -> None:
    """Append a manual step to a Test."""
    step = {"action": args.action, "data": args.data or "", "result": args.result or ""}
    key = args.key.upper()
    if args.dry_run:
        print(f"Would add step to {key}: {step}")
        return
    try:
        add_test_step(_issue_id(key), step, _auth_token())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Added step to {key}")


def step_edit_command(args: argparse.Namespace) -> None:
    """Update fields of one manual step of a Test."""
    fields = {
        name: value
        for name, value in (
            ("action", args.action),
            ("data", args.data),
            ("result", args.result),
        )
        if value is not None
    }
    if not fields:
        print("Error: give at least one of --action, --data, --result", file=sys.stderr)
        raise SystemExit(1)
    key = args.key.upper()
    try:
        token = _auth_token()
        step_id = _existing_step_id(key, args.step, token)
        if args.dry_run:
            print(f"Would update {key} step {args.step}: {fields}")
            return
        update_test_step(step_id, fields, token)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Updated {key} step {args.step}")


def step_attach_command(args: argparse.Namespace) -> None:
    """Attach files to one manual step of a Test."""
    files = [Path(name) for name in args.files]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        print(f"Error: file not found: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(1)
    key = args.key.upper()
    names = ", ".join(path.name for path in files)
    try:
        token = _auth_token()
        step_id = _existing_step_id(key, args.step, token)
        if args.dry_run:
            print(f"Would attach {names} to {key} step {args.step}")
            return
        add_step_attachments(step_id, files, token)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Attached {names} to {key} step {args.step}")


def step_rm_command(args: argparse.Namespace) -> None:
    """Delete one manual step of a Test."""
    key = args.key.upper()
    try:
        token = _auth_token()
        step_id = _existing_step_id(key, args.step, token)
        if args.dry_run:
            print(f"Would remove {key} step {args.step}")
            return
        remove_test_step(step_id, token)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Removed {key} step {args.step}")


def steps_put_command(args: argparse.Namespace) -> None:
    """Replace all manual steps of a Test with the table in a markdown file."""
    key = args.key.upper()
    try:
        steps = parse_steps_markdown(Path(args.file).read_text(encoding="utf-8"))
        token = _auth_token()
        current = len(fetch_test_steps(key, token))
        if args.dry_run:
            print(f"Would replace {current} step(s) of {key} with {len(steps)}")
            return
        issue_id = _issue_id(key)
        remove_all_test_steps(issue_id, token)
        for step in steps:
            add_test_step(issue_id, step, token)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Replaced {current} step(s) of {key} with {len(steps)}")


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
