"""Markdown conversion utilities."""

import re
from html.parser import HTMLParser
from pathlib import Path

import markdown


def extract_local_images(md_content: str) -> list[tuple[str, str]]:
    """Extract local image references from markdown.

    Args:
        md_content: Markdown content

    Returns:
        List of (alt_text, image_path) tuples for local images only
    """
    # Pattern: ![alt](path) - but not URLs
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    images = []
    for match in re.finditer(pattern, md_content):
        alt, path = match.group(1), match.group(2)
        # Skip URLs (http://, https://, //)
        if not path.startswith(('http://', 'https://', '//')):
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
        if path.startswith(('http://', 'https://', '//')):
            return match.group(0)
        # Use just the filename for attachment reference
        filename = Path(path).name
        return f'![{alt}](attachment:{filename})'

    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_image, md_content)


def convert_attachments_to_images(md_content: str, image_dir: str = "./images") -> str:
    """Convert Confluence attachment references back to local paths.

    Converts: ![alt](attachment:foo.png)
    To: ![alt](./images/foo.png)
    """
    def replace_attachment(match: re.Match) -> str:
        alt = match.group(1)
        path = match.group(2)
        if path.startswith('attachment:'):
            filename = path[len('attachment:'):]
            return f'![{alt}]({image_dir}/{filename})'
        return match.group(0)

    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_attachment, md_content)


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
        f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>'
        f'</ac:structured-macro>'
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
    lines = md_content.split('\n')
    result = []
    in_code_block = False

    for line in lines:
        # Track fenced code blocks to avoid modifying them
        if line.startswith('```'):
            in_code_block = not in_code_block
            result.append(line)
            continue

        if in_code_block:
            result.append(line)
            continue

        # Match list items with leading whitespace
        # Pattern: leading spaces + list marker (-, *, +, or number.)
        match = re.match(r'^( +)([-*+]|\d+\.) ', line)
        if match:
            indent = match.group(1)
            # Double the indent (2 -> 4, 4 -> 8, etc.)
            new_indent = indent * 2
            result.append(new_indent + line[len(indent):])
        else:
            result.append(line)

    return '\n'.join(result)


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
        r'^\[TOC\]$',
        '<!--TOC_PLACEHOLDER-->',
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
        r'(<p>)?<!--TOC_PLACEHOLDER-->(</p>)?',
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

    html = re.sub(r'<img\s+([^>]*)/>', img_to_attachment, html)

    return html


def storage_to_markdown(html_content: str, image_dir: str = "./images") -> str:
    """Convert Confluence storage format to Markdown.

    Args:
        html_content: Confluence storage format HTML
        image_dir: Directory for local image paths

    Returns:
        Markdown text
    """
    # Convert Confluence attachment images to markdown
    # <ac:image ac:alt="..."><ri:attachment ri:filename="..."/></ac:image>
    def attachment_to_img(match: re.Match) -> str:
        alt = match.group(1) or ""
        filename = match.group(2)
        return f'![{alt}]({image_dir}/{filename})'

    html_content = re.sub(
        r'<ac:image(?:\s+ac:alt="([^"]*)")?[^>]*>\s*<ri:attachment\s+ri:filename="([^"]+)"[^/]*/>\s*</ac:image>',
        attachment_to_img,
        html_content,
    )

    # Convert Confluence TOC macro to [TOC]
    html_content = re.sub(
        r'<ac:structured-macro[^>]*ac:name="toc"[^>]*/?>(?:</ac:structured-macro>)?',
        '\n[TOC]\n',
        html_content,
    )

    # First, convert Confluence code macros to placeholder fenced blocks
    # Pattern: <ac:structured-macro ac:name="code">...<ac:parameter ac:name="language">X</ac:parameter>...<ac:plain-text-body><![CDATA[...]]></ac:plain-text-body>...</ac:structured-macro>
    html_content = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r'<ac:parameter[^>]*ac:name="language"[^>]*>([^<]*)</ac:parameter>.*?'
        r'<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?'
        r'</ac:structured-macro>',
        _macro_to_code_block,
        html_content,
        flags=re.DOTALL,
    )

    # Also handle code macros without language parameter
    html_content = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r'<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?'
        r'</ac:structured-macro>',
        lambda m: f"\n```\n{m.group(1).rstrip(chr(10))}\n```\n",
        html_content,
        flags=re.DOTALL,
    )

    class MarkdownExtractor(HTMLParser):
        HEADER_LEVELS = {
            "h1": "#", "h2": "##", "h3": "###",
            "h4": "####", "h5": "#####", "h6": "######",
        }

        def __init__(self):
            super().__init__()
            self.text = []
            self.in_code = False
            self.list_stack = []  # Track nested lists: ("ul",) or ("ol", current_num)
            self.just_closed_list = False  # Track if we just closed a nested list
            # Table state
            self.in_table = False
            self.in_thead = False
            self.table_row = []  # Current row cells
            self.table_header_done = False

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == "br":
                self.text.append("\n")
            elif tag in self.HEADER_LEVELS:
                self.text.append(f"\n{self.HEADER_LEVELS[tag]} ")
            elif tag == "ul":
                if self.list_stack:  # Nested list - need newline
                    self.text.append("\n")
                self.list_stack.append(("ul",))
            elif tag == "ol":
                if self.list_stack:  # Nested list - need newline
                    self.text.append("\n")
                start = int(attrs_dict.get("start", 1))
                self.list_stack.append(("ol", start))
            elif tag == "li":
                indent = "  " * (len(self.list_stack) - 1)  # 2-space indent (normalized on input)
                if self.list_stack and self.list_stack[-1][0] == "ol":
                    num = self.list_stack[-1][1]
                    self.text.append(f"{indent}{num}. ")
                    # Increment for next item
                    self.list_stack[-1] = ("ol", num + 1)
                else:
                    self.text.append(f"{indent}- ")
            elif tag == "code" and not self.in_code:
                self.text.append("`")
                self.in_code = True
            elif tag == "pre":
                pass  # Handled by code
            elif tag in {"strong", "b"}:
                self.text.append("**")
            elif tag in {"em", "i"}:
                self.text.append("*")
            elif tag == "hr":
                self.text.append("\n---\n")
            elif tag == "a":
                href = attrs_dict.get("href", "")
                self.text.append("[")
                self._pending_link = href
            elif tag == "img":
                src = attrs_dict.get("src", "")
                alt = attrs_dict.get("alt", "")
                self.text.append(f"![{alt}]({src})")
            elif tag == "blockquote":
                self.text.append("\n> ")
            elif tag == "table":
                self.in_table = True
                self.table_header_done = False
                self.text.append("\n")
            elif tag == "thead":
                self.in_thead = True
            elif tag == "tbody":
                self.in_thead = False
            elif tag in {"tr", "th", "td"}:
                if tag == "tr":
                    self.table_row = []

        def handle_endtag(self, tag):
            if tag in self.HEADER_LEVELS:
                self.text.append("\n")
            elif tag in {"ul", "ol"}:
                if self.list_stack:
                    self.list_stack.pop()
                # Only add newline after top-level list
                if not self.list_stack:
                    self.text.append("\n")
                else:
                    self.just_closed_list = True
            elif tag == "li":
                # Skip newline if we just closed a nested list (already have one)
                if self.just_closed_list:
                    self.just_closed_list = False
                else:
                    self.text.append("\n")
            elif tag in {"p", "div"}:
                self.text.append("\n\n")
            elif tag == "code" and self.in_code:
                self.text.append("`")
                self.in_code = False
            elif tag == "pre":
                pass
            elif tag in {"strong", "b"}:
                self.text.append("**")
            elif tag in {"em", "i"}:
                self.text.append("*")
            elif tag == "a":
                href = getattr(self, "_pending_link", "")
                self.text.append(f"]({href})")
                self._pending_link = ""
            elif tag == "blockquote":
                self.text.append("\n")
            elif tag == "table":
                self.in_table = False
                self.text.append("\n")
            elif tag == "thead":
                self.in_thead = False
            elif tag in {"th", "td"}:
                pass  # Cell content captured in handle_data
            elif tag == "tr":
                if self.table_row:
                    self.text.append("| " + " | ".join(self.table_row) + " |\n")
                    if self.in_thead or (self.in_table and not self.table_header_done):
                        # Add separator after header row
                        self.text.append("|" + "|".join(["---"] * len(self.table_row)) + "|\n")
                        self.table_header_done = True
                    self.table_row = []

        def handle_data(self, data):
            # Skip whitespace-only data when inside a list or table (between tags)
            if (self.list_stack or self.in_table) and not data.strip():
                return
            # Capture table cell content
            if self.in_table:
                self.table_row.append(data.strip())
                return
            self.text.append(data)

    extractor = MarkdownExtractor()
    extractor.feed(html_content)

    text = "".join(extractor.text)
    # Collapse multiple newlines into max 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
