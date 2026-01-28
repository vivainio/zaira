"""Tests for confluence_api module."""

import pytest

from zaira import confluence_api


class TestApiOverrides:
    """Tests for API override mechanism."""

    def test_set_api_stores_override(self):
        """set_api stores function override."""
        def mock_fn():
            return "mocked"

        confluence_api.set_api("test_func", mock_fn)
        try:
            assert "test_func" in confluence_api._api_overrides
            assert confluence_api._api_overrides["test_func"]() == "mocked"
        finally:
            confluence_api.reset_api()

    def test_reset_api_clears_overrides(self):
        """reset_api clears all overrides."""
        confluence_api.set_api("func1", lambda: 1)
        confluence_api.set_api("func2", lambda: 2)

        confluence_api.reset_api()

        assert confluence_api._api_overrides == {}


class TestFetchPage:
    """Tests for fetch_page with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "fetch_page",
            lambda page_id, expand: {"id": page_id, "title": "Mocked"}
        )

        result = confluence_api.fetch_page("12345", "body.storage")

        assert result["id"] == "12345"
        assert result["title"] == "Mocked"


class TestCreatePage:
    """Tests for create_page with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "create_page",
            lambda space, title, body, parent: {
                "id": "99999",
                "title": title,
                "space": {"key": space},
            }
        )

        result = confluence_api.create_page("TEST", "New Page", "<p>Body</p>")

        assert result["id"] == "99999"
        assert result["title"] == "New Page"
        assert result["space"]["key"] == "TEST"


class TestUpdatePage:
    """Tests for update_page with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "update_page",
            lambda page_id, title, body, version, page_type: {
                "id": page_id,
                "title": title,
                "version": {"number": version + 1},
            }
        )

        result = confluence_api.update_page("123", "Updated", "<p>New</p>", 5)

        assert result["id"] == "123"
        assert result["title"] == "Updated"
        assert result["version"]["number"] == 6


class TestDeletePage:
    """Tests for delete_page with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api("delete_page", lambda page_id: True)

        result = confluence_api.delete_page("123")

        assert result is True


class TestGetChildPages:
    """Tests for get_child_pages with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "get_child_pages",
            lambda page_id, limit: [
                {"id": "1", "title": "Child 1"},
                {"id": "2", "title": "Child 2"},
            ]
        )

        result = confluence_api.get_child_pages("parent123")

        assert len(result) == 2
        assert result[0]["title"] == "Child 1"


class TestSearchPages:
    """Tests for search_pages with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "search_pages",
            lambda cql, limit, expand: {
                "results": [{"id": "1", "title": "Found"}],
                "size": 1,
            }
        )

        result = confluence_api.search_pages('text ~ "test"')

        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Found"


class TestGetPageLabels:
    """Tests for get_page_labels with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "get_page_labels",
            lambda page_id: ["label1", "label2", "label3"]
        )

        result = confluence_api.get_page_labels("123")

        assert result == ["label1", "label2", "label3"]


class TestAddPageLabels:
    """Tests for add_page_labels with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "add_page_labels",
            lambda page_id, labels: True
        )

        result = confluence_api.add_page_labels("123", ["new-label"])

        assert result is True

    def test_returns_true_for_empty_labels(self, mock_confluence):
        """Returns True immediately for empty labels list."""
        # No override needed - function handles this internally
        result = confluence_api.add_page_labels("123", [])

        assert result is True


class TestSetPageLabels:
    """Tests for set_page_labels with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "set_page_labels",
            lambda page_id, labels: True
        )

        result = confluence_api.set_page_labels("123", ["a", "b"])

        assert result is True


class TestGetAttachments:
    """Tests for get_attachments with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "get_attachments",
            lambda page_id, expand: {
                "results": [{"title": "file.png", "id": "att1"}]
            }
        )

        result = confluence_api.get_attachments("123")

        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "file.png"


class TestUploadAttachment:
    """Tests for upload_attachment with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence, tmp_path):
        """Uses override function when set."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        confluence_api.set_api(
            "upload_attachment",
            lambda page_id, file_path, filename: {
                "id": "att123",
                "title": filename or file_path.name,
            }
        )

        result = confluence_api.upload_attachment("123", test_file)

        assert result["id"] == "att123"
        assert result["title"] == "test.txt"


class TestGetPageProperty:
    """Tests for get_page_property with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "get_page_property",
            lambda page_id, key: {
                "key": key,
                "value": {"data": "test"},
                "version": {"number": 1},
            }
        )

        result = confluence_api.get_page_property("123", "my-prop")

        assert result["key"] == "my-prop"
        assert result["value"]["data"] == "test"


class TestSetPageProperty:
    """Tests for set_page_property with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "set_page_property",
            lambda page_id, key, value: True
        )

        result = confluence_api.set_page_property("123", "key", {"data": "val"})

        assert result is True
