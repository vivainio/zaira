"""Tests for markdown conversion utilities."""

from pathlib import Path
from unittest.mock import patch

import pytest

from zaira.mdconv import (
    RENDERERS,
    cleanup_render_temps,
    markdown_to_storage,
    markdown_to_jira_wiki,
    jira_wiki_to_markdown,
    is_jira_wiki,
    render_diagram_blocks,
    storage_to_markdown,
    extract_local_images,
    convert_images_to_attachments,
    convert_attachments_to_images,
)
from tests.jira_wiki_samples import (
    HEADINGS,
    TEXT_EFFECTS,
    COLOR,
    TEXT_BREAKS,
    LINKS,
    IMAGES,
    BULLET_LISTS,
    NUMBERED_LISTS,
    MIXED_LISTS,
    BLOCKQUOTES,
    TABLES,
    CODE_BLOCKS,
    NOFORMAT,
    PANELS,
    FULL_DOCUMENT,
)


class TestExtractLocalImages:
    """Tests for extract_local_images function."""

    def test_extracts_local_images(self):
        """Extracts local image references."""
        md = "![Alt text](./images/photo.png)\n![Another](path/to/image.jpg)"
        result = extract_local_images(md)

        assert len(result) == 2
        assert ("Alt text", "./images/photo.png") in result
        assert ("Another", "path/to/image.jpg") in result

    def test_skips_http_urls(self):
        """Skips HTTP/HTTPS URLs."""
        md = "![Web](https://example.com/image.png)\n![Local](./local.png)"
        result = extract_local_images(md)

        assert len(result) == 1
        assert ("Local", "./local.png") in result

    def test_skips_protocol_relative_urls(self):
        """Skips protocol-relative URLs."""
        md = "![Image](//cdn.example.com/img.png)"
        result = extract_local_images(md)

        assert len(result) == 0

    def test_handles_empty_alt_text(self):
        """Handles images with empty alt text."""
        md = "![](image.png)"
        result = extract_local_images(md)

        assert result == [("", "image.png")]

    def test_no_images(self):
        """Returns empty list when no images."""
        md = "Just text, no images"
        result = extract_local_images(md)

        assert result == []


class TestConvertImagesToAttachments:
    """Tests for convert_images_to_attachments function."""

    def test_converts_local_images(self):
        """Converts local image paths to attachment references."""
        md = "![Alt](./images/photo.png)"
        result = convert_images_to_attachments(md)

        assert result == "![Alt](attachment:photo.png)"

    def test_preserves_urls(self):
        """Preserves HTTP/HTTPS URLs."""
        md = "![Web](https://example.com/image.png)"
        result = convert_images_to_attachments(md)

        assert result == md

    def test_preserves_protocol_relative_urls(self):
        """Preserves protocol-relative URLs."""
        md = "![Img](//cdn.example.com/img.png)"
        result = convert_images_to_attachments(md)

        assert result == md

    def test_handles_nested_paths(self):
        """Extracts just filename from nested paths."""
        md = "![Img](path/to/deep/image.png)"
        result = convert_images_to_attachments(md)

        assert result == "![Img](attachment:image.png)"


class TestConvertAttachmentsToImages:
    """Tests for convert_attachments_to_images function."""

    def test_converts_attachment_references(self):
        """Converts attachment references to local paths."""
        md = "![Alt](attachment:photo.png)"
        result = convert_attachments_to_images(md)

        assert result == "![Alt](./images/photo.png)"

    def test_custom_image_dir(self):
        """Uses custom image directory."""
        md = "![Alt](attachment:photo.png)"
        result = convert_attachments_to_images(md, image_dir="./assets")

        assert result == "![Alt](./assets/photo.png)"

    def test_preserves_non_attachment_refs(self):
        """Preserves non-attachment image references."""
        md = "![Alt](./local/image.png)"
        result = convert_attachments_to_images(md)

        assert result == md

    def test_preserves_urls(self):
        """Preserves HTTP URLs."""
        md = "![Web](https://example.com/img.png)"
        result = convert_attachments_to_images(md)

        assert result == md


class TestMarkdownToStorage:
    """Tests for markdown_to_storage function."""

    def test_headers(self):
        md = "# H1\n## H2\n### H3"
        html = markdown_to_storage(md)
        assert "<h1>H1</h1>" in html
        assert "<h2>H2</h2>" in html
        assert "<h3>H3</h3>" in html

    def test_bold_italic(self):
        md = "This is **bold** and *italic*"
        html = markdown_to_storage(md)
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_links(self):
        md = "[link text](https://example.com)"
        html = markdown_to_storage(md)
        assert '<a href="https://example.com">link text</a>' in html

    def test_code_block_with_language(self):
        md = "```python\nprint('hello')\n```"
        html = markdown_to_storage(md)
        assert '<ac:structured-macro ac:name="code">' in html
        assert '<ac:parameter ac:name="language">python</ac:parameter>' in html
        assert "print('hello')" in html

    def test_code_block_language_mapping(self):
        """Test that language aliases are mapped correctly."""
        test_cases = [
            ("js", "javascript"),
            ("ts", "typescript"),
            ("py", "python"),
            ("sh", "bash"),
            ("yml", "yaml"),
            ("csharp", "c#"),
        ]
        for md_lang, confluence_lang in test_cases:
            md = f"```{md_lang}\ncode\n```"
            html = markdown_to_storage(md)
            assert (
                f'<ac:parameter ac:name="language">{confluence_lang}</ac:parameter>'
                in html
            )

    def test_code_block_without_language(self):
        md = "```\nplain code\n```"
        html = markdown_to_storage(md)
        assert '<ac:parameter ac:name="language">none</ac:parameter>' in html

    def test_code_block_html_entities(self):
        """Test that HTML in code blocks is preserved."""
        md = '```html\n<div class="foo">text</div>\n```'
        html = markdown_to_storage(md)
        assert '<div class="foo">text</div>' in html

    def test_toc(self):
        md = "# Title\n\n[TOC]\n\n## Section"
        html = markdown_to_storage(md)
        assert '<ac:structured-macro ac:name="toc"/>' in html
        assert "[TOC]" not in html

    def test_unordered_list(self):
        md = "- Item 1\n- Item 2"
        html = markdown_to_storage(md)
        assert "<ul>" in html
        assert "<li>Item 1</li>" in html
        assert "<li>Item 2</li>" in html

    def test_ordered_list(self):
        md = "1. First\n2. Second"
        html = markdown_to_storage(md)
        assert "<ol>" in html
        assert "<li>First</li>" in html

    def test_nested_list_2_space_indent(self):
        """Test that 2-space indented nested lists work."""
        md = "- Item 1\n  - Nested A\n  - Nested B\n- Item 2"
        html = markdown_to_storage(md)
        # Should have nested ul
        assert html.count("<ul>") == 2
        assert html.count("</ul>") == 2

    def test_nested_list_deep(self):
        """Test deeply nested lists with 2-space indent."""
        md = "- Item 1\n  - Nested A\n    - Deep\n  - Nested B\n- Item 2"
        html = markdown_to_storage(md)
        assert html.count("<ul>") == 3  # Top level + 2 nested levels

    def test_ordered_list_continuation(self):
        """Test sane_lists extension preserves list start number."""
        md = "1. First\n2. Second\n\nParagraph\n\n3. Third\n4. Fourth"
        html = markdown_to_storage(md)
        assert 'start="3"' in html

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = markdown_to_storage(md)
        assert "<table>" in html
        assert "<th>A</th>" in html
        assert "<td>1</td>" in html


class TestStorageToMarkdown:
    """Tests for storage_to_markdown function."""

    def test_headers(self):
        html = "<h1>Title</h1><h2>Section</h2>"
        md = storage_to_markdown(html)
        assert "# Title" in md
        assert "## Section" in md

    def test_bold_italic(self):
        html = "<p>This is <strong>bold</strong> and <em>italic</em></p>"
        md = storage_to_markdown(html)
        assert "**bold**" in md
        assert "*italic*" in md

    def test_links(self):
        html = '<a href="https://example.com">link</a>'
        md = storage_to_markdown(html)
        assert "[link](https://example.com)" in md

    def test_code_macro(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">python</ac:parameter>'
            '<ac:plain-text-body><![CDATA[print("hello")]]></ac:plain-text-body>'
            "</ac:structured-macro>"
        )
        md = storage_to_markdown(html)
        assert "```python" in md
        assert 'print("hello")' in md
        assert "```" in md

    def test_code_macro_language_mapping(self):
        """Test reverse language mapping."""
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">html/xml</ac:parameter>'
            "<ac:plain-text-body><![CDATA[<div></div>]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        md = storage_to_markdown(html)
        assert "```xml" in md

    def test_code_macro_none_language(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">none</ac:parameter>'
            "<ac:plain-text-body><![CDATA[code]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        md = storage_to_markdown(html)
        # Should have empty language (just ```)
        assert "```\n" in md

    def test_toc_macro(self):
        html = '<ac:structured-macro ac:name="toc"/>'
        md = storage_to_markdown(html)
        assert "[TOC]" in md

    def test_unordered_list(self):
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        md = storage_to_markdown(html)
        assert "- Item 1" in md
        assert "- Item 2" in md

    def test_ordered_list(self):
        html = "<ol><li>First</li><li>Second</li></ol>"
        md = storage_to_markdown(html)
        assert "1. First" in md
        assert "2. Second" in md

    def test_ordered_list_start(self):
        html = '<ol start="3"><li>Third</li><li>Fourth</li></ol>'
        md = storage_to_markdown(html)
        assert "3. Third" in md
        assert "4. Fourth" in md

    def test_nested_list(self):
        html = "<ul><li>Item 1<ul><li>Nested</li></ul></li><li>Item 2</li></ul>"
        md = storage_to_markdown(html)
        assert "- Item 1" in md
        assert "  - Nested" in md
        assert "- Item 2" in md

    def test_table(self):
        html = (
            "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
            "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
        )
        md = storage_to_markdown(html)
        assert "| A | B |" in md
        assert "|---|---|" in md
        assert "| 1 | 2 |" in md


class TestMarkdownToJiraWiki:
    """Tests for markdown_to_jira_wiki function."""

    def test_headers(self):
        assert markdown_to_jira_wiki("## Section") == "h2. Section"
        assert markdown_to_jira_wiki("### Sub") == "h3. Sub"

    def test_h1_not_converted(self):
        """Single # is Jira numbered list — not converted to h1."""
        assert markdown_to_jira_wiki("# Title") == "# Title"

    def test_bold(self):
        result = markdown_to_jira_wiki("This is **bold** text")
        assert result == "This is *bold* text"

    def test_italic_single_star_unchanged(self):
        """Single *text* is valid Jira bold — left as-is to avoid mangling."""
        result = markdown_to_jira_wiki("This is *italic* text")
        assert result == "This is *italic* text"

    def test_bold_double_underscore(self):
        result = markdown_to_jira_wiki("This is __bold__ text")
        assert result == "This is *bold* text"

    def test_inline_code(self):
        result = markdown_to_jira_wiki("Use `print()` here")
        assert result == "Use {{print()}} here"

    def test_link(self):
        result = markdown_to_jira_wiki("[click here](https://example.com)")
        assert result == "[click here|https://example.com]"

    def test_image(self):
        result = markdown_to_jira_wiki("![alt text](image.png)")
        assert result == "!image.png!"

    def test_image_before_link(self):
        """Images are processed before links to avoid double-conversion."""
        result = markdown_to_jira_wiki("![alt](img.png) and [link](url)")
        assert result == "!img.png! and [link|url]"

    def test_fenced_code_block(self):
        md = "```python\nprint('hello')\n```"
        result = markdown_to_jira_wiki(md)
        assert result == "{code:language=python}\nprint('hello')\n{code}"

    def test_fenced_code_block_no_lang(self):
        md = "```\nplain code\n```"
        result = markdown_to_jira_wiki(md)
        assert result == "{code}\nplain code\n{code}"

    def test_fenced_code_block_lang_alias(self):
        md = "```py\ncode\n```"
        result = markdown_to_jira_wiki(md)
        assert "{code:language=python}" in result

    def test_bullet_list(self):
        md = "- Item 1\n- Item 2"
        result = markdown_to_jira_wiki(md)
        assert result == "* Item 1\n* Item 2"

    def test_nested_bullet_list(self):
        md = "- Item 1\n  - Nested\n- Item 2"
        result = markdown_to_jira_wiki(md)
        assert "* Item 1" in result
        assert "** Nested" in result
        assert "* Item 2" in result

    def test_numbered_list(self):
        md = "1. First\n2. Second"
        result = markdown_to_jira_wiki(md)
        assert result == "# First\n# Second"

    def test_blockquote(self):
        result = markdown_to_jira_wiki("> This is a quote")
        assert result == "bq. This is a quote"

    def test_horizontal_rule(self):
        assert markdown_to_jira_wiki("---") == "----"
        assert markdown_to_jira_wiki("***") == "----"

    def test_strikethrough(self):
        result = markdown_to_jira_wiki("~~deleted~~")
        assert result == "-deleted-"

    def test_jira_wiki_passthrough(self):
        """Jira wiki syntax passes through unchanged."""
        jira = "h2. Heading\n\n*bold* and _italic_\n\n[link|https://example.com]"
        result = markdown_to_jira_wiki(jira)
        # h2. heading line: no markdown headers, so _convert_inline_md processes it
        assert "h2. Heading" in result
        assert "[link|https://example.com]" in result

    def test_full_document(self):
        md = "## Overview\n\nThis is **important** and uses [the API](https://api.example.com).\n\n- Step 1\n- Step 2\n\n```python\ncode()\n```"
        result = markdown_to_jira_wiki(md)
        assert "h2. Overview" in result
        assert "*important*" in result
        assert "[the API|https://api.example.com]" in result
        assert "* Step 1" in result
        assert "* Step 2" in result
        assert "{code:language=python}" in result
        assert "code()" in result
        assert "{code}" in result


class TestMarkdownToJiraWikiSymmetry:
    """Verify that markdown_to_jira_wiki output is stable.

    After conversion, detect_markdown(result) must be False — meaning the
    output is valid Jira wiki that won't be re-converted if passed through
    the pipeline again.
    """

    CASES = [
        "## Heading",
        "# Title",
        "**bold text**",
        "*italic text*",
        "__also bold__",
        "[click here](https://example.com)",
        "![alt](image.png)",
        "```python\nprint('hi')\n```",
        "```\nplain code\n```",
        "`inline code`",
        "- bullet one\n- bullet two",
        "  - nested bullet",
        "1. first\n2. second",
        "> blockquote text",
        "~~strikethrough~~",
        "## Heading\n\n**bold** and *italic* with [a link](https://x.com).\n\n- item\n\n```py\ncode()\n```",
    ]

    def test_converted_output_not_detected_as_markdown(self):
        """Each converted result must not trigger detect_markdown."""
        from zaira.create import detect_markdown

        for md in self.CASES:
            result = markdown_to_jira_wiki(md)
            assert not detect_markdown(result), (
                f"Output still detected as markdown after conversion.\n"
                f"  Input:  {md!r}\n"
                f"  Output: {result!r}"
            )

    def test_idempotent_under_pipeline(self):
        """Converting already-converted Jira wiki does not change it further."""
        from zaira.create import detect_markdown

        for md in self.CASES:
            first = markdown_to_jira_wiki(md)
            # Simulate passing through the pipeline a second time:
            # detect_markdown guards the call in practice, but call directly
            # to verify the output is stable.
            if not detect_markdown(first):
                second = markdown_to_jira_wiki(first)
                assert second == first, (
                    f"Output changed on second pass.\n"
                    f"  Input:   {md!r}\n"
                    f"  Pass 1:  {first!r}\n"
                    f"  Pass 2:  {second!r}"
                )


class TestRoundTrip:
    """Test that markdown survives round-trip conversion."""

    def test_simple_document(self):
        md = "# Title\n\nParagraph with **bold**."
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        storage2 = markdown_to_storage(back)
        assert storage == storage2

    def test_code_blocks(self):
        md = "```python\ndef foo():\n    pass\n```"
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        storage2 = markdown_to_storage(back)
        assert storage == storage2

    def test_nested_lists(self):
        md = "- Item 1\n  - Nested A\n  - Nested B\n- Item 2"
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        storage2 = markdown_to_storage(back)
        assert storage == storage2

    def test_nested_lists_deep(self):
        md = (
            "- First item\n"
            "- Second item\n"
            "- Third item\n"
            "  - Nested item\n"
            "  - Another nested item\n"
            "    - Deep nested item\n"
            "- Fourth item"
        )
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        # Verify nesting is preserved
        assert "  - Nested item" in back
        assert "  - Another nested item" in back
        assert "    - Deep nested item" in back
        # Verify round-trip stability
        storage2 = markdown_to_storage(back)
        assert storage == storage2

    def test_ordered_lists(self):
        md = "1. First\n  1. Sub 1\n  2. Sub 2\n2. Second"
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        storage2 = markdown_to_storage(back)
        assert storage == storage2

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        storage2 = markdown_to_storage(back)
        assert storage == storage2

    def test_toc(self):
        md = "# Doc\n\n[TOC]\n\n## Section"
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        storage2 = markdown_to_storage(back)
        assert storage == storage2

    def test_comprehensive_document(self):
        md = """# Document

[TOC]

## Introduction

This is **bold** and *italic* with a [link](https://example.com).

## Code

```python
def hello():
    print("hello")
```

## Lists

- Item 1
  - Nested
- Item 2

1. First
2. Second

## Table

| Col1 | Col2 |
|------|------|
| A    | B    |
"""
        storage = markdown_to_storage(md)
        back = storage_to_markdown(storage)
        storage2 = markdown_to_storage(back)
        assert storage == storage2


class TestJiraWikiToMarkdown:
    """Tests for jira_wiki_to_markdown function."""

    def test_headers(self):
        assert jira_wiki_to_markdown("h2. Section") == "## Section"
        assert jira_wiki_to_markdown("h3. Sub") == "### Sub"
        assert jira_wiki_to_markdown("h1. Title") == "# Title"

    def test_bold(self):
        result = jira_wiki_to_markdown("This is *bold* text")
        assert result == "This is **bold** text"

    def test_italic(self):
        result = jira_wiki_to_markdown("This is _italic_ text")
        assert result == "This is *italic* text"

    def test_strikethrough(self):
        result = jira_wiki_to_markdown("This is -deleted- text")
        assert result == "This is ~~deleted~~ text"

    def test_inline_code(self):
        result = jira_wiki_to_markdown("Use {{print()}} here")
        assert result == "Use `print()` here"

    def test_link(self):
        result = jira_wiki_to_markdown("[click here|https://example.com]")
        assert result == "[click here](https://example.com)"

    def test_image(self):
        result = jira_wiki_to_markdown("!image.png!")
        assert result == "![](image.png)"

    def test_code_block_with_language(self):
        wiki = "{code:language=python}\nprint('hello')\n{code}"
        result = jira_wiki_to_markdown(wiki)
        assert result == "```python\nprint('hello')\n```"

    def test_code_block_no_language(self):
        wiki = "{code}\nplain code\n{code}"
        result = jira_wiki_to_markdown(wiki)
        assert result == "```\nplain code\n```"

    def test_code_block_short_language(self):
        wiki = "{code:python}\ncode\n{code}"
        result = jira_wiki_to_markdown(wiki)
        assert result == "```python\ncode\n```"

    def test_bullet_list(self):
        wiki = "* Item 1\n* Item 2"
        result = jira_wiki_to_markdown(wiki)
        assert result == "- Item 1\n- Item 2"

    def test_nested_bullet_list(self):
        wiki = "* Item 1\n** Nested\n* Item 2"
        result = jira_wiki_to_markdown(wiki)
        assert "- Item 1" in result
        assert "  - Nested" in result
        assert "- Item 2" in result

    def test_numbered_list(self):
        wiki = "# First\n# Second"
        result = jira_wiki_to_markdown(wiki)
        assert result == "1. First\n1. Second"

    def test_nested_numbered_list(self):
        wiki = "# First\n## Nested\n# Second"
        result = jira_wiki_to_markdown(wiki)
        assert "1. First" in result
        assert "  1. Nested" in result
        assert "1. Second" in result

    def test_blockquote(self):
        result = jira_wiki_to_markdown("bq. This is a quote")
        assert result == "> This is a quote"

    def test_horizontal_rule(self):
        assert jira_wiki_to_markdown("----") == "---"

    def test_table(self):
        wiki = "||Name||Age||\n|Alice|30|\n|Bob|25|"
        result = jira_wiki_to_markdown(wiki)
        assert "| Name | Age |" in result
        assert "|---|---|" in result
        assert "| Alice | 30 |" in result
        assert "| Bob | 25 |" in result

    def test_full_document(self):
        wiki = (
            "h2. Overview\n\n"
            "This is *important* and uses [the API|https://api.example.com].\n\n"
            "* Step 1\n* Step 2\n\n"
            "{code:language=python}\ncode()\n{code}"
        )
        result = jira_wiki_to_markdown(wiki)
        assert "## Overview" in result
        assert "**important**" in result
        assert "[the API](https://api.example.com)" in result
        assert "- Step 1" in result
        assert "- Step 2" in result
        assert "```python" in result
        assert "code()" in result
        assert "```" in result

    def test_strikethrough_not_in_words(self):
        """Hyphens inside words should not be treated as strikethrough."""
        result = jira_wiki_to_markdown("well-known")
        assert result == "well-known"

    def test_noformat_block(self):
        wiki = "{noformat}\nsome preformatted text\n{noformat}"
        result = jira_wiki_to_markdown(wiki)
        assert result == "```\nsome preformatted text\n```"

    def test_noformat_inline_start(self):
        """Noformat starting on same line as content."""
        wiki = "{noformat}var x = 1;\nvar y = 2;\n{noformat}"
        result = jira_wiki_to_markdown(wiki)
        assert "```" in result
        assert "var x = 1;" in result
        assert "var y = 2;" in result

    def test_noformat_single_line(self):
        """Noformat opening and closing on same line."""
        wiki = "{noformat}some code{noformat}"
        result = jira_wiki_to_markdown(wiki)
        assert result == "`some code`"

    def test_plain_text_unchanged(self):
        result = jira_wiki_to_markdown("Just plain text here.")
        assert result == "Just plain text here."


class TestIsJiraWiki:
    """Tests for is_jira_wiki detection function."""

    def test_detects_headers(self):
        assert is_jira_wiki("h2. Section title")

    def test_detects_code_blocks(self):
        assert is_jira_wiki("{code:language=python}\nprint()\n{code}")

    def test_detects_table_headers(self):
        assert is_jira_wiki("||Name||Age||")

    def test_detects_blockquote(self):
        assert is_jira_wiki("bq. Some quote")

    def test_detects_inline_code(self):
        assert is_jira_wiki("Use {{print()}} here")

    def test_detects_bold(self):
        assert is_jira_wiki("This is *bold* text")

    def test_detects_noformat(self):
        assert is_jira_wiki("{noformat}some text{noformat}")

    def test_detects_links(self):
        assert is_jira_wiki("[click here|https://example.com]")

    def test_plain_text_not_detected(self):
        assert not is_jira_wiki("Just plain text.")

    def test_markdown_not_detected(self):
        assert not is_jira_wiki("## Heading\n\n**bold** and [link](url)")

    def test_empty_string(self):
        assert not is_jira_wiki("")


class TestJiraWikiRoundTrip:
    """Test that markdown_to_jira_wiki output fed to jira_wiki_to_markdown
    produces equivalent markdown."""

    CASES = [
        ("## Heading", "## Heading"),
        ("### Sub heading", "### Sub heading"),
        ("This is **bold** text", "This is **bold** text"),
        ("`inline code`", "`inline code`"),
        ("[click here](https://example.com)", "[click here](https://example.com)"),
        ("- bullet one\n- bullet two", "- bullet one\n- bullet two"),
        ("- outer\n  - nested", "- outer\n  - nested"),
        ("1. first\n2. second", "1. first\n1. second"),
        ("> blockquote text", "> blockquote text"),
        ("~~strikethrough~~", "~~strikethrough~~"),
        ("---", "---"),
        ("```python\ncode()\n```", "```python\ncode()\n```"),
        ("```\nplain\n```", "```\nplain\n```"),
    ]

    def test_round_trip(self):
        for md_input, expected in self.CASES:
            jira = markdown_to_jira_wiki(md_input)
            back = jira_wiki_to_markdown(jira)
            assert back == expected, (
                f"Round-trip failed.\n"
                f"  Input:    {md_input!r}\n"
                f"  Jira:     {jira!r}\n"
                f"  Back:     {back!r}\n"
                f"  Expected: {expected!r}"
            )


class TestJiraWikiToMarkdownRoundTrip:
    """Test that jira_wiki_to_markdown output fed to markdown_to_jira_wiki
    produces equivalent Jira wiki."""

    CASES = [
        # (wiki input, expected after round-trip)
        ("h2. Heading", "h2. Heading"),
        ("h3. Sub heading", "h3. Sub heading"),
        ("This is *bold* text", "This is *bold* text"),
        ("{{inline_code}}", "{{inline_code}}"),
        ("[click here|https://example.com]", "[click here|https://example.com]"),
        ("* bullet one\n* bullet two", "* bullet one\n* bullet two"),
        ("* outer\n** nested", "* outer\n** nested"),
        ("# first\n# second", "# first\n# second"),
        ("bq. blockquote text", "bq. blockquote text"),
        ("-deleted-", "-deleted-"),
        ("----", "----"),
        (
            "{code:language=python}\ncode()\n{code}",
            "{code:language=python}\ncode()\n{code}",
        ),
        ("{code}\nplain\n{code}", "{code}\nplain\n{code}"),
        # Tables: markdown_to_jira_wiki passes markdown tables through,
        # so the round-trip stabilizes on markdown table format
        ("||Name||Age||\n|Alice|30|", "| Name | Age |\n|---|---|\n| Alice | 30 |"),
    ]

    def test_round_trip(self):
        for wiki_input, expected in self.CASES:
            md = jira_wiki_to_markdown(wiki_input)
            back = markdown_to_jira_wiki(md)
            assert back == expected, (
                f"Round-trip failed.\n"
                f"  Input:    {wiki_input!r}\n"
                f"  Markdown: {md!r}\n"
                f"  Back:     {back!r}\n"
                f"  Expected: {expected!r}"
            )

    def test_real_ticket_description(self):
        """Round-trip a realistic Jira wiki description like AC-1538."""
        wiki = (
            "h2. Summary\n\n"
            "Update Dynatrace OneAgent version.\n\n"
            "h2. Version Changes\n\n"
            "||*Platform*||*Old Version*||*New Version*||\n"
            "|Linux|1.291.165|1.299.73|\n"
            "|Windows|1.291.107|1.299.73|\n\n"
            "h2. Implementation\n\n"
            "Repository: {{alusta-aws-node-prereq}}\n\n"
            "*Linux files:*\n\n"
            "* {{3rd_party_urls_linux.txt}}\n"
            "* {{Installers/install-dynatrace-agent.sh}}\n\n"
            "h2. Acceptance Criteria\n\n"
            "* Agent version is upgraded\n"
            "* Data is passed to server"
        )
        md = jira_wiki_to_markdown(wiki)
        # Verify key conversions happened
        assert "## Summary" in md
        assert "## Version Changes" in md
        assert "| **Platform** | **Old Version** | **New Version** |" in md
        assert "|---|---|---|" in md
        assert "`alusta-aws-node-prereq`" in md
        assert "`3rd_party_urls_linux.txt`" in md
        assert "- Agent version is upgraded" in md
        # Round-trip back
        back = markdown_to_jira_wiki(md)
        assert "h2. Summary" in back
        assert "h2. Version Changes" in back
        assert "{{alusta-aws-node-prereq}}" in back
        assert "{{3rd_party_urls_linux.txt}}" in back
        assert "* Agent version is upgraded" in back


class TestAtlassianWikiSamples:
    """Tests based on Atlassian's official Text Formatting Notation reference.

    Source: https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa
    """

    @pytest.mark.parametrize(
        "wiki,expected", HEADINGS, ids=[f"h{i + 1}" for i in range(len(HEADINGS))]
    )
    def test_headings(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected",
        TEXT_EFFECTS,
        ids=[w[:30].replace(" ", "_") for w, _ in TEXT_EFFECTS],
    )
    def test_text_effects(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize("wiki,expected", COLOR, ids=[w[:30] for w, _ in COLOR])
    def test_color(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected", TEXT_BREAKS, ids=[repr(w)[:30] for w, _ in TEXT_BREAKS]
    )
    def test_text_breaks(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize("wiki,expected", LINKS, ids=[w[:40] for w, _ in LINKS])
    def test_links(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize("wiki,expected", IMAGES, ids=[w[:40] for w, _ in IMAGES])
    def test_images(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected",
        BULLET_LISTS,
        ids=[f"bullet_{i}" for i in range(len(BULLET_LISTS))],
    )
    def test_bullet_lists(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected",
        NUMBERED_LISTS,
        ids=[f"numbered_{i}" for i in range(len(NUMBERED_LISTS))],
    )
    def test_numbered_lists(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected",
        MIXED_LISTS,
        ids=[f"mixed_{i}" for i in range(len(MIXED_LISTS))],
    )
    def test_mixed_lists(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected", BLOCKQUOTES, ids=[f"bq_{i}" for i in range(len(BLOCKQUOTES))]
    )
    def test_blockquotes(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected", TABLES, ids=[f"table_{i}" for i in range(len(TABLES))]
    )
    def test_tables(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected", CODE_BLOCKS, ids=[f"code_{i}" for i in range(len(CODE_BLOCKS))]
    )
    def test_code_blocks(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected", NOFORMAT, ids=[f"noformat_{i}" for i in range(len(NOFORMAT))]
    )
    def test_noformat(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    @pytest.mark.parametrize(
        "wiki,expected", PANELS, ids=[f"panel_{i}" for i in range(len(PANELS))]
    )
    def test_panels(self, wiki, expected):
        assert jira_wiki_to_markdown(wiki) == expected

    def test_full_document(self):
        wiki_input, expected = FULL_DOCUMENT
        assert jira_wiki_to_markdown(wiki_input) == expected


class TestMixedWikiAndMarkdown:
    """Tests for mixed Confluence wiki markup and markdown syntax."""

    def test_wiki_heading_with_markdown(self):
        """Wiki h1. heading is converted alongside markdown."""
        md = "Regular markdown\n\nh1. Wiki Heading\n\nMore *markdown*"
        result = markdown_to_storage(md)

        assert "<h1>Wiki Heading</h1>" in result
        assert "<p>Regular markdown</p>" in result
        # When wiki syntax is detected, *text* is treated as wiki bold (not markdown italic)
        assert "<strong>markdown</strong>" in result

    def test_wiki_blockquote_with_markdown(self):
        """Wiki bq. blockquote works with markdown."""
        md = "Start\n\nbq. Wiki quote\n\nEnd with _italic_"
        result = markdown_to_storage(md)

        assert "<blockquote>" in result
        assert "Wiki quote" in result
        # Wiki markup uses _italic_ for italics
        assert "<em>italic</em>" in result

    def test_wiki_code_block_with_markdown(self):
        """Wiki {code} block alongside markdown code."""
        md = "Markdown code:\n\n```python\ncode1\n```\n\nWiki code:\n\n{code:language=java}\ncode2\n{code}"
        result = markdown_to_storage(md)

        # Code blocks are converted to code macros
        assert 'ac:name="code"' in result
        assert "code1" in result
        assert "code2" in result


class TestRawXMLPassthrough:
    """Tests for raw Confluence storage XML passthrough."""

    def test_raw_macro_xml_passthrough(self):
        """Raw structured macro XML is preserved."""
        md = """Content

<ac:structured-macro ac:name="status">
  <ac:parameter ac:name="colour">green</ac:parameter>
</ac:structured-macro>

More content"""
        result = markdown_to_storage(md)

        assert 'ac:name="status"' in result
        assert "colour" in result

    def test_raw_html_elements_passthrough(self):
        """Raw HTML elements are passed through."""
        md = "Text\n\n<blockquote><p>Raw quote</p></blockquote>\n\nMore"
        result = markdown_to_storage(md)

        assert "<blockquote>" in result
        assert "Raw quote" in result

    def test_raw_image_macro_passthrough(self):
        """Raw image macro XML is preserved."""
        md = '<ac:image><ri:attachment ri:filename="test.png"/></ac:image>'
        result = markdown_to_storage(md)

        assert "ac:image" in result
        assert "test.png" in result


class TestConfluenceMacros:
    """Tests for Confluence macro handling."""

    def test_page_tree_macro_markdown_to_storage(self):
        """Converts page-tree macro syntax to structured macro XML."""
        md = "Documentation\n\n{page-tree:root=@self}"
        result = markdown_to_storage(md)

        assert '<ac:structured-macro ac:name="page-tree">' in result
        assert '<ac:parameter ac:name="root">@self</ac:parameter>' in result

    def test_toc_macro_markdown_to_storage(self):
        """Converts toc macro without params."""
        md = "Content\n\n{toc}"
        result = markdown_to_storage(md)

        assert '<ac:structured-macro ac:name="toc">' in result

    def test_macro_with_multiple_params(self):
        """Converts macros with multiple parameters."""
        md = "{info:title=Note|icon=true}"
        result = markdown_to_storage(md)

        assert '<ac:structured-macro ac:name="info">' in result
        assert 'ac:name="title"' in result
        assert 'ac:name="icon"' in result

    def test_macro_in_paragraph(self):
        """Preserves macro that appears in its own paragraph."""
        md = "Some text\n\n{page-tree:root=@self}\n\nMore text"
        result = markdown_to_storage(md)

        assert "<ac:structured-macro" in result
        assert "<p>Some text</p>" in result
        assert "<p>More text</p>" in result

    def test_storage_to_markdown_page_tree(self):
        """Converts storage format back to macro markdown."""
        storage = (
            "<p>Documentation</p>"
            '<ac:structured-macro ac:name="page-tree">'
            '<ac:parameter ac:name="root">@self</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = storage_to_markdown(storage)

        assert "{page-tree:root=@self}" in result
        assert "Documentation" in result

    def test_round_trip_page_tree(self):
        """Round-trip: markdown -> storage -> markdown preserves macro."""
        original_md = "Page listing\n\n{page-tree:root=@self}"

        # Markdown -> storage
        storage = markdown_to_storage(original_md)
        assert '<ac:structured-macro ac:name="page-tree">' in storage

        # Storage -> markdown
        result_md = storage_to_markdown(storage)
        assert "{page-tree:root=@self}" in result_md

        # Back to storage
        storage_again = markdown_to_storage(result_md)
        assert '<ac:structured-macro ac:name="page-tree">' in storage_again

    def test_unknown_braces_not_converted_to_macro(self):
        """Literal {word} that isn't a Confluence macro stays as text."""
        md = "GET /api/{documentId}/images/{imageId}"
        result = markdown_to_storage(md)

        assert "MACRO_PLACEHOLDER" not in result
        assert "ac:structured-macro" not in result
        assert "{documentId}" in result
        assert "{imageId}" in result

    def test_known_macro_still_converted(self):
        """Known macros like {toc} are still converted."""
        md = "Before\n\n{toc}\n\nAfter"
        result = markdown_to_storage(md)

        assert '<ac:structured-macro ac:name="toc">' in result


class TestDiagramRendering:
    """Tests for render_diagram_blocks and renderer registry."""

    def _fake_run(self, cmd: list[str], capture_output: bool, timeout: float) -> object:
        """Helper: simulate a successful render by creating the output PNG."""
        # Find the output path — it's the arg after -o, or the last arg for d2/ditaa
        if "-o" in cmd:
            out_path = cmd[cmd.index("-o") + 1]
        else:
            out_path = cmd[-1]
        Path(out_path).write_bytes(b"fake png data")

        class FakeResult:
            returncode = 0
            stderr = b""

        return FakeResult()

    def _fake_run_fail(
        self, cmd: list[str], capture_output: bool, timeout: float
    ) -> object:
        class FakeResult:
            returncode = 1
            stderr = b"Parse error"

        return FakeResult()

    def test_no_renderers_returns_unchanged(self):
        """When renderers is None, content is returned unchanged."""
        md = "```mermaid\ngraph TD\n  A-->B\n```"
        result, temps = render_diagram_blocks(md, None)
        assert result == md
        assert temps == []

    def test_empty_renderers_returns_unchanged(self):
        """When renderers is empty list, content is returned unchanged."""
        md = "```mermaid\ngraph TD\n  A-->B\n```"
        result, temps = render_diagram_blocks(md, [])
        assert result == md
        assert temps == []

    def test_unavailable_renderer_raises(self):
        """When the CLI tool is not installed, raises RuntimeError with install hint."""
        md = "```mermaid\ngraph TD\n  A-->B\n```"
        with patch("zaira.mdconv.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="not found"):
                render_diagram_blocks(md, ["mermaid"])

    def test_unknown_renderer_raises(self):
        """Unknown renderer name raises ValueError."""
        md = "```mermaid\ngraph TD\n  A-->B\n```"
        with pytest.raises(ValueError, match="Unknown renderer"):
            render_diagram_blocks(md, ["nosuchrenderer"])

    def test_no_matching_blocks_returns_unchanged(self):
        """Content without matching blocks is returned unchanged."""
        md = "# Hello\n\n```python\nprint('hi')\n```"
        with patch("zaira.mdconv.shutil.which", return_value="/usr/bin/mmdc"):
            result, temps = render_diagram_blocks(md, ["mermaid"])
        assert result == md
        assert temps == []

    def test_renders_mermaid_block(self):
        """Mermaid block is replaced by rendered image."""
        md = "Before\n\n```mermaid\ngraph TD\n  A-->B\n```\n\nAfter"

        with (
            patch("zaira.mdconv.shutil.which", return_value="/usr/bin/mmdc"),
            patch("zaira.mdconv.subprocess.run", side_effect=self._fake_run),
        ):
            result, temps = render_diagram_blocks(md, ["mermaid"])

        assert len(temps) == 1
        assert "```mermaid" not in result
        assert "![mermaid diagram](" in result
        assert "Before" in result
        assert "After" in result
        cleanup_render_temps(temps)

    def test_renders_dot_block(self):
        """Dot/graphviz block is replaced by rendered image."""
        md = "```dot\ndigraph { A -> B }\n```"

        with (
            patch("zaira.mdconv.shutil.which", return_value="/usr/bin/dot"),
            patch("zaira.mdconv.subprocess.run", side_effect=self._fake_run),
        ):
            result, temps = render_diagram_blocks(md, ["dot"])

        assert len(temps) == 1
        assert "```dot" not in result
        assert "![dot diagram](" in result
        cleanup_render_temps(temps)

    def test_multiple_renderers(self):
        """Multiple renderer types can be active at once."""
        md = "```mermaid\ngraph TD\n  A-->B\n```\n\n```dot\ndigraph { X -> Y }\n```"

        with (
            patch("zaira.mdconv.shutil.which", return_value="/usr/bin/fake"),
            patch("zaira.mdconv.subprocess.run", side_effect=self._fake_run),
        ):
            result, temps = render_diagram_blocks(md, ["mermaid", "dot"])

        assert len(temps) == 2
        assert "![mermaid diagram](" in result
        assert "![dot diagram](" in result
        cleanup_render_temps(temps)

    def test_multiple_blocks_same_type(self):
        """Multiple blocks of the same type are all rendered."""
        md = "```mermaid\ngraph TD\n  A-->B\n```\n\n```mermaid\ngraph LR\n  X-->Y\n```"

        with (
            patch("zaira.mdconv.shutil.which", return_value="/usr/bin/mmdc"),
            patch("zaira.mdconv.subprocess.run", side_effect=self._fake_run),
        ):
            result, temps = render_diagram_blocks(md, ["mermaid"])

        assert len(temps) == 2
        assert result.count("![mermaid diagram](") == 2
        cleanup_render_temps(temps)

    def test_failed_render_leaves_block(self):
        """When render fails, the block is left as-is."""
        md = "```mermaid\ninvalid\n```"

        with (
            patch("zaira.mdconv.shutil.which", return_value="/usr/bin/mmdc"),
            patch("zaira.mdconv.subprocess.run", side_effect=self._fake_run_fail),
        ):
            result, temps = render_diagram_blocks(md, ["mermaid"])

        assert result == md
        assert temps == []

    def test_deterministic_filename_from_content(self):
        """Same content produces the same filename across runs."""
        md = "```mermaid\ngraph TD\n  A-->B\n```"

        filenames = []
        original_fake = self._fake_run

        def tracking_run(
            cmd: list[str], capture_output: bool, timeout: float
        ) -> object:
            if "-o" in cmd:
                out_path = cmd[cmd.index("-o") + 1]
            else:
                out_path = cmd[-1]
            filenames.append(Path(out_path).name)
            return original_fake(cmd, capture_output, timeout)

        for _ in range(2):
            with (
                patch("zaira.mdconv.shutil.which", return_value="/usr/bin/mmdc"),
                patch("zaira.mdconv.subprocess.run", side_effect=tracking_run),
            ):
                _, temps = render_diagram_blocks(md, ["mermaid"])
            cleanup_render_temps(temps)

        assert filenames[0] == filenames[1]

    def test_only_requested_renderers_activate(self):
        """Blocks for unrequested renderers are not processed."""
        md = "```mermaid\ngraph TD\n  A-->B\n```\n\n```dot\ndigraph { X -> Y }\n```"

        with (
            patch("zaira.mdconv.shutil.which", return_value="/usr/bin/mmdc"),
            patch("zaira.mdconv.subprocess.run", side_effect=self._fake_run),
        ):
            result, temps = render_diagram_blocks(md, ["mermaid"])

        assert len(temps) == 1
        assert "![mermaid diagram](" in result
        assert "![dot diagram](" not in result
        cleanup_render_temps(temps)

    def test_registry_has_expected_renderers(self):
        """Registry contains all documented renderers."""
        assert "mermaid" in RENDERERS
        assert "mermaid-slow" in RENDERERS
        assert "plantuml" in RENDERERS
        assert "dot" in RENDERERS
        assert "graphviz" in RENDERERS
        assert "d2" in RENDERERS
        assert "ditaa" in RENDERERS

    def test_renderer_build_command(self):
        """DiagramRenderer.build_command resolves placeholders."""
        r = RENDERERS["mermaid"]
        in_path = Path("/tmp/in.mmd")
        out_path = Path("/tmp/out.png")
        cmd = r.build_command(in_path, out_path)
        # First element is either "mmdr" or a resolved path ending with mmdr
        assert cmd[0] == "mmdr" or cmd[0].lower().endswith("mmdr")
        # Use str(Path()) to handle platform-specific separators
        assert cmd[1:] == ["-i", str(in_path), "-o", str(out_path), "-e", "svg"]

    def test_mermaid_slow_build_command(self):
        """mermaid-slow renderer uses mmdc (legacy mermaid-cli)."""
        r = RENDERERS["mermaid-slow"]
        in_path = Path("/tmp/in.mmd")
        out_path = Path("/tmp/out.png")
        cmd = r.build_command(in_path, out_path)
        assert cmd[0] == "mmdc" or cmd[0].lower().endswith(("mmdc", "mmdc.cmd"))
        assert cmd[1:] == ["-i", str(in_path), "-o", str(out_path)]

    def test_graphviz_aliases_to_dot(self):
        """'graphviz' renderer uses 'dot' command."""
        assert RENDERERS["graphviz"].cmd == "dot"

    def test_cleanup_render_temps_noop_on_empty(self):
        """cleanup_render_temps does nothing with empty list."""
        cleanup_render_temps([])  # should not raise
