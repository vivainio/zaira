"""Tests for wiki module."""

import argparse
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

import pytest

from zaira.wiki import (
    parse_front_matter,
    write_front_matter,
    parse_page_id,
    put_command,
    slugify,
    compute_file_hash,
    get_sync_property,
    set_sync_property,
    check_images_changed,
)


class TestParseFrontMatter:
    """Tests for parse_front_matter function."""

    def test_no_front_matter(self) -> None:
        """Returns empty dict and full content when no front matter."""
        content = "# Title\n\nBody content"
        front_matter, body = parse_front_matter(content)

        assert front_matter == {}
        assert body == content

    def test_parses_front_matter(self) -> None:
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

    def test_handles_labels_list(self) -> None:
        """Handles list values in front matter."""
        content = """---
title: Tagged Page
labels: [bug, urgent]
---

Content
"""
        front_matter, body = parse_front_matter(content)

        assert front_matter["labels"] == ["bug", "urgent"]

    def test_invalid_yaml_returns_content(self) -> None:
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

    def test_missing_closing_delimiter(self) -> None:
        """Returns content when closing --- is missing."""
        content = """---
title: No closing
"""
        front_matter, body = parse_front_matter(content)

        assert front_matter == {}
        assert body == content


class TestWriteFrontMatter:
    """Tests for write_front_matter function."""

    def test_empty_front_matter(self) -> None:
        """Returns body unchanged when front matter is empty."""
        body = "# Title\n\nContent"
        result = write_front_matter({}, body)

        assert result == body

    def test_writes_front_matter(self) -> None:
        """Writes front matter with body."""
        front_matter = {"title": "My Page", "confluence": 12345}
        body = "# Content here"

        result = write_front_matter(front_matter, body)

        assert result.startswith("---\n")
        assert "title: My Page" in result
        assert "confluence: 12345" in result
        assert "---\n\n# Content here" in result

    def test_lists_inline(self) -> None:
        """Lists are written inline."""
        front_matter = {"labels": ["a", "b", "c"]}
        body = "Content"

        result = write_front_matter(front_matter, body)

        # Should be inline list format
        assert "[a, b, c]" in result

    def test_strips_leading_whitespace_from_body(self) -> None:
        """Strips leading whitespace from body."""
        front_matter = {"title": "Test"}
        body = "\n\n\n# Content"

        result = write_front_matter(front_matter, body)

        assert result.endswith("---\n\n# Content")


class TestParsePageId:
    """Tests for parse_page_id function."""

    def test_numeric_id(self) -> None:
        """Returns numeric ID as-is."""
        assert parse_page_id("12345") == "12345"
        assert parse_page_id("1") == "1"

    def test_extracts_from_pages_url(self) -> None:
        """Extracts ID from /pages/ID URL pattern."""
        url = "https://site.atlassian.net/wiki/spaces/SPACE/pages/123456/Title"
        assert parse_page_id(url) == "123456"

    def test_extracts_from_viewpage_url(self) -> None:
        """Extracts ID from viewpage.action URL pattern."""
        url = "https://site.atlassian.net/wiki/pages/viewpage.action?pageId=789012"
        assert parse_page_id(url) == "789012"

    def test_extracts_from_pages_url_without_title(self) -> None:
        """Extracts ID from URL without title."""
        url = "https://site.atlassian.net/wiki/spaces/TEST/pages/555555"
        assert parse_page_id(url) == "555555"

    def test_returns_input_if_not_matching(self) -> None:
        """Returns input if no pattern matches."""
        assert parse_page_id("some-identifier") == "some-identifier"


class TestSlugify:
    """Tests for slugify function."""

    def test_basic_slugify(self) -> None:
        """Converts title to lowercase slug."""
        assert slugify("Hello World") == "hello-world"
        assert slugify("My Page Title") == "my-page-title"

    def test_removes_special_characters(self) -> None:
        """Removes special characters."""
        assert slugify("Test: Special!") == "test-special"
        assert slugify("Page (v2)") == "page-v2"

    def test_collapses_multiple_hyphens(self) -> None:
        """Collapses multiple hyphens."""
        assert slugify("Test   Multiple   Spaces") == "test-multiple-spaces"
        assert slugify("A - B - C") == "a-b-c"

    def test_strips_leading_trailing_hyphens(self) -> None:
        """Strips leading and trailing hyphens."""
        assert slugify("---Test---") == "test"
        assert slugify("!Test!") == "test"

    def test_truncates_long_titles(self) -> None:
        """Truncates titles longer than 80 characters."""
        long_title = "A" * 100
        result = slugify(long_title)
        assert len(result) <= 80

    def test_preserves_numbers(self) -> None:
        """Preserves numbers in slug."""
        assert slugify("Version 2.0") == "version-20"
        assert slugify("Sprint 123") == "sprint-123"

    def test_handles_empty_string(self) -> None:
        """Handles empty string."""
        assert slugify("") == ""

    def test_handles_unicode(self) -> None:
        """Handles unicode characters by removing them."""
        # Unicode letters should be kept as word characters
        result = slugify("Café Menu")
        assert "caf" in result


class TestParseFrontMatterRoundTrip:
    """Tests for round-trip parsing and writing."""

    def test_round_trip(self) -> None:
        """Front matter survives round-trip."""
        original_fm = {"title": "Test Page", "confluence": 12345}
        original_body = "# Content\n\nBody text"

        written = write_front_matter(original_fm, original_body)
        parsed_fm, parsed_body = parse_front_matter(written)

        assert parsed_fm["title"] == original_fm["title"]
        assert parsed_fm["confluence"] == original_fm["confluence"]
        assert "# Content" in parsed_body

    def test_round_trip_with_labels(self) -> None:
        """Front matter with lists survives round-trip."""
        original_fm = {"title": "Tagged", "labels": ["a", "b"]}
        original_body = "Content"

        written = write_front_matter(original_fm, original_body)
        parsed_fm, parsed_body = parse_front_matter(written)

        assert parsed_fm["labels"] == ["a", "b"]


class TestSlugifyEdgeCases:
    """Additional edge cases for slugify function."""

    def test_all_special_chars(self) -> None:
        """Handles string of only special characters."""
        result = slugify("!@#$%^&*()")
        assert result == ""

    def test_mixed_unicode_ascii(self) -> None:
        """Handles mixed unicode and ASCII."""
        result = slugify("Test Seite")
        assert "test" in result
        assert "seite" in result

    def test_multiple_spaces_and_hyphens(self) -> None:
        """Collapses multiple spaces and hyphens."""
        assert slugify("a   -   b") == "a-b"
        assert slugify("test--case") == "test-case"


class TestParsePageIdEdgeCases:
    """Additional edge cases for parse_page_id."""

    def test_url_with_trailing_slash(self) -> None:
        """Handles URL with trailing slash."""
        url = "https://site.atlassian.net/wiki/spaces/SPACE/pages/123456/"
        assert parse_page_id(url) == "123456"

    def test_url_with_query_params(self) -> None:
        """Handles URL with query parameters."""
        url = "https://site.atlassian.net/wiki/spaces/SPACE/pages/123456?param=value"
        assert parse_page_id(url) == "123456"

    def test_url_must_have_lowercase_pages(self) -> None:
        """URL must have lowercase /pages/ to match."""
        # URL with uppercase Pages won't match the pattern
        url = "https://SITE.atlassian.net/wiki/SPACES/TEST/Pages/999999/Title"
        # Returns the input unchanged since pattern doesn't match
        assert parse_page_id(url) == url

        # Lowercase /pages/ works
        url_lower = "https://site.atlassian.net/wiki/spaces/TEST/pages/888888/Title"
        assert parse_page_id(url_lower) == "888888"


class TestWriteFrontMatterEdgeCases:
    """Additional edge cases for write_front_matter."""

    def test_nested_dict_values(self) -> None:
        """Handles nested dict values."""
        fm = {"meta": {"key": "value"}}
        body = "Content"

        result = write_front_matter(fm, body)

        assert "meta:" in result
        assert "key:" in result

    def test_numeric_values(self) -> None:
        """Handles numeric values."""
        fm = {"page_id": 12345, "version": 3.14}
        body = "Content"

        result = write_front_matter(fm, body)

        assert "12345" in result
        assert "3.14" in result

    def test_boolean_values(self) -> None:
        """Handles boolean values."""
        fm = {"draft": True, "published": False}
        body = "Content"

        result = write_front_matter(fm, body)

        assert "true" in result.lower()
        assert "false" in result.lower()


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_computes_sha256(self, tmp_path) -> None:
        """Computes SHA256 hash of file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = compute_file_hash(test_file)

        # SHA256 hash is 64 hex characters
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path) -> None:
        """Same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("identical content")
        file2.write_text("identical content")

        assert compute_file_hash(file1) == compute_file_hash(file2)

    def test_different_content_different_hash(self, tmp_path) -> None:
        """Different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content one")
        file2.write_text("content two")

        assert compute_file_hash(file1) != compute_file_hash(file2)


class TestGetSyncProperty:
    """Tests for get_sync_property function."""

    def test_returns_property_value(self, mock_confluence) -> None:
        """Returns value from property."""
        from zaira import confluence_api

        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {"value": {"source_hash": "abc123"}},
        )

        result = get_sync_property("12345")

        assert result == {"source_hash": "abc123"}

    def test_returns_none_when_not_found(self, mock_confluence) -> None:
        """Returns None when property not found."""
        from zaira import confluence_api

        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = get_sync_property("12345")

        assert result is None


class TestSetSyncProperty:
    """Tests for set_sync_property function."""

    def test_sets_property(self, mock_confluence) -> None:
        """Sets property and returns True."""
        from zaira import confluence_api

        called_with = {}

        def mock_set(page_id: str, key: str, value: object) -> bool:
            called_with["page_id"] = page_id
            called_with["key"] = key
            called_with["value"] = value
            return True

        confluence_api.set_api("set_page_property", mock_set)

        result = set_sync_property("12345", {"hash": "xyz"})

        assert result is True
        assert called_with["page_id"] == "12345"
        assert called_with["value"] == {"hash": "xyz"}


class TestCheckImagesChanged:
    """Tests for check_images_changed function."""

    def test_returns_false_no_images(self, tmp_path) -> None:
        """Returns False when no images in content."""
        md_file = tmp_path / "test.md"
        md_file.write_text("No images here")

        result = check_images_changed(md_file, "No images here", {})

        assert result is False

    def test_returns_true_for_new_image(self, tmp_path) -> None:
        """Returns True when image not in stored hashes."""
        # Create markdown file with image reference
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"

        # Create the image file
        (tmp_path / "image.png").write_bytes(b"image data")

        result = check_images_changed(md_file, content, {})

        assert result is True

    def test_returns_false_for_unchanged_image(self, tmp_path) -> None:
        """Returns False when image hash matches stored hash."""
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"

        # Create image file
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"image data")

        # Compute the actual hash
        stored_hash = compute_file_hash(img_file)

        result = check_images_changed(md_file, content, {"image.png": stored_hash})

        assert result is False

    def test_returns_true_for_changed_image(self, tmp_path) -> None:
        """Returns True when image hash differs from stored."""
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"

        # Create image file
        (tmp_path / "image.png").write_bytes(b"new data")

        result = check_images_changed(md_file, content, {"image.png": "old_hash"})

        assert result is True

    def test_skips_missing_images(self, tmp_path) -> None:
        """Skips images that don't exist."""
        md_file = tmp_path / "test.md"
        content = "![Alt](./missing.png)"

        # Don't create the image file

        result = check_images_changed(md_file, content, {})

        assert result is False


class TestGetChildren:
    """Tests for _get_children function."""

    def test_returns_empty_for_no_children(self, mock_confluence) -> None:
        """Returns empty list when page has no children."""
        from zaira.wiki import _get_children
        from zaira import confluence_api

        confluence_api.set_api("get_child_pages", lambda page_id, limit: [])

        result = _get_children("12345")

        assert result == []

    def test_returns_child_ids(self, mock_confluence) -> None:
        """Returns list of child page IDs."""
        from zaira.wiki import _get_children
        from zaira import confluence_api

        def mock_get_children(page_id: str, limit: int) -> list[object]:
            if page_id == "12345":
                return [{"id": "111"}, {"id": "222"}]
            return []

        confluence_api.set_api("get_child_pages", mock_get_children)

        result = _get_children("12345")

        assert result == ["111", "222"]

    def test_returns_nested_children(self, mock_confluence) -> None:
        """Recursively fetches nested children."""
        from zaira.wiki import _get_children
        from zaira import confluence_api

        def mock_get_children(page_id: str, limit: int) -> list[object]:
            if page_id == "12345":
                return [{"id": "111"}]
            elif page_id == "111":
                return [{"id": "222"}]
            return []

        confluence_api.set_api("get_child_pages", mock_get_children)

        result = _get_children("12345")

        assert result == ["111", "222"]


class TestFetchPage:
    """Tests for _fetch_page function."""

    def test_returns_page_dict(self, mock_confluence) -> None:
        """Returns page dict on success."""
        from zaira.wiki import _fetch_page
        from zaira import confluence_api

        page_data = {"id": "12345", "title": "Test", "body": {"storage": {"value": ""}}}
        confluence_api.set_api("fetch_page", lambda page_id, expand: page_data)

        result = _fetch_page("12345")

        assert result == page_data

    def test_returns_none_on_error(self, mock_confluence, capsys) -> None:
        """Returns None when fetch fails."""
        from zaira.wiki import _fetch_page
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        result = _fetch_page("12345")

        assert result is None
        captured = capsys.readouterr()
        assert "Error fetching 12345" in captured.err


class TestFetchLabels:
    """Tests for _fetch_labels function."""

    def test_returns_labels(self, mock_confluence) -> None:
        """Returns list of labels."""
        from zaira.wiki import _fetch_labels
        from zaira import confluence_api

        confluence_api.set_api("get_page_labels", lambda page_id: ["label1", "label2"])

        result = _fetch_labels("12345")

        assert result == ["label1", "label2"]


class TestGetPageInfo:
    """Tests for _get_page_info function."""

    def test_returns_page_info(self, mock_confluence) -> None:
        """Returns parent_id and space_key."""
        from zaira.wiki import _get_page_info
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "ancestors": [{"id": "111"}, {"id": "222"}],
                "space": {"key": "TEST"},
            },
        )

        result = _get_page_info("12345")

        from zaira.types import PageInfo

        assert result == PageInfo(parent_id="222", space_key="TEST")

    def test_returns_none_on_error(self, mock_confluence) -> None:
        """Returns None when page not found."""
        from zaira.wiki import _get_page_info
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        result = _get_page_info("12345")

        assert result is None

    def test_returns_none_parent_at_root(self, mock_confluence) -> None:
        """Returns None parent_id when page is at space root."""
        from zaira.wiki import _get_page_info
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {"ancestors": [], "space": {"key": "TEST"}},
        )

        result = _get_page_info("12345")

        from zaira.types import PageInfo

        assert result == PageInfo(parent_id=None, space_key="TEST")


class TestSyncImages:
    """Tests for sync_images function."""

    def test_returns_empty_for_no_images(self, tmp_path, mock_confluence) -> None:
        """Returns empty dict when no images in content."""
        from zaira.wiki import sync_images

        md_file = tmp_path / "test.md"
        md_file.write_text("No images")

        result = sync_images("12345", md_file, "No images", {})

        assert result == {}

    def test_uploads_new_image(self, tmp_path, mock_confluence, capsys) -> None:
        """Uploads new image and returns hash."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        # Create markdown file and image
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"image data")

        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "upload_attachment", lambda page_id, path, filename: {"id": "att1"}
        )

        result = sync_images("12345", md_file, content, {})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Uploaded image: image.png" in captured.out

    def test_updates_existing_image(self, tmp_path, mock_confluence, capsys) -> None:
        """Updates existing attachment when image changed."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"new image data")

        confluence_api.set_api(
            "get_attachments",
            lambda page_id, expand: {"results": [{"title": "image.png", "id": "att1"}]},
        )
        confluence_api.set_api(
            "update_attachment", lambda page_id, att_id, path, filename: {"id": "att1"}
        )

        result = sync_images("12345", md_file, content, {"image.png": "old_hash"})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Updated image: image.png" in captured.out

    def test_skips_unchanged_image(self, tmp_path, mock_confluence, capsys) -> None:
        """Skips upload when image unchanged."""
        from zaira.wiki import sync_images, compute_file_hash
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"image data")

        stored_hash = compute_file_hash(img_file)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = sync_images("12345", md_file, content, {"image.png": stored_hash})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Uploaded" not in captured.out
        assert "Updated" not in captured.out

    def test_warns_for_missing_image(self, tmp_path, mock_confluence, capsys) -> None:
        """Warns when referenced image doesn't exist."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./missing.png)"

        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = sync_images("12345", md_file, content, {})

        assert "missing.png" not in result
        captured = capsys.readouterr()
        assert "Warning: Image not found" in captured.err


class TestDownloadImages:
    """Tests for download_images function."""

    def test_downloads_nothing_when_no_attachments(
        self, tmp_path, mock_confluence
    ) -> None:
        """Does nothing when page has no attachments."""
        from zaira.wiki import download_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        download_images("12345", md_file)

        assert not (tmp_path / "images").exists()

    def test_downloads_image_attachments(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Downloads image attachments to images directory."""
        from zaira.wiki import download_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        confluence_api.set_api(
            "get_attachments",
            lambda page_id, expand: {
                "results": [
                    {
                        "title": "image.png",
                        "_links": {"download": "/download/image.png"},
                    }
                ],
                "_links": {"base": "https://site.atlassian.net/wiki"},
            },
        )
        confluence_api.set_api("download_attachment", lambda url, path: True)

        download_images("12345", md_file)

        assert (tmp_path / "images").exists()
        captured = capsys.readouterr()
        assert "Downloaded image: image.png" in captured.out

    def test_skips_non_image_attachments(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Skips non-image file extensions."""
        from zaira.wiki import download_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        confluence_api.set_api(
            "get_attachments",
            lambda page_id, expand: {
                "results": [
                    {
                        "title": "document.pdf",
                        "_links": {"download": "/download/document.pdf"},
                    }
                ],
                "_links": {"base": "https://site.atlassian.net"},
            },
        )

        download_images("12345", md_file)

        captured = capsys.readouterr()
        assert "document.pdf" not in captured.out


class TestPrintPageTree:
    """Tests for _print_page_tree function."""

    def test_prints_single_page(self, mock_confluence, capsys) -> None:
        """Prints single page without children."""
        from zaira.wiki import _print_page_tree
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {"title": "Test Page", "space": {"key": "TEST"}},
        )
        confluence_api.set_api("get_child_pages", lambda page_id, limit: [])

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            count = _print_page_tree("12345")

        assert count == 1
        captured = capsys.readouterr()
        assert "Test Page" in captured.out
        assert "12345" in captured.out

    def test_returns_zero_on_error(self, mock_confluence, capsys) -> None:
        """Returns 0 when page fetch fails."""
        from zaira.wiki import _print_page_tree
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        count = _print_page_tree("12345")

        assert count == 0
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_prints_children(self, mock_confluence, capsys) -> None:
        """Prints page with children."""
        from zaira.wiki import _print_page_tree
        from zaira import confluence_api

        def mock_fetch(page_id: str, expand: str) -> dict[str, object]:
            return {"title": f"Page {page_id}", "space": {"key": "TEST"}}

        def mock_children(page_id: str, limit: int) -> list[object]:
            if page_id == "12345":
                return [{"id": "111"}]
            return []

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_child_pages", mock_children)

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            count = _print_page_tree("12345")

        assert count == 2
        captured = capsys.readouterr()
        assert "Page 12345" in captured.out
        assert "Page 111" in captured.out


class TestWikiCommand:
    """Tests for wiki_command function."""

    def test_calls_wiki_func(self) -> None:
        """Calls wiki_func when present."""
        from zaira.wiki import wiki_command
        import argparse

        called = []
        args = argparse.Namespace(wiki_func=lambda a: called.append(a))

        wiki_command(args)

        assert len(called) == 1

    def test_prints_usage_without_func(self, capsys) -> None:
        """Prints usage when wiki_func not present."""
        from zaira.wiki import wiki_command
        import argparse

        args = argparse.Namespace()

        with pytest.raises(SystemExit) as exc_info:
            wiki_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.out


class TestExportPageToFile:
    """Tests for _export_page_to_file function."""

    def test_exports_page(self, tmp_path, mock_confluence, capsys) -> None:
        """Exports page to markdown file."""
        from zaira.wiki import _export_page_to_file
        from zaira import confluence_api

        page = {
            "id": "12345",
            "title": "Test Page",
            "version": {"number": 1},
            "body": {"storage": {"value": "<p>Content</p>"}},
        }

        confluence_api.set_api("get_page_labels", lambda page_id: ["label1"])
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _export_page_to_file(page, tmp_path)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".md"
        content = result.read_text()
        assert "confluence: 12345" in content
        assert "title: Test Page" in content
        assert "label1" in content


class TestSearchCommand:
    """Tests for search_command function."""

    def test_search_with_query(self, mock_confluence, capsys) -> None:
        """Searches with text query."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "search_pages",
            lambda cql, limit, expand: {
                "results": [
                    {
                        "id": "12345",
                        "title": "Found Page",
                        "space": {"key": "TEST"},
                        "_links": {"webui": "/spaces/TEST/pages/12345/Found+Page"},
                    }
                ]
            },
        )

        args = argparse.Namespace(
            query="test",
            space=None,
            cql=None,
            creator=None,
            label=None,
            limit=25,
            format="default",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            search_command(args)

        captured = capsys.readouterr()
        assert "Found Page" in captured.out
        assert "TEST" in captured.out

    def test_search_json_format(self, mock_confluence, capsys) -> None:
        """Returns JSON format when requested."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse
        import json

        results = {"results": [{"id": "12345", "title": "Page"}]}
        confluence_api.set_api("search_pages", lambda cql, limit, expand: results)

        args = argparse.Namespace(
            query="test",
            space=None,
            cql=None,
            creator=None,
            label=None,
            limit=25,
            format="json",
        )

        search_command(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "results" in output

    def test_search_url_format(self, mock_confluence, capsys) -> None:
        """Returns URL-only format when requested."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "search_pages",
            lambda cql, limit, expand: {
                "results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]
            },
        )

        args = argparse.Namespace(
            query="test",
            space=None,
            cql=None,
            creator=None,
            label=None,
            limit=25,
            format="url",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            search_command(args)

        captured = capsys.readouterr()
        assert "https://site.atlassian.net/wiki/spaces/TEST/pages/12345" in captured.out

    def test_search_id_format(self, mock_confluence, capsys) -> None:
        """Returns ID-only format when requested."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "search_pages",
            lambda cql, limit, expand: {
                "results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]
            },
        )

        args = argparse.Namespace(
            query="test",
            space=None,
            cql=None,
            creator=None,
            label=None,
            limit=25,
            format="id",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            search_command(args)

        captured = capsys.readouterr()
        assert captured.out.strip() == "12345"

    def test_search_no_results(self, mock_confluence, capsys) -> None:
        """Exits gracefully when no results."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "search_pages", lambda cql, limit, expand: {"results": []}
        )

        args = argparse.Namespace(
            query="nonexistent",
            space=None,
            cql=None,
            creator=None,
            label=None,
            limit=25,
            format="default",
        )

        with pytest.raises(SystemExit) as exc_info:
            search_command(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No results found" in captured.err

    def test_search_error(self, mock_confluence, capsys) -> None:
        """Handles API errors."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "search_pages",
            lambda cql, limit, expand: {
                "error": "401 - Unauthorized",
                "text": "Invalid credentials",
            },
        )

        args = argparse.Namespace(
            query="test",
            space=None,
            cql=None,
            creator=None,
            label=None,
            limit=25,
            format="default",
        )

        with pytest.raises(SystemExit) as exc_info:
            search_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_search_with_space_filter(self, mock_confluence, capsys) -> None:
        """Filters by space."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        cql_received = []

        def mock_search(cql: str, limit: int, expand: str) -> dict[str, object]:
            cql_received.append(cql)
            return {
                "results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]
            }

        confluence_api.set_api("search_pages", mock_search)

        args = argparse.Namespace(
            query="test",
            space="MYSPACE",
            cql=None,
            creator=None,
            label=None,
            limit=25,
            format="default",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            search_command(args)

        assert 'space = "MYSPACE"' in cql_received[0]

    def test_search_with_creator_filter(self, mock_confluence, capsys) -> None:
        """Filters by creator."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        cql_received = []

        def mock_search(cql: str, limit: int, expand: str) -> dict[str, object]:
            cql_received.append(cql)
            return {
                "results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]
            }

        confluence_api.set_api("search_pages", mock_search)

        args = argparse.Namespace(
            query="test",
            cql=None,
            space=None,
            creator="John Doe",
            label=None,
            limit=25,
            format="default",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            search_command(args)

        assert 'creator.fullname ~ "John Doe"' in cql_received[0]

    def test_search_with_label_filter(self, mock_confluence, capsys) -> None:
        """Filters by label, with the value quoted.

        Confluence's CQL parser silently fails ("could not parse cql") on
        hyphenated label values passed unquoted, e.g. label=aws-services —
        the value must always be quoted.
        """
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        cql_received = []

        def mock_search(cql: str, limit: int, expand: str) -> dict[str, object]:
            cql_received.append(cql)
            return {
                "results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]
            }

        confluence_api.set_api("search_pages", mock_search)

        args = argparse.Namespace(
            query="test",
            cql=None,
            space=None,
            creator=None,
            label="aws-services",
            limit=25,
            format="default",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            search_command(args)

        assert 'label = "aws-services"' in cql_received[0]

    def test_search_with_space_and_label_filter(self, mock_confluence, capsys) -> None:
        """Combines space and label filters with AND, both quoted."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        cql_received = []

        def mock_search(cql: str, limit: int, expand: str) -> dict[str, object]:
            cql_received.append(cql)
            return {
                "results": [{"id": "12345", "title": "Page", "space": {"key": "BTA"}}]
            }

        confluence_api.set_api("search_pages", mock_search)

        args = argparse.Namespace(
            query="Proton",
            cql=None,
            space="BTA",
            creator=None,
            label="aws-services",
            limit=25,
            format="default",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            search_command(args)

        cql = cql_received[0]
        assert 'space = "BTA"' in cql
        assert 'label = "aws-services"' in cql
        assert " AND " in cql


class TestGetCommand:
    """Tests for get_command function."""

    def test_get_no_pages_error(self, capsys) -> None:
        """Errors when no pages specified."""
        from zaira.wiki import get_command
        import argparse

        args = argparse.Namespace(pages=[])

        with pytest.raises(SystemExit) as exc_info:
            get_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No pages specified" in captured.err

    def test_get_list_mode(self, mock_confluence, capsys) -> None:
        """Lists page tree when --list is used."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Root Page",
                "space": {"key": "TEST"},
            },
        )
        confluence_api.set_api("get_child_pages", lambda page_id, limit: [])

        args = argparse.Namespace(
            pages=["12345"],
            list=True,
            children=False,
            output=None,
            format="markdown",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            get_command(args)

        captured = capsys.readouterr()
        assert "Root Page" in captured.out
        assert "1 page(s)" in captured.out

    def test_get_single_page_stdout_markdown(self, mock_confluence, capsys) -> None:
        """Gets single page in markdown format to stdout."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "TEST", "name": "Test Space"},
                "body": {"storage": {"value": "<p>Hello</p>"}},
            },
        )
        confluence_api.set_api("get_page_labels", lambda page_id: [])

        args = argparse.Namespace(
            pages=["12345"],
            list=False,
            children=False,
            output=None,
            format="markdown",
        )

        get_command(args)

        captured = capsys.readouterr()
        assert "confluence: 12345" in captured.out
        assert "title: Test Page" in captured.out

    def test_get_single_page_stdout_json(self, mock_confluence, capsys) -> None:
        """Gets single page in JSON format to stdout."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse
        import json

        page_data = {
            "id": "12345",
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "TEST", "name": "Test Space"},
            "body": {"storage": {"value": "<p>Hello</p>"}},
        }
        confluence_api.set_api("fetch_page", lambda page_id, expand: page_data)

        args = argparse.Namespace(
            pages=["12345"],
            list=False,
            children=False,
            output=None,
            format="json",
        )

        get_command(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["id"] == "12345"

    def test_get_single_page_stdout_html(self, mock_confluence, capsys) -> None:
        """Gets single page in HTML format to stdout."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "TEST", "name": "Test Space"},
                "body": {"storage": {"value": "<p>Hello</p>"}},
            },
        )

        args = argparse.Namespace(
            pages=["12345"],
            list=False,
            children=False,
            output=None,
            format="html",
        )

        get_command(args)

        captured = capsys.readouterr()
        assert "Title: Test Page" in captured.out
        assert "<p>Hello</p>" in captured.out

    def test_get_multiple_pages_requires_output(self, mock_confluence, capsys) -> None:
        """Multiple pages require output directory."""
        from zaira.wiki import get_command
        import argparse

        args = argparse.Namespace(
            pages=["12345", "67890"],
            list=False,
            children=False,
            output=None,
            format="markdown",
        )

        with pytest.raises(SystemExit) as exc_info:
            get_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "require -o/--output directory" in captured.err

    def test_get_multiple_pages_to_dir(self, tmp_path, mock_confluence, capsys) -> None:
        """Gets multiple pages to output directory."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        def mock_fetch(page_id: str, expand: str) -> dict[str, object]:
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
            }

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        output_dir = tmp_path / "output"
        args = argparse.Namespace(
            pages=["12345", "67890"],
            list=False,
            children=False,
            output=str(output_dir),
            format="markdown",
        )

        get_command(args)

        assert output_dir.exists()
        files = list(output_dir.glob("*.md"))
        assert len(files) == 2
        captured = capsys.readouterr()
        assert "Exported 2 page(s)" in captured.out

    def test_get_with_children(self, mock_confluence, capsys, tmp_path) -> None:
        """Gets page with children expanded."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        def mock_fetch(page_id: str, expand: str) -> dict[str, object]:
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
            }

        def mock_children(page_id: str, limit: int) -> list[object]:
            if page_id == "12345":
                return [{"id": "111"}]
            return []

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_child_pages", mock_children)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            pages=["12345"],
            list=False,
            children=True,
            output=str(tmp_path / "test_output"),
            format="markdown",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            get_command(args)

        captured = capsys.readouterr()
        assert "Found 1 child page(s)" in captured.err

    def test_get_page_fetch_error(self, mock_confluence, capsys) -> None:
        """Handles page fetch error."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        args = argparse.Namespace(
            pages=["12345"],
            list=False,
            children=False,
            output=None,
            format="markdown",
        )

        with pytest.raises(SystemExit) as exc_info:
            get_command(args)

        assert exc_info.value.code == 1


class TestCreateCommand:
    """Tests for create_command function."""

    def test_create_page_with_markdown(
        self, mock_confluence, capsys, monkeypatch
    ) -> None:
        """Creates page with markdown body."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("# Hello\n\nWorld"))

        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "12345",
                "version": {"number": 1},
            },
        )

        args = argparse.Namespace(
            title="New Page",
            space="TEST",
            parent=None,
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out

    def test_create_page_empty_body_error(self, capsys, monkeypatch) -> None:
        """Errors when stdin is empty."""
        from zaira.wiki import create_command
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("   "))

        args = argparse.Namespace(
            title="New Page",
            space="TEST",
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No content on stdin" in captured.err

    def test_create_page_requires_space_or_parent(self, capsys, monkeypatch) -> None:
        """Errors when neither space nor parent specified."""
        from zaira.wiki import create_command
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("Content"))

        args = argparse.Namespace(
            title="New Page",
            space=None,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Either --space or --parent is required" in captured.err

    def test_create_page_infers_space_from_parent(
        self, mock_confluence, capsys, monkeypatch
    ) -> None:
        """Infers space from parent page."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("Content"))

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "ancestors": [],
                "space": {"key": "INFERRED"},
            },
        )
        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "12345",
                "version": {"number": 1},
            },
        )

        args = argparse.Namespace(
            title="New Page",
            space=None,
            parent="99999",
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out

    def test_create_page_api_error(self, mock_confluence, capsys, monkeypatch) -> None:
        """Handles API error on create."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("Content"))

        confluence_api.set_api("create_page", lambda space, title, body, parent: None)

        args = argparse.Namespace(
            title="New Page",
            space="TEST",
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error creating page" in captured.err

    def test_create_page_reads_from_stdin(
        self, mock_confluence, capsys, monkeypatch
    ) -> None:
        """Reads body from stdin."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("File content here"))

        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "12345",
                "version": {"number": 1},
            },
        )

        args = argparse.Namespace(
            title="New Page",
            space="TEST",
            parent=None,
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out


class TestAttachCommand:
    """Tests for attach_command function."""

    def test_attach_uploads_file(self, tmp_path, mock_confluence, capsys) -> None:
        """Uploads file as attachment."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"image data")

        confluence_api.set_api("get_attachments", lambda page_id: {"results": []})
        confluence_api.set_api(
            "upload_attachment", lambda page_id, path, filename: {"id": "att1"}
        )

        args = argparse.Namespace(
            page="12345",
            files=[str(test_file)],
            replace=False,
        )

        attach_command(args)

        captured = capsys.readouterr()
        assert "Uploaded: test.png" in captured.out
        assert "ac:image" in captured.out

    def test_attach_replaces_existing(self, tmp_path, mock_confluence, capsys) -> None:
        """Replaces existing attachment when --replace is used."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"image data")

        confluence_api.set_api(
            "get_attachments",
            lambda page_id, expand: {"results": [{"title": "test.png", "id": "att1"}]},
        )
        confluence_api.set_api(
            "update_attachment", lambda page_id, att_id, path, filename: {"id": "att1"}
        )

        args = argparse.Namespace(
            page="12345",
            files=[str(test_file)],
            replace=True,
        )

        attach_command(args)

        captured = capsys.readouterr()
        assert "Updated: test.png" in captured.out

    def test_attach_no_files_error(self, capsys) -> None:
        """Errors when no files found."""
        from zaira.wiki import attach_command
        import argparse

        args = argparse.Namespace(
            page="12345",
            files=["nonexistent*.xyz"],
            replace=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            attach_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_attach_upload_error(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles upload error."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"image data")

        confluence_api.set_api("get_attachments", lambda page_id: {"results": []})
        confluence_api.set_api(
            "upload_attachment", lambda page_id, path, filename: None
        )

        args = argparse.Namespace(
            page="12345",
            files=[str(test_file)],
            replace=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            attach_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error uploading" in captured.err


class TestDeleteCommand:
    """Tests for delete_command function."""

    def test_delete_page_not_found(self, mock_confluence, capsys) -> None:
        """Errors when page not found."""
        from zaira.wiki import delete_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        args = argparse.Namespace(page="12345", yes=True)

        with pytest.raises(SystemExit) as exc_info:
            delete_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Page not found" in captured.err

    def test_delete_page_with_yes(self, mock_confluence, capsys) -> None:
        """Deletes page when --yes is specified."""
        from zaira.wiki import delete_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "space": {"key": "TEST"},
            },
        )
        confluence_api.set_api("delete_page", lambda page_id: True)

        args = argparse.Namespace(page="12345", yes=True)

        delete_command(args)

        captured = capsys.readouterr()
        assert "Deleted page 12345" in captured.out

    def test_delete_page_api_error(self, mock_confluence, capsys) -> None:
        """Handles API error on delete."""
        from zaira.wiki import delete_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "space": {"key": "TEST"},
            },
        )
        confluence_api.set_api("delete_page", lambda page_id: False)

        args = argparse.Namespace(page="12345", yes=True)

        with pytest.raises(SystemExit) as exc_info:
            delete_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error deleting page" in captured.err

    def test_delete_page_cancel_confirmation(
        self, mock_confluence, capsys, monkeypatch
    ) -> None:
        """Cancels when user doesn't confirm."""
        from zaira.wiki import delete_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "space": {"key": "TEST"},
            },
        )

        monkeypatch.setattr("builtins.input", lambda prompt: "no")

        args = argparse.Namespace(page="12345", yes=False)

        with pytest.raises(SystemExit) as exc_info:
            delete_command(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Deletion cancelled" in captured.out


class TestEditCommand:
    """Tests for edit_command function."""

    def test_edit_page_not_found(self, mock_confluence, capsys) -> None:
        """Errors when page not found."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent=None,
            space=None,
            labels=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            edit_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Page not found" in captured.err

    def test_edit_page_title(self, mock_confluence, capsys) -> None:
        """Edits page title."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Old Title",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [],
            },
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key, parent_id: True,
        )

        args = argparse.Namespace(
            page="12345",
            title="New Title",
            parent=None,
            space=None,
            labels=None,
        )

        edit_command(args)

        captured = capsys.readouterr()
        assert "Updated page 12345" in captured.out
        assert "Old Title" in captured.out
        assert "New Title" in captured.out

    def test_edit_page_labels(self, mock_confluence, capsys) -> None:
        """Edits page labels."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [],
            },
        )
        confluence_api.set_api("get_page_labels", lambda page_id: ["old-label"])
        confluence_api.set_api("remove_page_label", lambda page_id, label: True)
        confluence_api.set_api("add_page_labels", lambda page_id, labels: True)

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent=None,
            space=None,
            labels="new-label,another",
        )

        edit_command(args)

        captured = capsys.readouterr()
        assert "Updated page 12345" in captured.out
        assert "label removed: old-label" in captured.out
        assert "label added:" in captured.out

    def test_edit_no_changes(self, mock_confluence, capsys) -> None:
        """Reports no changes when nothing changed."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [],
            },
        )

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent=None,
            space=None,
            labels=None,
        )

        edit_command(args)

        captured = capsys.readouterr()
        assert "No changes made" in captured.out

    def test_edit_page_parent(self, mock_confluence, capsys) -> None:
        """Edits page parent."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [{"id": "111"}],
            },
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key, parent_id: True,
        )

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent="222",
            space=None,
            labels=None,
        )

        edit_command(args)

        captured = capsys.readouterr()
        assert "Updated page 12345" in captured.out
        assert "parent:" in captured.out

    def test_edit_page_space(self, mock_confluence, capsys) -> None:
        """Edits page space."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "OLD"},
                "ancestors": [],
            },
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key, parent_id: True,
        )

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent=None,
            space="NEW",
            labels=None,
        )

        edit_command(args)

        captured = capsys.readouterr()
        assert "Updated page 12345" in captured.out
        assert "space:" in captured.out

    def test_edit_update_properties_error(self, mock_confluence, capsys) -> None:
        """Handles error when updating properties."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Old Title",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [],
            },
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key, parent_id: None,
        )

        args = argparse.Namespace(
            page="12345",
            title="New Title",
            parent=None,
            space=None,
            labels=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            edit_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error updating page properties" in captured.err


class TestPutOneFile:
    """Tests for _put_one_file function."""

    def test_put_file_not_found(self, tmp_path, capsys) -> None:
        """Errors when file not found."""
        from zaira.wiki import _put_one_file

        result = _put_one_file(
            tmp_path / "nonexistent.md", None, None, False, False, False, False
        )

        assert result is False
        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_put_empty_file(self, tmp_path, capsys) -> None:
        """Errors when file is empty."""
        from zaira.wiki import _put_one_file

        md_file = tmp_path / "empty.md"
        md_file.write_text("   ")

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "File is empty" in captured.err

    def test_put_no_page_id(self, tmp_path, capsys) -> None:
        """Skips file without confluence front matter."""
        from zaira.wiki import _put_one_file

        md_file = tmp_path / "no_id.md"
        md_file.write_text("# Just content\n\nNo front matter")

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "no 'confluence:'" in captured.err

    def test_put_status_mode(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows status when --status is used."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 2},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": "abc123",
                    "uploaded_version": 1,
                    "uploaded_at": "2024-01-01T00:00:00Z",
                }
            },
        )

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Page ID: 12345" in captured.out
        assert "Remote version: 2" in captured.out

    def test_put_diff_mode(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows diff when --diff is used."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# New Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = _put_one_file(md_file, None, None, False, False, False, True)

        assert result is True
        captured = capsys.readouterr()
        assert "Diff for" in captured.out

    def test_put_pull_mode(self, tmp_path, mock_confluence, capsys) -> None:
        """Pulls content from remote when --pull is used."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Local Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Remote Title",
                "version": {"number": 3},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Remote Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_page_labels", lambda page_id: ["remote-label"])
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = _put_one_file(md_file, None, None, True, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pulled version 3" in captured.out
        content = md_file.read_text()
        assert "Remote Title" in content
        assert "remote-label" in content

    def test_put_conflict_detection(self, tmp_path, mock_confluence, capsys) -> None:
        """Detects conflict when local and remote both changed."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed local content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 3},  # Remote is version 3
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Remote changed</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": "old_hash",  # Local content changed
                    "uploaded_version": 2,  # Last synced at version 2
                }
            },
        )

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "Conflict" in captured.err

    def test_put_already_synced(self, tmp_path, mock_confluence, capsys) -> None:
        """Reports already in sync."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api
        import hashlib

        content = "# Content"
        local_hash = hashlib.sha256(content.encode()).hexdigest()

        md_file = tmp_path / "test.md"
        md_file.write_text(f"---\nconfluence: 12345\n---\n\n{content}")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": local_hash,
                    "uploaded_version": 1,
                    "images": {},
                }
            },
        )

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "already in sync" in captured.out

    def test_put_push_success(self, tmp_path, mock_confluence, capsys) -> None:
        """Successfully pushes content."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text(
            "---\nconfluence: 12345\ntitle: Updated Title\n---\n\n# New Content"
        )

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Old Title",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pushed" in captured.out
        assert "version 1 -> 2" in captured.out
        assert "title:" in captured.out

    def test_put_with_mermaid_rendering(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Pushes content with mermaid blocks rendered to PNG attachments."""
        import shutil

        if not shutil.which("mmdr") and not shutil.which("mmdc"):
            pytest.skip("neither mmdr nor mmdc installed")

        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text(
            "---\nconfluence: 12345\n---\n\n# Architecture\n\n"
            "```mermaid\ngraph TD\n    A[Client] --> B[Server]\n```\n\nSome text.\n"
        )

        uploaded_attachments = []
        pushed_body = {}

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Architecture",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        def capture_upload(
            page_id: str, filepath: Path, filename: str | None = None
        ) -> dict[str, object]:
            uploaded_attachments.append(filepath.name)
            return {"id": "att-1", "title": filepath.name}

        confluence_api.set_api("upload_attachment", capture_upload)

        def capture_update(
            page_id: str, title: str, body: str, version: int, ptype: str
        ) -> dict[str, object]:
            pushed_body["html"] = body
            return {"version": {"number": 2}}

        confluence_api.set_api("update_page", capture_update)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(
            md_file, None, None, False, False, False, False, renderers=["mermaid"]
        )

        assert result is True

        # Verify a mermaid SVG was uploaded as attachment
        assert len(uploaded_attachments) == 1
        assert uploaded_attachments[0].startswith("mermaid-")
        assert uploaded_attachments[0].endswith(".svg")

        # Verify the pushed HTML embeds the rendered image
        html = pushed_body["html"]
        assert '<ri:attachment ri:filename="mermaid-' in html

        captured = capsys.readouterr()
        assert "Pushed" in captured.out

    def test_put_with_labels(self, tmp_path, mock_confluence, capsys) -> None:
        """Pushes content with labels."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text(
            "---\nconfluence: 12345\nlabels: [new-label, another]\n---\n\n# Content"
        )

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_page_labels", lambda page_id: ["old-label"])
        confluence_api.set_api("remove_page_label", lambda page_id, label: True)
        confluence_api.set_api("add_page_labels", lambda page_id, labels: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pushed" in captured.out

    def test_put_update_error(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles update error."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page", lambda page_id, title, body, version, ptype: None
        )

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "Error updating" in captured.err

    def test_put_page_fetch_error(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles page fetch error."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "Error fetching" in captured.err

    def test_put_force_overwrite(self, tmp_path, mock_confluence, capsys) -> None:
        """Force overwrites conflict."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed local content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 3},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Remote changed</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": "old_hash",
                    "uploaded_version": 2,
                }
            },
        )
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 4}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, None, False, True, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pushed" in captured.out


class TestPutCommand:
    """Tests for put_command function."""

    def test_put_no_files_error(self, capsys) -> None:
        """Errors when no files specified."""
        from zaira.wiki import put_command
        import argparse

        args = argparse.Namespace(
            files=[],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No files specified" in captured.err

    def test_put_single_file(self, tmp_path, mock_confluence, capsys) -> None:
        """Processes single file."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            files=[str(md_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Pushed" in captured.out

    def test_put_directory(self, tmp_path, mock_confluence, capsys) -> None:
        """Processes directory of markdown files."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Create files in directory
        md_file1 = tmp_path / "file1.md"
        md_file1.write_text("---\nconfluence: 111\n---\n\n# Content 1")
        md_file2 = tmp_path / "file2.md"
        md_file2.write_text("---\nconfluence: 222\n---\n\n# Content 2")

        def mock_fetch(page_id: str, expand: str) -> dict[str, object]:
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            }

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Processed 2 file(s)" in captured.out

    def test_put_unlinked_file_skipped(self, tmp_path, mock_confluence, capsys) -> None:
        """Skips files without confluence front matter."""
        from zaira.wiki import put_command
        import argparse

        md_file = tmp_path / "unlinked.md"
        md_file.write_text("# No front matter")

        args = argparse.Namespace(
            files=[str(md_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Skipping" in captured.err
        assert "Use --create" in captured.err

    def test_put_create_new_page(self, tmp_path, mock_confluence, capsys) -> None:
        """Creates new page for unlinked file with --create."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Create linked file (to determine parent)
        linked_file = tmp_path / "linked.md"
        linked_file.write_text("---\nconfluence: 12345\n---\n\n# Linked")

        # Create unlinked file
        unlinked_file = tmp_path / "new_page.md"
        unlinked_file.write_text("# New Page\n\nContent for new page")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": page_id,
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [{"id": "parent-id"}],
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "99999",
                "version": {"number": 1},
            },
        )

        args = argparse.Namespace(
            files=[str(linked_file), str(unlinked_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Created page 99999" in captured.out

    def test_create_resolves_my_space_alias(
        self, tmp_path, mock_confluence, capsys, monkeypatch
    ) -> None:
        """put --create resolves the 'my' space alias before creating a page.

        Regression: previously put's create path passed the literal "my" to the
        Confluence API (only create_command resolved it), producing an
        unhelpful error.
        """
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Unlinked file with space: my in front matter -> per-file resolve path
        unlinked_file = tmp_path / "new_page.md"
        unlinked_file.write_text("---\nspace: my\n---\n\n# New Page\n\nContent")

        monkeypatch.setattr(
            confluence_api, "get_personal_space_key", lambda: "~personal123"
        )

        seen_spaces: list[str] = []

        def fake_create_page(
            space: str, title: str, body: str, parent: str | None
        ) -> dict[str, object]:
            seen_spaces.append(space)
            return {"id": "99999", "version": {"number": 1}}

        confluence_api.set_api("create_page", fake_create_page)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        args = argparse.Namespace(
            files=[str(unlinked_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
        )

        put_command(args)

        # The resolved personal key must be used, never the literal "my".
        assert seen_spaces == ["~personal123"]
        captured = capsys.readouterr()
        assert "Created page 99999" in captured.out


class TestCreatePageForFile:
    """Tests for _create_page_for_file function."""

    def test_creates_page_with_heading_title(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Uses first heading as title."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("# My Page Title\n\nContent here")

        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "12345",
                "version": {"number": 1},
            },
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = _create_page_for_file(md_file, "parent-id", "TEST")

        assert result is True
        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out
        content = md_file.read_text()
        assert "confluence: 12345" in content

    def test_creates_page_with_filename_title(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Uses filename as title when no heading."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "my-page-name.md"
        md_file.write_text("Just content, no heading")

        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "12345",
                "version": {"number": 1},
            },
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = _create_page_for_file(md_file, "parent-id", "TEST")

        assert result is True

    def test_create_page_api_error(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles API error on create."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("# Title\n\nContent")

        confluence_api.set_api("create_page", lambda space, title, body, parent: None)

        result = _create_page_for_file(md_file, "parent-id", "TEST")

        assert result is False
        captured = capsys.readouterr()
        assert "Error creating page" in captured.err

    def test_creates_page_with_title_prefix(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Applies title_prefix to page title."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("# My Page\n\nContent here")

        created_titles = []

        def mock_create(
            space: str, title: str, body: str, parent: str | None
        ) -> dict[str, object]:
            created_titles.append(title)
            return {"id": "12345", "version": {"number": 1}}

        confluence_api.set_api("create_page", mock_create)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = _create_page_for_file(
            md_file, "parent-id", "TEST", title_prefix="Demo - "
        )

        assert result is True
        assert len(created_titles) == 1
        assert created_titles[0] == "Demo - My Page"

    def test_creates_page_without_title_prefix(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Creates page normally when title_prefix is empty."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("# My Page\n\nContent here")

        created_titles = []

        def mock_create(
            space: str, title: str, body: str, parent: str | None
        ) -> dict[str, object]:
            created_titles.append(title)
            return {"id": "12345", "version": {"number": 1}}

        confluence_api.set_api("create_page", mock_create)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = _create_page_for_file(md_file, "parent-id", "TEST", title_prefix="")

        assert result is True
        assert len(created_titles) == 1
        assert created_titles[0] == "My Page"


class TestPutOneFileStatusCases:
    """Additional status cases for _put_one_file."""

    def test_status_local_ahead(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows Local ahead status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": "old_hash",
                    "uploaded_version": 1,
                    "images": {},
                }
            },
        )

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: Local ahead" in captured.out

    def test_status_remote_ahead(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows Remote ahead status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api
        import hashlib

        content = "# Content"
        local_hash = hashlib.sha256(content.encode()).hexdigest()

        md_file = tmp_path / "test.md"
        md_file.write_text(f"---\nconfluence: 12345\n---\n\n{content}")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 2},  # Remote is newer
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": local_hash,  # Local unchanged
                    "uploaded_version": 1,
                    "images": {},
                }
            },
        )

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: Remote ahead" in captured.out

    def test_status_in_sync(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows In sync status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api
        import hashlib

        content = "# Content"
        local_hash = hashlib.sha256(content.encode()).hexdigest()

        md_file = tmp_path / "test.md"
        md_file.write_text(f"---\nconfluence: 12345\n---\n\n{content}")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": local_hash,
                    "uploaded_version": 1,
                    "images": {},
                }
            },
        )

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: In sync" in captured.out

    def test_status_no_sync_metadata(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows No sync metadata status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: No sync metadata" in captured.out

    def test_status_conflict(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows CONFLICT status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 3},  # Remote changed
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "value": {
                    "source_hash": "old_hash",  # Local also changed
                    "uploaded_version": 2,
                    "images": {},
                }
            },
        )

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: CONFLICT" in captured.out

    def test_diff_no_differences(self, tmp_path, mock_confluence, capsys) -> None:
        """Shows no differences message."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        # Use content that when round-tripped looks similar
        md_file.write_text("---\nconfluence: 12345\n---\n\nSame content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Same content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = _put_one_file(md_file, None, None, False, False, False, True)

        assert result is True
        captured = capsys.readouterr()
        assert "no content differences" in captured.out

    def test_pull_removes_labels(self, tmp_path, mock_confluence, capsys) -> None:
        """Pull removes labels when not in remote."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text(
            "---\nconfluence: 12345\nlabels: [local-label]\n---\n\n# Content"
        )

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Remote Content</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_page_labels", lambda page_id: []
        )  # No remote labels
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        result = _put_one_file(md_file, None, None, True, False, False, False)

        assert result is True
        content = md_file.read_text()
        assert "local-label" not in content


class TestPutCommandEdgeCases:
    """Additional edge cases for put_command."""

    def test_put_create_no_parent_error(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Errors when --create used without parent available."""
        from zaira.wiki import put_command
        import argparse

        unlinked_file = tmp_path / "new.md"
        unlinked_file.write_text("# New Page")

        args = argparse.Namespace(
            files=[str(unlinked_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,  # No parent specified
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No linked files to determine parent from" in captured.err

    def test_put_create_parent_error(self, tmp_path, mock_confluence, capsys) -> None:
        """Errors when parent page info cannot be fetched."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        unlinked_file = tmp_path / "new.md"
        unlinked_file.write_text("# New Page")

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        args = argparse.Namespace(
            files=[str(unlinked_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent="invalid-parent",
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Could not get info for parent page" in captured.err

    def test_put_file_not_exists_warning(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Warns when file doesn't exist in batch."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        existing_file = tmp_path / "exists.md"
        existing_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": page_id,
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            files=[str(existing_file), str(tmp_path / "nonexistent.md")],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Warning: File not found" in captured.err

    def test_put_labels_as_string(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles labels as comma-separated string."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text(
            "---\nconfluence: 12345\nlabels: label1, label2\n---\n\n# Content"
        )

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api("add_page_labels", lambda page_id, labels: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True


class TestSyncImagesErrors:
    """Error handling for sync_images."""

    def test_upload_error(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles upload error."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"image data")

        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "upload_attachment", lambda page_id, path, filename: None
        )

        result = sync_images("12345", md_file, content, {})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Error uploading" in captured.err


class TestGetCommandEdgeCases:
    """Additional edge cases for get_command."""

    def test_get_multiple_pages_failed_export(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Continues when one page export fails."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        def mock_fetch(page_id: str, expand: str) -> object:
            if page_id == "12345":
                return None  # First page fails
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
            }

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        output_dir = tmp_path / "output"
        args = argparse.Namespace(
            pages=["12345", "67890"],
            list=False,
            children=False,
            output=str(output_dir),
            format="markdown",
        )

        get_command(args)

        captured = capsys.readouterr()
        assert "Exported 1 page(s)" in captured.out

    def test_get_page_with_labels(self, mock_confluence, capsys) -> None:
        """Gets page with labels in markdown output."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "TEST", "name": "Test Space"},
                "body": {"storage": {"value": "<p>Hello</p>"}},
            },
        )
        confluence_api.set_api("get_page_labels", lambda page_id: ["tag1", "tag2"])

        args = argparse.Namespace(
            pages=["12345"],
            list=False,
            children=False,
            output=None,
            format="markdown",
        )

        get_command(args)

        captured = capsys.readouterr()
        assert "labels:" in captured.out
        assert "tag1" in captured.out


class TestAttachCommandEdgeCases:
    """Additional edge cases for attach_command."""

    def test_attach_glob_pattern(self, tmp_path, mock_confluence, capsys) -> None:
        """Processes glob patterns."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        # Create multiple image files
        (tmp_path / "img1.png").write_bytes(b"image1")
        (tmp_path / "img2.png").write_bytes(b"image2")

        confluence_api.set_api("get_attachments", lambda page_id: {"results": []})
        confluence_api.set_api(
            "upload_attachment", lambda page_id, path, filename: {"id": "att"}
        )

        args = argparse.Namespace(
            page="12345",
            files=[str(tmp_path / "*.png")],
            replace=False,
        )

        attach_command(args)

        captured = capsys.readouterr()
        assert "Uploaded:" in captured.out


class TestCreateCommandEdgeCases:
    """Additional edge cases for create_command."""

    def test_create_parent_space_fetch_error(
        self, mock_confluence, capsys, monkeypatch
    ) -> None:
        """Errors when cannot get space from parent."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("Content"))

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "ancestors": [],
                "space": {},  # Missing key
            },
        )

        args = argparse.Namespace(
            title="New Page",
            space=None,
            parent="99999",
        )

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Could not get space" in captured.err


class TestAttachCommandNoFilesToUpload:
    """Test attach command edge case with empty files."""

    def test_attach_no_files_to_upload(self, capsys) -> None:
        """Errors when no files to upload after glob expansion."""
        from zaira.wiki import attach_command
        import argparse

        args = argparse.Namespace(
            page="12345",
            files=[],  # Empty list
            replace=False,
        )

        with pytest.raises(SystemExit) as exc_info:
            attach_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No files to upload" in captured.err


class TestPutCommandMoreCases:
    """More edge cases for put_command."""

    def test_put_create_different_parents(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Errors when linked files have different parents."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Create two linked files
        file1 = tmp_path / "file1.md"
        file1.write_text("---\nconfluence: 111\n---\n\n# Content 1")
        file2 = tmp_path / "file2.md"
        file2.write_text("---\nconfluence: 222\n---\n\n# Content 2")

        # Create unlinked file
        unlinked = tmp_path / "new.md"
        unlinked.write_text("# New Page")

        def mock_fetch(page_id: str, expand: str) -> dict[str, object]:
            parent = "parent-1" if page_id == "111" else "parent-2"
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [{"id": parent}],  # Different parents!
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            }

        confluence_api.set_api("fetch_page", mock_fetch)

        args = argparse.Namespace(
            files=[str(file1), str(file2), str(unlinked)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "different parents" in captured.err

    def test_put_create_pages_at_root(self, tmp_path, mock_confluence, capsys) -> None:
        """Errors when linked pages are at space root."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        linked = tmp_path / "linked.md"
        linked.write_text("---\nconfluence: 111\n---\n\n# Content")

        unlinked = tmp_path / "new.md"
        unlinked.write_text("# New Page")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": page_id,
                "title": "Page",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [],  # At root - no parent
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
            },
        )

        args = argparse.Namespace(
            files=[str(linked), str(unlinked)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "space root" in captured.err

    def test_put_create_no_parents_determinable(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Errors when no parents can be determined from linked files."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        linked = tmp_path / "linked.md"
        linked.write_text("---\nconfluence: 111\n---\n\n# Content")

        unlinked = tmp_path / "new.md"
        unlinked.write_text("# New Page")

        # Simulate page info fetch returning None
        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        args = argparse.Namespace(
            files=[str(linked), str(unlinked)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Could not determine parent" in captured.err

    def test_put_with_title_override(self, tmp_path, mock_confluence, capsys) -> None:
        """Uses title override when provided."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Original Title",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, "New Title", False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "title:" in captured.out

    def test_put_invalid_labels_type(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles invalid labels type."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        # Labels as a number (invalid)
        md_file.write_text("---\nconfluence: 12345\nlabels: 123\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        # Should not call add_page_labels with empty set

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True

    def test_put_glob_pattern_in_files(self, tmp_path, mock_confluence, capsys) -> None:
        """Handles glob patterns in files argument."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Create files matching pattern
        md1 = tmp_path / "file1.md"
        md1.write_text("---\nconfluence: 111\n---\n\n# Content 1")
        md2 = tmp_path / "file2.md"
        md2.write_text("---\nconfluence: 222\n---\n\n# Content 2")

        def mock_fetch(page_id: str, expand: str) -> dict[str, object]:
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            }

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            files=[str(tmp_path / "*.md")],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Processed 2 file(s)" in captured.out

    def test_put_batch_with_failures(self, tmp_path, mock_confluence, capsys) -> None:
        """Reports failures in batch mode."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md1 = tmp_path / "good.md"
        md1.write_text("---\nconfluence: 111\n---\n\n# Content")

        md2 = tmp_path / "bad.md"
        md2.write_text("---\nconfluence: 222\n---\n\n# Content")

        def mock_fetch(page_id: str, expand: str) -> object:
            if page_id == "222":
                return None  # Simulate failure
            return {
                "id": page_id,
                "title": "Page",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            }

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            files=[str(md1), str(md2)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "1 failed" in captured.out

    def test_put_create_with_parent_info(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Creates page using parent info when --parent specified."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        unlinked = tmp_path / "new.md"
        unlinked.write_text("# New Page\n\nContent")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "ancestors": [],
                "space": {"key": "FROM_PARENT"},
            },
        )
        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "99999",
                "version": {"number": 1},
            },
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        args = argparse.Namespace(
            files=[str(unlinked)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent="parent-page-id",
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Created page 99999" in captured.out


class TestPutCommandStdinMode:
    """Tests for put_command stdin mode."""

    def test_put_stdin_empty_error(self, mock_confluence, capsys, monkeypatch) -> None:
        """Errors when stdin is empty."""
        from zaira.wiki import put_command
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("   "))

        args = argparse.Namespace(
            files=None,
            body="-",
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Empty input from stdin" in captured.err

    def test_put_stdin_no_page_id_error(
        self, mock_confluence, capsys, monkeypatch
    ) -> None:
        """Errors when no page ID and no front matter."""
        from zaira.wiki import put_command
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("# Just content"))

        args = argparse.Namespace(
            files=None,
            body="-",
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No page ID" in captured.err

    def test_put_stdin_with_page_id(self, mock_confluence, capsys, monkeypatch) -> None:
        """Processes stdin with page ID from front matter."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse
        import io

        stdin_content = "---\nconfluence: 12345\n---\n\n# Content"
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_content))

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            files=None,
            body="-",
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 0

    def test_put_body_not_a_file_error(self, capsys) -> None:
        """Errors when -b argument is not a file."""
        from zaira.wiki import put_command
        import argparse

        args = argparse.Namespace(
            files=None,
            body="/nonexistent/path/to/file.md",
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Not a file" in captured.err

    def test_put_body_as_file(self, tmp_path, mock_confluence, capsys) -> None:
        """Processes -b argument as file path."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md_file = tmp_path / "input.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            files=None,
            body=str(md_file),
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "Pushed" in captured.out


class TestCreateCommandStdinMode:
    """Tests for create_command stdin mode."""

    def test_create_reads_from_stdin(
        self, mock_confluence, capsys, monkeypatch
    ) -> None:
        """Reads body from stdin."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("# Content from stdin"))

        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "12345",
                "version": {"number": 1},
            },
        )

        args = argparse.Namespace(
            title="New Page",
            body="-",
            markdown=True,
            space="TEST",
            parent=None,
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://site.atlassian.net",
        ):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out


class TestPutNoMarkdownFilesFound:
    """Test when no markdown files are found after processing."""

    def test_put_directory_no_markdown_files(self, tmp_path, capsys) -> None:
        """Errors when directory has no markdown files."""
        from zaira.wiki import put_command
        import argparse

        # Create directory with non-markdown files
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        (empty_dir / "readme.txt").write_text("Not markdown")

        args = argparse.Namespace(
            files=[str(empty_dir)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            put_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No markdown files found" in captured.err


class TestPutCreateModeFailure:
    """Test failure in create mode for unlinked files."""

    def test_put_create_unlinked_file_failure(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Reports failure when creating new page fails."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Create a linked file to get parent info
        linked = tmp_path / "linked.md"
        linked.write_text("---\nconfluence: 111\n---\n\n# Linked")

        # Create unlinked file
        unlinked = tmp_path / "new.md"
        unlinked.write_text("# New Page\n\nContent")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": page_id,
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "ancestors": [{"id": "parent-id"}],
                "body": {"storage": {"value": "<p>Old</p>"}},
                "type": "page",
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        # Make create_page fail
        confluence_api.set_api("create_page", lambda space, title, body, parent: None)

        args = argparse.Namespace(
            files=[str(linked), str(unlinked)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
            space=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "1 failed" in captured.out


class TestBuildFolderPath:
    """Tests for _build_folder_path function."""

    def test_no_ancestors(self) -> None:
        """Returns None for empty ancestors."""
        from zaira.wiki import _build_folder_path

        assert _build_folder_path([]) is None

    def test_only_homepage(self) -> None:
        """Returns None when only homepage ancestor (no folders)."""
        from zaira.wiki import _build_folder_path

        ancestors = [{"id": "1", "title": "Home", "type": "page"}]
        assert _build_folder_path(ancestors) is None

    def test_single_folder(self) -> None:
        """Returns single folder name."""
        from zaira.wiki import _build_folder_path

        ancestors = [
            {"id": "1", "title": "Home", "type": "page"},
            {"id": "2", "title": "dochub", "type": "folder"},
        ]
        assert _build_folder_path(ancestors) == "dochub"

    def test_nested_folders(self) -> None:
        """Returns slash-separated path for nested folders."""
        from zaira.wiki import _build_folder_path

        ancestors = [
            {"id": "1", "title": "Home", "type": "page"},
            {"id": "2", "title": "dochub", "type": "folder"},
            {"id": "3", "title": "docs", "type": "folder"},
        ]
        assert _build_folder_path(ancestors) == "dochub/docs"

    def test_skips_page_ancestors(self) -> None:
        """Only includes folder-type ancestors in path."""
        from zaira.wiki import _build_folder_path

        ancestors = [
            {"id": "1", "title": "Home", "type": "page"},
            {"id": "2", "title": "Some Page", "type": "page"},
            {"id": "3", "title": "my-folder", "type": "folder"},
        ]
        assert _build_folder_path(ancestors) == "my-folder"


class TestExportPageToFileWithFolders:
    """Tests for space/folder front matter in _export_page_to_file."""

    def test_exports_with_space_and_folder(self, tmp_path, mock_confluence) -> None:
        """Exports page with space: and folder: in front matter."""
        from zaira.wiki import _export_page_to_file
        from zaira import confluence_api

        page = {
            "id": "12345",
            "title": "Test Page",
            "version": {"number": 1},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "space": {"key": "ENG"},
            "ancestors": [
                {"id": "1", "title": "Home", "type": "page"},
                {"id": "2", "title": "dochub", "type": "folder"},
                {"id": "3", "title": "docs", "type": "folder"},
            ],
        }

        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _export_page_to_file(page, tmp_path)

        assert result is not None
        assert result.exists()
        # File should be in subdirectory
        assert result.parent == tmp_path / "dochub" / "docs"
        content = result.read_text()
        assert "space: ENG" in content
        assert "folder: dochub/docs" in content

    def test_exports_without_folder_at_root(self, tmp_path, mock_confluence) -> None:
        """Exports root page without folder: in front matter."""
        from zaira.wiki import _export_page_to_file
        from zaira import confluence_api

        page = {
            "id": "12345",
            "title": "Root Page",
            "version": {"number": 1},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "space": {"key": "ENG"},
            "ancestors": [
                {"id": "1", "title": "Home", "type": "page"},
            ],
        }

        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _export_page_to_file(page, tmp_path)

        assert result is not None
        assert result.parent == tmp_path
        content = result.read_text()
        assert "space: ENG" in content
        assert "folder:" not in content


class TestCreatePageFromFrontMatterFolder:
    """Tests for put --create with space:/folder: front matter."""

    def test_creates_page_with_folder_front_matter(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Creates page using space: and folder: from front matter."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md_file = tmp_path / "new-page.md"
        md_file.write_text(
            "---\ntitle: My New Page\nspace: TEST\nfolder: dochub/docs\n---\n\nContent here"
        )

        created_pages = []
        confluence_api.set_api(
            "get_space_root_folders",
            lambda space_key, limit=100: [
                {"id": "100", "title": "dochub", "type": "folder"}
            ],
        )
        confluence_api.set_api(
            "get_child_folders",
            lambda content_id, limit=100: (
                [{"id": "200", "title": "docs", "type": "folder"}]
                if content_id == "100"
                else []
            ),
        )
        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: (
                created_pages.append({"space": space, "title": title, "parent": parent})
                or {"id": "999", "version": {"number": 1}}
            ),
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        args = argparse.Namespace(
            files=[str(md_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
            space=None,
        )

        put_command(args)

        assert len(created_pages) == 1
        assert created_pages[0]["space"] == "TEST"
        assert created_pages[0]["title"] == "My New Page"
        assert created_pages[0]["parent"] == "200"

    def test_creates_missing_folders(self, tmp_path, mock_confluence, capsys) -> None:
        """Creates folders that don't exist when resolving path."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md_file = tmp_path / "deep-page.md"
        md_file.write_text(
            "---\ntitle: Deep Page\nspace: TEST\nfolder: new-folder\n---\n\nContent"
        )

        created_folders = []
        created_pages = []
        confluence_api.set_api(
            "get_space_root_folders",
            lambda space_key, limit=100: [],
        )
        confluence_api.set_api(
            "create_folder",
            lambda space, title, parent: (
                created_folders.append({"title": title})
                or {"id": "300", "title": title}
            ),
        )
        confluence_api.set_api(
            "get_child_folders",
            lambda content_id, limit=100: [],
        )
        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: (
                created_pages.append({"parent": parent})
                or {"id": "999", "version": {"number": 1}}
            ),
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        args = argparse.Namespace(
            files=[str(md_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
            space=None,
        )

        put_command(args)

        assert len(created_folders) == 1
        assert created_folders[0]["title"] == "new-folder"
        assert len(created_pages) == 1
        assert created_pages[0]["parent"] == "300"

    def test_error_without_space(self, tmp_path, mock_confluence, capsys) -> None:
        """Reports error when folder: is present but space: is missing."""
        from zaira.wiki import put_command
        import argparse

        md_file = tmp_path / "no-space.md"
        md_file.write_text("---\ntitle: No Space\nfolder: some-folder\n---\n\nContent")

        args = argparse.Namespace(
            files=[str(md_file)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=True,
            parent=None,
            space=None,
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "no 'space:'" in captured.err

    def test_title_from_front_matter(self, tmp_path, mock_confluence, capsys) -> None:
        """Uses title from front matter over heading and filename."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "ugly-filename.md"
        md_file.write_text("---\ntitle: Nice Title\n---\n\n# Heading Title\n\nContent")

        created_titles = []
        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: (
                created_titles.append(title) or {"id": "999", "version": {"number": 1}}
            ),
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        _create_page_for_file(md_file, "parent-id", "TEST")

        assert created_titles[0] == "Nice Title"


class TestGetCommandFolderFrontMatter:
    """Tests for space:/folder: in get command output."""

    def test_get_single_page_includes_space_and_folder(
        self, mock_confluence, capsys
    ) -> None:
        """Single page stdout includes space: and folder: in front matter."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": page_id,
                "title": "Nested Page",
                "version": {"number": 1},
                "space": {"key": "ENG", "name": "Engineering"},
                "ancestors": [
                    {"id": "1", "title": "Home", "type": "page"},
                    {"id": "2", "title": "projects", "type": "folder"},
                ],
                "body": {"storage": {"value": "<p>Hello</p>"}},
            },
        )
        confluence_api.set_api("get_page_labels", lambda page_id: [])

        args = argparse.Namespace(
            pages=["12345"],
            output=None,
            children=False,
            list=False,
            format="md",
        )

        get_command(args)

        captured = capsys.readouterr()
        assert "space: ENG" in captured.out
        assert "folder: projects" in captured.out

    def test_get_root_page_no_folder(self, mock_confluence, capsys) -> None:
        """Root page has space: but no folder: in front matter."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": page_id,
                "title": "Root Page",
                "version": {"number": 1},
                "space": {"key": "ENG", "name": "Engineering"},
                "ancestors": [
                    {"id": "1", "title": "Home", "type": "page"},
                ],
                "body": {"storage": {"value": "<p>Hello</p>"}},
            },
        )
        confluence_api.set_api("get_page_labels", lambda page_id: [])

        args = argparse.Namespace(
            pages=["12345"],
            output=None,
            children=False,
            list=False,
            format="md",
        )

        get_command(args)

        captured = capsys.readouterr()
        assert "space: ENG" in captured.out
        assert "folder:" not in captured.out


class TestPullWithFolderFrontMatter:
    """Tests for --pull populating space:/folder: in front matter."""

    def test_pull_adds_space_and_folder(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Pull updates front matter with space: and folder:."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "page.md"
        md_file.write_text("---\nconfluence: 12345\ntitle: Old\n---\n\nOld content")

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": page_id,
                "title": "Updated Title",
                "version": {"number": 3},
                "space": {"key": "ENG"},
                "ancestors": [
                    {"id": "1", "title": "Home", "type": "page"},
                    {"id": "2", "title": "engineering", "type": "folder"},
                    {"id": "3", "title": "specs", "type": "folder"},
                ],
                "body": {"storage": {"value": "<p>New content</p>"}},
            },
        )
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )

        _put_one_file(md_file, None, None, pull=True, force=False, status=False)

        content = md_file.read_text()
        assert "space: ENG" in content
        assert "folder: engineering/specs" in content
        assert "title: Updated Title" in content


class TestLsCommand:
    """Tests for wiki ls command."""

    def test_ls_shows_folders_and_pages(self, mock_confluence, capsys) -> None:
        """Lists folders and pages in a space."""
        from zaira.wiki import ls_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "get_space_root_pages",
            lambda space_key, limit=100: [
                {"id": "1", "title": "Homepage", "type": "page"},
            ],
        )
        confluence_api.set_api(
            "get_space_root_folders",
            lambda space_key, limit=100: [
                {"id": "10", "title": "docs", "type": "folder"},
            ],
        )
        confluence_api.set_api("get_child_folders", lambda cid, limit=100: [])
        confluence_api.set_api("get_child_pages", lambda cid, limit=100: [])

        args = argparse.Namespace(space="TEST", depth=0)

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://example.atlassian.net",
        ):
            ls_command(args)

        captured = capsys.readouterr()
        assert "[folder] docs" in captured.out
        assert "Homepage" in captured.out

    def test_ls_parses_url(self, mock_confluence, capsys) -> None:
        """Parses space key from URL."""
        from zaira.wiki import ls_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "get_space_root_pages",
            lambda space_key, limit=100: [
                {"id": "1", "title": "Home", "type": "page"},
            ],
        )
        confluence_api.set_api(
            "get_space_root_folders", lambda space_key, limit=100: []
        )
        confluence_api.set_api("get_child_folders", lambda cid, limit=100: [])
        confluence_api.set_api("get_child_pages", lambda cid, limit=100: [])

        args = argparse.Namespace(
            space="https://example.atlassian.net/wiki/spaces/ENG/overview",
            depth=0,
        )

        with patch(
            "zaira.wiki.get_server_from_config",
            return_value="https://example.atlassian.net",
        ):
            ls_command(args)

        captured = capsys.readouterr()
        assert "Home" in captured.out

    def test_ls_empty_space(self, mock_confluence, capsys) -> None:
        """Exits with error for empty space."""
        from zaira.wiki import ls_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("get_space_root_pages", lambda space_key, limit=100: [])
        confluence_api.set_api(
            "get_space_root_folders", lambda space_key, limit=100: []
        )

        args = argparse.Namespace(space="EMPTY", depth=1)

        with pytest.raises(SystemExit):
            ls_command(args)


class TestPutMovesFolder:
    """Tests for wiki put moving pages when folder: changes."""

    def test_put_moves_page_to_new_folder(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Moves page when local folder: differs from remote ancestors."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text(
            "---\nconfluence: 12345\nspace: TEST\nfolder: new-folder\n---\n\nContent"
        )

        move_calls = []
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
                "ancestors": [
                    {"id": "1", "title": "Home", "type": "page"},
                    {"id": "2", "title": "old-folder", "type": "folder"},
                ],
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "resolve_folder_path",
            lambda space_key, folder_path, create_missing: "300",
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key=None, parent_id=None: (
                move_calls.append({"parent_id": parent_id})
                or {"version": {"number": 2}}
            ),
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 3}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        assert len(move_calls) == 1
        assert move_calls[0]["parent_id"] == "300"

    def test_put_no_move_when_folder_unchanged(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Does not move page when folder: matches remote."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text(
            "---\nconfluence: 12345\nspace: TEST\nfolder: my-folder\n---\n\nContent"
        )

        move_calls = []
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
                "ancestors": [
                    {"id": "1", "title": "Home", "type": "page"},
                    {"id": "2", "title": "my-folder", "type": "folder"},
                ],
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key=None, parent_id=None: (
                move_calls.append(True) or {"version": {"number": 2}}
            ),
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 2}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        assert len(move_calls) == 0

    def test_put_moves_page_to_root(self, tmp_path, mock_confluence, capsys) -> None:
        """Moves page to space root when folder: is removed."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\nspace: TEST\n---\n\nContent")

        move_calls = []
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
                "type": "page",
                "ancestors": [
                    {"id": "1", "title": "Home", "type": "page"},
                    {"id": "2", "title": "old-folder", "type": "folder"},
                ],
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "get_attachments", lambda page_id, expand: {"results": []}
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key=None, parent_id=None: (
                move_calls.append({"parent_id": parent_id})
                or {"version": {"number": 2}}
            ),
        )
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, ptype: {"version": {"number": 3}},
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        assert len(move_calls) == 1
        assert move_calls[0]["parent_id"] is None


class TestEditParentFolderPath:
    """Tests for wiki edit --parent with folder paths."""

    def test_edit_parent_with_folder_path(self, mock_confluence, capsys) -> None:
        """Resolves folder path for --parent."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        update_calls = []
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "ENG"},
                "ancestors": [{"id": "1", "title": "Home", "type": "page"}],
            },
        )
        confluence_api.set_api(
            "resolve_folder_path",
            lambda space_key, folder_path, create_missing: "500",
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key=None, parent_id=None: (
                update_calls.append({"parent_id": parent_id}) or True
            ),
        )

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent="guides/api",
            space=None,
            labels=None,
        )

        edit_command(args)

        assert len(update_calls) == 1
        assert update_calls[0]["parent_id"] == "500"

    def test_edit_parent_folder_path_not_found(self, mock_confluence, capsys) -> None:
        """Errors when folder path cannot be resolved."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "ENG"},
                "ancestors": [{"id": "1", "title": "Home", "type": "page"}],
            },
        )
        confluence_api.set_api(
            "resolve_folder_path",
            lambda space_key, folder_path, create_missing: None,
        )

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent="nonexistent/path",
            space=None,
            labels=None,
        )

        with pytest.raises(SystemExit):
            edit_command(args)

        captured = capsys.readouterr()
        assert "Could not resolve folder path" in captured.err

    def test_edit_parent_folder_uses_target_space(
        self, mock_confluence, capsys
    ) -> None:
        """Uses --space for folder resolution when provided."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        resolve_calls = []
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "title": "Test Page",
                "version": {"number": 1},
                "space": {"key": "OLD"},
                "ancestors": [{"id": "1", "title": "Home", "type": "page"}],
            },
        )
        confluence_api.set_api(
            "resolve_folder_path",
            lambda space_key, folder_path, create_missing: (
                resolve_calls.append(space_key) or "600"
            ),
        )
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, ptype, title, space_key=None, parent_id=None: True,
        )

        args = argparse.Namespace(
            page="12345",
            title=None,
            parent="docs/api",
            space="NEW",
            labels=None,
        )

        edit_command(args)

        assert resolve_calls[0] == "NEW"


class TestMirrorPreprocessing:
    """Tests for --mirror flag preprocessing in put_command."""

    def test_mirror_derives_folder_from_relative_path(self, tmp_path) -> None:
        """Mirror sets folder: based on file's relative path to input directory."""
        # Create nested structure
        sub = tmp_path / "team" / "backend"
        sub.mkdir(parents=True)
        f = sub / "design.md"
        f.write_text("---\ntitle: Design\n---\n\n# Design doc\n")

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
            space="ENG",
            mirror=True,
        )

        # Run put_command — it will preprocess then fail on API calls, so we
        # mock the rest and just check the file was rewritten.
        with (
            patch("zaira.wiki._put_one_file"),
            patch("zaira.wiki._create_page_for_file"),
            patch("zaira.wiki._get_page_info"),
            patch(
                "zaira.wiki._resolve_parent_from_front_matter",
                return_value=("parent_id", "ENG"),
            ),
        ):
            try:
                put_command(args)
            except SystemExit:
                pass

        content = f.read_text()
        fm, _ = parse_front_matter(content)
        assert fm["space"] == "ENG"
        assert fm["folder"] == "team/backend"

    def test_mirror_with_parent_uses_relative_folder(self, tmp_path) -> None:
        """Mirror with --parent stores relative folder path (parent is used during resolution)."""
        sub = tmp_path / "api"
        sub.mkdir()
        f = sub / "endpoints.md"
        f.write_text("---\ntitle: Endpoints\n---\n\n# Endpoints\n")

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent="12345",  # Now treated as parent folder ID
            space="ENG",
            mirror=True,
            prefix=None,
        )

        with (
            patch("zaira.wiki._put_one_file"),
            patch("zaira.wiki._create_page_for_file"),
            patch("zaira.wiki._get_page_info"),
            patch(
                "zaira.wiki._resolve_parent_from_front_matter",
                return_value=("pid", "ENG"),
            ),
        ):
            try:
                put_command(args)
            except SystemExit:
                pass

        content = f.read_text()
        fm, _ = parse_front_matter(content)
        # With new behavior, folder is just the relative path (parent ID used during resolution)
        assert fm["folder"] == "api"

    def test_mirror_root_files_get_no_folder(self, tmp_path) -> None:
        """Files at root of input dir get no folder: set."""
        f = tmp_path / "readme.md"
        f.write_text("---\ntitle: Readme\n---\n\n# Readme\n")

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
            space="ENG",
            mirror=True,
        )

        with (
            patch("zaira.wiki._put_one_file"),
            patch("zaira.wiki._create_page_for_file"),
            patch("zaira.wiki._get_page_info"),
            patch(
                "zaira.wiki._resolve_parent_from_front_matter",
                return_value=("pid", "ENG"),
            ),
        ):
            try:
                put_command(args)
            except SystemExit:
                pass

        content = f.read_text()
        fm, _ = parse_front_matter(content)
        assert fm["space"] == "ENG"
        assert "folder" not in fm

    def test_mirror_linked_files_get_updated_folder(self, tmp_path) -> None:
        """Already-linked files get folder: updated (triggers move on push)."""
        sub = tmp_path / "new-location"
        sub.mkdir()
        f = sub / "page.md"
        f.write_text("---\ntitle: Page\nconfluence: 99999\n---\n\n# Page\n")

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
            space="ENG",
            mirror=True,
        )

        with (
            patch("zaira.wiki._put_one_file", return_value=True),
            patch("zaira.wiki._create_page_for_file"),
            patch("zaira.wiki._get_page_info"),
            patch(
                "zaira.wiki._resolve_parent_from_front_matter",
                return_value=("pid", "ENG"),
            ),
        ):
            try:
                put_command(args)
            except SystemExit:
                pass

        content = f.read_text()
        fm, _ = parse_front_matter(content)
        assert fm["folder"] == "new-location"
        assert fm["space"] == "ENG"

    def test_mirror_without_space_errors(self, tmp_path) -> None:
        """--mirror without --space errors when files lack space:."""
        f = tmp_path / "page.md"
        f.write_text("---\ntitle: Page\n---\n\n# Page\n")

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
            space=None,
            mirror=True,
        )

        with pytest.raises(SystemExit):
            put_command(args)

    def test_mirror_recursive_glob(self, tmp_path) -> None:
        """Mirror picks up nested files via rglob."""
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "top.md").write_text("---\ntitle: Top\n---\n\nTop\n")
        (tmp_path / "a" / "mid.md").write_text("---\ntitle: Mid\n---\n\nMid\n")
        (tmp_path / "a" / "b" / "deep.md").write_text("---\ntitle: Deep\n---\n\nDeep\n")

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent=None,
            space="ENG",
            mirror=True,
        )

        with (
            patch("zaira.wiki._put_one_file"),
            patch("zaira.wiki._create_page_for_file"),
            patch("zaira.wiki._get_page_info"),
            patch(
                "zaira.wiki._resolve_parent_from_front_matter",
                return_value=("pid", "ENG"),
            ),
        ):
            try:
                put_command(args)
            except SystemExit:
                pass

        # Check all three files were found and processed
        top_fm, _ = parse_front_matter((tmp_path / "top.md").read_text())
        mid_fm, _ = parse_front_matter((tmp_path / "a" / "mid.md").read_text())
        deep_fm, _ = parse_front_matter((tmp_path / "a" / "b" / "deep.md").read_text())

        assert top_fm["space"] == "ENG"
        assert "folder" not in top_fm
        assert mid_fm["folder"] == "a"
        assert deep_fm["folder"] == "a/b"

    def test_mirror_root_with_parent_no_folder(self, tmp_path) -> None:
        """Root files with --parent don't get folder in front matter (parent ID used during resolution)."""
        f = tmp_path / "page.md"
        f.write_text("---\ntitle: Page\n---\n\n# Page\n")

        args = argparse.Namespace(
            files=[str(tmp_path)],
            body=None,
            page=None,
            title=None,
            pull=False,
            force=False,
            status=False,
            diff=False,
            create=False,
            parent="12345",  # Now treated as parent folder ID
            space="ENG",
            mirror=True,
            prefix=None,
        )

        with (
            patch("zaira.wiki._put_one_file"),
            patch("zaira.wiki._create_page_for_file"),
            patch("zaira.wiki._get_page_info"),
            patch(
                "zaira.wiki._resolve_parent_from_front_matter",
                return_value=("pid", "ENG"),
            ),
        ):
            try:
                put_command(args)
            except SystemExit:
                pass

        content = f.read_text()
        fm, _ = parse_front_matter(content)
        # With new behavior, root files don't get folder (parent ID used during resolution)
        assert "folder" not in fm


class TestResolveParentFromFrontMatter:
    """Tests for _resolve_parent_from_front_matter function."""

    def test_returns_mirror_parent_when_no_folder(
        self, tmp_path, mock_confluence
    ) -> None:
        """Returns mirror_parent_id when file has no folder in front matter."""
        from zaira.wiki import _resolve_parent_from_front_matter

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nspace: ENG\n---\n\n# Content\n")

        parent_id, space = _resolve_parent_from_front_matter(
            md_file, mirror_parent_id="parent-123"
        )

        assert parent_id == "parent-123"
        assert space == "ENG"

    def test_returns_none_parent_when_no_folder_no_mirror(
        self, tmp_path, mock_confluence
    ) -> None:
        """Returns None parent when no folder and no mirror_parent_id."""
        from zaira.wiki import _resolve_parent_from_front_matter

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nspace: ENG\n---\n\n# Content\n")

        parent_id, space = _resolve_parent_from_front_matter(md_file)

        assert parent_id is None
        assert space == "ENG"

    def test_applies_name_prefix_to_folder_segments(
        self, tmp_path, mock_confluence
    ) -> None:
        """Applies name_prefix to each folder segment."""
        from zaira.wiki import _resolve_parent_from_front_matter
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nspace: ENG\nfolder: api/v2\n---\n\n# Content\n")

        resolve_calls = []

        def mock_resolve(space: str, path: str, create: bool) -> str:
            resolve_calls.append((space, path, create))
            return "resolved-id"

        confluence_api.set_api("resolve_folder_path", mock_resolve)

        parent_id, space = _resolve_parent_from_front_matter(
            md_file, name_prefix="Demo - "
        )

        assert parent_id == "resolved-id"
        assert space == "ENG"
        assert len(resolve_calls) == 1
        assert resolve_calls[0][1] == "Demo - api/Demo - v2"

    def test_uses_resolve_folder_path_from_parent_with_mirror(
        self, tmp_path, mock_confluence
    ) -> None:
        """Uses resolve_folder_path_from_parent when mirror_parent_id is set."""
        from zaira.wiki import _resolve_parent_from_front_matter
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nspace: ENG\nfolder: sub\n---\n\n# Content\n")

        resolve_calls = []

        def mock_resolve_from_parent(
            space: str, parent: str | None, path: str, create: bool
        ) -> str:
            resolve_calls.append((space, parent, path, create))
            return "resolved-id"

        confluence_api.set_api(
            "resolve_folder_path_from_parent", mock_resolve_from_parent
        )

        parent_id, space = _resolve_parent_from_front_matter(
            md_file, mirror_parent_id="parent-123"
        )

        assert parent_id == "resolved-id"
        assert len(resolve_calls) == 1
        assert resolve_calls[0][0] == "ENG"
        assert resolve_calls[0][1] == "parent-123"
        assert resolve_calls[0][2] == "sub"
        assert resolve_calls[0][3] is True

    def test_combines_mirror_parent_and_prefix(self, tmp_path, mock_confluence) -> None:
        """Combines mirror_parent_id and name_prefix correctly."""
        from zaira.wiki import _resolve_parent_from_front_matter
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nspace: ENG\nfolder: docs/api\n---\n\n# Content\n")

        resolve_calls = []

        def mock_resolve_from_parent(
            space: str, parent: str | None, path: str, create: bool
        ) -> str:
            resolve_calls.append((space, parent, path, create))
            return "resolved-id"

        confluence_api.set_api(
            "resolve_folder_path_from_parent", mock_resolve_from_parent
        )

        parent_id, space = _resolve_parent_from_front_matter(
            md_file, mirror_parent_id="parent-123", name_prefix="Test - "
        )

        assert parent_id == "resolved-id"
        # Should apply prefix to each segment
        assert resolve_calls[0][2] == "Test - docs/Test - api"

    def test_returns_none_when_no_space(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Returns None, None when no space in front matter or default."""
        from zaira.wiki import _resolve_parent_from_front_matter

        md_file = tmp_path / "test.md"
        md_file.write_text("---\ntitle: Test\n---\n\n# Content\n")

        parent_id, space = _resolve_parent_from_front_matter(md_file)

        assert parent_id is None
        assert space is None
        captured = capsys.readouterr()
        assert "has no 'space:'" in captured.err

    def test_uses_default_space_when_not_in_front_matter(
        self, tmp_path, mock_confluence
    ) -> None:
        """Uses default_space when not specified in front matter."""
        from zaira.wiki import _resolve_parent_from_front_matter

        md_file = tmp_path / "test.md"
        md_file.write_text("---\ntitle: Test\n---\n\n# Content\n")

        parent_id, space = _resolve_parent_from_front_matter(
            md_file, default_space="DEFAULT"
        )

        assert space == "DEFAULT"

    def test_returns_none_when_folder_resolution_fails(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Returns None, None when folder resolution fails."""
        from zaira.wiki import _resolve_parent_from_front_matter
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nspace: ENG\nfolder: nonexistent\n---\n\n# Content\n")

        confluence_api.set_api("resolve_folder_path", lambda s, p, c: None)

        parent_id, space = _resolve_parent_from_front_matter(md_file)

        assert parent_id is None
        assert space is None
        captured = capsys.readouterr()
        assert "Could not resolve folder path" in captured.err


class TestAppendSectionSlug:
    """Tests for _append_section_slug function."""

    def test_simple_id_unchanged(self) -> None:
        from zaira.wiki import _append_section_slug

        assert _append_section_slug("ci-status") == "ci-status"

    def test_sanitizes_special_characters(self) -> None:
        from zaira.wiki import _append_section_slug

        assert _append_section_slug("CI Status: build#42") == "CI-Status-build-42"

    def test_empty_falls_back_to_default(self) -> None:
        from zaira.wiki import _append_section_slug

        assert _append_section_slug("   ") == "default"


class TestAppendCommand:
    """Tests for append_command function."""

    def _args(
        self,
        tmp_path: Path,
        content: str,
        page: str | None = "12345",
        section: str | None = None,
        raw: bool = False,
        use_stdin: bool = False,
    ) -> argparse.Namespace:
        if use_stdin:
            file_arg = "-"
        else:
            f = tmp_path / "append.md"
            f.write_text(content)
            file_arg = str(f)
        return argparse.Namespace(page=page, section=section, file=file_arg, raw=raw)

    def test_appends_when_no_previous_property(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """First run appends to end of body and records the property."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "type": "page",
                "version": {"number": 3},
                "body": {"storage": {"value": "<p>Existing</p>"}},
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        update_calls = []

        def fake_update(
            page_id: str, title: str, body: str, version: int, page_type: str
        ) -> dict[str, object]:
            update_calls.append((page_id, title, body, version, page_type))
            return {"version": {"number": version + 1}}

        confluence_api.set_api("update_page", fake_update)

        set_calls = []
        confluence_api.set_api(
            "set_page_property",
            lambda page_id, key, value: set_calls.append((page_id, key, value)) or True,
        )

        args = self._args(tmp_path, "New content", section="ci-status", raw=True)
        append_command(args)

        assert len(update_calls) == 1
        _, _, body, version, _ = update_calls[0]
        assert body == "<p>Existing</p>New content"
        assert version == 3

        assert set_calls[0][1] == "zaira-append-ci-status"
        assert set_calls[0][2] == {"content": "New content"}

        captured = capsys.readouterr()
        assert (
            "Appended section 'ci-status' on page 12345 (version 3 -> 4)"
            in captured.out
        )

    def test_replaces_previous_block_in_place(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Replaces the previously tracked block instead of duplicating."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "type": "page",
                "version": {"number": 5},
                "body": {"storage": {"value": "<p>Before</p>OLD BLOCK<p>After</p>"}},
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {"value": {"content": "OLD BLOCK"}},
        )

        update_calls = []

        def fake_update(
            page_id: str, title: str, body: str, version: int, page_type: str
        ) -> dict[str, object]:
            update_calls.append(body)
            return {"version": {"number": version + 1}}

        confluence_api.set_api("update_page", fake_update)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = self._args(tmp_path, "NEW BLOCK", section="ci-status", raw=True)
        append_command(args)

        assert update_calls[0] == "<p>Before</p>NEW BLOCK<p>After</p>"
        captured = capsys.readouterr()
        assert "Replaced section 'ci-status'" in captured.out

    def test_falls_back_to_append_when_previous_block_edited_away(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """If tracked block no longer matches remote content, appends instead."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "type": "page",
                "version": {"number": 5},
                "body": {"storage": {"value": "<p>Manually edited</p>"}},
            },
        )
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {"value": {"content": "OLD BLOCK"}},
        )

        update_calls = []

        def fake_update(
            page_id: str, title: str, body: str, version: int, page_type: str
        ) -> dict[str, object]:
            update_calls.append(body)
            return {"version": {"number": version + 1}}

        confluence_api.set_api("update_page", fake_update)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = self._args(tmp_path, "NEW BLOCK", section="ci-status", raw=True)
        append_command(args)

        assert update_calls[0] == "<p>Manually edited</p>NEW BLOCK"
        captured = capsys.readouterr()
        assert "Appended section 'ci-status'" in captured.out

    def test_markdown_conversion_applied_without_raw(
        self, tmp_path, mock_confluence
    ) -> None:
        """Content is converted from markdown to storage format unless --raw."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "type": "page",
                "version": {"number": 1},
                "body": {"storage": {"value": ""}},
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        update_calls = []

        def fake_update(
            page_id: str, title: str, body: str, version: int, page_type: str
        ) -> dict[str, object]:
            update_calls.append(body)
            return {"version": {"number": version + 1}}

        confluence_api.set_api("update_page", fake_update)
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = self._args(tmp_path, "Hello world", raw=False)
        append_command(args)

        assert update_calls[0] == "<p>Hello world</p>"

    def test_reads_content_from_stdin(
        self, tmp_path, mock_confluence, monkeypatch
    ) -> None:
        """Reads content from stdin when file is '-'."""
        import io
        from zaira.wiki import append_command
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "type": "page",
                "version": {"number": 1},
                "body": {"storage": {"value": ""}},
            },
        )
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, page_type: {
                "version": {"number": version + 1}
            },
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        monkeypatch.setattr("sys.stdin", io.StringIO("Stdin content"))

        args = self._args(tmp_path, "", raw=True, use_stdin=True)
        append_command(args)

    def test_errors_on_missing_file(self, tmp_path, capsys) -> None:
        """Errors and exits when file does not exist."""
        from zaira.wiki import append_command

        args = argparse.Namespace(
            page="12345",
            section="ci-status",
            file=str(tmp_path / "missing.md"),
            raw=True,
        )

        with pytest.raises(SystemExit):
            append_command(args)

        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_errors_on_empty_content(self, tmp_path, mock_confluence, capsys) -> None:
        """Errors and exits when content is empty/whitespace."""
        from zaira.wiki import append_command

        f = tmp_path / "empty.md"
        f.write_text("   ")

        args = argparse.Namespace(
            page="12345", section="ci-status", file=str(f), raw=True
        )

        with pytest.raises(SystemExit):
            append_command(args)

        captured = capsys.readouterr()
        assert "empty content" in captured.err

    def test_errors_when_page_fetch_fails(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Errors and exits when the page cannot be fetched."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        args = self._args(tmp_path, "content", raw=True)

        with pytest.raises(SystemExit):
            append_command(args)

        captured = capsys.readouterr()
        assert "Error fetching page" in captured.err

    def test_accepts_page_url(self, tmp_path, mock_confluence) -> None:
        """Resolves a page URL to its numeric id via parse_page_id."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        seen_page_ids = []

        def fake_fetch(page_id: str, expand: str) -> dict[str, object]:
            seen_page_ids.append(page_id)
            return {
                "id": page_id,
                "title": "Test",
                "type": "page",
                "version": {"number": 1},
                "body": {"storage": {"value": ""}},
            }

        confluence_api.set_api("fetch_page", fake_fetch)
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, page_type: {
                "version": {"number": version + 1}
            },
        )
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = self._args(
            tmp_path,
            "content",
            page="https://example.atlassian.net/wiki/spaces/SPACE/pages/98765/Title",
            raw=True,
        )
        append_command(args)

        assert seen_page_ids == ["98765"]

    def test_plain_append_without_section_skips_property_tracking(
        self, tmp_path, mock_confluence, capsys
    ) -> None:
        """Without --section, always appends and never touches page properties."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "type": "page",
                "version": {"number": 3},
                "body": {"storage": {"value": "<p>Existing</p>"}},
            },
        )

        def fail_get(page_id: str, key: str) -> NoReturn:
            raise AssertionError("get_page_property should not be called")

        def fail_set(page_id: str, key: str, value: object) -> NoReturn:
            raise AssertionError("set_page_property should not be called")

        confluence_api.set_api("get_page_property", fail_get)
        confluence_api.set_api("set_page_property", fail_set)

        update_calls = []

        def fake_update(
            page_id: str, title: str, body: str, version: int, page_type: str
        ) -> dict[str, object]:
            update_calls.append(body)
            return {"version": {"number": version + 1}}

        confluence_api.set_api("update_page", fake_update)

        args = self._args(tmp_path, "New content", raw=True)
        append_command(args)

        assert update_calls[0] == "<p>Existing</p>New content"
        captured = capsys.readouterr()
        assert "Appended to page 12345 (version 3 -> 4)" in captured.out

    def test_plain_append_duplicates_on_rerun(self, tmp_path, mock_confluence) -> None:
        """Without --section, re-running duplicates content instead of replacing it."""
        from zaira.wiki import append_command
        from zaira import confluence_api

        body_state = {"value": "<p>Existing</p>"}

        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {
                "id": "12345",
                "title": "Test",
                "type": "page",
                "version": {"number": 1},
                "body": {"storage": {"value": body_state["value"]}},
            },
        )

        def fake_update(
            page_id: str, title: str, body: str, version: int, page_type: str
        ) -> dict[str, object]:
            body_state["value"] = body
            return {"version": {"number": version + 1}}

        confluence_api.set_api("update_page", fake_update)

        append_command(self._args(tmp_path, "Same block", raw=True))
        append_command(self._args(tmp_path, "Same block", raw=True))

        assert body_state["value"] == "<p>Existing</p>Same blockSame block"
