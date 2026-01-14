"""Export Jira tickets to markdown or JSON."""

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from zaira.config import TICKETS_DIR, find_project_root
from zaira.info import get_field_name
from zaira.jira_client import get_jira, get_jira_site
from zaira.boards import get_board_issues_jql, get_sprint_issues_jql
from zaira.types import Attachment, Comment, Ticket, get_user_identifier, yaml_quote


def normalize_title(title: str) -> str:
    """Convert title to filename-safe slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > 50:
        slug = slug[:50].rsplit("-", 1)[0]
    return slug


def extract_description(desc: dict | str | list | Any | None) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not desc:
        return "No description"
    if isinstance(desc, str):
        return desc

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
) -> Ticket | None:
    """Fetch ticket details.

    Args:
        key: Ticket key (e.g., "FOO-123")
        full: Include extra fields for JSON export
        include_custom: Include custom fields with schema name lookup
        include_attachments: Include attachment metadata
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
            "description": extract_description(desc),
            "components": [c.name for c in (fields.components or [])],
            "labels": fields.labels or [],
            "parent": {
                "key": fields.parent.key,
                "summary": fields.parent.fields.summary,
            }
            if hasattr(fields, "parent") and fields.parent
            else None,
            "issuelinks": [
                {
                    "type": link.type.name,
                    "direction": "outward"
                    if hasattr(link, "outwardIssue")
                    else "inward",
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
                for link in (fields.issuelinks or [])
            ],
        }

        # Add custom fields with human-readable names
        if include_custom:
            raw_fields = issue.raw.get("fields", {})
            custom_fields = {}
            for field_id, value in raw_fields.items():
                if field_id.startswith("customfield_") and value is not None:
                    extracted = extract_custom_field_value(value)
                    if not is_placeholder_value(extracted):
                        field_name = get_field_name(field_id)
                        if field_name and not _is_bogus_field_name(field_name):
                            custom_fields[field_name] = extracted
                        elif not field_name:
                            # Keep ID if name not in schema
                            custom_fields[field_id] = extracted
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
                attachments.append({
                    "id": att.id,
                    "filename": att.filename,
                    "size": att.size,
                    "mimeType": getattr(att, "mimeType", "application/octet-stream"),
                    "author": att.author.displayName if att.author else "Unknown",
                    "created": att.created or "",
                })
            ticket["attachments"] = attachments

        return ticket
    except Exception as e:
        print(f"  Error fetching {key}: {e}")
        return None


def get_comments(key: str) -> list[Comment]:
    """Fetch ticket comments."""
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="comment")
        comments = issue.fields.comment.comments if issue.fields.comment else []
        result: list[Comment] = []
        for c in comments:
            body = c.body
            if hasattr(body, "raw"):
                body = extract_description(body.raw)
            elif hasattr(body, "__dict__"):
                body = extract_description(body.__dict__)
            result.append(
                Comment(
                    author=c.author.displayName if c.author else "Unknown",
                    created=c.created or "",
                    body=body if isinstance(body, str) else str(body),
                )
            )
        return result
    except Exception:
        return []


def get_pull_requests(issue_id: str) -> list[dict]:
    """Fetch GitHub PRs linked to a Jira issue via dev-status API."""
    jira = get_jira()
    try:
        resp = jira._session.get(
            f'{jira._options["server"]}/rest/dev-status/1.0/issue/detail',
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
                prs.append({
                    "name": pr.get("name"),
                    "url": pr.get("url"),
                    "status": pr.get("status"),
                })
        return prs
    except Exception:
        return []


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


def download_attachment(attachment: Attachment, output_dir: Path) -> bool:
    """Download a single attachment to the output directory.

    Args:
        attachment: Attachment metadata dict
        output_dir: Directory to save the file

    Returns:
        True if successful, False otherwise
    """
    size = attachment.get("size", 0)
    if size > MAX_ATTACHMENT_SIZE:
        size_mb = size / (1024 * 1024)
        print(f"    Skipping {attachment['filename']} ({size_mb:.1f} MB > 10 MB limit)")
        return False

    jira = get_jira()
    try:
        # Construct the attachment URL
        url = f'{jira._options["server"]}/secure/attachment/{attachment["id"]}/{attachment["filename"]}'
        resp = jira._session.get(url)
        resp.raise_for_status()

        output_dir.mkdir(parents=True, exist_ok=True)
        outfile = output_dir / attachment["filename"]
        outfile.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    Error downloading {attachment['filename']}: {e}")
        return False


def search_tickets(jql: str) -> list[str]:
    """Search for tickets and return list of keys."""
    jira = get_jira()
    try:
        issues = jira.search_issues(jql, maxResults=False)
        return [issue.key for issue in issues]
    except Exception as e:
        print(f"Error searching: {e}")
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


def format_ticket_markdown(
    ticket: dict, comments: list[Comment], synced: str, jira_site: str
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

    # Build custom fields YAML lines
    custom_fields_yaml = ""
    custom_fields = ticket.get("custom_fields", {})
    for name, value in sorted(custom_fields.items()):
        custom_fields_yaml += f"{name}: {format_custom_field_value(value)}\n"

    md = f"""---
key: {key}
summary: {yaml_quote(summary)}
type: {yaml_quote(issue_type)}
status: {yaml_quote(status)}
priority: {yaml_quote(priority)}
assignee: {yaml_quote(assignee)}
reporter: {yaml_quote(reporter)}
components: {yaml_quote(components)}
labels: {yaml_quote(labels)}
parent: {parent}
{custom_fields_yaml}synced: {synced}
url: https://{jira_site}/browse/{key}
---

# {key}: {summary}

## Description

{description}

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
    ticket: dict, comments: list[Comment], synced: str, jira_site: str
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


def export_ticket(
    key: str,
    output_dir: Path,
    fmt: str = "md",
    with_prs: bool = False,
    include_custom: bool = False,
    with_attachments: bool = False,
) -> bool:
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
        return False

    if with_prs:
        ticket["pullRequests"] = get_pull_requests(ticket["id"])

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
    if with_attachments:
        attachments = ticket.get("attachments", [])
        if attachments:
            attach_dir = output_dir / "attachments" / key
            print(f"  Downloading {len(attachments)} attachment(s)...")
            seen: dict[str, int] = {}
            for att in attachments:
                orig_name = att["filename"]
                if orig_name in seen:
                    seen[orig_name] += 1
                    # Insert counter before extension: foo.png -> foo_2.png
                    base, dot, ext = orig_name.rpartition(".")
                    if dot:
                        att["filename"] = f"{base}_{seen[orig_name]}.{ext}"
                    else:
                        att["filename"] = f"{orig_name}_{seen[orig_name]}"
                else:
                    seen[orig_name] = 1
                download_attachment(att, attach_dir)

    if fmt == "json":
        outfile.write_text(format_ticket_json(ticket, comments, synced, jira_site))
    else:
        outfile.write_text(format_ticket_markdown(ticket, comments, synced, jira_site))

    print(f"  Saved to {outfile}")

    # Create symlinks (only for markdown)
    if fmt == "md":
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

    return True


def export_to_stdout(
    key: str, fmt: str = "md", with_prs: bool = False, include_custom: bool = False
) -> bool:
    """Export a single ticket to stdout."""
    ticket = get_ticket(key, full=(fmt == "json"), include_custom=include_custom)
    if not ticket:
        print(f"Error: Could not fetch {key}", file=sys.stderr)
        return False

    if with_prs:
        ticket["pullRequests"] = get_pull_requests(ticket["id"])

    comments = get_comments(key)
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

    # Default to stdout if no zproject.toml found, otherwise files
    has_project = find_project_root() is not None
    force_files = getattr(args, "files", False)
    if args.output == "-":
        to_stdout = True
    elif args.output or force_files:
        to_stdout = False
    else:
        to_stdout = not has_project

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
            export_to_stdout(key, fmt=fmt, with_prs=with_prs, include_custom=include_custom)
    else:
        output_dir = Path(args.output) if args.output else TICKETS_DIR
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
