"""Markdown conversion utilities."""

import hashlib
import html
import re
import shutil
import subprocess
import sys
import tempfile
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


class DiagramRenderer:
    """Definition for a fenced-block diagram renderer."""

    def __init__(
        self,
        name: str,
        cmd: str,
        args: list[str],
        src_ext: str = ".txt",
        out_ext: str = ".png",
        install_hint: str | None = None,
    ) -> None:
        self.name = name
        self.cmd = cmd
        self.args = args
        self.src_ext = src_ext
        self.out_ext = out_ext
        self.install_hint = install_hint

    def build_command(self, in_path: Path, out_path: Path) -> list[str]:
        """Build the CLI command with placeholders resolved."""
        # Use shutil.which to resolve the full path - required on Windows
        # where .cmd/.bat wrappers won't execute without shell=True
        resolved_cmd = shutil.which(self.cmd) or self.cmd
        result = [resolved_cmd]
        for arg in self.args:
            result.append(
                arg.replace("{in}", str(in_path))
                .replace("{out}", str(out_path))
                .replace("{outdir}", str(out_path.parent))
            )
        return result

    def is_available(self) -> bool:
        return shutil.which(self.cmd) is not None


# Registry of supported diagram renderers
RENDERERS: dict[str, DiagramRenderer] = {
    "mermaid": DiagramRenderer(
        name="mermaid",
        cmd="mmdr",
        args=["-i", "{in}", "-o", "{out}", "-e", "svg"],
        src_ext=".mmd",
        out_ext=".svg",
        install_hint="Download from https://github.com/1jehuang/mermaid-rs-renderer/releases or: cargo install mermaid-rs-renderer",
    ),
    "mermaid-slow": DiagramRenderer(
        name="mermaid-slow",
        cmd="mmdc",
        args=["-i", "{in}", "-o", "{out}"],
        src_ext=".mmd",
        install_hint="npm install -g @mermaid-js/mermaid-cli",
    ),
    "plantuml": DiagramRenderer(
        name="plantuml",
        cmd="plantuml",
        args=["-tpng", "-o", "{outdir}", "{in}"],
        src_ext=".puml",
    ),
    "dot": DiagramRenderer(
        name="dot",
        cmd="dot",
        args=["-Tpng", "-o", "{out}", "{in}"],
        src_ext=".dot",
    ),
    "graphviz": DiagramRenderer(
        name="graphviz",
        cmd="dot",
        args=["-Tpng", "-o", "{out}", "{in}"],
        src_ext=".dot",
    ),
    "d2": DiagramRenderer(
        name="d2",
        cmd="d2",
        args=["{in}", "{out}"],
        src_ext=".d2",
    ),
    "ditaa": DiagramRenderer(
        name="ditaa",
        cmd="ditaa",
        args=["{in}", "{out}"],
        src_ext=".ditaa",
    ),
}


def render_diagram_blocks(
    md_content: str,
    renderers: list[str] | None = None,
) -> tuple[str, list[Path]]:
    """Render fenced diagram blocks to images.

    Finds fenced code blocks matching requested renderers, renders each to an
    image in a temp directory, and replaces the code block with the rendered
    image. Renderers whose CLI tool is not installed are silently skipped.

    Args:
        md_content: Markdown content
        renderers: List of renderer names to activate (e.g. ["mermaid", "dot"]).
            If None, no rendering is done.

    Returns:
        Tuple of (modified_content, list_of_temp_png_paths).
        Caller is responsible for cleaning up temp files via cleanup_render_temps().
    """
    if not renderers:
        return md_content, []

    # Resolve requested renderers to available ones
    active: list[tuple[str, DiagramRenderer]] = []
    for name in renderers:
        renderer = RENDERERS.get(name)
        if not renderer:
            raise ValueError(
                f"Unknown renderer '{name}'. Available: {', '.join(RENDERERS)}"
            )
        if renderer.is_available():
            active.append((name, renderer))
        else:
            hint = f" {renderer.install_hint}" if renderer.install_hint else ""
            raise RuntimeError(f"Renderer '{name}': '{renderer.cmd}' not found.{hint}")

    if not active:
        return md_content, []

    # Build a combined pattern matching any active renderer's fence tag
    tags = "|".join(re.escape(name) for name, _ in active)
    pattern = re.compile(rf"```({tags})\s*\n(.*?)```", re.DOTALL)
    blocks = list(pattern.finditer(md_content))
    if not blocks:
        return md_content, []

    tmpdir = Path(tempfile.mkdtemp(prefix="zaira-render-"))
    temp_files: list[Path] = []
    renderer_map = dict(active)

    # Process in reverse order to preserve string positions
    for match in reversed(blocks):
        tag = match.group(1)
        source = match.group(2)
        renderer = renderer_map[tag]

        content_hash = hashlib.sha256(source.encode()).hexdigest()[:12]
        filename = f"{tag}-{content_hash}{renderer.out_ext}"
        out_file = tmpdir / filename
        src_file = tmpdir / f"{tag}-{content_hash}{renderer.src_ext}"

        src_file.write_text(source, encoding="utf-8")
        cmd = renderer.build_command(src_file, out_file)

        result = subprocess.run(cmd, capture_output=True, timeout=30)

        if result.returncode == 0 and out_file.exists():
            replacement = f"![{tag} diagram]({out_file})"
            md_content = (
                md_content[: match.start()] + replacement + md_content[match.end() :]
            )
            temp_files.append(out_file)
        else:
            print(
                f"  Warning: {tag} render failed: {result.stderr.decode(errors='replace').strip()}",
                file=sys.stderr,
            )

    return md_content, temp_files


def cleanup_render_temps(temp_files: list[Path]) -> None:
    """Remove temporary rendered PNG files and their parent directory."""
    if not temp_files:
        return
    tmpdir = temp_files[0].parent
    # Remove the entire temp directory
    shutil.rmtree(tmpdir, ignore_errors=True)


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


def _parse_confluence_macro(macro_str: str) -> tuple[str, dict]:
    """Parse Confluence macro syntax {name:param1=value1|param2=value2}.

    Args:
        macro_str: String like "page-tree:root=@self" or "toc"

    Returns:
        Tuple of (macro_name, params_dict)
    """
    if ":" not in macro_str:
        return macro_str, {}

    name, params_str = macro_str.split(":", 1)
    params = {}

    # Parse param1=value1|param2=value2
    for param_pair in params_str.split("|"):
        if "=" in param_pair:
            key, val = param_pair.split("=", 1)
            params[key.strip()] = val.strip()

    return name, params


def _confluence_macro_to_xml(macro_str: str) -> str:
    """Convert Confluence macro syntax to structured macro XML.

    Args:
        macro_str: String like "{page-tree:root=@self}"

    Returns:
        Confluence storage format XML
    """
    # Remove the braces
    if macro_str.startswith("{") and macro_str.endswith("}"):
        macro_content = macro_str[1:-1]
    else:
        macro_content = macro_str

    name, params = _parse_confluence_macro(macro_content)

    # Build the macro XML
    xml = f'<ac:structured-macro ac:name="{name}">'

    for param_name, param_value in params.items():
        xml += f'<ac:parameter ac:name="{param_name}">{param_value}</ac:parameter>'

    xml += "</ac:structured-macro>"

    return xml


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

    Supports mixed Confluence/Jira wiki markup and markdown syntax.
    Wiki syntax is automatically converted to markdown first.

    Args:
        md_content: Markdown text (may contain Confluence/Jira wiki markup)
        convert_local_images: If True, convert local image paths to attachment refs

    Returns:
        HTML suitable for Confluence storage format
    """
    # Convert Confluence/Jira wiki syntax to markdown first
    # This allows users to mix wiki and markdown syntax
    # Only convert if we detect unambiguous wiki patterns (h1., bq., {code}, etc.)
    # to avoid false positives with markdown (*italic*, etc.)
    has_unambiguous_wiki = bool(
        re.search(
            r"^h[1-6]\.|^bq\.|^\|\||{code|{panel|{quote|{color|{info|{warning|{error|{quote",
            md_content,
            re.MULTILINE,
        )
    )
    if has_unambiguous_wiki:
        md_content = jira_wiki_to_markdown(md_content)

    # Extract Confluence macros {name:params} before markdown processing
    # Replace with placeholders to preserve them through markdown conversion
    # Only match known Confluence macros to avoid mangling literal braces
    # (e.g. {documentId} in REST paths)
    _KNOWN_MACROS = {
        "anchor",
        "attachments",
        "children",
        "code",
        "color",
        "column",
        "compose",
        "content-report-table",
        "contributors",
        "details",
        "error",
        "excerpt",
        "excerpt-include",
        "expand",
        "html",
        "include",
        "info",
        "jira",
        "layout",
        "loremipsum",
        "multimedia",
        "noformat",
        "note",
        "page-tree",
        "panel",
        "quote",
        "recently-updated",
        "section",
        "status",
        "tip",
        "toc",
        "warning",
    }
    macro_placeholders = {}
    macro_pattern = r"\{([a-z\-]+)(?::([^}]*))?\}"

    def preserve_macro(match: re.Match) -> str:
        name = match.group(1).lower()
        if name not in _KNOWN_MACROS:
            return match.group(0)  # leave unknown {words} as-is
        macro_str = match.group(0)
        placeholder = f"<!--MACRO_PLACEHOLDER_{len(macro_placeholders)}-->"
        macro_placeholders[placeholder] = macro_str
        return placeholder

    md_content = re.sub(macro_pattern, preserve_macro, md_content, flags=re.IGNORECASE)

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

    # Escape mid-word underscores so markdown doesn't treat them as emphasis
    # e.g. FILE_STORE_AIRPORT_STAGE should not become FILE<em>STORE</em>AIRPORT_STAGE
    # Skip HTML comments (placeholders) and fenced code blocks
    def _escape_mid_word_underscores(text: str) -> str:
        parts = re.split(r"(<!--.*?-->|```.*?```)", text, flags=re.DOTALL)
        for i, part in enumerate(parts):
            if not part.startswith("<!--") and not part.startswith("```"):
                parts[i] = re.sub(r"(?<=\w)_(?=\w)", r"\_", part)
        return "".join(parts)

    md_content = _escape_mid_word_underscores(md_content)

    extensions = [
        "tables",
        "fenced_code",
        "sane_lists",
    ]
    html = markdown.markdown(md_content, extensions=extensions)

    # Convert ~~strikethrough~~ to <del> tags
    html = re.sub(r"~~(.*?)~~", r"<del>\1</del>", html)

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

    # Restore and convert Confluence macros
    for placeholder, macro_str in macro_placeholders.items():
        macro_xml = _confluence_macro_to_xml(macro_str)
        # Remove wrapper <p> tags if markdown wrapped the placeholder
        html = html.replace(f"<p>{placeholder}</p>", macro_xml)
        html = html.replace(placeholder, macro_xml)

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
            # SVG images need explicit width — Confluence renders them tiny otherwise
            width_attr = ' ac:width="800"' if filename.endswith(".svg") else ""
            return f'<ac:image{alt_attr}{width_attr}><ri:attachment ri:filename="{filename}"/></ac:image>'
        return match.group(0)

    html = re.sub(r"<img\s+([^>]*)/>", img_to_attachment, html)

    # Convert Jira-style emoticons to Confluence emoticon macros
    _EMOTICON_MAP = {
        "(/)": "tick",
        "(x)": "cross",
        "(!)": "warning",
        "(i)": "information",
        "(?)": "question",
        "(+)": "plus",
        "(-)": "minus",
        "(on)": "light-on",
        "(off)": "light-off",
        "(*)": "yellow-star",
    }
    for emoticon, name in _EMOTICON_MAP.items():
        html = html.replace(emoticon, f'<ac:emoticon ac:name="{name}"/>')

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
        else:
            # Preserve generic macros as {name:param1=value1|param2=value2}
            params = []
            body_elem = None
            for child in elem:
                child_tag = _get_tag(child)
                if child_tag == "parameter":
                    param_name = _get_attr(child, "name", AC_NS) or _get_attr(
                        child, "name"
                    )
                    param_value = child.text or ""
                    if param_name:
                        params.append(f"{param_name}={param_value}")
                elif child_tag == "rich-text-body":
                    body_elem = child

            macro_str = macro_name or ""
            if params:
                macro_str += ":" + "|".join(params)

            if body_elem is not None:
                body_md = _process_children(
                    body_elem, image_dir, list_stack, in_table, table_state
                )
                return f"\n{{{macro_str}}}\n{body_md}\n{{{macro_name}}}\n"
            return f"\n{{{macro_str}}}\n"

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

    # Confluence emoticon
    if tag == "emoticon":
        _EMOTICON_REVERSE = {
            "tick": "(/)",
            "cross": "(x)",
            "warning": "(!)",
            "information": "(i)",
            "question": "(?)",
            "plus": "(+)",
            "minus": "(-)",
            "light-on": "(on)",
            "light-off": "(off)",
            "yellow-star": "(*)",
        }
        name = _get_attr(elem, "name", AC_NS) or _get_attr(elem, "name") or ""
        return _EMOTICON_REVERSE.get(name, f"({name})")

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

    if tag in {"del", "s"}:
        inner = _process_children(elem, image_dir, list_stack, in_table, table_state)
        return f"~~{inner}~~"

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


def _convert_inline_md(text: str) -> str:
    """Convert inline markdown formatting to Jira wiki markup."""
    # Images before links: ![alt](url) -> !url!
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"!\2!", text)
    # Links: [text](url) -> [text|url]
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"[\1|\2]", text)
    # Bold: **text** or __text__ -> *text*
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"*\1*", text)
    text = re.sub(r"__([^_\n]+)__", r"*\1*", text)
    # Note: single *text* is intentionally NOT converted to _text_ because
    # *text* is valid Jira bold markup — converting it would mangle Jira wiki
    # that passes through the pipeline a second time.
    # Strikethrough: ~~text~~ -> -text-
    text = re.sub(r"~~([^~\n]+)~~", r"-\1-", text)
    # Inline code: `code` -> {{code}}
    text = re.sub(r"`([^`]+)`", r"{{\1}}", text)
    return text


def markdown_to_jira_wiki(text: str) -> str:
    """Convert markdown text to Jira wiki markup.

    Handles headers, bold, italic, links, images, fenced code blocks,
    inline code, bullet lists, numbered lists, blockquotes, and horizontal rules.
    """
    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Fenced code blocks: ```lang\n...\n```
        fence_match = re.match(r"^```(\w*)\s*$", line)
        if fence_match:
            lang = fence_match.group(1)
            lang = LANG_MAP.get(lang.lower(), lang.lower()) if lang else ""
            lang_attr = f":language={lang}" if lang else ""
            code_lines = []
            i += 1
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                code_lines.append(lines[i])
                i += 1
            result.append(f"{{code{lang_attr}}}")
            result.extend(code_lines)
            result.append("{code}")
            i += 1  # skip closing ```
            continue

        # Headers: ## Heading -> h2. Heading (single # skipped — Jira numbered list)
        header_match = re.match(r"^(#{2,6})\s+(.*)", line)
        if header_match:
            level = len(header_match.group(1))
            content = _convert_inline_md(header_match.group(2))
            result.append(f"h{level}. {content}")
            i += 1
            continue

        # Horizontal rule: --- or *** or ___ on its own line
        if re.match(r"^(---+|\*\*\*+|___+)\s*$", line):
            result.append("----")
            i += 1
            continue

        # Blockquotes: > text -> bq. text
        bq_match = re.match(r"^>\s*(.*)", line)
        if bq_match:
            result.append(f"bq. {_convert_inline_md(bq_match.group(1))}")
            i += 1
            continue

        # Bullet lists: - item (markdown) -> * item (Jira)
        bullet_match = re.match(r"^(\s*)-\s+(.*)", line)
        if bullet_match:
            indent = len(bullet_match.group(1))
            level = indent // 2 + 1
            content = _convert_inline_md(bullet_match.group(2))
            result.append("*" * level + " " + content)
            i += 1
            continue

        # Numbered lists: 1. item -> # item
        num_match = re.match(r"^(\s*)\d+\.\s+(.*)", line)
        if num_match:
            indent = len(num_match.group(1))
            level = indent // 2 + 1
            content = _convert_inline_md(num_match.group(2))
            result.append("#" * level + " " + content)
            i += 1
            continue

        # Regular line - apply inline conversions
        result.append(_convert_inline_md(line))
        i += 1

    return "\n".join(result)


def _convert_inline_jira(text: str) -> str:
    """Convert inline Jira wiki formatting to markdown."""
    # Extract inline code spans first to protect them from further conversion
    code_spans: list[str] = []

    def _save_code(m: re.Match) -> str:
        code_spans.append(m.group(1))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    text = re.sub(r"\{\{([^}]+)\}\}", _save_code, text)

    # Images: !url! or !url|params! -> ![](url)  (before links to avoid conflicts)
    def _jira_img_to_md(m: re.Match) -> str:
        img = m.group(1)
        # Strip |params (width, alt, etc.)
        url = img.split("|")[0]
        return f"![]({url})"

    text = re.sub(r"!([^!\s][^!\n]*?)!", _jira_img_to_md, text)

    # Links: [text|url] or [text|url|smart-link] -> [text](url)
    def _jira_link_to_md(m: re.Match) -> str:
        label = m.group(1)
        rest = m.group(2)
        # Strip Jira rendering hints like |smart-link, |smart-card
        url = rest.split("|")[0]
        # When label equals URL, just emit the URL
        if label == url:
            return url
        return f"[{label}]({url})"

    text = re.sub(r"\[([^]|]+)\|([^]]+)\]", _jira_link_to_md, text)
    # Bare URL links: [http://url] -> http://url (but not [text](url) markdown links)
    text = re.sub(r"\[(https?://[^\]]+)\](?!\()", r"\1", text)
    # User mentions: [~username] or [~accountid:...] -> @username
    text = re.sub(r"\[~(?:accountid:)?([^\]]+)\]", r"@\1", text)
    # Attachment links: [^filename] -> filename
    text = re.sub(r"\[\^([^\]]+)\]", r"\1", text)
    # Bold: *text* -> **text** (single-star Jira bold)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"**\1**", text)
    # Italic: _text_ -> *text*
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"*\1*", text)
    # Citation: ??text?? -> *text*
    text = re.sub(r"\?\?([^?\n]+)\?\?", r"*\1*", text)
    # Strikethrough: -text- -> ~~text~~
    text = re.sub(r"(?<![-\w])-([^-\n]+)-(?![-\w])", r"~~\1~~", text)
    # Inserted/underline: +text+ -> *text* (no markdown underline)
    text = re.sub(r"(?<!\w)\+([^+\n]+)\+(?!\w)", r"*\1*", text)
    # Superscript: ^text^ -> <sup>text</sup>
    text = re.sub(r"\^([^^\n]+)\^", r"<sup>\1</sup>", text)
    # Subscript: ~text~ -> <sub>text</sub>
    text = re.sub(r"(?<!~)~([^~\n]+)~(?!~)", r"<sub>\1</sub>", text)
    # Color: {color:xxx}text{color} -> text (strip color markup)
    text = re.sub(r"\{color(?::[^}]*)?\}(.*?)\{color\}", r"\1", text)
    # Forced line break: \\ -> <br> (but not \\\ or inside URLs)
    text = re.sub(r"(?<!\\)\\\\(?!\\)", "<br>", text)
    # Em dash: --- -> — and en dash: -- -> – (only standalone, not ---- rule)
    text = re.sub(r"(?<!-)---(?!-)", "—", text)
    text = re.sub(r"(?<!-)--(?!-)", "–", text)

    # Restore inline code spans
    def _restore_code(m: re.Match) -> str:
        return f"`{code_spans[int(m.group(1))]}`"

    text = re.sub(r"\x00CODE(\d+)\x00", _restore_code, text)
    return text


def jira_wiki_to_markdown(text: str) -> str:
    """Convert Jira wiki markup to markdown.

    Handles headers, bold, italic, links, images, code blocks,
    inline code, bullet lists, numbered lists, blockquotes, horizontal rules,
    and tables.
    """
    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Quote blocks: {quote}...{quote} -> blockquote
        if re.match(r"^\{quote\}\s*$", line):
            quote_lines = []
            i += 1
            while i < len(lines) and not re.match(r"^\{quote\}\s*$", lines[i]):
                quote_lines.append(lines[i])
                i += 1
            for ql in quote_lines:
                result.append(f"> {_convert_inline_jira(ql)}")
            i += 1  # skip closing {quote}
            continue

        # Panel blocks: {panel:...}...{panel} -> blockquote with optional title
        panel_match = re.match(r"^\{panel(?::([^}]*))?\}\s*$", line)
        if panel_match:
            params = panel_match.group(1) or ""
            title = ""
            if params:
                title_match = re.search(r"title=([^|}]+)", params)
                if title_match:
                    title = title_match.group(1).strip()
            panel_lines = []
            i += 1
            while i < len(lines) and not re.match(r"^\{panel\}\s*$", lines[i]):
                panel_lines.append(lines[i])
                i += 1
            if title:
                result.append(f"> **{title}**")
            for pl in panel_lines:
                result.append(f"> {_convert_inline_jira(pl)}")
            i += 1  # skip closing {panel}
            continue

        # Noformat blocks: {noformat}...{noformat} -> ```...```
        noformat_match = re.match(r"^\{noformat\}(.*)", line)
        if noformat_match:
            first_line_content = noformat_match.group(1)
            # Check if closing {noformat} is on the same line
            if "{noformat}" in first_line_content:
                inline = first_line_content.split("{noformat}")[0]
                result.append(f"`{inline.strip()}`")
                i += 1
                continue
            code_lines = []
            if first_line_content:
                code_lines.append(first_line_content)
            i += 1
            while i < len(lines):
                if "{noformat}" in lines[i]:
                    # Content before closing tag
                    before = lines[i].split("{noformat}")[0]
                    if before:
                        code_lines.append(before)
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            result.append("```")
            result.extend(code_lines)
            result.append("```")
            continue

        # Code blocks: {code:language=python}...{code}
        code_match = re.match(r"^\{code(?::([^}]*))?\}\s*$", line)
        if code_match:
            params = code_match.group(1) or ""
            lang = ""
            if params:
                # Parse language=python or just python
                lang_match = re.search(r"language=(\w+)", params)
                if lang_match:
                    lang = lang_match.group(1)
                elif re.match(r"^\w+$", params):
                    lang = params
            lang = LANG_MAP_REVERSE.get(lang.lower(), lang.lower()) if lang else ""
            code_lines = []
            i += 1
            while i < len(lines) and not re.match(r"^\{code\}\s*$", lines[i]):
                code_lines.append(lines[i])
                i += 1
            result.append(f"```{lang}")
            result.extend(code_lines)
            result.append("```")
            i += 1  # skip closing {code}
            continue

        # Headers: h2. Text -> ## Text
        header_match = re.match(r"^h([1-6])\.\s+(.*)", line)
        if header_match:
            level = int(header_match.group(1))
            content = _convert_inline_jira(header_match.group(2))
            result.append("#" * level + " " + content)
            i += 1
            continue

        # Horizontal rule: ----
        if re.match(r"^-{4,}\s*$", line):
            result.append("---")
            i += 1
            continue

        # Blockquotes: bq. text -> > text
        bq_match = re.match(r"^bq\.\s+(.*)", line)
        if bq_match:
            result.append(f"> {_convert_inline_jira(bq_match.group(1))}")
            i += 1
            continue

        # Mixed and regular lists: *, #, *#, #*, **, ##, etc.
        list_match = re.match(r"^([*#]+)\s+(.*)", line)
        if list_match:
            markers = list_match.group(1)
            content = _convert_inline_jira(list_match.group(2))
            level = len(markers)
            indent = "  " * (level - 1)
            # Last character determines list type
            if markers[-1] == "#":
                result.append(f"{indent}1. {content}")
            else:
                result.append(f"{indent}- {content}")
            i += 1
            continue

        # Table header row: ||header||header||
        table_header_match = re.match(r"^\|\|(.+)\|\|\s*$", line)
        if table_header_match:
            cells = [
                _convert_inline_jira(c.strip())
                for c in table_header_match.group(1).split("||")
            ]
            result.append("| " + " | ".join(cells) + " |")
            result.append("|" + "|".join("---" for _ in cells) + "|")
            i += 1
            continue

        # Table data row: |cell|cell|
        table_row_match = re.match(r"^\|(.+)\|\s*$", line)
        if table_row_match and "||" not in line:
            cells = [
                _convert_inline_jira(c.strip())
                for c in table_row_match.group(1).split("|")
            ]
            result.append("| " + " | ".join(cells) + " |")
            i += 1
            continue

        # Regular line - apply inline conversions
        result.append(_convert_inline_jira(line))
        i += 1

    return "\n".join(result)


def is_jira_wiki(text: str) -> bool:
    """Detect whether text contains Jira wiki markup.

    Looks for patterns unique to Jira wiki that wouldn't appear in plain text
    or markdown.
    """
    patterns = [
        r"^h[1-6]\.\s",  # h2. Header
        r"\{code(:[^}]*)?\}",  # {code} or {code:language=python}
        r"\{noformat\}",  # {noformat} blocks
        r"\{quote\}",  # {quote} blocks
        r"\{panel(:[^}]*)?\}",  # {panel} blocks
        r"\{color(:[^}]*)?\}",  # {color:red}text{color}
        r"^\|\|.+\|\|",  # ||table||headers||
        r"^bq\.\s",  # bq. blockquote
        r"\{\{[^}]+\}\}",  # {{inline code}}
        r"(?<!\*)\*[^*\n]+\*(?!\*)",  # *bold* (single-star)
        r"\[([^]|]+)\|([^]]+)\]",  # [text|url] links
        r"!(?!\[)[^!\s][^!\n]*!",  # !image! or !image|params! (not ![alt])
        r"\?\?[^?\n]+\?\?",  # ??citation??
        r"\[~",  # [~user] mentions
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.MULTILINE):
            return True
    return False


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
        # HTML entities (e.g. &copy; &mdash; &rarr;) are not defined in XML.
        # Replace them with Unicode, but preserve the 5 XML predefined entities.
        _XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}

        def _replace_entity(m: re.Match) -> str:
            name = m.group(1)
            if name in _XML_ENTITIES:
                return m.group(0)
            return html.unescape(m.group(0))

        html_content = re.sub(r"&([a-zA-Z]+);", _replace_entity, html_content)
        wrapped = f'<root xmlns:ac="{AC_NS}" xmlns:ri="{RI_NS}">{html_content}</root>'
        try:
            root = ET.fromstring(wrapped)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse Confluence storage format: {e}") from e

    text = _elem_to_markdown(root, image_dir, [], False, {})

    # Collapse multiple newlines into max 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
