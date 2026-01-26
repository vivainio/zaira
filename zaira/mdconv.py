"""Markdown conversion utilities."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import markdown

# Confluence namespace URIs
AC_NS = "http://atlassian.com/content"
RI_NS = "http://atlassian.com/resource/identifier"


def extract_local_images(md_content: str) -> list[tuple[str, str]]:
    """Extract local image references from markdown.

    Args:
        md_content: Markdown content

    Returns:
        List of (alt_text, image_path) tuples for local images only
    """
    # Pattern: ![alt](path) - but not URLs
    pattern = r"!\[([^\]]*)\]\(([^)]+)\)"
    images = []
    for match in re.finditer(pattern, md_content):
        alt, path = match.group(1), match.group(2)
        # Skip URLs (http://, https://, //)
        if not path.startswith(("http://", "https://", "//")):
            images.append((alt, path))
    return images


def convert_images_to_attachments(md_content: str) -> str:
    """Convert markdown image syntax to Confluence attachment references.

    Converts: ![alt](./images/foo.png)
    To: ![alt](attachment:foo.png)

    The actual file upload happens separately.
    """

    def replace_image(match: re.Match) -> str:
        alt = match.group(1)
        path = match.group(2)
        # Skip URLs
        if path.startswith(("http://", "https://", "//")):
            return match.group(0)
        # Use just the filename for attachment reference
        filename = Path(path).name
        return f"![{alt}](attachment:{filename})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_image, md_content)


def convert_attachments_to_images(md_content: str, image_dir: str = "./images") -> str:
    """Convert Confluence attachment references back to local paths.

    Converts: ![alt](attachment:foo.png)
    To: ![alt](./images/foo.png)
    """

    def replace_attachment(match: re.Match) -> str:
        alt = match.group(1)
        path = match.group(2)
        if path.startswith("attachment:"):
            filename = path[len("attachment:") :]
            return f"![{alt}]({image_dir}/{filename})"
        return match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace_attachment, md_content)


# Map markdown language names to Confluence code macro languages
LANG_MAP = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "rb": "ruby",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "yml": "yaml",
    "cs": "c#",
    "csharp": "c#",
    "cpp": "c++",
    "xml": "html/xml",
    "html": "html/xml",
    "ps1": "powershell",
    "psm1": "powershell",
}

# Reverse map for Confluence -> markdown
LANG_MAP_REVERSE = {
    "html/xml": "xml",
    "c#": "csharp",
    "c++": "cpp",
    "none": "",
}


def _code_block_to_macro(match: re.Match) -> str:
    """Convert HTML code block to Confluence code macro."""
    lang = match.group(1) or ""
    code = match.group(2)

    # Normalize language name
    lang = LANG_MAP.get(lang.lower(), lang.lower()) if lang else "none"

    # Unescape HTML entities in code content
    code = (
        code.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&amp;", "&")  # Must be last
    )

    return (
        f'<ac:structured-macro ac:name="code">'
        f'<ac:parameter ac:name="language">{lang}</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
        f"</ac:structured-macro>"
    )


def _macro_to_code_block(match: re.Match) -> str:
    """Convert Confluence code macro to markdown fenced code block."""
    lang = match.group(1) or ""
    code = match.group(2)

    # Normalize language name back to markdown conventions
    lang = LANG_MAP_REVERSE.get(lang.lower(), lang.lower())

    # Remove trailing newline if present (will be added by fence)
    code = code.rstrip("\n")

    return f"\n```{lang}\n{code}\n```\n"


def _normalize_list_indent(md_content: str) -> str:
    """Convert 2-space list indents to 4-space for markdown parser.

    The Python markdown library requires 4-space indentation for nested lists.
    This preprocessor allows users to write with 2-space indents.
    """
    lines = md_content.split("\n")
    result = []
    in_code_block = False

    for line in lines:
        # Track fenced code blocks to avoid modifying them
        if line.startswith("```"):
            in_code_block = not in_code_block
            result.append(line)
            continue

        if in_code_block:
            result.append(line)
            continue

        # Match list items with leading whitespace
        # Pattern: leading spaces + list marker (-, *, +, or number.)
        match = re.match(r"^( +)([-*+]|\d+\.) ", line)
        if match:
            indent = match.group(1)
            # Double the indent (2 -> 4, 4 -> 8, etc.)
            new_indent = indent * 2
            result.append(new_indent + line[len(indent) :])
        else:
            result.append(line)

    return "\n".join(result)


def markdown_to_storage(md_content: str, convert_local_images: bool = True) -> str:
    """Convert Markdown to Confluence storage format.

    Args:
        md_content: Markdown text
        convert_local_images: If True, convert local image paths to attachment refs

    Returns:
        HTML suitable for Confluence storage format
    """
    # Convert local images to attachment references before processing
    if convert_local_images:
        md_content = convert_images_to_attachments(md_content)

    # Normalize 2-space list indents to 4-space
    md_content = _normalize_list_indent(md_content)

    # Convert [TOC] marker before markdown processing
    md_content = re.sub(
        r"^\[TOC\]$",
        "<!--TOC_PLACEHOLDER-->",
        md_content,
        flags=re.MULTILINE,
    )

    extensions = [
        "tables",
        "fenced_code",
        "sane_lists",
    ]
    html = markdown.markdown(md_content, extensions=extensions)

    # Convert <pre><code class="language-X">...</code></pre> to Confluence code macro
    html = re.sub(
        r'<pre><code(?:\s+class="language-([^"]*)")?>(.*?)</code></pre>',
        _code_block_to_macro,
        html,
        flags=re.DOTALL,
    )

    # Convert TOC placeholder to Confluence TOC macro
    html = re.sub(
        r"(<p>)?<!--TOC_PLACEHOLDER-->(</p>)?",
        '<ac:structured-macro ac:name="toc"/>',
        html,
    )

    # Convert attachment images to Confluence attachment macro
    # <img alt="..." src="attachment:filename.png" /> -> <ac:image><ri:attachment ri:filename="..."/></ac:image>
    def img_to_attachment(match: re.Match) -> str:
        attrs = match.group(1)
        alt_match = re.search(r'alt="([^"]*)"', attrs)
        src_match = re.search(r'src="attachment:([^"]*)"', attrs)
        if src_match:
            filename = src_match.group(1)
            alt = alt_match.group(1) if alt_match else ""
            alt_attr = f' ac:alt="{alt}"' if alt else ""
            return f'<ac:image{alt_attr}><ri:attachment ri:filename="{filename}"/></ac:image>'
        return match.group(0)

    html = re.sub(r"<img\s+([^>]*)/>", img_to_attachment, html)

    return html


def _get_tag(elem: ET.Element) -> str:
    """Get local tag name without namespace."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _get_attr(elem: ET.Element, name: str, ns: str | None = None) -> str | None:
    """Get attribute value, checking both namespaced and prefixed forms."""
    if ns:
        # Try full namespace URI form first
        val = elem.get(f"{{{ns}}}{name}")
        if val is not None:
            return val
    # Try without namespace
    return elem.get(name)


def _extract_code_macro(elem: ET.Element) -> tuple[str, str]:
    """Extract language and code from a Confluence code macro element."""
    lang = ""
    code = ""

    for child in elem:
        tag = _get_tag(child)
        if tag == "parameter":
            param_name = _get_attr(child, "name", AC_NS) or _get_attr(child, "name")
            if param_name == "language":
                lang = (child.text or "").strip()
        elif tag == "plain-text-body":
            code = child.text or ""

    return lang, code


def _elem_to_markdown(
    elem: ET.Element,
    image_dir: str,
    list_stack: list[tuple],
    in_table: bool,
    table_state: dict,
) -> str:
    """Recursively convert an XML element to markdown."""
    tag = _get_tag(elem)

    # Confluence structured-macro
    if tag == "structured-macro":
        macro_name = _get_attr(elem, "name", AC_NS) or _get_attr(elem, "name")
        if macro_name == "code":
            lang, code = _extract_code_macro(elem)
            lang = LANG_MAP_REVERSE.get(lang.lower(), lang.lower()) if lang else ""
            code = code.rstrip("\n")
            return f"\n```{lang}\n{code}\n```\n"
        elif macro_name == "toc":
            return "\n[TOC]\n"
        # Unknown macro - skip
        return ""

    # Confluence image with attachment
    if tag == "image":
        alt = _get_attr(elem, "alt", AC_NS) or ""
        for child in elem:
            if _get_tag(child) == "attachment":
                filename = (
                    _get_attr(child, "filename", RI_NS)
                    or _get_attr(child, "filename")
                    or ""
                )
                return f"![{alt}]({image_dir}/{filename})"
        return ""

    # Headers
    header_map = {
        "h1": "#",
        "h2": "##",
        "h3": "###",
        "h4": "####",
        "h5": "#####",
        "h6": "######",
    }
    if tag in header_map:
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return f"\n{header_map[tag]} {inner}\n"

    # Lists
    if tag == "ul":
        new_stack = list_stack + [("ul",)]
        prefix = "\n" if list_stack else ""
        inner = _process_children(elem, image_dir, new_stack, in_table, table_state)
        suffix = "\n" if not list_stack else ""
        return prefix + inner + suffix

    if tag == "ol":
        start = int(elem.get("start", 1))
        new_stack = list_stack + [("ol", start)]
        prefix = "\n" if list_stack else ""
        inner = _process_children(elem, image_dir, new_stack, in_table, table_state)
        suffix = "\n" if not list_stack else ""
        return prefix + inner + suffix

    if tag == "li":
        indent = "  " * (len(list_stack) - 1)
        if list_stack and list_stack[-1][0] == "ol":
            num = list_stack[-1][1]
            marker = f"{indent}{num}. "
            # Mutate for next sibling - create new tuple
            list_stack[-1] = ("ol", num + 1)
        else:
            marker = f"{indent}- "
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return marker + inner.strip() + "\n"

    # Table handling
    if tag == "table":
        state = {"in_thead": False, "header_done": False}
        inner = _process_children(elem, image_dir, list_stack, True, state)
        return "\n" + inner + "\n"

    if tag == "thead":
        table_state["in_thead"] = True
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        table_state["in_thead"] = False
        return inner

    if tag == "tbody":
        return _process_children(elem, image_dir, list_stack, in_table, table_state)

    if tag == "tr":
        cells = []
        for child in elem:
            child_tag = _get_tag(child)
            if child_tag in {"th", "td"}:
                cell_text = _process_children(
                    child, image_dir, list_stack, in_table, table_state
                )
                cells.append(cell_text.strip())
        if not cells:
            return ""
        row = "| " + " | ".join(cells) + " |\n"
        if table_state.get("in_thead") or not table_state.get("header_done"):
            row += "|" + "|".join(["---"] * len(cells)) + "|\n"
            table_state["header_done"] = True
        return row

    if tag in {"th", "td"}:
        return _process_children(elem, image_dir, list_stack, in_table, table_state)

    # Inline formatting
    if tag in {"strong", "b"}:
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return f"**{inner}**"

    if tag in {"em", "i"}:
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return f"*{inner}*"

    if tag == "code":
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return f"`{inner}`"

    if tag == "a":
        href = elem.get("href", "")
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return f"[{inner}]({href})"

    if tag == "img":
        src = elem.get("src", "")
        alt = elem.get("alt", "")
        return f"![{alt}]({src})"

    if tag == "br":
        return "\n"

    if tag == "hr":
        return "\n---\n"

    if tag == "blockquote":
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        lines = inner.strip().split("\n")
        return "\n" + "\n".join(f"> {line}" for line in lines) + "\n"

    # Block elements that just add spacing
    if tag in {"p", "div"}:
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return inner + "\n\n"

    # Default: process children
    return _process_children(elem, image_dir, list_stack, in_table, table_state)


def _process_children(
    elem: ET.Element,
    image_dir: str,
    list_stack: list[tuple],
    in_table: bool,
    table_state: dict,
) -> str:
    """Process element's text and children."""
    result = []

    # Element's direct text
    if elem.text:
        text = elem.text
        # Skip whitespace-only in lists/tables
        if (list_stack or in_table) and not text.strip():
            pass
        else:
            result.append(text)

    # Process children
    for child in elem:
        result.append(
            _elem_to_markdown(child, image_dir, list_stack, in_table, table_state)
        )
        # Tail text after child
        if child.tail:
            tail = child.tail
            if (list_stack or in_table) and not tail.strip():
                pass
            else:
                result.append(tail)

    return "".join(result)


def storage_to_markdown(html_content: str, image_dir: str = "./images") -> str:
    """Convert Confluence storage format to Markdown.

    Args:
        html_content: Confluence storage format HTML
        image_dir: Directory for local image paths

    Returns:
        Markdown text
    """
    # Wrap content in root element with namespace declarations
    wrapped = f'<root xmlns:ac="{AC_NS}" xmlns:ri="{RI_NS}">{html_content}</root>'

    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        # Handle common issues: HTML entities not defined in XML
        # Replace common HTML entities with Unicode equivalents
        html_content = html_content.replace("&nbsp;", "\u00a0")
        html_content = html_content.replace("&ldquo;", "\u201c")
        html_content = html_content.replace("&rdquo;", "\u201d")
        html_content = html_content.replace("&lsquo;", "\u2018")
        html_content = html_content.replace("&rsquo;", "\u2019")
        html_content = html_content.replace("&mdash;", "\u2014")
        html_content = html_content.replace("&ndash;", "\u2013")
        html_content = html_content.replace("&hellip;", "\u2026")
        wrapped = f'<root xmlns:ac="{AC_NS}" xmlns:ri="{RI_NS}">{html_content}</root>'
        try:
            root = ET.fromstring(wrapped)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse Confluence storage format: {e}") from e

    text = _elem_to_markdown(root, image_dir, [], False, {})

    # Collapse multiple newlines into max 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
