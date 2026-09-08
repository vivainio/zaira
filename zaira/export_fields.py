"""Value/field extraction and formatting helpers shared by ticket export."""

import re
from datetime import datetime
from typing import Any

from zaira.mdconv import is_jira_wiki, jira_wiki_to_markdown
from zaira.types import yaml_quote


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

    def extract_text(node: Any) -> str:
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


def _field_block(label: str, text: Any) -> str:
    """Render a labeled Xray step field as natural markdown, preserving any
    embedded paragraphs/bullet lists instead of flattening them into a table cell."""
    text = str(text or "").strip()
    if not text:
        return ""
    return f"\n**{label}:** {text}\n"
