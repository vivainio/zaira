"""Export Jira tickets to markdown."""

import re
from datetime import datetime
from pathlib import Path

from zaira.config import TICKETS_DIR
from zaira.jira_client import get_jira, get_jira_site
from zaira.boards import get_board_issues_jql, get_sprint_issues_jql


def normalize_title(title: str) -> str:
    """Convert title to filename-safe slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > 50:
        slug = slug[:50].rsplit("-", 1)[0]
    return slug


def extract_description(desc) -> str:
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


def get_ticket(key: str) -> dict | None:
    """Fetch ticket details."""
    jira = get_jira()
    try:
        issue = jira.issue(key, expand="renderedFields")
        fields = issue.fields

        # Handle description - could be ADF or string
        desc = fields.description
        if hasattr(desc, "__dict__"):
            # It's an ADF object, convert to dict
            desc = desc.raw if hasattr(desc, "raw") else None

        return {
            "key": issue.key,
            "summary": fields.summary or "No summary",
            "issuetype": fields.issuetype.name if fields.issuetype else "Unknown",
            "status": fields.status.name if fields.status else "Unknown",
            "priority": fields.priority.name if fields.priority else "None",
            "assignee": fields.assignee.emailAddress if fields.assignee else "Unassigned",
            "reporter": fields.reporter.emailAddress if fields.reporter else "Unknown",
            "created": fields.created or "Unknown",
            "updated": fields.updated or "Unknown",
            "description": extract_description(desc),
            "components": [c.name for c in (fields.components or [])],
            "labels": fields.labels or [],
            "parent": {
                "key": fields.parent.key,
                "summary": fields.parent.fields.summary,
            } if hasattr(fields, "parent") and fields.parent else None,
        }
    except Exception as e:
        print(f"  Error fetching {key}: {e}")
        return None


def get_comments(key: str) -> list:
    """Fetch ticket comments."""
    jira = get_jira()
    try:
        issue = jira.issue(key, fields="comment")
        comments = issue.fields.comment.comments if issue.fields.comment else []
        result = []
        for c in comments:
            body = c.body
            if hasattr(body, "raw"):
                body = extract_description(body.raw)
            elif hasattr(body, "__dict__"):
                body = extract_description(body.__dict__)
            result.append({
                "author": c.author.displayName if c.author else "Unknown",
                "created": c.created or "",
                "body": body if isinstance(body, str) else str(body),
            })
        return result
    except Exception:
        return []


def search_tickets(jql: str) -> list[str]:
    """Search for tickets and return list of keys."""
    jira = get_jira()
    try:
        issues = jira.search_issues(jql, maxResults=False)
        return [issue.key for issue in issues]
    except Exception as e:
        print(f"Error searching: {e}")
        return []


def export_ticket(key: str, output_dir: Path) -> bool:
    """Export a single ticket to markdown."""
    print(f"Exporting {key}...")

    ticket = get_ticket(key)
    if not ticket:
        print(f"  Error: Could not fetch {key}")
        return False

    comments = get_comments(key)

    # Extract fields
    summary = ticket.get("summary", "No summary")
    issue_type = ticket.get("issuetype", "Unknown")
    status = ticket.get("status", "Unknown")
    priority = ticket.get("priority", "None")
    assignee = ticket.get("assignee", "Unassigned")
    reporter = ticket.get("reporter", "Unknown")
    created = ticket.get("created", "Unknown")
    updated = ticket.get("updated", "Unknown")
    description = ticket.get("description", "No description") or "No description"
    components = ", ".join(ticket.get("components", [])) or "None"
    labels = ", ".join(ticket.get("labels", [])) or "None"
    parent_data = ticket.get("parent")
    parent = parent_data["key"] if parent_data else "None"

    filename = f"{key}-{normalize_title(summary)}.md"

    # YAML quoting helper
    def yaml_quote(val: str) -> str:
        if any(c in val for c in ':{}[]&*#?|-<>=!%@\\"\'\n'):
            escaped = val.replace('"', '\\"')
            return f'"{escaped}"'
        return val

    synced = datetime.now().isoformat(timespec='seconds')
    jira_site = get_jira_site()

    # Build markdown
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
synced: {synced}
url: https://{jira_site}/browse/{key}
---

# {key}: {summary}

## Description

{description}

## Comments

"""

    if comments:
        for c in comments:
            author = c.get("author", "Unknown")
            date = c.get("created", "")
            body = c.get("body", "")
            md += f"### {author} ({date})\n\n{body}\n\n"
    else:
        md += "_No comments_\n"

    # Write file
    output_dir.mkdir(parents=True, exist_ok=True)
    outfile = output_dir / filename
    outfile.write_text(md)
    print(f"  Saved to {outfile}")

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
        parent_dirname = f"{parent_data['key']}-{normalize_title(parent_data['summary'])}"
        parent_dir = output_dir / "by-parent" / parent_dirname
        parent_dir.mkdir(parents=True, exist_ok=True)
        link = parent_dir / filename
        link.unlink(missing_ok=True)
        link.symlink_to(f"../../{filename}")

    return True


def export_command(args):
    """Handle export subcommand."""
    output_dir = Path(args.output) if args.output else TICKETS_DIR

    tickets = list(args.tickets)

    # Build JQL from options
    jql = args.jql
    if args.board:
        jql = get_board_issues_jql(args.board)
        print(f"Using board {args.board}")
    elif args.sprint:
        jql = get_sprint_issues_jql(args.sprint)
        print(f"Using sprint {args.sprint}")

    if jql:
        print(f"Searching: {jql}")
        found = search_tickets(jql)
        print(f"Found {len(found)} tickets")
        tickets.extend(found)

    if not tickets:
        print("No tickets specified. Use ticket keys, --jql, --board, or --sprint.")
        import sys
        sys.exit(1)

    success = 0
    for key in tickets:
        if export_ticket(key, output_dir):
            success += 1

    print(f"\nExported {success}/{len(tickets)} tickets to {output_dir}/")
