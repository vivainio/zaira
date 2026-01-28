"""Tests for wiki module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from zaira.wiki import (
    parse_front_matter,
    write_front_matter,
    parse_page_id,
    slugify,
    compute_file_hash,
    get_sync_property,
    set_sync_property,
    check_images_changed,
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


class TestSlugifyEdgeCases:
    """Additional edge cases for slugify function."""

    def test_all_special_chars(self):
        """Handles string of only special characters."""
        result = slugify("!@#$%^&*()")
        assert result == ""

    def test_mixed_unicode_ascii(self):
        """Handles mixed unicode and ASCII."""
        result = slugify("Test Seite")
        assert "test" in result
        assert "seite" in result

    def test_multiple_spaces_and_hyphens(self):
        """Collapses multiple spaces and hyphens."""
        assert slugify("a   -   b") == "a-b"
        assert slugify("test--case") == "test-case"


class TestParsePageIdEdgeCases:
    """Additional edge cases for parse_page_id."""

    def test_url_with_trailing_slash(self):
        """Handles URL with trailing slash."""
        url = "https://site.atlassian.net/wiki/spaces/SPACE/pages/123456/"
        assert parse_page_id(url) == "123456"

    def test_url_with_query_params(self):
        """Handles URL with query parameters."""
        url = "https://site.atlassian.net/wiki/spaces/SPACE/pages/123456?param=value"
        assert parse_page_id(url) == "123456"

    def test_url_must_have_lowercase_pages(self):
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

    def test_nested_dict_values(self):
        """Handles nested dict values."""
        fm = {"meta": {"key": "value"}}
        body = "Content"

        result = write_front_matter(fm, body)

        assert "meta:" in result
        assert "key:" in result

    def test_numeric_values(self):
        """Handles numeric values."""
        fm = {"page_id": 12345, "version": 3.14}
        body = "Content"

        result = write_front_matter(fm, body)

        assert "12345" in result
        assert "3.14" in result

    def test_boolean_values(self):
        """Handles boolean values."""
        fm = {"draft": True, "published": False}
        body = "Content"

        result = write_front_matter(fm, body)

        assert "true" in result.lower()
        assert "false" in result.lower()


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_computes_sha256(self, tmp_path):
        """Computes SHA256 hash of file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = compute_file_hash(test_file)

        # SHA256 hash is 64 hex characters
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_content_same_hash(self, tmp_path):
        """Same content produces same hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("identical content")
        file2.write_text("identical content")

        assert compute_file_hash(file1) == compute_file_hash(file2)

    def test_different_content_different_hash(self, tmp_path):
        """Different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content one")
        file2.write_text("content two")

        assert compute_file_hash(file1) != compute_file_hash(file2)


class TestGetSyncProperty:
    """Tests for get_sync_property function."""

    def test_returns_property_value(self, mock_confluence):
        """Returns value from property."""
        from zaira import confluence_api

        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {"value": {"source_hash": "abc123"}}
        )

        result = get_sync_property("12345")

        assert result == {"source_hash": "abc123"}

    def test_returns_none_when_not_found(self, mock_confluence):
        """Returns None when property not found."""
        from zaira import confluence_api

        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = get_sync_property("12345")

        assert result is None


class TestSetSyncProperty:
    """Tests for set_sync_property function."""

    def test_sets_property(self, mock_confluence):
        """Sets property and returns True."""
        from zaira import confluence_api

        called_with = {}

        def mock_set(page_id, key, value):
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

    def test_returns_false_no_images(self, tmp_path):
        """Returns False when no images in content."""
        md_file = tmp_path / "test.md"
        md_file.write_text("No images here")

        result = check_images_changed(md_file, "No images here", {})

        assert result is False

    def test_returns_true_for_new_image(self, tmp_path):
        """Returns True when image not in stored hashes."""
        # Create markdown file with image reference
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"

        # Create the image file
        (tmp_path / "image.png").write_bytes(b"image data")

        result = check_images_changed(md_file, content, {})

        assert result is True

    def test_returns_false_for_unchanged_image(self, tmp_path):
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

    def test_returns_true_for_changed_image(self, tmp_path):
        """Returns True when image hash differs from stored."""
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"

        # Create image file
        (tmp_path / "image.png").write_bytes(b"new data")

        result = check_images_changed(md_file, content, {"image.png": "old_hash"})

        assert result is True

    def test_skips_missing_images(self, tmp_path):
        """Skips images that don't exist."""
        md_file = tmp_path / "test.md"
        content = "![Alt](./missing.png)"

        # Don't create the image file

        result = check_images_changed(md_file, content, {})

        assert result is False


class TestGetChildren:
    """Tests for _get_children function."""

    def test_returns_empty_for_no_children(self, mock_confluence):
        """Returns empty list when page has no children."""
        from zaira.wiki import _get_children
        from zaira import confluence_api

        confluence_api.set_api("get_child_pages", lambda page_id, limit: [])

        result = _get_children("12345")

        assert result == []

    def test_returns_child_ids(self, mock_confluence):
        """Returns list of child page IDs."""
        from zaira.wiki import _get_children
        from zaira import confluence_api

        def mock_get_children(page_id, limit):
            if page_id == "12345":
                return [{"id": "111"}, {"id": "222"}]
            return []

        confluence_api.set_api("get_child_pages", mock_get_children)

        result = _get_children("12345")

        assert result == ["111", "222"]

    def test_returns_nested_children(self, mock_confluence):
        """Recursively fetches nested children."""
        from zaira.wiki import _get_children
        from zaira import confluence_api

        def mock_get_children(page_id, limit):
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

    def test_returns_page_dict(self, mock_confluence):
        """Returns page dict on success."""
        from zaira.wiki import _fetch_page
        from zaira import confluence_api

        page_data = {"id": "12345", "title": "Test", "body": {"storage": {"value": ""}}}
        confluence_api.set_api("fetch_page", lambda page_id, expand: page_data)

        result = _fetch_page("12345")

        assert result == page_data

    def test_returns_none_on_error(self, mock_confluence, capsys):
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

    def test_returns_labels(self, mock_confluence):
        """Returns list of labels."""
        from zaira.wiki import _fetch_labels
        from zaira import confluence_api

        confluence_api.set_api("get_page_labels", lambda page_id: ["label1", "label2"])

        result = _fetch_labels("12345")

        assert result == ["label1", "label2"]


class TestGetPageInfo:
    """Tests for _get_page_info function."""

    def test_returns_page_info(self, mock_confluence):
        """Returns parent_id and space_key."""
        from zaira.wiki import _get_page_info
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "ancestors": [{"id": "111"}, {"id": "222"}],
            "space": {"key": "TEST"}
        })

        result = _get_page_info("12345")

        assert result == {"parent_id": "222", "space_key": "TEST"}

    def test_returns_none_on_error(self, mock_confluence):
        """Returns None when page not found."""
        from zaira.wiki import _get_page_info
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        result = _get_page_info("12345")

        assert result is None

    def test_returns_none_parent_at_root(self, mock_confluence):
        """Returns None parent_id when page is at space root."""
        from zaira.wiki import _get_page_info
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "ancestors": [],
            "space": {"key": "TEST"}
        })

        result = _get_page_info("12345")

        assert result == {"parent_id": None, "space_key": "TEST"}


class TestSyncImages:
    """Tests for sync_images function."""

    def test_returns_empty_for_no_images(self, tmp_path, mock_confluence):
        """Returns empty dict when no images in content."""
        from zaira.wiki import sync_images

        md_file = tmp_path / "test.md"
        md_file.write_text("No images")

        result = sync_images("12345", md_file, "No images", {})

        assert result == {}

    def test_uploads_new_image(self, tmp_path, mock_confluence, capsys):
        """Uploads new image and returns hash."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        # Create markdown file and image
        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"image data")

        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("upload_attachment", lambda page_id, path, filename: {"id": "att1"})

        result = sync_images("12345", md_file, content, {})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Uploaded image: image.png" in captured.out

    def test_updates_existing_image(self, tmp_path, mock_confluence, capsys):
        """Updates existing attachment when image changed."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"new image data")

        confluence_api.set_api("get_attachments", lambda page_id, expand: {
            "results": [{"title": "image.png", "id": "att1"}]
        })
        confluence_api.set_api("update_attachment", lambda page_id, att_id, path, filename: {"id": "att1"})

        result = sync_images("12345", md_file, content, {"image.png": "old_hash"})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Updated image: image.png" in captured.out

    def test_skips_unchanged_image(self, tmp_path, mock_confluence, capsys):
        """Skips upload when image unchanged."""
        from zaira.wiki import sync_images, compute_file_hash
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"image data")

        stored_hash = compute_file_hash(img_file)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

        result = sync_images("12345", md_file, content, {"image.png": stored_hash})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Uploaded" not in captured.out
        assert "Updated" not in captured.out

    def test_warns_for_missing_image(self, tmp_path, mock_confluence, capsys):
        """Warns when referenced image doesn't exist."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./missing.png)"

        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

        result = sync_images("12345", md_file, content, {})

        assert "missing.png" not in result
        captured = capsys.readouterr()
        assert "Warning: Image not found" in captured.err


class TestDownloadImages:
    """Tests for download_images function."""

    def test_downloads_nothing_when_no_attachments(self, tmp_path, mock_confluence):
        """Does nothing when page has no attachments."""
        from zaira.wiki import download_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

        download_images("12345", md_file)

        assert not (tmp_path / "images").exists()

    def test_downloads_image_attachments(self, tmp_path, mock_confluence, capsys):
        """Downloads image attachments to images directory."""
        from zaira.wiki import download_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        confluence_api.set_api("get_attachments", lambda page_id, expand: {
            "results": [{"title": "image.png", "_links": {"download": "/download/image.png"}}],
            "_links": {"base": "https://site.atlassian.net/wiki"}
        })
        confluence_api.set_api("download_attachment", lambda url, path: True)

        download_images("12345", md_file)

        assert (tmp_path / "images").exists()
        captured = capsys.readouterr()
        assert "Downloaded image: image.png" in captured.out

    def test_skips_non_image_attachments(self, tmp_path, mock_confluence, capsys):
        """Skips non-image file extensions."""
        from zaira.wiki import download_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        confluence_api.set_api("get_attachments", lambda page_id, expand: {
            "results": [{"title": "document.pdf", "_links": {"download": "/download/document.pdf"}}],
            "_links": {"base": "https://site.atlassian.net"}
        })

        download_images("12345", md_file)

        captured = capsys.readouterr()
        assert "document.pdf" not in captured.out


class TestPrintPageTree:
    """Tests for _print_page_tree function."""

    def test_prints_single_page(self, mock_confluence, capsys):
        """Prints single page without children."""
        from zaira.wiki import _print_page_tree
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "space": {"key": "TEST"}
        })
        confluence_api.set_api("get_child_pages", lambda page_id, limit: [])

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            count = _print_page_tree("12345")

        assert count == 1
        captured = capsys.readouterr()
        assert "Test Page" in captured.out
        assert "12345" in captured.out

    def test_returns_zero_on_error(self, mock_confluence, capsys):
        """Returns 0 when page fetch fails."""
        from zaira.wiki import _print_page_tree
        from zaira import confluence_api

        confluence_api.set_api("fetch_page", lambda page_id, expand: None)

        count = _print_page_tree("12345")

        assert count == 0
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_prints_children(self, mock_confluence, capsys):
        """Prints page with children."""
        from zaira.wiki import _print_page_tree
        from zaira import confluence_api

        def mock_fetch(page_id, expand):
            return {"title": f"Page {page_id}", "space": {"key": "TEST"}}

        def mock_children(page_id, limit):
            if page_id == "12345":
                return [{"id": "111"}]
            return []

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_child_pages", mock_children)

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            count = _print_page_tree("12345")

        assert count == 2
        captured = capsys.readouterr()
        assert "Page 12345" in captured.out
        assert "Page 111" in captured.out


class TestWikiCommand:
    """Tests for wiki_command function."""

    def test_calls_wiki_func(self):
        """Calls wiki_func when present."""
        from zaira.wiki import wiki_command
        import argparse

        called = []
        args = argparse.Namespace(wiki_func=lambda a: called.append(a))

        wiki_command(args)

        assert len(called) == 1

    def test_prints_usage_without_func(self, capsys):
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

    def test_exports_page(self, tmp_path, mock_confluence, capsys):
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
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
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

    def test_search_with_query(self, mock_confluence, capsys):
        """Searches with text query."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("search_pages", lambda cql, limit, expand: {
            "results": [
                {
                    "id": "12345",
                    "title": "Found Page",
                    "space": {"key": "TEST"},
                    "_links": {"webui": "/spaces/TEST/pages/12345/Found+Page"},
                }
            ]
        })

        args = argparse.Namespace(
            query="test",
            space=None,
            creator=None,
            limit=25,
            format="default",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            search_command(args)

        captured = capsys.readouterr()
        assert "Found Page" in captured.out
        assert "TEST" in captured.out

    def test_search_json_format(self, mock_confluence, capsys):
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
            creator=None,
            limit=25,
            format="json",
        )

        search_command(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "results" in output

    def test_search_url_format(self, mock_confluence, capsys):
        """Returns URL-only format when requested."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("search_pages", lambda cql, limit, expand: {
            "results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]
        })

        args = argparse.Namespace(
            query="test",
            space=None,
            creator=None,
            limit=25,
            format="url",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            search_command(args)

        captured = capsys.readouterr()
        assert "https://site.atlassian.net/wiki/spaces/TEST/pages/12345" in captured.out

    def test_search_id_format(self, mock_confluence, capsys):
        """Returns ID-only format when requested."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("search_pages", lambda cql, limit, expand: {
            "results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]
        })

        args = argparse.Namespace(
            query="test",
            space=None,
            creator=None,
            limit=25,
            format="id",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            search_command(args)

        captured = capsys.readouterr()
        assert captured.out.strip() == "12345"

    def test_search_no_results(self, mock_confluence, capsys):
        """Exits gracefully when no results."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("search_pages", lambda cql, limit, expand: {"results": []})

        args = argparse.Namespace(
            query="nonexistent",
            space=None,
            creator=None,
            limit=25,
            format="default",
        )

        with pytest.raises(SystemExit) as exc_info:
            search_command(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No results found" in captured.err

    def test_search_error(self, mock_confluence, capsys):
        """Handles API errors."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("search_pages", lambda cql, limit, expand: {
            "error": "401 - Unauthorized",
            "text": "Invalid credentials",
        })

        args = argparse.Namespace(
            query="test",
            space=None,
            creator=None,
            limit=25,
            format="default",
        )

        with pytest.raises(SystemExit) as exc_info:
            search_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_search_with_space_filter(self, mock_confluence, capsys):
        """Filters by space."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        cql_received = []

        def mock_search(cql, limit, expand):
            cql_received.append(cql)
            return {"results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]}

        confluence_api.set_api("search_pages", mock_search)

        args = argparse.Namespace(
            query="test",
            space="MYSPACE",
            creator=None,
            limit=25,
            format="default",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            search_command(args)

        assert 'space = "MYSPACE"' in cql_received[0]

    def test_search_with_creator_filter(self, mock_confluence, capsys):
        """Filters by creator."""
        from zaira.wiki import search_command
        from zaira import confluence_api
        import argparse

        cql_received = []

        def mock_search(cql, limit, expand):
            cql_received.append(cql)
            return {"results": [{"id": "12345", "title": "Page", "space": {"key": "TEST"}}]}

        confluence_api.set_api("search_pages", mock_search)

        args = argparse.Namespace(
            query="test",
            space=None,
            creator="John Doe",
            limit=25,
            format="default",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            search_command(args)

        assert 'creator.fullname ~ "John Doe"' in cql_received[0]


class TestGetCommand:
    """Tests for get_command function."""

    def test_get_no_pages_error(self, capsys):
        """Errors when no pages specified."""
        from zaira.wiki import get_command
        import argparse

        args = argparse.Namespace(pages=[])

        with pytest.raises(SystemExit) as exc_info:
            get_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No pages specified" in captured.err

    def test_get_list_mode(self, mock_confluence, capsys):
        """Lists page tree when --list is used."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Root Page",
            "space": {"key": "TEST"},
        })
        confluence_api.set_api("get_child_pages", lambda page_id, limit: [])

        args = argparse.Namespace(
            pages=["12345"],
            list=True,
            children=False,
            output=None,
            format="markdown",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            get_command(args)

        captured = capsys.readouterr()
        assert "Root Page" in captured.out
        assert "1 page(s)" in captured.out

    def test_get_single_page_stdout_markdown(self, mock_confluence, capsys):
        """Gets single page in markdown format to stdout."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "TEST", "name": "Test Space"},
            "body": {"storage": {"value": "<p>Hello</p>"}},
        })
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

    def test_get_single_page_stdout_json(self, mock_confluence, capsys):
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

    def test_get_single_page_stdout_html(self, mock_confluence, capsys):
        """Gets single page in HTML format to stdout."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "TEST", "name": "Test Space"},
            "body": {"storage": {"value": "<p>Hello</p>"}},
        })

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

    def test_get_multiple_pages_requires_output(self, mock_confluence, capsys):
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

    def test_get_multiple_pages_to_dir(self, tmp_path, mock_confluence, capsys):
        """Gets multiple pages to output directory."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        def mock_fetch(page_id, expand):
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
            }

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
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

    def test_get_with_children(self, mock_confluence, capsys):
        """Gets page with children expanded."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        def mock_fetch(page_id, expand):
            return {
                "id": page_id,
                "title": f"Page {page_id}",
                "version": {"number": 1},
                "space": {"key": "TEST"},
                "body": {"storage": {"value": "<p>Content</p>"}},
            }

        def mock_children(page_id, limit):
            if page_id == "12345":
                return [{"id": "111"}]
            return []

        confluence_api.set_api("fetch_page", mock_fetch)
        confluence_api.set_api("get_child_pages", mock_children)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        args = argparse.Namespace(
            pages=["12345"],
            list=False,
            children=True,
            output=str(Path("/tmp/test_output")),
            format="markdown",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            get_command(args)

        captured = capsys.readouterr()
        assert "Found 1 child page(s)" in captured.err

    def test_get_page_fetch_error(self, mock_confluence, capsys):
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

    def test_create_page_with_markdown(self, mock_confluence, capsys):
        """Creates page with markdown body."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "12345",
            "version": {"number": 1},
        })

        args = argparse.Namespace(
            title="New Page",
            body="# Hello\n\nWorld",
            markdown=True,
            space="TEST",
            parent=None,
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out

    def test_create_page_empty_body_error(self, capsys):
        """Errors when body is empty."""
        from zaira.wiki import create_command
        import argparse

        args = argparse.Namespace(
            title="New Page",
            body="   ",
            markdown=False,
            space="TEST",
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Body content cannot be empty" in captured.err

    def test_create_page_requires_space_or_parent(self, capsys):
        """Errors when neither space nor parent specified."""
        from zaira.wiki import create_command
        import argparse

        args = argparse.Namespace(
            title="New Page",
            body="Content",
            markdown=False,
            space=None,
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Either --space or --parent is required" in captured.err

    def test_create_page_infers_space_from_parent(self, mock_confluence, capsys):
        """Infers space from parent page."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "ancestors": [],
            "space": {"key": "INFERRED"},
        })
        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "12345",
            "version": {"number": 1},
        })

        args = argparse.Namespace(
            title="New Page",
            body="Content",
            markdown=False,
            space=None,
            parent="99999",
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out

    def test_create_page_api_error(self, mock_confluence, capsys):
        """Handles API error on create."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("create_page", lambda space, title, body, parent: None)

        args = argparse.Namespace(
            title="New Page",
            body="Content",
            markdown=False,
            space="TEST",
            parent=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            create_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error creating page" in captured.err

    def test_create_page_reads_from_file(self, tmp_path, mock_confluence, capsys):
        """Reads body from file."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse

        content_file = tmp_path / "content.txt"
        content_file.write_text("File content here")

        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "12345",
            "version": {"number": 1},
        })

        args = argparse.Namespace(
            title="New Page",
            body=str(content_file),
            markdown=False,
            space="TEST",
            parent=None,
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out


class TestAttachCommand:
    """Tests for attach_command function."""

    def test_attach_uploads_file(self, tmp_path, mock_confluence, capsys):
        """Uploads file as attachment."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"image data")

        confluence_api.set_api("get_attachments", lambda page_id: {"results": []})
        confluence_api.set_api("upload_attachment", lambda page_id, path, filename: {"id": "att1"})

        args = argparse.Namespace(
            page="12345",
            files=[str(test_file)],
            replace=False,
        )

        attach_command(args)

        captured = capsys.readouterr()
        assert "Uploaded: test.png" in captured.out
        assert "ac:image" in captured.out

    def test_attach_replaces_existing(self, tmp_path, mock_confluence, capsys):
        """Replaces existing attachment when --replace is used."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"image data")

        confluence_api.set_api("get_attachments", lambda page_id, expand: {
            "results": [{"title": "test.png", "id": "att1"}]
        })
        confluence_api.set_api("update_attachment", lambda page_id, att_id, path, filename: {"id": "att1"})

        args = argparse.Namespace(
            page="12345",
            files=[str(test_file)],
            replace=True,
        )

        attach_command(args)

        captured = capsys.readouterr()
        assert "Updated: test.png" in captured.out

    def test_attach_no_files_error(self, capsys):
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

    def test_attach_upload_error(self, tmp_path, mock_confluence, capsys):
        """Handles upload error."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"image data")

        confluence_api.set_api("get_attachments", lambda page_id: {"results": []})
        confluence_api.set_api("upload_attachment", lambda page_id, path, filename: None)

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

    def test_delete_page_not_found(self, mock_confluence, capsys):
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

    def test_delete_page_with_yes(self, mock_confluence, capsys):
        """Deletes page when --yes is specified."""
        from zaira.wiki import delete_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "space": {"key": "TEST"},
        })
        confluence_api.set_api("delete_page", lambda page_id: True)

        args = argparse.Namespace(page="12345", yes=True)

        delete_command(args)

        captured = capsys.readouterr()
        assert "Deleted page 12345" in captured.out

    def test_delete_page_api_error(self, mock_confluence, capsys):
        """Handles API error on delete."""
        from zaira.wiki import delete_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "space": {"key": "TEST"},
        })
        confluence_api.set_api("delete_page", lambda page_id: False)

        args = argparse.Namespace(page="12345", yes=True)

        with pytest.raises(SystemExit) as exc_info:
            delete_command(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error deleting page" in captured.err

    def test_delete_page_cancel_confirmation(self, mock_confluence, capsys, monkeypatch):
        """Cancels when user doesn't confirm."""
        from zaira.wiki import delete_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "space": {"key": "TEST"},
        })

        monkeypatch.setattr("builtins.input", lambda prompt: "no")

        args = argparse.Namespace(page="12345", yes=False)

        with pytest.raises(SystemExit) as exc_info:
            delete_command(args)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Deletion cancelled" in captured.out


class TestEditCommand:
    """Tests for edit_command function."""

    def test_edit_page_not_found(self, mock_confluence, capsys):
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

    def test_edit_page_title(self, mock_confluence, capsys):
        """Edits page title."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Old Title",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [],
        })
        confluence_api.set_api("update_page_properties", lambda page_id, version, ptype, title, space_key, parent_id: True)

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

    def test_edit_page_labels(self, mock_confluence, capsys):
        """Edits page labels."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [],
        })
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

    def test_edit_no_changes(self, mock_confluence, capsys):
        """Reports no changes when nothing changed."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [],
        })

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

    def test_edit_page_parent(self, mock_confluence, capsys):
        """Edits page parent."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [{"id": "111"}],
        })
        confluence_api.set_api("update_page_properties", lambda page_id, version, ptype, title, space_key, parent_id: True)

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

    def test_edit_page_space(self, mock_confluence, capsys):
        """Edits page space."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "OLD"},
            "ancestors": [],
        })
        confluence_api.set_api("update_page_properties", lambda page_id, version, ptype, title, space_key, parent_id: True)

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

    def test_edit_update_properties_error(self, mock_confluence, capsys):
        """Handles error when updating properties."""
        from zaira.wiki import edit_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "title": "Old Title",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [],
        })
        confluence_api.set_api("update_page_properties", lambda page_id, version, ptype, title, space_key, parent_id: None)

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

    def test_put_file_not_found(self, tmp_path, capsys):
        """Errors when file not found."""
        from zaira.wiki import _put_one_file

        result = _put_one_file(
            tmp_path / "nonexistent.md",
            None, None, False, False, False, False
        )

        assert result is False
        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_put_empty_file(self, tmp_path, capsys):
        """Errors when file is empty."""
        from zaira.wiki import _put_one_file

        md_file = tmp_path / "empty.md"
        md_file.write_text("   ")

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "File is empty" in captured.err

    def test_put_no_page_id(self, tmp_path, capsys):
        """Skips file without confluence front matter."""
        from zaira.wiki import _put_one_file

        md_file = tmp_path / "no_id.md"
        md_file.write_text("# Just content\n\nNo front matter")

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "no 'confluence:'" in captured.err

    def test_put_status_mode(self, tmp_path, mock_confluence, capsys):
        """Shows status when --status is used."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 2},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": "abc123",
                "uploaded_version": 1,
                "uploaded_at": "2024-01-01T00:00:00Z",
            }
        })

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Page ID: 12345" in captured.out
        assert "Remote version: 2" in captured.out

    def test_put_diff_mode(self, tmp_path, mock_confluence, capsys):
        """Shows diff when --diff is used."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# New Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = _put_one_file(md_file, None, None, False, False, False, True)

        assert result is True
        captured = capsys.readouterr()
        assert "Diff for" in captured.out

    def test_put_pull_mode(self, tmp_path, mock_confluence, capsys):
        """Pulls content from remote when --pull is used."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Local Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Remote Title",
            "version": {"number": 3},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Remote Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_page_labels", lambda page_id: ["remote-label"])
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

        result = _put_one_file(md_file, None, None, True, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pulled version 3" in captured.out
        content = md_file.read_text()
        assert "Remote Title" in content
        assert "remote-label" in content

    def test_put_conflict_detection(self, tmp_path, mock_confluence, capsys):
        """Detects conflict when local and remote both changed."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed local content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 3},  # Remote is version 3
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Remote changed</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": "old_hash",  # Local content changed
                "uploaded_version": 2,  # Last synced at version 2
            }
        })

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "Conflict" in captured.err

    def test_put_already_synced(self, tmp_path, mock_confluence, capsys):
        """Reports already in sync."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api
        import hashlib

        content = "# Content"
        local_hash = hashlib.sha256(content.encode()).hexdigest()

        md_file = tmp_path / "test.md"
        md_file.write_text(f"---\nconfluence: 12345\n---\n\n{content}")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": local_hash,
                "uploaded_version": 1,
                "images": {},
            }
        })

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "already in sync" in captured.out

    def test_put_push_success(self, tmp_path, mock_confluence, capsys):
        """Successfully pushes content."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\ntitle: Updated Title\n---\n\n# New Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Old Title",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pushed" in captured.out
        assert "version 1 -> 2" in captured.out
        assert "title:" in captured.out

    def test_put_with_labels(self, tmp_path, mock_confluence, capsys):
        """Pushes content with labels."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\nlabels: [new-label, another]\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_page_labels", lambda page_id: ["old-label"])
        confluence_api.set_api("remove_page_label", lambda page_id, label: True)
        confluence_api.set_api("add_page_labels", lambda page_id, labels: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pushed" in captured.out

    def test_put_update_error(self, tmp_path, mock_confluence, capsys):
        """Handles update error."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: None)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is False
        captured = capsys.readouterr()
        assert "Error updating" in captured.err

    def test_put_page_fetch_error(self, tmp_path, mock_confluence, capsys):
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

    def test_put_force_overwrite(self, tmp_path, mock_confluence, capsys):
        """Force overwrites conflict."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed local content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 3},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Remote changed</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": "old_hash",
                "uploaded_version": 2,
            }
        })
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 4}
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, None, False, True, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Pushed" in captured.out


class TestPutCommand:
    """Tests for put_command function."""

    def test_put_no_files_error(self, capsys):
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

    def test_put_single_file(self, tmp_path, mock_confluence, capsys):
        """Processes single file."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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

    def test_put_directory(self, tmp_path, mock_confluence, capsys):
        """Processes directory of markdown files."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Create files in directory
        md_file1 = tmp_path / "file1.md"
        md_file1.write_text("---\nconfluence: 111\n---\n\n# Content 1")
        md_file2 = tmp_path / "file2.md"
        md_file2.write_text("---\nconfluence: 222\n---\n\n# Content 2")

        def mock_fetch(page_id, expand):
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
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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

    def test_put_unlinked_file_skipped(self, tmp_path, mock_confluence, capsys):
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

    def test_put_create_new_page(self, tmp_path, mock_confluence, capsys):
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

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": page_id,
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [{"id": "parent-id"}],
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "99999",
            "version": {"number": 1},
        })

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


class TestCreatePageForFile:
    """Tests for _create_page_for_file function."""

    def test_creates_page_with_heading_title(self, tmp_path, mock_confluence, capsys):
        """Uses first heading as title."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("# My Page Title\n\nContent here")

        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "12345",
            "version": {"number": 1},
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

        result = _create_page_for_file(md_file, "parent-id", "TEST")

        assert result is True
        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out
        content = md_file.read_text()
        assert "confluence: 12345" in content

    def test_creates_page_with_filename_title(self, tmp_path, mock_confluence, capsys):
        """Uses filename as title when no heading."""
        from zaira.wiki import _create_page_for_file
        from zaira import confluence_api

        md_file = tmp_path / "my-page-name.md"
        md_file.write_text("Just content, no heading")

        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "12345",
            "version": {"number": 1},
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

        result = _create_page_for_file(md_file, "parent-id", "TEST")

        assert result is True

    def test_create_page_api_error(self, tmp_path, mock_confluence, capsys):
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


class TestPutOneFileStatusCases:
    """Additional status cases for _put_one_file."""

    def test_status_local_ahead(self, tmp_path, mock_confluence, capsys):
        """Shows Local ahead status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": "old_hash",
                "uploaded_version": 1,
                "images": {},
            }
        })

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: Local ahead" in captured.out

    def test_status_remote_ahead(self, tmp_path, mock_confluence, capsys):
        """Shows Remote ahead status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api
        import hashlib

        content = "# Content"
        local_hash = hashlib.sha256(content.encode()).hexdigest()

        md_file = tmp_path / "test.md"
        md_file.write_text(f"---\nconfluence: 12345\n---\n\n{content}")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 2},  # Remote is newer
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": local_hash,  # Local unchanged
                "uploaded_version": 1,
                "images": {},
            }
        })

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: Remote ahead" in captured.out

    def test_status_in_sync(self, tmp_path, mock_confluence, capsys):
        """Shows In sync status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api
        import hashlib

        content = "# Content"
        local_hash = hashlib.sha256(content.encode()).hexdigest()

        md_file = tmp_path / "test.md"
        md_file.write_text(f"---\nconfluence: 12345\n---\n\n{content}")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": local_hash,
                "uploaded_version": 1,
                "images": {},
            }
        })

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: In sync" in captured.out

    def test_status_no_sync_metadata(self, tmp_path, mock_confluence, capsys):
        """Shows No sync metadata status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: No sync metadata" in captured.out

    def test_status_conflict(self, tmp_path, mock_confluence, capsys):
        """Shows CONFLICT status."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Changed content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 3},  # Remote changed
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: {
            "value": {
                "source_hash": "old_hash",  # Local also changed
                "uploaded_version": 2,
                "images": {},
            }
        })

        result = _put_one_file(md_file, None, None, False, False, True, False)

        assert result is True
        captured = capsys.readouterr()
        assert "Status: CONFLICT" in captured.out

    def test_diff_no_differences(self, tmp_path, mock_confluence, capsys):
        """Shows no differences message."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        # Use content that when round-tripped looks similar
        md_file.write_text("---\nconfluence: 12345\n---\n\nSame content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Same content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)

        result = _put_one_file(md_file, None, None, False, False, False, True)

        assert result is True
        captured = capsys.readouterr()
        assert "no content differences" in captured.out

    def test_pull_removes_labels(self, tmp_path, mock_confluence, capsys):
        """Pull removes labels when not in remote."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\nlabels: [local-label]\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Remote Content</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_page_labels", lambda page_id: [])  # No remote labels
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

        result = _put_one_file(md_file, None, None, True, False, False, False)

        assert result is True
        content = md_file.read_text()
        assert "local-label" not in content


class TestPutCommandEdgeCases:
    """Additional edge cases for put_command."""

    def test_put_create_no_parent_error(self, tmp_path, mock_confluence, capsys):
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

    def test_put_create_parent_error(self, tmp_path, mock_confluence, capsys):
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

    def test_put_file_not_exists_warning(self, tmp_path, mock_confluence, capsys):
        """Warns when file doesn't exist in batch."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        existing_file = tmp_path / "exists.md"
        existing_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": page_id,
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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

    def test_put_labels_as_string(self, tmp_path, mock_confluence, capsys):
        """Handles labels as comma-separated string."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\nlabels: label1, label2\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        confluence_api.set_api("add_page_labels", lambda page_id, labels: True)

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True


class TestSyncImagesErrors:
    """Error handling for sync_images."""

    def test_upload_error(self, tmp_path, mock_confluence, capsys):
        """Handles upload error."""
        from zaira.wiki import sync_images
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        content = "![Alt](./image.png)"
        img_file = tmp_path / "image.png"
        img_file.write_bytes(b"image data")

        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("upload_attachment", lambda page_id, path, filename: None)

        result = sync_images("12345", md_file, content, {})

        assert "image.png" in result
        captured = capsys.readouterr()
        assert "Error uploading" in captured.err


class TestGetCommandEdgeCases:
    """Additional edge cases for get_command."""

    def test_get_multiple_pages_failed_export(self, tmp_path, mock_confluence, capsys):
        """Continues when one page export fails."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        def mock_fetch(page_id, expand):
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
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
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

    def test_get_page_with_labels(self, mock_confluence, capsys):
        """Gets page with labels in markdown output."""
        from zaira.wiki import get_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test Page",
            "version": {"number": 1},
            "space": {"key": "TEST", "name": "Test Space"},
            "body": {"storage": {"value": "<p>Hello</p>"}},
        })
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

    def test_attach_glob_pattern(self, tmp_path, mock_confluence, capsys):
        """Processes glob patterns."""
        from zaira.wiki import attach_command
        from zaira import confluence_api
        import argparse

        # Create multiple image files
        (tmp_path / "img1.png").write_bytes(b"image1")
        (tmp_path / "img2.png").write_bytes(b"image2")

        confluence_api.set_api("get_attachments", lambda page_id: {"results": []})
        confluence_api.set_api("upload_attachment", lambda page_id, path, filename: {"id": "att"})

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

    def test_create_parent_space_fetch_error(self, mock_confluence, capsys):
        """Errors when cannot get space from parent."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "ancestors": [],
            "space": {},  # Missing key
        })

        args = argparse.Namespace(
            title="New Page",
            body="Content",
            markdown=False,
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

    def test_attach_no_files_to_upload(self, capsys):
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

    def test_put_create_different_parents(self, tmp_path, mock_confluence, capsys):
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

        def mock_fetch(page_id, expand):
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

    def test_put_create_pages_at_root(self, tmp_path, mock_confluence, capsys):
        """Errors when linked pages are at space root."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        linked = tmp_path / "linked.md"
        linked.write_text("---\nconfluence: 111\n---\n\n# Content")

        unlinked = tmp_path / "new.md"
        unlinked.write_text("# New Page")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": page_id,
            "title": "Page",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [],  # At root - no parent
            "body": {"storage": {"value": "<p>Content</p>"}},
            "type": "page",
        })

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

    def test_put_create_no_parents_determinable(self, tmp_path, mock_confluence, capsys):
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

    def test_put_with_title_override(self, tmp_path, mock_confluence, capsys):
        """Uses title override when provided."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Original Title",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)

        result = _put_one_file(md_file, None, "New Title", False, False, False, False)

        assert result is True
        captured = capsys.readouterr()
        assert "title:" in captured.out

    def test_put_invalid_labels_type(self, tmp_path, mock_confluence, capsys):
        """Handles invalid labels type."""
        from zaira.wiki import _put_one_file
        from zaira import confluence_api

        md_file = tmp_path / "test.md"
        # Labels as a number (invalid)
        md_file.write_text("---\nconfluence: 12345\nlabels: 123\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_page_labels", lambda page_id: [])
        # Should not call add_page_labels with empty set

        result = _put_one_file(md_file, None, None, False, False, False, False)

        assert result is True

    def test_put_glob_pattern_in_files(self, tmp_path, mock_confluence, capsys):
        """Handles glob patterns in files argument."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        # Create files matching pattern
        md1 = tmp_path / "file1.md"
        md1.write_text("---\nconfluence: 111\n---\n\n# Content 1")
        md2 = tmp_path / "file2.md"
        md2.write_text("---\nconfluence: 222\n---\n\n# Content 2")

        def mock_fetch(page_id, expand):
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
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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

    def test_put_batch_with_failures(self, tmp_path, mock_confluence, capsys):
        """Reports failures in batch mode."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md1 = tmp_path / "good.md"
        md1.write_text("---\nconfluence: 111\n---\n\n# Content")

        md2 = tmp_path / "bad.md"
        md2.write_text("---\nconfluence: 222\n---\n\n# Content")

        def mock_fetch(page_id, expand):
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
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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

    def test_put_create_with_parent_info(self, tmp_path, mock_confluence, capsys):
        """Creates page using parent info when --parent specified."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        unlinked = tmp_path / "new.md"
        unlinked.write_text("# New Page\n\nContent")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "ancestors": [],
            "space": {"key": "FROM_PARENT"},
        })
        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "99999",
            "version": {"number": 1},
        })
        confluence_api.set_api("set_page_property", lambda page_id, key, value: True)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})

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

    def test_put_stdin_empty_error(self, mock_confluence, capsys, monkeypatch):
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

    def test_put_stdin_no_page_id_error(self, mock_confluence, capsys, monkeypatch):
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

    def test_put_stdin_with_page_id(self, mock_confluence, capsys, monkeypatch):
        """Processes stdin with page ID from front matter."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse
        import io

        stdin_content = "---\nconfluence: 12345\n---\n\n# Content"
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_content))

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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

    def test_put_body_not_a_file_error(self, capsys):
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

    def test_put_body_as_file(self, tmp_path, mock_confluence, capsys):
        """Processes -b argument as file path."""
        from zaira.wiki import put_command
        from zaira import confluence_api
        import argparse

        md_file = tmp_path / "input.md"
        md_file.write_text("---\nconfluence: 12345\n---\n\n# Content")

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": "12345",
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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

    def test_create_reads_from_stdin(self, mock_confluence, capsys, monkeypatch):
        """Reads body from stdin."""
        from zaira.wiki import create_command
        from zaira import confluence_api
        import argparse
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("# Content from stdin"))

        confluence_api.set_api("create_page", lambda space, title, body, parent: {
            "id": "12345",
            "version": {"number": 1},
        })

        args = argparse.Namespace(
            title="New Page",
            body="-",
            markdown=True,
            space="TEST",
            parent=None,
        )

        with patch("zaira.wiki.get_server_from_config", return_value="https://site.atlassian.net"):
            create_command(args)

        captured = capsys.readouterr()
        assert "Created page 12345" in captured.out


class TestPutNoMarkdownFilesFound:
    """Test when no markdown files are found after processing."""

    def test_put_directory_no_markdown_files(self, tmp_path, capsys):
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

    def test_put_create_unlinked_file_failure(self, tmp_path, mock_confluence, capsys):
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

        confluence_api.set_api("fetch_page", lambda page_id, expand: {
            "id": page_id,
            "title": "Test",
            "version": {"number": 1},
            "space": {"key": "TEST"},
            "ancestors": [{"id": "parent-id"}],
            "body": {"storage": {"value": "<p>Old</p>"}},
            "type": "page",
        })
        confluence_api.set_api("get_page_property", lambda page_id, key: None)
        confluence_api.set_api("get_attachments", lambda page_id, expand: {"results": []})
        confluence_api.set_api("update_page", lambda page_id, title, body, version, ptype: {
            "version": {"number": 2}
        })
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
        )

        put_command(args)

        captured = capsys.readouterr()
        assert "1 failed" in captured.out
