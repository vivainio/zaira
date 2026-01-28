"""Tests for wiki module."""

import pytest

from zaira.wiki import (
    parse_front_matter,
    write_front_matter,
    parse_page_id,
    slugify,
)


class TestParseFrontMatter:
    """Tests for parse_front_matter function."""

    def test_no_front_matter(self):
        """Returns empty dict and full content when no front matter."""
        content = "# Title\n\nBody content"
        front_matter, body = parse_front_matter(content)

        assert front_matter == {}
        assert body == content

    def test_parses_front_matter(self):
        """Parses YAML front matter correctly."""
        content = """---
title: My Page
confluence: 12345
---

# Body here
"""
        front_matter, body = parse_front_matter(content)

        assert front_matter["title"] == "My Page"
        assert front_matter["confluence"] == 12345
        assert "# Body here" in body

    def test_handles_labels_list(self):
        """Handles list values in front matter."""
        content = """---
title: Tagged Page
labels: [bug, urgent]
---

Content
"""
        front_matter, body = parse_front_matter(content)

        assert front_matter["labels"] == ["bug", "urgent"]

    def test_invalid_yaml_returns_content(self):
        """Returns original content on invalid YAML."""
        content = """---
invalid: yaml: content: here
  bad indentation
---

Body
"""
        front_matter, body = parse_front_matter(content)

        # Should return empty front matter and original content
        assert front_matter == {}

    def test_missing_closing_delimiter(self):
        """Returns content when closing --- is missing."""
        content = """---
title: No closing
"""
        front_matter, body = parse_front_matter(content)

        assert front_matter == {}
        assert body == content


class TestWriteFrontMatter:
    """Tests for write_front_matter function."""

    def test_empty_front_matter(self):
        """Returns body unchanged when front matter is empty."""
        body = "# Title\n\nContent"
        result = write_front_matter({}, body)

        assert result == body

    def test_writes_front_matter(self):
        """Writes front matter with body."""
        front_matter = {"title": "My Page", "confluence": 12345}
        body = "# Content here"

        result = write_front_matter(front_matter, body)

        assert result.startswith("---\n")
        assert "title: My Page" in result
        assert "confluence: 12345" in result
        assert "---\n\n# Content here" in result

    def test_lists_inline(self):
        """Lists are written inline."""
        front_matter = {"labels": ["a", "b", "c"]}
        body = "Content"

        result = write_front_matter(front_matter, body)

        # Should be inline list format
        assert "[a, b, c]" in result

    def test_strips_leading_whitespace_from_body(self):
        """Strips leading whitespace from body."""
        front_matter = {"title": "Test"}
        body = "\n\n\n# Content"

        result = write_front_matter(front_matter, body)

        assert result.endswith("---\n\n# Content")


class TestParsePageId:
    """Tests for parse_page_id function."""

    def test_numeric_id(self):
        """Returns numeric ID as-is."""
        assert parse_page_id("12345") == "12345"
        assert parse_page_id("1") == "1"

    def test_extracts_from_pages_url(self):
        """Extracts ID from /pages/ID URL pattern."""
        url = "https://site.atlassian.net/wiki/spaces/SPACE/pages/123456/Title"
        assert parse_page_id(url) == "123456"

    def test_extracts_from_viewpage_url(self):
        """Extracts ID from viewpage.action URL pattern."""
        url = "https://site.atlassian.net/wiki/pages/viewpage.action?pageId=789012"
        assert parse_page_id(url) == "789012"

    def test_extracts_from_pages_url_without_title(self):
        """Extracts ID from URL without title."""
        url = "https://site.atlassian.net/wiki/spaces/TEST/pages/555555"
        assert parse_page_id(url) == "555555"

    def test_returns_input_if_not_matching(self):
        """Returns input if no pattern matches."""
        assert parse_page_id("some-identifier") == "some-identifier"


class TestSlugify:
    """Tests for slugify function."""

    def test_basic_slugify(self):
        """Converts title to lowercase slug."""
        assert slugify("Hello World") == "hello-world"
        assert slugify("My Page Title") == "my-page-title"

    def test_removes_special_characters(self):
        """Removes special characters."""
        assert slugify("Test: Special!") == "test-special"
        assert slugify("Page (v2)") == "page-v2"

    def test_collapses_multiple_hyphens(self):
        """Collapses multiple hyphens."""
        assert slugify("Test   Multiple   Spaces") == "test-multiple-spaces"
        assert slugify("A - B - C") == "a-b-c"

    def test_strips_leading_trailing_hyphens(self):
        """Strips leading and trailing hyphens."""
        assert slugify("---Test---") == "test"
        assert slugify("!Test!") == "test"

    def test_truncates_long_titles(self):
        """Truncates titles longer than 80 characters."""
        long_title = "A" * 100
        result = slugify(long_title)
        assert len(result) <= 80

    def test_preserves_numbers(self):
        """Preserves numbers in slug."""
        assert slugify("Version 2.0") == "version-20"
        assert slugify("Sprint 123") == "sprint-123"

    def test_handles_empty_string(self):
        """Handles empty string."""
        assert slugify("") == ""

    def test_handles_unicode(self):
        """Handles unicode characters by removing them."""
        # Unicode letters should be kept as word characters
        result = slugify("Café Menu")
        assert "caf" in result


class TestParseFrontMatterRoundTrip:
    """Tests for round-trip parsing and writing."""

    def test_round_trip(self):
        """Front matter survives round-trip."""
        original_fm = {"title": "Test Page", "confluence": 12345}
        original_body = "# Content\n\nBody text"

        written = write_front_matter(original_fm, original_body)
        parsed_fm, parsed_body = parse_front_matter(written)

        assert parsed_fm["title"] == original_fm["title"]
        assert parsed_fm["confluence"] == original_fm["confluence"]
        assert "# Content" in parsed_body

    def test_round_trip_with_labels(self):
        """Front matter with lists survives round-trip."""
        original_fm = {"title": "Tagged", "labels": ["a", "b"]}
        original_body = "Content"

        written = write_front_matter(original_fm, original_body)
        parsed_fm, parsed_body = parse_front_matter(written)

        assert parsed_fm["labels"] == ["a", "b"]
