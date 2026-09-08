"""YAML front matter parsing for wiki markdown files."""

import re
from typing import Any


def parse_front_matter(content: str) -> tuple[dict, str]:
    """Parse YAML front matter from markdown content.

    Args:
        content: Markdown content with optional front matter

    Returns:
        Tuple of (front_matter_dict, body_content)
    """
    import yaml

    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}, content

    end_pos = end_match.end() + 3
    front_matter_str = content[4 : end_match.start() + 3]
    body = content[end_pos:]

    try:
        front_matter = yaml.safe_load(front_matter_str) or {}
    except yaml.YAMLError:
        return {}, content

    return front_matter, body


def write_front_matter(front_matter: dict, body: str) -> str:
    """Write YAML front matter to markdown content.

    Args:
        front_matter: Front matter dict
        body: Markdown body content

    Returns:
        Combined content with front matter
    """
    import yaml

    if not front_matter:
        return body

    # Use inline style for lists (e.g., labels: [a, b, c])
    class InlineListDumper(yaml.SafeDumper):
        pass

    def represent_list(dumper: Any, data: list[Any]) -> Any:
        return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)

    InlineListDumper.add_representer(list, represent_list)

    fm_str = yaml.dump(
        front_matter, Dumper=InlineListDumper, default_flow_style=False, sort_keys=False
    )
    return f"---\n{fm_str}---\n\n{body.lstrip()}"
