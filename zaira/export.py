"""Export Jira tickets to markdown or JSON."""

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from zaira.info import get_field_custom_type, get_field_name, load_default_fields
from zaira.jira_client import format_jira_error, get_jira, get_jira_site
from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
from zaira.mdconv import is_jira_wiki, jira_wiki_to_markdown
from zaira.types import Attachment, Comment, get_user_identifier, yaml_quote


def _format_timestamp(ts: str) -> str:
    """Format Jira timestamp to shorter ISO form.

    2026-01-29T22:50:09.667+0200 -> 2026-01-29 22:50
    """
    if not ts:
        return ts
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts


def normalize_title(title: str) -> str:
    """Convert title to filename-safe slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > 50:
        slug = slug[:50].rsplit("-", 1)[0]
    return slug


def extract_description(
    desc: dict | str | list | Any | None, *, raw: bool = False
) -> str:
    """Extract plain text from Atlassian Document Format.

    Args:
        raw: If True, skip wiki-to-markdown conversion (preserve Jira wiki markup).
    """
    if not desc:
        return "No description"
    if isinstance(desc, str):
        if raw:
            return desc
        return jira_wiki_to_markdown(desc) if is_jira_wiki(desc) else desc

    def extract_text(node) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            if node.get("type") == "text":
                return node.get("text", "")
            if node.get("type") == "hardBreak":
                return "\n"
            if node.get("type") == "inlineCard":
                return node.get("attrs", {}).get("url", "")
            content = node.get("content", [])
            return "".join(extract_text(c) for c in content)
        if isinstance(node, list):
            return "".join(extract_text(c) for c in node)
        return ""

    return extract_text(desc).strip()


def extract_custom_field_value(value: Any) -> Any:
    """Extract a serializable value from a custom field.

    Handles various Jira field types like objects with 'value' or 'name' attrs.
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [extract_custom_field_value(v) for v in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "name"):
        return value.name
    if hasattr(value, "key"):
        return value.key
    if isinstance(value, dict):
        if "value" in value:
            return value["value"]
        if "displayName" in value:
            return value["displayName"]
        if "name" in value:
            return value["name"]
    return str(value)


# Patterns that indicate placeholder/unassigned values
PLACEHOLDER_PATTERNS = [
    "?",
    "{}",
    "[]",
    "pending",
    "n/a",
    "none",
    "unknown",
    "unassigned",
    "no analysis",
    "not needed",
    "not applicable",
    "* list",
    "please remember",
    "<img src=",
    "warning:",
    "||",  # table markup templates
    "*user story",
    "*saas approval",
    "*post upgrade",
    "some risk",
]


def is_placeholder_value(value: Any) -> bool:
    """Check if a value is a placeholder/unassigned value that should be skipped."""
    if value is None:
        return True
    if isinstance(value, list):
        # Filter out lists with only N/A type values
        filtered = [v for v in value if not _is_na_value(v)]
        return len(filtered) == 0
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        v = value.strip().lower()
        if not v:
            return True
        for pattern in PLACEHOLDER_PATTERNS:
            if v == pattern or v.startswith(pattern):
                return True
    return False


def _is_na_value(value: Any) -> bool:
    """Check if a single value is N/A or similar."""
    if not isinstance(value, str):
        return False
    v = value.strip().lower()
    return v in ("n/a", "n/a - not applicable", "none", "unknown", "")


def _is_bogus_field_name(name: str) -> bool:
    """Check if a field name is bogus/administrative and should be skipped."""
    n = name.lower()
    return (
        n.startswith("warning")
        or n.startswith("rank")
        or "comment" in n
        or n.startswith("checklist")
    )


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
        print(f"  Error fetching {key}: {format_jira_error(e)}")
        return None


def get_comments(key: str, raw: bool = False) -> list[Comment]:
    """Fetch ticket comments."""
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="comment")
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
    except Exception:
        return []


def get_linked_tests(key: str) -> list[dict]:
    """Fetch Xray Test and Test Execution issues linked to a Jira issue.

    Follows 'Tests' link type (inward = "tested by") to find Test issues,
    then checks for Test Executions linked to those tests.
    """
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="issuelinks")
        test_keys = []
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
                                "key": linked.key,
                                "summary": linked.fields.summary,
                                "status": linked.fields.status.name,
                            }
                        )
                    elif (
                        lt_name in ("Story", "Bug", "Task", "Epic")
                        and linked.key != key
                    ):
                        if link.type.name == "Tests":
                            also_tests.append(linked.key)

                tests.append(
                    {
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
    except Exception:
        return []


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
    a list of dicts with 'key' and 'value'.
    """
    jira = get_jira()
    try:
        session = jira._session
        if session is None:
            return []
        resp = session.get(jira._get_url(f"issue/{issue_id}/properties"))
        keys = [p["key"] for p in resp.json().get("keys", [])]
        results = []
        for key in keys:
            if any(key.startswith(p) for p in PROPS_SKIP_PREFIXES):
                continue
            r = session.get(jira._get_url(f"issue/{issue_id}/properties/{key}"))
            if r.status_code == 200:
                results.append({"key": key, "value": r.json().get("value", {})})
        return results
    except Exception:
        return []


def format_ducket(prop: dict) -> str:
    """Format a ducket property (ducketId + rows) as a markdown table."""
    value = prop["value"]
    rows = value.get("rows", [])
    if not rows:
        return ""
    # Collect all column names in order of first appearance
    cols: list[str] = []
    for row in rows:
        for col in row.get("columns", {}):
            if col not in cols:
                cols.append(col)
    if not cols:
        return ""
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    lines = [header, sep]
    for row in sorted(rows, key=lambda r: r.get("order", 0)):
        cells = [str(row.get("columns", {}).get(c, "")) for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def get_pull_requests(issue_id: str) -> list[dict]:
    """Fetch GitHub PRs linked to a Jira issue via dev-status API."""
    jira = get_jira()
    try:
        assert jira._session is not None
        resp = jira._session.get(
            f"{jira._options['server']}/rest/dev-status/1.0/issue/detail",
            params={
                "issueId": issue_id,
                "applicationType": "GitHub",
                "dataType": "pullrequest",
            },
        )
        data = resp.json()
        prs = []
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
    except Exception:
        return []


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


def format_custom_field_value(value: Any) -> str:
    """Format a custom field value for YAML output."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(yaml_quote(str(v)) for v in value) + "]"
    return yaml_quote(str(value))


def format_ticket_minimal(ticket: dict[str, Any]) -> str:
    """Format ticket as minimal markdown: key + summary front matter, description body."""
    key = ticket.get("key", "")
    summary = ticket.get("summary", "No summary")
    description = ticket.get("description", "No description") or "No description"
    body_field_name = ticket.get("body_field")
    field_line = f"field: {yaml_quote(body_field_name)}\n" if body_field_name else ""
    return f"---\nkey: {key}\nsummary: {yaml_quote(summary)}\n{field_line}---\n{description}\n"


def format_ticket_markdown(
    ticket: dict[str, Any], comments: list[Comment], synced: str, jira_site: str
) -> str:
    """Format ticket data as markdown."""
    key = ticket.get("key", "")
    summary = ticket.get("summary", "No summary")
    issue_type = ticket.get("issuetype", "Unknown")
    status = ticket.get("status", "Unknown")
    priority = ticket.get("priority", "None")
    assignee = ticket.get("assignee", "Unassigned")
    reporter = ticket.get("reporter", "Unknown")
    description = ticket.get("description", "No description") or "No description"
    components = ", ".join(ticket.get("components", [])) or "None"
    labels = ", ".join(ticket.get("labels", [])) or "None"
    parent_data = ticket.get("parent")
    parent = parent_data["key"] if parent_data else "None"

    # Build custom fields YAML lines (non-textarea fields from --all-fields)
    custom_fields_yaml = ""
    custom_fields = ticket.get("custom_fields", {})
    for name, value in sorted(custom_fields.items()):
        custom_fields_yaml += f"{name}: {format_custom_field_value(value)}\n"

    # Build field: line if body was promoted from a named field
    body_field_name = ticket.get("body_field")
    body_field_yaml = (
        f"field: {yaml_quote(body_field_name)}\n" if body_field_name else ""
    )

    # Build paragraph sections (textarea fields, always shown)
    paragraph_fields = ticket.get("paragraph_fields", {})
    paragraph_sections = "".join(
        f"\n## {name}\n\n{value}\n"
        for name, value in sorted(paragraph_fields.items())
        if value.strip()
    )

    md = f"""---
key: {key}
summary: {yaml_quote(summary)}
type: {yaml_quote(issue_type)}
status: {yaml_quote(status)}
priority: {yaml_quote(priority)}
assignee: {yaml_quote(assignee)}
reporter: {yaml_quote(reporter)}
created: {_format_timestamp(ticket.get("created", ""))}
updated: {_format_timestamp(ticket.get("updated", ""))}
components: {yaml_quote(components)}
labels: {yaml_quote(labels)}
parent: {parent}
{custom_fields_yaml}{body_field_yaml}synced: {synced}
url: https://{jira_site}/browse/{key}
---

# {key}: {summary}

## Description

{description}
{paragraph_sections}
## Links

"""
    issuelinks = ticket.get("issuelinks", [])
    if issuelinks:
        for link in issuelinks:
            link_type = link.get("type", "Related")
            direction = link.get("direction", "outward")
            link_key = link.get("key", "")
            link_summary = link.get("summary", "")
            dir_label = "" if direction == "outward" else " (inward)"
            md += f"- {link_type}{dir_label}: {link_key} - {link_summary}\n"
    else:
        md += "_No links_\n"

    tests = ticket.get("tests", [])
    if tests:
        md += """
## Tests

"""
        for t in tests:
            md += f"- {t['key']}: {t['summary']}\n"
            md += f"  Status: {t['status']} | Assignee: {t['assignee']}\n"
            if t.get("alsoTests"):
                md += f"  Also tests: {', '.join(t['alsoTests'])}\n"
            for ex in t.get("executions", []):
                md += f"  - Execution {ex['key']}: {ex['summary']} ({ex['status']})\n"

    pull_requests = ticket.get("pullRequests", [])
    if pull_requests:
        md += """
## Pull Requests

"""
        for pr in pull_requests:
            name = pr.get("name", "")
            url = pr.get("url", "")
            status = pr.get("status", "")
            md += f"- [{name}]({url}) ({status})\n"

    attachments = ticket.get("attachments", [])
    if attachments:
        md += """
## Attachments

"""
        for att in attachments:
            att_filename = att.get("filename", "")
            size_kb = att.get("size", 0) // 1024
            author = att.get("author", "Unknown")
            created = att.get("created", "")[:10]  # Just the date part
            md += f"- [{att_filename}](attachments/{key}/{att_filename}) ({size_kb} KB, {author}, {created})\n"

    properties = ticket.get("properties", [])
    if properties:
        md += """
## Properties

"""
        for prop in properties:
            value = prop["value"]
            if isinstance(value, dict) and "ducketId" in value:
                table = format_ducket(prop)
                if table:
                    md += table + "\n\n"
            else:
                md += f"**{prop['key']}**: {json.dumps(value)}\n\n"

    md += """
## Comments

"""
    if comments:
        for c in comments:
            md += f"### {c.author} ({c.created})\n\n{c.body}\n\n"
    else:
        md += "_No comments_\n"

    return md


def format_ticket_json(
    ticket: dict[str, Any], comments: list[Comment], synced: str, jira_site: str
) -> str:
    """Format ticket data as JSON."""
    key = ticket.get("key", "")
    data = {
        **ticket,
        "comments": [asdict(c) for c in comments],
        "synced": synced,
        "url": f"https://{jira_site}/browse/{key}",
    }
    return json.dumps(data, indent=2)


class PendingAttachment:
    """An attachment to download later."""

    __slots__ = ("attachment", "output_dir")

    def __init__(self, attachment: Attachment, output_dir: Path) -> None:
        self.attachment = attachment
        self.output_dir = output_dir

    def download(self) -> bool:
        return download_attachment(self.attachment, self.output_dir)


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
) -> bool | list[PendingAttachment]:
    """Export a single ticket to markdown or JSON.

    Returns:
        bool when defer_attachments is False (success/failure).
        list[PendingAttachment] when defer_attachments is True and successful,
        or False on failure.
    """
    print(f"Exporting {key}...")

    ticket = get_ticket(
        key,
        full=(fmt == "json"),
        include_custom=include_custom,
        include_attachments=True,  # Always include metadata for markdown section
    )
    if not ticket:
        print(f"  Error: Could not fetch {key}")
        return False

    if with_prs:
        ticket["pullRequests"] = get_pull_requests(ticket["id"])
    if with_tests:
        ticket["tests"] = get_linked_tests(key)
    if with_props:
        ticket["properties"] = get_issue_properties(ticket["id"])

    comments = get_comments(key)
    synced = datetime.now().isoformat(timespec="seconds")
    jira_site = get_jira_site()

    summary = ticket.get("summary", "No summary")
    parent_data = ticket.get("parent")

    ext = "json" if fmt == "json" else "md"
    filename = f"{key}-{normalize_title(summary)}.{ext}"

    output_dir.mkdir(parents=True, exist_ok=True)
    outfile = output_dir / filename

    # Download attachments to attachments/{key}/
    pending: list[PendingAttachment] = []
    if with_attachments:
        attachments = ticket.get("attachments", [])
        if attachments:
            attach_dir = output_dir / "attachments" / key
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

            if not defer_attachments:
                print(f"  Downloading {len(pending)} attachment(s)...")
                for p in pending:
                    p.download()

    if fmt == "json":
        outfile.write_text(
            format_ticket_json(ticket, comments, synced, jira_site), encoding="utf-8"
        )
    else:
        outfile.write_text(
            format_ticket_markdown(ticket, comments, synced, jira_site),
            encoding="utf-8",
        )

    print(f"  Saved to {outfile}")

    # Create symlinks (only for markdown, disabled by default)
    if symlinks and fmt == "md":
        # Create symlinks by component
        for comp in ticket.get("components", []):
            if comp:
                comp_dir = output_dir / "by-component" / comp.lower().replace(" ", "-")
                comp_dir.mkdir(parents=True, exist_ok=True)
                link = comp_dir / filename
                link.unlink(missing_ok=True)
                link.symlink_to(f"../../{filename}")

        # Create symlinks by parent
        if parent_data:
            parent_dirname = (
                f"{parent_data['key']}-{normalize_title(parent_data['summary'])}"
            )
            parent_dir = output_dir / "by-parent" / parent_dirname
            parent_dir.mkdir(parents=True, exist_ok=True)
            link = parent_dir / filename
            link.unlink(missing_ok=True)
            link.symlink_to(f"../../{filename}")

    if defer_attachments:
        return pending
    return True


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

    if with_prs:
        ticket["pullRequests"] = get_pull_requests(ticket["id"])
    if with_tests:
        ticket["tests"] = get_linked_tests(key)
    if with_props:
        ticket["properties"] = get_issue_properties(ticket["id"])

    comments = get_comments(key, raw=raw)
    synced = datetime.now().isoformat(timespec="seconds")
    jira_site = get_jira_site()

    if fmt == "json":
        print(format_ticket_json(ticket, comments, synced, jira_site))
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
        for key in tickets:
            export_to_stdout(
                key, fmt=fmt, with_prs=with_prs, include_custom=include_custom
            )
    else:
        if args.output:
            output_dir = Path(args.output)
        else:
            from zaira.config import get_tickets_dir

            output_dir = get_tickets_dir()
        success = 0
        for key in tickets:
            if export_ticket(
                key,
                output_dir,
                fmt=fmt,
                with_prs=with_prs,
                include_custom=include_custom,
                with_attachments=True,  # Always download attachments for file exports
            ):
                success += 1
        print(f"\nExported {success}/{len(tickets)} tickets to {output_dir}/")
