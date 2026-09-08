"""Export Jira tickets to markdown or JSON."""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
from zaira.errors import ResourceFetchFailed
from zaira.export_fields import _format_timestamp as _format_timestamp
from zaira.export_fields import (
    _is_bogus_field_name,
    extract_custom_field_value,
    extract_description,
    is_placeholder_value,
    normalize_title,
)
from zaira.export_render import (
    format_ticket_json,
    format_ticket_markdown,
    format_ticket_minimal,
    format_ticket_ndjson,
)
from zaira.info import get_field_custom_type, get_field_name, load_default_fields
from zaira.jira_client import format_jira_error, get_jira, get_jira_site
from zaira.mdconv import is_jira_wiki, jira_wiki_to_markdown
from zaira.types import Attachment, Comment, get_user_identifier
from zaira.types import yaml_quote as yaml_quote
from zaira.util import atomic_write_text


def get_ticket(
    key: str,
    full: bool = False,
    include_custom: bool = False,
    include_attachments: bool = False,
    raw: bool = False,
) -> dict[str, Any] | None:
    """Fetch ticket details.

    Args:
        key: Ticket key (e.g., "FOO-123")
        full: Include extra fields for JSON export
        include_custom: Include custom fields with schema name lookup
        include_attachments: Include attachment metadata
        raw: Skip wiki-to-markdown conversion (preserve Jira wiki markup)
    """
    jira = get_jira()
    try:
        issue = jira.issue(key, expand="renderedFields")
        fields = issue.fields

        # Handle description - could be ADF or string
        desc = fields.description
        if hasattr(desc, "__dict__"):
            # It's an ADF object, convert to dict
            desc = desc.raw if hasattr(desc, "raw") else None

        ticket = {
            "id": issue.id,
            "key": issue.key,
            "summary": fields.summary or "No summary",
            "issuetype": fields.issuetype.name if fields.issuetype else "Unknown",
            "status": fields.status.name if fields.status else "Unknown",
            "priority": fields.priority.name if fields.priority else "None",
            "assignee": get_user_identifier(fields.assignee) or "Unassigned",
            "reporter": get_user_identifier(fields.reporter) or "Unknown",
            "created": fields.created or "Unknown",
            "updated": fields.updated or "Unknown",
            "description": extract_description(desc, raw=raw),
            "components": list(
                dict.fromkeys(c.name for c in (fields.components or []))
            ),
            "labels": fields.labels or [],
            "parent": (
                {
                    "key": fields.parent.key,
                    "summary": fields.parent.fields.summary,
                }
                if hasattr(fields, "parent") and fields.parent
                else None
            ),
            "issuelinks": [
                {
                    "type": link.type.name,
                    "direction": (
                        "outward" if hasattr(link, "outwardIssue") else "inward"
                    ),
                    "key": (
                        link.outwardIssue.key
                        if hasattr(link, "outwardIssue")
                        else link.inwardIssue.key
                    ),
                    "summary": (
                        link.outwardIssue.fields.summary
                        if hasattr(link, "outwardIssue")
                        else link.inwardIssue.fields.summary
                    ),
                }
                for link in (getattr(fields, "issuelinks", None) or [])
            ],
        }

        # Add custom fields with human-readable names
        # paragraph_fields: textarea custom fields always shown as body sections
        # custom_fields: non-textarea fields shown in YAML front matter;
        #   always included if in default_fields.txt, otherwise only with --all-fields
        raw_fields_data = issue.raw.get("fields", {})
        paragraph_fields: dict[str, str] = {}
        custom_fields: dict[str, Any] = {}
        default_fields_lower = {f.lower() for f in load_default_fields()}
        for field_id, value in raw_fields_data.items():
            if not field_id.startswith("customfield_") or value is None:
                continue
            is_option = isinstance(value, dict) and ("value" in value or "id" in value)
            extracted = extract_custom_field_value(value)
            if not is_option and is_placeholder_value(extracted):
                continue
            field_name = get_field_name(field_id)
            if not field_name:
                if include_custom:
                    custom_fields[field_id] = extracted
                continue
            if _is_bogus_field_name(field_name):
                continue
            custom_type = get_field_custom_type(field_id)
            is_textarea = custom_type == "textarea" or (
                isinstance(extracted, str) and "\n" in extracted
            )
            if is_textarea and isinstance(extracted, str):
                text = (
                    jira_wiki_to_markdown(extracted)
                    if is_jira_wiki(extracted)
                    else extracted
                )
                paragraph_fields[field_name] = text
            elif include_custom or field_name.lower() in default_fields_lower:
                custom_fields[field_name] = extracted
        ticket["paragraph_fields"] = paragraph_fields
        ticket["custom_fields"] = custom_fields

        # Add extra fields for JSON export
        if full:
            ticket["project"] = fields.project.key if fields.project else None
            ticket["resolution"] = fields.resolution.name if fields.resolution else None
            ticket["resolutiondate"] = (
                fields.resolutiondate if hasattr(fields, "resolutiondate") else None
            )
            ticket["statusCategory"] = (
                fields.status.statusCategory.name
                if fields.status and fields.status.statusCategory
                else None
            )
            ticket["fixVersions"] = [v.name for v in (fields.fixVersions or [])]
            ticket["versions"] = [v.name for v in (fields.versions or [])]
            ticket["votes"] = fields.votes.votes if fields.votes else 0
            ticket["watches"] = fields.watches.watchCount if fields.watches else 0
            ticket["subtasks"] = [
                {
                    "key": st.key,
                    "summary": st.fields.summary,
                    "status": st.fields.status.name,
                    "issuetype": (
                        st.fields.issuetype.name if st.fields.issuetype else "Unknown"
                    ),
                }
                for st in (fields.subtasks or [])
            ]
            ticket["assigneeDisplayName"] = (
                fields.assignee.displayName if fields.assignee else None
            )
            ticket["reporterDisplayName"] = (
                fields.reporter.displayName if fields.reporter else None
            )
            ticket["creator"] = get_user_identifier(fields.creator)
            ticket["creatorDisplayName"] = (
                fields.creator.displayName if fields.creator else None
            )

        # Add attachment metadata
        if include_attachments:
            attachments = []
            for att in getattr(fields, "attachment", None) or []:
                attachments.append(
                    {
                        "id": att.id,
                        "filename": att.filename,
                        "size": att.size,
                        "mimeType": getattr(
                            att, "mimeType", "application/octet-stream"
                        ),
                        "author": att.author.displayName if att.author else "Unknown",
                        "created": att.created or "",
                    }
                )
            ticket["attachments"] = attachments

        return ticket
    except Exception as e:
        print(f"  Error fetching {key}: {format_jira_error(e)}", file=sys.stderr)
        return None


def _fetch_comments(key: str, raw: bool = False) -> list[Comment]:
    """Fetch and parse ticket comments.

    Raises ResourceFetchFailed if Jira could not be reached or rejected the
    request, as distinct from the ticket legitimately having no comments.
    """
    from jira.exceptions import JIRAError

    jira = get_jira()
    try:
        issue = jira.issue(key, fields="comment")
    except JIRAError as e:
        raise ResourceFetchFailed(
            f"could not fetch comments for {key}: {format_jira_error(e)}"
        ) from e
    comments = issue.fields.comment.comments if issue.fields.comment else []
    result: list[Comment] = []
    for c in comments:
        body = c.body
        if hasattr(body, "raw"):
            body = extract_description(body.raw, raw=raw)
        elif hasattr(body, "__dict__"):
            body = extract_description(body.__dict__, raw=raw)
        body_str = body if isinstance(body, str) else str(body)
        if not raw and is_jira_wiki(body_str):
            body_str = jira_wiki_to_markdown(body_str)
        result.append(
            Comment(
                author=c.author.displayName if c.author else "Unknown",
                created=_format_timestamp(c.created or ""),
                body=body_str,
                id=c.id,
            )
        )
    return result


def get_comments(key: str, raw: bool = False) -> list[Comment]:
    """Fetch ticket comments.

    Returns [] both when the ticket has no comments and when fetching them
    failed -- see _fetch_comments for the distinction available internally.
    """
    try:
        return _fetch_comments(key, raw)
    except Exception:
        return []


def get_linked_tests(key: str) -> list[dict]:
    """Fetch Xray Test and Test Execution issues linked to a Jira issue.

    Returns [] both when there are no linked tests and when fetching them
    failed -- see _fetch_linked_tests for the distinction available
    internally.
    """
    try:
        return _fetch_linked_tests(key)
    except Exception:
        return []


def _fetch_linked_tests(key: str) -> list[dict]:
    """Fetch Xray Test and Test Execution issues linked to a Jira issue.

    Follows 'Tests' link type (inward = "tested by") to find Test issues,
    then checks for Test Executions linked to those tests.

    Raises ResourceFetchFailed if the issue itself could not be fetched, as
    distinct from it legitimately having no linked tests.
    """
    from jira.exceptions import JIRAError

    jira = get_jira()
    try:
        issue = jira.issue(key, fields="issuetype,issuelinks")
    except JIRAError as e:
        raise ResourceFetchFailed(
            f"could not fetch linked tests for {key}: {format_jira_error(e)}"
        ) from e
    issue_type = issue.fields.issuetype.name
    test_keys = [key] if issue_type in ("Test", "Test Case", "Test Case 2") else []
    for link in getattr(issue.fields, "issuelinks", None) or []:
        if link.type.name != "Tests":
            continue
        if hasattr(link, "inwardIssue"):
            linked = link.inwardIssue
        elif hasattr(link, "outwardIssue"):
            linked = link.outwardIssue
        else:
            continue
        if linked.fields.issuetype.name in (
            "Test",
            "Test Case",
            "Test Case 2",
        ):
            test_keys.append(linked.key)

    if not test_keys:
        return []

    # Fetch full details for each test
    tests = []
    for tk in test_keys:
        try:
            t = jira.issue(tk, fields="summary,status,assignee,issuelinks")
            f = t.fields
            # Find test executions linked to this test
            executions = []
            also_tests = []
            for link in getattr(f, "issuelinks", None) or []:
                if hasattr(link, "inwardIssue"):
                    linked = link.inwardIssue
                elif hasattr(link, "outwardIssue"):
                    linked = link.outwardIssue
                else:
                    continue
                lt_name = linked.fields.issuetype.name
                if lt_name in ("Test Execution", "Sub Test Execution"):
                    executions.append(
                        {
                            "id": linked.id,
                            "key": linked.key,
                            "summary": linked.fields.summary,
                            "status": linked.fields.status.name,
                        }
                    )
                elif lt_name in ("Story", "Bug", "Task", "Epic") and linked.key != key:
                    if link.type.name == "Tests":
                        also_tests.append(linked.key)

            tests.append(
                {
                    "id": t.id,
                    "key": t.key,
                    "summary": f.summary,
                    "status": f.status.name,
                    "assignee": get_user_identifier(f.assignee) or "Unassigned",
                    "executions": executions,
                    "alsoTests": also_tests,
                }
            )
        except Exception:
            continue
    return tests


def get_xray_tests(key: str) -> list[dict]:
    """Fetch linked Xray tests and add Cloud-hosted manual steps and run results."""
    tests = get_linked_tests(key)
    if not tests:
        return tests
    try:
        from zaira.xray import add_steps

        add_steps(tests)
    except Exception as e:
        print(f"Warning: could not fetch Xray test steps: {e}", file=sys.stderr)
    try:
        from zaira.xray import add_test_run_results

        add_test_run_results(tests)
    except Exception as e:
        print(f"Warning: could not fetch Xray test run results: {e}", file=sys.stderr)
    return tests


PROPS_SKIP_PREFIXES = (
    "jqlt.",
    "scriptrunner.",
    "history-",
    "index-history-",
    "tge",
    "checklist",
    "issue.content",
    "ducket-data",
)


def get_issue_properties(issue_id: str) -> list[dict]:
    """Fetch interesting issue properties (e.g. ducket grids).

    Skips noise properties (jqlt.*, scriptrunner.*, etc.) and returns
    a list of dicts with 'key' and 'value'. Returns [] both when there are
    no interesting properties and when fetching them failed -- see
    _fetch_issue_properties for the distinction available internally.
    """
    try:
        return _fetch_issue_properties(issue_id)
    except Exception:
        return []


def _fetch_issue_properties(issue_id: str) -> list[dict]:
    """Fetch interesting issue properties (e.g. ducket grids).

    Raises ResourceFetchFailed if the properties list could not be fetched,
    as distinct from the issue legitimately having none.
    """
    jira = get_jira()
    session = jira._session
    if session is None:
        raise ResourceFetchFailed(
            f"no active session to fetch properties for {issue_id}"
        )
    resp = session.get(jira._get_url(f"issue/{issue_id}/properties"))
    if not resp.ok:
        raise ResourceFetchFailed(
            f"could not list properties for {issue_id}: HTTP {resp.status_code}"
        )
    keys = [p["key"] for p in resp.json().get("keys", [])]
    results = []
    for key in keys:
        if any(key.startswith(p) for p in PROPS_SKIP_PREFIXES):
            continue
        r = session.get(jira._get_url(f"issue/{issue_id}/properties/{key}"))
        if r.status_code == 200:
            results.append({"key": key, "value": r.json().get("value", {})})
    return results


def get_pull_requests(issue_id: str) -> list[dict]:
    """Fetch GitHub PRs linked to a Jira issue via dev-status API.

    Returns [] both when there are no linked pull requests and when
    fetching them failed -- see _fetch_pull_requests for the distinction
    available internally.
    """
    try:
        return _fetch_pull_requests(issue_id)
    except Exception:
        return []


def _fetch_pull_requests(issue_id: str) -> list[dict]:
    """Fetch GitHub PRs linked to a Jira issue via dev-status API.

    The "detail" endpoint needs the exact application instance type (e.g.
    "oAuth-com.github.integration.production") as `applicationType` --
    the generic "GitHub" type some Atlassian docs show silently returns
    an empty `detail` list even when PRs exist, since it doesn't match
    the actual registered integration instance for this site. So this
    first asks the "summary" endpoint which instance type(s) reported
    pull requests for this issue (the `byInstanceType` keys under
    `pullrequest`), then queries "detail" once per instance and merges
    the results -- covering sites with more than one GitHub integration
    (e.g. cloud + on-prem) too.

    Raises ResourceFetchFailed if a request fails, as distinct from the
    issue legitimately having no linked pull requests.
    """
    jira = get_jira()
    assert jira._session is not None
    summary_resp = jira._session.get(
        f"{jira._options['server']}/rest/dev-status/1.0/issue/summary",
        params={"issueId": issue_id},
    )
    if not summary_resp.ok:
        raise ResourceFetchFailed(
            f"could not fetch linked pull requests for {issue_id}: "
            f"HTTP {summary_resp.status_code}"
        )
    instance_types = (
        summary_resp.json()
        .get("summary", {})
        .get("pullrequest", {})
        .get("byInstanceType", {})
        .keys()
    )
    prs = []
    for app_type in instance_types:
        resp = jira._session.get(
            f"{jira._options['server']}/rest/dev-status/1.0/issue/detail",
            params={
                "issueId": issue_id,
                "applicationType": app_type,
                "dataType": "pullrequest",
            },
        )
        if not resp.ok:
            raise ResourceFetchFailed(
                f"could not fetch linked pull requests for {issue_id}: "
                f"HTTP {resp.status_code}"
            )
        data = resp.json()
        for detail in data.get("detail", []):
            for pr in detail.get("pullRequests", []):
                prs.append(
                    {
                        "name": pr.get("name"),
                        "url": pr.get("url"),
                        "status": pr.get("status"),
                    }
                )
    return prs


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


def download_attachment(
    attachment: Attachment, output_dir: Path, enforce_size_limit: bool = True
) -> bool:
    """Download a single attachment to the output directory.

    Args:
        attachment: Attachment metadata dict
        output_dir: Directory to save the file
        enforce_size_limit: If True, skip files larger than MAX_ATTACHMENT_SIZE.

    Returns:
        True if successful, False otherwise
    """
    size = attachment.get("size", 0)
    if enforce_size_limit and size > MAX_ATTACHMENT_SIZE:
        size_mb = size / (1024 * 1024)
        print(
            f"    Skipping {attachment['filename']} ({size_mb:.1f} MB > 10 MB limit); "
            f"request it by exact filename to download anyway"
        )
        return False

    jira = get_jira()
    try:
        # Construct the attachment URL
        assert jira._session is not None
        url = f"{jira._options['server']}/secure/attachment/{attachment['id']}/{attachment['filename']}"
        resp = jira._session.get(url)
        resp.raise_for_status()

        output_dir.mkdir(parents=True, exist_ok=True)
        outfile = output_dir / attachment["filename"]
        outfile.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    Error downloading {attachment['filename']}: {format_jira_error(e)}")
        return False


def get_attachment_command(args: argparse.Namespace) -> None:
    """Handle get-attachment subcommand."""
    from fnmatch import fnmatch

    key = args.key.upper()
    pattern = args.pattern
    output_dir = Path(getattr(args, "output", None) or ".")

    ticket = get_ticket(key, include_attachments=True)
    if not ticket:
        print(f"Error: Could not fetch {key}", file=sys.stderr)
        sys.exit(1)

    attachments = ticket.get("attachments", [])
    if not attachments:
        print(f"No attachments on {key}")
        return

    matched = [a for a in attachments if fnmatch(a["filename"], pattern)]
    if not matched:
        print(f"No attachments matching '{pattern}' on {key}")
        print("Available attachments:")
        for a in attachments:
            size_kb = a.get("size", 0) // 1024
            print(f"  {a['filename']} ({size_kb} KB)")
        return

    is_glob = any(c in pattern for c in "*?[")
    enforce_size_limit = is_glob or len(matched) > 1

    print(f"Downloading {len(matched)} attachment(s) from {key}...")
    success = 0
    for att in matched:
        size_kb = att.get("size", 0) // 1024
        print(f"  {att['filename']} ({size_kb} KB)...", end=" ")
        if download_attachment(att, output_dir, enforce_size_limit=enforce_size_limit):
            print("done")
            success += 1
        else:
            print("failed")

    print(f"\nDownloaded {success}/{len(matched)} files to {output_dir}/")
    if success < len(matched):
        sys.exit(1)


def search_tickets(jql: str) -> list[str]:
    """Search for tickets and return list of keys."""
    jira = get_jira()
    try:
        issues = jira.search_issues(jql, maxResults=False)
        return [issue.key for issue in issues]
    except Exception as e:
        print(f"Error searching: {format_jira_error(e)}")
        return []


class PendingAttachment:
    """An attachment to download later."""

    __slots__ = ("attachment", "output_dir")

    def __init__(self, attachment: Attachment, output_dir: Path) -> None:
        self.attachment = attachment
        self.output_dir = output_dir

    def download(self) -> bool:
        return download_attachment(self.attachment, self.output_dir)


@dataclass
class ExportResult:
    """Structured outcome of export_ticket().

    status distinguishes a failed ticket fetch from a successful export.
    pending_attachments holds attachments not yet downloaded (only
    populated when defer_attachments=True); attachment_failures holds
    attachments export_ticket tried and failed to download itself (only
    possible when defer_attachments=False).
    """

    status: Literal["success", "failed"]
    path: Path | None = None
    pending_attachments: list[PendingAttachment] = field(default_factory=list)
    attachment_failures: list[PendingAttachment] = field(default_factory=list)


def _enrich_ticket(
    ticket: dict[str, Any],
    key: str,
    with_prs: bool,
    with_tests: bool,
    with_props: bool,
) -> None:
    """Add optional PR/test/property sections to a fetched ticket dict, in place."""
    if with_prs:
        ticket["pullRequests"] = get_pull_requests(ticket["id"])
    if with_tests:
        ticket["tests"] = get_xray_tests(key)
    if with_props:
        ticket["properties"] = get_issue_properties(ticket["id"])


def _prepare_pending_attachments(
    ticket: dict[str, Any], output_dir: Path, key: str, with_attachments: bool
) -> list[PendingAttachment]:
    """Build the list of attachments to download, deduping filename collisions."""
    if not with_attachments:
        return []
    attachments = ticket.get("attachments", [])
    if not attachments:
        return []

    attach_dir = output_dir / "attachments" / key
    pending: list[PendingAttachment] = []
    seen: dict[str, int] = {}
    for att in attachments:
        orig_name = att["filename"]
        if orig_name in seen:
            seen[orig_name] += 1
            # Insert counter before extension: foo.png -> foo_2.png
            base, dot, ext_part = orig_name.rpartition(".")
            if dot:
                att["filename"] = f"{base}_{seen[orig_name]}.{ext_part}"
            else:
                att["filename"] = f"{orig_name}_{seen[orig_name]}"
        else:
            seen[orig_name] = 1
        pending.append(PendingAttachment(att, attach_dir))
    return pending


def _write_ticket_file(
    outfile: Path,
    fmt: str,
    ticket: dict[str, Any],
    comments: list[Comment],
    synced: str,
    jira_site: str,
) -> None:
    """Write formatted ticket content (md/json/ndjson) to outfile."""
    if fmt == "json":
        content = format_ticket_json(ticket, comments, synced, jira_site)
    elif fmt == "ndjson":
        content = format_ticket_ndjson(ticket, comments, synced, jira_site)
    else:
        content = format_ticket_markdown(ticket, comments, synced, jira_site)
    atomic_write_text(outfile, content)


def _create_ticket_symlinks(
    output_dir: Path,
    filename: str,
    ticket: dict[str, Any],
    parent_data: dict[str, Any] | None,
) -> None:
    """Create by-component and by-parent symlinks for a markdown export."""
    for comp in ticket.get("components", []):
        if comp:
            comp_dir = output_dir / "by-component" / comp.lower().replace(" ", "-")
            comp_dir.mkdir(parents=True, exist_ok=True)
            link = comp_dir / filename
            link.unlink(missing_ok=True)
            link.symlink_to(f"../../{filename}")

    if parent_data:
        parent_dirname = (
            f"{parent_data['key']}-{normalize_title(parent_data['summary'])}"
        )
        parent_dir = output_dir / "by-parent" / parent_dirname
        parent_dir.mkdir(parents=True, exist_ok=True)
        link = parent_dir / filename
        link.unlink(missing_ok=True)
        link.symlink_to(f"../../{filename}")


def export_ticket(
    key: str,
    output_dir: Path,
    fmt: str = "md",
    with_prs: bool = False,
    with_tests: bool = False,
    with_props: bool = False,
    include_custom: bool = False,
    with_attachments: bool = False,
    symlinks: bool = False,
    defer_attachments: bool = False,
) -> ExportResult:
    """Export a single ticket to markdown or JSON."""
    print(f"Exporting {key}...")

    ticket = get_ticket(
        key,
        full=(fmt == "json"),
        include_custom=include_custom,
        include_attachments=True,  # Always include metadata for markdown section
    )
    if not ticket:
        print(f"  Error: Could not fetch {key}")
        return ExportResult(status="failed")

    _enrich_ticket(ticket, key, with_prs, with_tests, with_props)

    comments = get_comments(key)
    synced = datetime.now().isoformat(timespec="seconds")
    jira_site = get_jira_site()

    summary = ticket.get("summary", "No summary")
    parent_data = ticket.get("parent")

    ext = {"json": "json", "ndjson": "ndjson"}.get(fmt, "md")
    filename = f"{key}-{normalize_title(summary)}.{ext}"

    output_dir.mkdir(parents=True, exist_ok=True)
    outfile = output_dir / filename

    # Download attachments to attachments/{key}/
    pending = _prepare_pending_attachments(ticket, output_dir, key, with_attachments)
    attachment_failures: list[PendingAttachment] = []
    if pending and not defer_attachments:
        print(f"  Downloading {len(pending)} attachment(s)...")
        for p in pending:
            if not p.download():
                attachment_failures.append(p)

    _write_ticket_file(outfile, fmt, ticket, comments, synced, jira_site)

    print(f"  Saved to {outfile}")

    # Create symlinks (only for markdown, disabled by default)
    if symlinks and fmt == "md":
        _create_ticket_symlinks(output_dir, filename, ticket, parent_data)

    if defer_attachments:
        return ExportResult(status="success", path=outfile, pending_attachments=pending)
    return ExportResult(
        status="success", path=outfile, attachment_failures=attachment_failures
    )


def _apply_body_field(ticket: dict[str, Any], body_field: str) -> None:
    """Promote a named field to body content, replacing description."""
    # Check paragraph_fields first (textarea fields)
    paragraph_fields = ticket.get("paragraph_fields", {})
    for name, value in list(paragraph_fields.items()):
        if name.lower() == body_field.lower():
            ticket["description"] = value
            ticket["body_field"] = name
            del paragraph_fields[name]
            return

    # Check custom_fields
    custom_fields = ticket.get("custom_fields", {})
    for name, value in list(custom_fields.items()):
        if name.lower() == body_field.lower():
            ticket["description"] = str(value)
            ticket["body_field"] = name
            del custom_fields[name]
            return

    print(f"Warning: field '{body_field}' not found on ticket", file=sys.stderr)


def export_to_stdout(
    key: str,
    fmt: str = "md",
    with_prs: bool = False,
    with_tests: bool = False,
    with_props: bool = False,
    include_custom: bool = False,
    minimal: bool = False,
    raw: bool = False,
    body_field: str | None = None,
) -> bool:
    """Export a single ticket to stdout."""
    # --field implies --all-fields so the target field is fetched
    if body_field:
        include_custom = True
    ticket = get_ticket(
        key, full=(fmt == "json"), include_custom=include_custom, raw=raw
    )
    if not ticket:
        print(f"Error: Could not fetch {key}", file=sys.stderr)
        return False

    if body_field:
        _apply_body_field(ticket, body_field)

    if minimal:
        print(format_ticket_minimal(ticket))
        return True

    _enrich_ticket(ticket, key, with_prs, with_tests, with_props)

    comments = get_comments(key, raw=raw)
    synced = datetime.now().isoformat(timespec="seconds")
    jira_site = get_jira_site()

    if fmt == "json":
        print(format_ticket_json(ticket, comments, synced, jira_site))
    elif fmt == "ndjson":
        print(format_ticket_ndjson(ticket, comments, synced, jira_site))
    else:
        print(format_ticket_markdown(ticket, comments, synced, jira_site))

    return True


def export_command(args: argparse.Namespace) -> None:
    """Handle export subcommand."""
    fmt = getattr(args, "format", "md")

    # Default to stdout, use --files or -o to save to files
    force_files = getattr(args, "files", False)
    if args.output and args.output != "-":
        to_stdout = False
    elif force_files:
        to_stdout = False
    else:
        to_stdout = True

    tickets = list(args.tickets)

    # Build JQL from options
    jql = args.jql
    if args.board:
        jql = get_board_issues_jql(args.board)
        if not to_stdout:
            print(f"Using board {args.board}")
    elif args.sprint:
        jql = get_sprint_issues_jql(args.sprint)
        if not to_stdout:
            print(f"Using sprint {args.sprint}")

    if jql:
        if not to_stdout:
            print(f"Searching: {jql}")
        found = search_tickets(jql)
        if not to_stdout:
            print(f"Found {len(found)} tickets")
        tickets.extend(found)

    if not tickets:
        print("No tickets specified. Use ticket keys, --jql, --board, or --sprint.")
        sys.exit(1)

    with_prs = getattr(args, "with_prs", False)
    include_custom = getattr(args, "all_fields", False)

    if to_stdout:
        ok = True
        for key in tickets:
            ok &= export_to_stdout(
                key, fmt=fmt, with_prs=with_prs, include_custom=include_custom
            )
        if not ok:
            sys.exit(1)
    else:
        if args.output:
            output_dir = Path(args.output)
        else:
            from zaira.config import get_tickets_dir

            output_dir = get_tickets_dir()
        success = 0
        for key in tickets:
            result = export_ticket(
                key,
                output_dir,
                fmt=fmt,
                with_prs=with_prs,
                include_custom=include_custom,
                with_attachments=True,  # Always download attachments for file exports
            )
            if result.status == "success":
                success += 1
        print(f"\nExported {success}/{len(tickets)} tickets to {output_dir}/")
