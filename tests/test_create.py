"""Tests for create module."""

import pytest

from zaira.create import detect_markdown, parse_content


class TestDetectMarkdown:
    """Tests for detect_markdown function."""

    def test_no_markdown_returns_empty(self):
        """Returns empty list for valid Jira markup."""
        text = """h2. Heading

*bold text*

[link|https://example.com]
"""
        result = detect_markdown(text)
        assert result == []

    def test_detects_markdown_headings(self):
        """Detects markdown ## headings."""
        text = "## My Heading"
        result = detect_markdown(text)
        assert len(result) == 1
        assert "h2." in result[0]

    def test_allows_single_hash(self):
        """Allows single # (Jira numbered list syntax)."""
        text = "# First item\n# Second item"
        result = detect_markdown(text)
        assert result == []

    def test_detects_markdown_links(self):
        """Detects markdown [text](url) links."""
        text = "Check out [this link](https://example.com)"
        result = detect_markdown(text)
        assert len(result) == 1
        assert "[this link|https://example.com]" in result[0]

    def test_detects_markdown_bold(self):
        """Detects markdown **bold** syntax."""
        text = "This is **bold** text"
        result = detect_markdown(text)
        assert len(result) == 1
        assert "'*text*'" in result[0]

    def test_detects_multiple_issues(self):
        """Detects multiple markdown issues."""
        text = """## Heading

**bold**

[link](https://example.com)
"""
        result = detect_markdown(text)
        assert len(result) == 3

    def test_limits_link_errors(self):
        """Only shows first 3 link errors."""
        text = """
[a](https://a.com)
[b](https://b.com)
[c](https://c.com)
[d](https://d.com)
[e](https://e.com)
"""
        result = detect_markdown(text)
        link_errors = [e for e in result if "link" in e.lower()]
        assert len(link_errors) == 3


class TestParseContent:
    """Tests for parse_content function."""

    def test_parses_front_matter(self):
        """Parses YAML front matter and body."""
        content = """---
project: TEST
summary: My ticket
---

This is the description.
"""
        front_matter, body = parse_content(content)

        assert front_matter["project"] == "TEST"
        assert front_matter["summary"] == "My ticket"
        assert body == "This is the description."

    def test_parses_list_values(self):
        """Parses list values in front matter."""
        content = """---
labels:
  - bug
  - urgent
components:
  - Backend
---

Description
"""
        front_matter, body = parse_content(content)

        assert front_matter["labels"] == ["bug", "urgent"]
        assert front_matter["components"] == ["Backend"]

    def test_raises_on_no_front_matter(self):
        """Raises ValueError when no front matter."""
        content = "Just regular content"

        with pytest.raises(ValueError, match="No YAML front matter"):
            parse_content(content)

    def test_raises_on_missing_closing_marker(self):
        """Raises ValueError when closing --- is missing."""
        content = """---
project: TEST
summary: Incomplete
"""
        with pytest.raises(ValueError):
            parse_content(content)

    def test_empty_body(self):
        """Handles empty body after front matter."""
        content = """---
project: TEST
---
"""
        front_matter, body = parse_content(content)

        assert front_matter["project"] == "TEST"
        assert body == ""

    def test_multiline_body(self):
        """Preserves multiline description body."""
        content = """---
project: TEST
---

Line 1

Line 2

Line 3
"""
        front_matter, body = parse_content(content)

        assert "Line 1" in body
        assert "Line 2" in body
        assert "Line 3" in body
