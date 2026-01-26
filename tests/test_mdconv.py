"""Tests for markdown conversion utilities."""

import pytest

from zaira.mdconv import markdown_to_storage, storage_to_markdown


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
            assert f'<ac:parameter ac:name="language">{confluence_lang}</ac:parameter>' in html

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
            '</ac:structured-macro>'
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
            '<ac:plain-text-body><![CDATA[<div></div>]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )
        md = storage_to_markdown(html)
        assert "```xml" in md

    def test_code_macro_none_language(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">none</ac:parameter>'
            '<ac:plain-text-body><![CDATA[code]]></ac:plain-text-body>'
            '</ac:structured-macro>'
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
