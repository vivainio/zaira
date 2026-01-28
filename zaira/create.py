"""Create Jira tickets from YAML front matter files."""

import argparse
import re
import sys
from pathlib import Path

import yaml

from zaira.edit import format_field_value
from zaira.info import get_field_id, load_schema
from zaira.jira_client import get_jira


def detect_markdown(text: str) -> list[str]:
    """Detect markdown syntax that should be Jira wiki markup.

    Returns list of error messages for each detected issue.
    """
    errors = []
    lines = text.split("\n")

    for i, line in enumerate(lines, 1):
        # Detect markdown headings: ## Heading (but not single # which is Jira numbered list)
        if re.match(r"^#{2,6}\s+\S", line):
            level = len(re.match(r"^(#+)", line).group(1))
            errors.append(
                f"Line {i}: Use 'h{level}. ' instead of '{'#' * level} ' for headings"
            )

    # Detect markdown links: [text](url)
    md_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
    if md_links:
        for link_text, url in md_links[:3]:  # Show first 3
            errors.append(
                f"Use '[{link_text}|{url}]' instead of '[{link_text}]({url})' for links"
            )

    # Detect markdown bold: **text**
    if re.search(r"\*\*[^*]+\*\*", text):
        errors.append("Use '*text*' instead of '**text**' for bold")

    return errors


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
        raise ValueError("No YAML front matter found (expected --- markers)")

    front_matter = yaml.safe_load(match.group(1))
    body = match.group(2).strip()

    return front_matter, body


def parse_ticket_file(path: Path) -> tuple[dict, str]:
    """Parse a ticket file with YAML front matter."""
    return parse_content(path.read_text())


def map_fields(front_matter: dict, description: str) -> dict:
    """Map front matter fields to Jira API field format.

    Args:
        front_matter: Parsed YAML front matter
        description: Markdown body as description

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
                    fields["components"] = [{"name": c} for c in value]
                elif value and value != "None":
                    fields["components"] = [
                        {"name": c.strip()} for c in value.split(",")
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
            # Try custom field lookup by name
            field_id = get_field_id(key)
            if field_id:
                fields[field_id] = format_field_value(field_id, value)
            else:
                print(f"Warning: Unknown field '{key}', skipping", file=sys.stderr)

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
        print(f"Error creating ticket: {e}", file=sys.stderr)
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
    if "project" not in front_matter:
        print("Error: 'project' field is required", file=sys.stderr)
        sys.exit(1)
    if "summary" not in front_matter:
        print("Error: 'summary' field is required", file=sys.stderr)
        sys.exit(1)

    # Check if schema is available for custom field mapping
    schema = load_schema()
    if not schema or "fields" not in schema:
        print(
            "Warning: No cached schema. Custom fields won't be mapped.", file=sys.stderr
        )
        print(
            "Run 'zaira info fields --refresh' to cache field mappings.",
            file=sys.stderr,
        )

    # Check for markdown syntax in description
    if description:
        md_errors = detect_markdown(description)
        if md_errors:
            print(
                "Error: Description contains markdown syntax. Use Jira wiki markup instead:",
                file=sys.stderr,
            )
            for err in md_errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)

    fields = map_fields(front_matter, description)
    dry_run = getattr(args, "dry_run", False)

    key = create_ticket(fields, dry_run=dry_run)
    if key:
        print(f"Created {key}")
