"""Create Jira tickets from YAML front matter files."""

import argparse
import re
import sys
from pathlib import Path

import yaml

from zaira.edit import format_field_value
from zaira.info import get_editmeta_field, load_editmeta
from zaira.jira_client import format_jira_error, get_jira
from zaira.util import fuzzy_match


def detect_markdown(text: str) -> bool:
    """Return True if text contains markdown syntax that should be converted."""
    lines = text.split("\n")
    for line in lines:
        # Markdown headings: ## Heading (2+ hashes; single # is Jira numbered list)
        if re.match(r"^#{2,6}\s+\S", line):
            return True
        # Fenced code blocks
        if re.match(r"^```", line):
            return True
        # Markdown bullet lists: - item (Jira uses * for bullets)
        if re.match(r"^\s*-\s+\S", line):
            return True
    # Markdown links: [text](url)
    if re.search(r"\[([^\]]+)\]\(([^)]+)\)", text):
        return True
    # Markdown bold: **text**
    if re.search(r"\*\*[^*]+\*\*", text):
        return True
    return False


# Standard Jira fields that don't need schema lookup
STANDARD_FIELDS = {
    "project": "project",
    "summary": "summary",
    "description": "description",
    "issuetype": "issuetype",
    "type": "issuetype",  # alias
    "priority": "priority",
    "assignee": "assignee",
    "reporter": "reporter",
    "labels": "labels",
    "components": "components",
    "parent": "parent",
    "fixversions": "fixVersions",
    "versions": "versions",
}

# Fields to skip (metadata, not Jira fields)
SKIP_FIELDS = {"key", "url", "synced", "status", "created", "updated"}


def parse_content(content: str) -> tuple[dict, str]:
    """Parse content with YAML front matter.

    Returns:
        Tuple of (front_matter_dict, description_body)
    """
    # Match YAML front matter between --- markers
    match = re.match(r"^---\n(.+?)\n---\n?(.*)", content, re.DOTALL)
    if not match:
        raise ValueError(
            "No YAML front matter found. Expected format:\n"
            "---\n"
            "project: PROJ\n"
            "type: Story\n"
            "summary: Title here\n"
            "---\n"
            "Description body here"
        )

    front_matter = yaml.safe_load(match.group(1))
    body = match.group(2).strip()

    return front_matter, body


def parse_ticket_file(path: Path) -> tuple[dict, str]:
    """Parse a ticket file with YAML front matter."""
    return parse_content(path.read_text())


def _suggest_fields(project: str, issue_type: str, name: str, n: int = 3) -> list[str]:
    """Suggest similar field names from editmeta."""
    editmeta = load_editmeta(project, issue_type)
    if not editmeta or "fields" not in editmeta:
        return []
    lower_to_original = {fn.lower(): fn for fn in editmeta["fields"]}
    matches = fuzzy_match(
        name.lower().replace("_", " "), list(lower_to_original.keys()), n=n
    )
    return [lower_to_original[m] for m in matches]


def map_fields(
    front_matter: dict, description: str, project: str = "", issue_type: str = ""
) -> dict:
    """Map front matter fields to Jira API field format.

    Args:
        front_matter: Parsed YAML front matter
        description: Markdown body as description
        project: Project key for editmeta lookup
        issue_type: Issue type name for editmeta lookup

    Returns:
        Dict ready for Jira API create_issue()
    """
    fields = {}

    # Always include description from body
    if description:
        fields["description"] = description

    for key, value in front_matter.items():
        key_lower = key.lower()

        # Skip metadata fields
        if key_lower in SKIP_FIELDS:
            continue

        # Handle standard fields
        if key_lower in STANDARD_FIELDS:
            jira_field = STANDARD_FIELDS[key_lower]

            if jira_field == "project":
                fields["project"] = {"key": value}
            elif jira_field == "issuetype":
                fields["issuetype"] = {"name": value}
            elif jira_field == "priority":
                fields["priority"] = {"name": value}
            elif jira_field == "assignee":
                fields["assignee"] = {"name": value} if value else None
            elif jira_field == "reporter":
                fields["reporter"] = {"name": value} if value else None
            elif jira_field == "components":
                if isinstance(value, list):
                    names = value
                elif value and value != "None":
                    names = [c.strip() for c in value.split(",")]
                else:
                    names = []
                if names:
                    from zaira.edit import _resolve_component

                    fields["components"] = [
                        _resolve_component(n, project) for n in names
                    ]
            elif jira_field == "labels":
                if isinstance(value, list):
                    fields["labels"] = value
                elif value and value != "None":
                    fields["labels"] = [lbl.strip() for lbl in value.split(",")]
            elif jira_field == "parent":
                if value and value != "None":
                    fields["parent"] = {"key": value}
            elif jira_field in ("fixVersions", "versions"):
                if isinstance(value, list):
                    fields[jira_field] = [{"name": v} for v in value]
                elif value:
                    fields[jira_field] = [{"name": v.strip()} for v in value.split(",")]
            else:
                fields[jira_field] = value
        else:
            em = get_editmeta_field(project, issue_type, key)
            if em:
                field_id = em[0]
                fields[field_id] = format_field_value(
                    field_id, value, project=project, issue_type=issue_type
                )
            else:
                msg = f"Warning: Unknown field '{key}', skipping"
                suggestions = _suggest_fields(project, issue_type, key)
                if suggestions:
                    msg += f". Did you mean: {', '.join(suggestions)}?"
                print(msg, file=sys.stderr)

    return fields


def create_ticket(fields: dict, dry_run: bool = False) -> str | None:
    """Create a Jira ticket.

    Args:
        fields: Mapped fields dict for Jira API
        dry_run: If True, just print what would be created

    Returns:
        Created ticket key, or None on failure
    """
    if dry_run:
        print("Dry run - would create ticket with fields:")
        for key, value in fields.items():
            print(f"  {key}: {value}")
        return None

    jira = get_jira()
    try:
        issue = jira.create_issue(fields=fields)
        return issue.key
    except Exception as e:
        print(f"Error creating ticket: {format_jira_error(e)}", file=sys.stderr)
        return None


def create_command(args: argparse.Namespace) -> None:
    """Handle create subcommand."""
    if args.file == "-":
        content = sys.stdin.read()
        try:
            front_matter, description = parse_content(content)
        except ValueError as e:
            print(f"Error parsing stdin: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        try:
            front_matter, description = parse_ticket_file(path)
        except ValueError as e:
            print(f"Error parsing file: {e}", file=sys.stderr)
            sys.exit(1)

    # Check required fields
    missing = []
    if "project" not in front_matter:
        missing.append("project")
    if "summary" not in front_matter:
        missing.append("summary")
    issue_type = front_matter.get("type") or front_matter.get("issuetype") or ""
    if not issue_type:
        missing.append("type")
    if missing:
        print(
            f"Error: missing required field(s): {', '.join(missing)}\n"
            "YAML front matter must include at least:\n"
            "---\n"
            "project: PROJ\n"
            "type: Story\n"
            "summary: Title here\n"
            "---",
            file=sys.stderr,
        )
        sys.exit(1)

    # Auto-convert markdown to Jira wiki if needed
    if description and detect_markdown(description):
        from zaira.mdconv import markdown_to_jira_wiki

        description = markdown_to_jira_wiki(description)

    project = front_matter.get("project", "")

    # Auto-learn editmeta if needed
    from zaira.info import ensure_editmeta_for_type

    ensure_editmeta_for_type(project, issue_type)

    fields = map_fields(
        front_matter,
        description,
        project=project,
        issue_type=issue_type,
    )
    dry_run = getattr(args, "dry_run", False)

    key = create_ticket(fields, dry_run=dry_run)
    if key:
        print(f"Created {key}")
        from zaira.activity_log import record

        summary = front_matter.get("summary", "")
        record("create", key, summary if summary else None)
