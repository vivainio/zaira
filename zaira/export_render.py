"""Markdown/JSON/NDJSON rendering of fetched ticket data."""

import json
from dataclasses import asdict
from typing import Any

from zaira.export_fields import (
    _field_block,
    _format_timestamp,
    format_custom_field_value,
)
from zaira.types import Comment, yaml_quote


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


def format_ticket_minimal(ticket: dict[str, Any]) -> str:
    """Format ticket as minimal markdown: key + summary front matter, description body."""
    key = ticket.get("key", "")
    summary = ticket.get("summary", "No summary")
    description = ticket.get("description", "No description") or "No description"
    body_field_name = ticket.get("body_field")
    field_line = f"field: {yaml_quote(body_field_name)}\n" if body_field_name else ""
    return f"---\nkey: {key}\nsummary: {yaml_quote(summary)}\n{field_line}---\n{description}\n"


def _render_links_section(issuelinks: list[dict[str, Any]]) -> str:
    """Render issue links as a markdown bullet list."""
    if not issuelinks:
        return "_No links_\n"
    lines = []
    for link in issuelinks:
        link_type = link.get("type", "Related")
        direction = link.get("direction", "outward")
        link_key = link.get("key", "")
        link_summary = link.get("summary", "")
        dir_label = "" if direction == "outward" else " (inward)"
        lines.append(f"- {link_type}{dir_label}: {link_key} - {link_summary}\n")
    return "".join(lines)


def _render_test_markdown(t: dict[str, Any]) -> str:
    """Render a single Xray test (with executions/steps) as markdown."""
    md = f"### {t['key']}: {t['summary']}\n\n"
    md += f"Status: {t['status']} | Assignee: {t['assignee']}\n"
    if t.get("alsoTests"):
        md += f"Also tests: {', '.join(t['alsoTests'])}\n"
    for ex in t.get("executions", []):
        run_status = ex.get("runStatus")
        run_suffix = f", run: {run_status}" if run_status else ""
        md += f"\n#### Execution {ex['key']}: {ex['summary']} ({ex['status']}{run_suffix})\n"
        run_steps = ex.get("steps", [])
        for number, rstep in enumerate(run_steps, 1):
            status = (rstep.get("status") or {}).get("name") or ""
            md += f"\n**Step {number}**{f' — {status}' if status else ''}\n"
            md += _field_block("Actual Result", rstep.get("actualResult"))
            md += _field_block("Comment", rstep.get("comment"))
    steps = t.get("steps", [])
    for number, step in enumerate(steps, 1):
        md += f"\n**Step {number}**\n"
        md += _field_block("Action", step.get("action"))
        md += _field_block("Data", step.get("data"))
        md += _field_block("Expected Result", step.get("result"))
    return md


def _render_pull_requests_section(pull_requests: list[dict[str, Any]]) -> str:
    """Render linked pull requests as a markdown bullet list."""
    lines = []
    for pr in pull_requests:
        name = pr.get("name", "")
        url = pr.get("url", "")
        status = pr.get("status", "")
        lines.append(f"- [{name}]({url}) ({status})\n")
    return "".join(lines)


def _render_attachments_section(attachments: list[dict[str, Any]], key: str) -> str:
    """Render attachments as a markdown bullet list."""
    lines = []
    for att in attachments:
        att_filename = att.get("filename", "")
        size_kb = att.get("size", 0) // 1024
        author = att.get("author", "Unknown")
        created = att.get("created", "")[:10]  # Just the date part
        lines.append(
            f"- [{att_filename}](attachments/{key}/{att_filename}) ({size_kb} KB, {author}, {created})\n"
        )
    return "".join(lines)


def _render_properties_section(properties: list[dict[str, Any]]) -> str:
    """Render issue properties (e.g. ducket grids) as markdown."""
    parts = []
    for prop in properties:
        value = prop["value"]
        if isinstance(value, dict) and "ducketId" in value:
            table = format_ducket(prop)
            if table:
                parts.append(table + "\n\n")
        else:
            parts.append(f"**{prop['key']}**: {json.dumps(value)}\n\n")
    return "".join(parts)


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
    md += _render_links_section(ticket.get("issuelinks", []))

    tests = ticket.get("tests", [])
    if tests:
        md += """
## Tests

"""
        for t in tests:
            md += _render_test_markdown(t) + "\n"

    pull_requests = ticket.get("pullRequests", [])
    if pull_requests:
        md += """
## Pull Requests

"""
        md += _render_pull_requests_section(pull_requests)

    attachments = ticket.get("attachments", [])
    if attachments:
        md += """
## Attachments

"""
        md += _render_attachments_section(attachments, key)

    properties = ticket.get("properties", [])
    if properties:
        md += """
## Properties

"""
        md += _render_properties_section(properties)

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


def format_ticket_ndjson(
    ticket: dict[str, Any], comments: list[Comment], synced: str, jira_site: str
) -> str:
    """Format ticket data as newline-delimited JSON segments.

    Each line is a standalone JSON object with a "type" field and, for
    content sections, a "markdown" field holding fully-rendered markdown
    text. This lets a consumer stream/filter by segment while still being
    able to render each segment's content as markdown.
    """
    key = ticket.get("key", "")
    parent_data = ticket.get("parent")
    lines: list[dict[str, Any]] = []

    lines.append(
        {
            "type": "meta",
            "key": key,
            "summary": ticket.get("summary", "No summary"),
            "issuetype": ticket.get("issuetype", "Unknown"),
            "status": ticket.get("status", "Unknown"),
            "priority": ticket.get("priority", "None"),
            "assignee": ticket.get("assignee", "Unassigned"),
            "reporter": ticket.get("reporter", "Unknown"),
            "created": _format_timestamp(ticket.get("created", "")),
            "updated": _format_timestamp(ticket.get("updated", "")),
            "components": ticket.get("components", []),
            "labels": ticket.get("labels", []),
            "parent": parent_data["key"] if parent_data else None,
            "custom_fields": ticket.get("custom_fields", {}),
            "body_field": ticket.get("body_field"),
            "synced": synced,
            "url": f"https://{jira_site}/browse/{key}",
        }
    )

    lines.append(
        {
            "type": "description",
            "markdown": ticket.get("description", "No description") or "No description",
        }
    )

    paragraph_fields = ticket.get("paragraph_fields", {})
    for name, value in sorted(paragraph_fields.items()):
        if value.strip():
            lines.append({"type": "paragraph", "name": name, "markdown": value})

    lines.append(
        {
            "type": "links",
            "markdown": _render_links_section(ticket.get("issuelinks", [])),
        }
    )

    for t in ticket.get("tests", []):
        lines.append(
            {
                "type": "test",
                "key": t.get("key"),
                "summary": t.get("summary"),
                "markdown": _render_test_markdown(t),
            }
        )

    for pr in ticket.get("pullRequests", []):
        lines.append(
            {
                "type": "pull_request",
                "name": pr.get("name", ""),
                "url": pr.get("url", ""),
                "status": pr.get("status", ""),
            }
        )

    attachments = ticket.get("attachments", [])
    if attachments:
        lines.append(
            {
                "type": "attachments",
                "markdown": _render_attachments_section(attachments, key),
            }
        )

    properties = ticket.get("properties", [])
    if properties:
        lines.append(
            {"type": "properties", "markdown": _render_properties_section(properties)}
        )

    for c in comments:
        lines.append(
            {
                "type": "comment",
                "author": c.author,
                "created": c.created,
                "markdown": c.body,
            }
        )

    return "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
