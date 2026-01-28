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


class TestRemovePageLabel:
    """Tests for remove_page_label with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "remove_page_label",
            lambda page_id, label: True
        )

        result = confluence_api.remove_page_label("123", "old-label")

        assert result is True


class TestUpdatePageProperties:
    """Tests for update_page_properties with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence):
        """Uses override function when set."""
        confluence_api.set_api(
            "update_page_properties",
            lambda page_id, version, page_type, title, space_key, parent_id: {
                "id": page_id,
                "title": title,
                "version": {"number": version + 1},
            }
        )

        result = confluence_api.update_page_properties(
            "123", 5, "page", "New Title", "SPACE", "456"
        )

        assert result["id"] == "123"
        assert result["title"] == "New Title"
        assert result["version"]["number"] == 6


class TestUpdateAttachment:
    """Tests for update_attachment with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence, tmp_path):
        """Uses override function when set."""
        test_file = tmp_path / "updated.txt"
        test_file.write_text("new content")

        confluence_api.set_api(
            "update_attachment",
            lambda page_id, att_id, file_path, filename: {
                "id": att_id,
                "title": filename or file_path.name,
            }
        )

        result = confluence_api.update_attachment("123", "att456", test_file)

        assert result["id"] == "att456"
        assert result["title"] == "updated.txt"


class TestDownloadAttachment:
    """Tests for download_attachment with mock overrides."""

    def test_uses_override_when_set(self, mock_confluence, tmp_path):
        """Uses override function when set."""
        dest = tmp_path / "downloaded.txt"

        confluence_api.set_api(
            "download_attachment",
            lambda url, dest_path: True
        )

        result = confluence_api.download_attachment(
            "https://confluence.example.com/att/123",
            dest
        )

        assert result is True


class TestGetAuth:
    """Tests for _get_auth function."""

    def test_raises_when_no_credentials(self, mock_confluence):
        """Raises ValueError when credentials not configured."""
        from unittest.mock import patch

        with (
            patch("zaira.confluence_api.load_credentials", return_value={}),
            patch("zaira.confluence_api.get_server_from_config", return_value=None),
            pytest.raises(ValueError) as exc_info,
        ):
            confluence_api._get_auth()

        assert "Credentials not configured" in str(exc_info.value)

    def test_raises_when_missing_email(self, mock_confluence):
        """Raises ValueError when email missing."""
        from unittest.mock import patch

        with (
            patch("zaira.confluence_api.load_credentials", return_value={"api_token": "token"}),
            patch("zaira.confluence_api.get_server_from_config", return_value="https://example.atlassian.net"),
            pytest.raises(ValueError) as exc_info,
        ):
            confluence_api._get_auth()

        assert "Credentials not configured" in str(exc_info.value)

    def test_returns_auth_tuple(self, mock_confluence):
        """Returns base URL and auth when configured."""
        from unittest.mock import patch

        with (
            patch("zaira.confluence_api.load_credentials", return_value={
                "email": "user@example.com",
                "api_token": "token123"
            }),
            patch("zaira.confluence_api.get_server_from_config", return_value="https://example.atlassian.net"),
        ):
            base_url, auth = confluence_api._get_auth()

        assert base_url == "https://example.atlassian.net/wiki/rest/api"
        assert auth.username == "user@example.com"
        assert auth.password == "token123"


class TestFetchPageWithRequests:
    """Tests for fetch_page with mocked requests."""

    def test_fetches_page_successfully(self, mock_confluence):
        """Fetches page from API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": "12345",
            "title": "Test Page",
            "body": {"storage": {"value": "<p>Content</p>"}},
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response) as mock_get,
        ):
            result = confluence_api.fetch_page("12345", "body.storage")

        assert result["id"] == "12345"
        assert result["title"] == "Test Page"
        mock_get.assert_called_once()

    def test_returns_none_on_error(self, mock_confluence):
        """Returns None when API request fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.fetch_page("99999")

        assert result is None


class TestCreatePageWithRequests:
    """Tests for create_page with mocked requests."""

    def test_creates_page_successfully(self, mock_confluence):
        """Creates page via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": "99999",
            "title": "New Page",
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response) as mock_post,
        ):
            result = confluence_api.create_page("SPACE", "New Page", "<p>Body</p>")

        assert result["id"] == "99999"
        mock_post.assert_called_once()

    def test_creates_page_with_parent(self, mock_confluence):
        """Creates page with parent ID."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": "99999"}

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response) as mock_post,
        ):
            result = confluence_api.create_page("SPACE", "Child", "<p>Body</p>", parent_id="12345")

        # Verify ancestors was included in payload
        call_kwargs = mock_post.call_args[1]
        assert "ancestors" in call_kwargs["json"]

    def test_returns_none_on_error(self, mock_confluence):
        """Returns None when creation fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response),
        ):
            result = confluence_api.create_page("SPACE", "New", "<p>Body</p>")

        assert result is None


class TestUpdatePageWithRequests:
    """Tests for update_page with mocked requests."""

    def test_updates_page_successfully(self, mock_confluence):
        """Updates page via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": "12345",
            "title": "Updated",
            "version": {"number": 6},
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.put", return_value=mock_response) as mock_put,
        ):
            result = confluence_api.update_page("12345", "Updated", "<p>New</p>", 5)

        assert result["version"]["number"] == 6
        mock_put.assert_called_once()

    def test_returns_none_on_error(self, mock_confluence):
        """Returns None when update fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.put", return_value=mock_response),
        ):
            result = confluence_api.update_page("12345", "Title", "<p>Body</p>", 1)

        assert result is None


class TestDeletePageWithRequests:
    """Tests for delete_page with mocked requests."""

    def test_deletes_page_successfully(self, mock_confluence):
        """Deletes page via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.delete", return_value=mock_response),
        ):
            result = confluence_api.delete_page("12345")

        assert result is True

    def test_returns_false_on_error(self, mock_confluence):
        """Returns False when deletion fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.delete", return_value=mock_response),
        ):
            result = confluence_api.delete_page("99999")

        assert result is False


class TestGetChildPagesWithRequests:
    """Tests for get_child_pages with mocked requests."""

    def test_gets_children_successfully(self, mock_confluence):
        """Gets child pages via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "results": [
                {"id": "1", "title": "Child 1"},
                {"id": "2", "title": "Child 2"},
            ]
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_child_pages("12345")

        assert len(result) == 2

    def test_returns_empty_on_error(self, mock_confluence):
        """Returns empty list when request fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_child_pages("99999")

        assert result == []


class TestSearchPagesWithRequests:
    """Tests for search_pages with mocked requests."""

    def test_searches_successfully(self, mock_confluence):
        """Searches pages via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "results": [{"id": "1", "title": "Found"}],
            "size": 1,
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.search_pages('text ~ "test"')

        assert len(result["results"]) == 1

    def test_returns_error_info_on_failure(self, mock_confluence):
        """Returns error info when search fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.reason = "Bad Request"
        mock_response.text = "Invalid CQL"

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.search_pages("invalid cql")

        assert result["results"] == []
        assert "400" in result["error"]


class TestGetPageLabelsWithRequests:
    """Tests for get_page_labels with mocked requests."""

    def test_gets_labels_successfully(self, mock_confluence):
        """Gets page labels via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "results": [
                {"name": "label1"},
                {"name": "label2"},
            ]
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_page_labels("12345")

        assert result == ["label1", "label2"]

    def test_returns_empty_on_error(self, mock_confluence):
        """Returns empty list when request fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_page_labels("99999")

        assert result == []


class TestAddPageLabelsWithRequests:
    """Tests for add_page_labels with mocked requests."""

    def test_adds_labels_successfully(self, mock_confluence):
        """Adds labels via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response),
        ):
            result = confluence_api.add_page_labels("12345", ["new-label"])

        assert result is True

    def test_returns_false_on_error(self, mock_confluence):
        """Returns False when adding labels fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response),
        ):
            result = confluence_api.add_page_labels("12345", ["label"])

        assert result is False


class TestSetPageLabelsWithRequests:
    """Tests for set_page_labels with actual logic."""

    def test_adds_and_removes_labels(self, mock_confluence):
        """Adds new labels and removes old ones."""
        from unittest.mock import patch, MagicMock

        # Mock current labels
        confluence_api.set_api("get_page_labels", lambda page_id: ["old", "keep"])

        removed_labels = []
        added_labels = []

        def mock_remove(page_id, label):
            removed_labels.append(label)
            return True

        def mock_add(page_id, labels):
            added_labels.extend(labels)
            return True

        confluence_api.set_api("remove_page_label", mock_remove)
        confluence_api.set_api("add_page_labels", mock_add)

        result = confluence_api.set_page_labels("12345", ["keep", "new"])

        assert result is True
        assert "old" in removed_labels
        assert "new" in added_labels
        assert "keep" not in removed_labels
        assert "keep" not in added_labels


class TestGetAttachmentsWithRequests:
    """Tests for get_attachments with mocked requests."""

    def test_gets_attachments_successfully(self, mock_confluence):
        """Gets attachments via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "results": [{"title": "file.png", "id": "att1"}]
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_attachments("12345")

        assert len(result["results"]) == 1

    def test_returns_empty_on_error(self, mock_confluence):
        """Returns empty results when request fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_attachments("99999")

        assert result["results"] == []


class TestUploadAttachmentWithRequests:
    """Tests for upload_attachment with mocked requests."""

    def test_uploads_successfully(self, mock_confluence, tmp_path):
        """Uploads attachment via API."""
        from unittest.mock import patch, MagicMock

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "results": [{"id": "att123", "title": "test.txt"}]
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response),
        ):
            result = confluence_api.upload_attachment("12345", test_file)

        assert result["id"] == "att123"

    def test_returns_none_on_error(self, mock_confluence, tmp_path):
        """Returns None when upload fails."""
        from unittest.mock import patch, MagicMock

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response),
        ):
            result = confluence_api.upload_attachment("12345", test_file)

        assert result is None


class TestGetPagePropertyWithRequests:
    """Tests for get_page_property with mocked requests."""

    def test_gets_property_successfully(self, mock_confluence):
        """Gets page property via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "key": "my-prop",
            "value": {"data": "test"},
            "version": {"number": 1},
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_page_property("12345", "my-prop")

        assert result["key"] == "my-prop"

    def test_returns_none_when_not_found(self, mock_confluence):
        """Returns None when property doesn't exist."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.get_page_property("12345", "nonexistent")

        assert result is None


class TestSetPagePropertyWithRequests:
    """Tests for set_page_property with mocked requests."""

    def test_creates_new_property(self, mock_confluence):
        """Creates new property when it doesn't exist."""
        from unittest.mock import patch, MagicMock

        mock_get_response = MagicMock()
        mock_get_response.ok = False  # Property doesn't exist

        mock_post_response = MagicMock()
        mock_post_response.ok = True

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_get_response),
            patch("requests.post", return_value=mock_post_response) as mock_post,
        ):
            result = confluence_api.set_page_property("12345", "new-prop", {"data": "val"})

        assert result is True
        mock_post.assert_called_once()

    def test_updates_existing_property(self, mock_confluence):
        """Updates existing property."""
        from unittest.mock import patch, MagicMock

        mock_get_response = MagicMock()
        mock_get_response.ok = True
        mock_get_response.json.return_value = {
            "key": "existing-prop",
            "version": {"number": 2},
        }

        mock_put_response = MagicMock()
        mock_put_response.ok = True

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.get", return_value=mock_get_response),
            patch("requests.put", return_value=mock_put_response) as mock_put,
        ):
            result = confluence_api.set_page_property("12345", "existing-prop", {"data": "new"})

        assert result is True
        mock_put.assert_called_once()
        # Verify version was incremented
        call_kwargs = mock_put.call_args[1]
        assert call_kwargs["json"]["version"]["number"] == 3


class TestUpdatePagePropertiesWithRequests:
    """Tests for update_page_properties with mocked requests."""

    def test_updates_properties_successfully(self, mock_confluence):
        """Updates page properties via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": "12345",
            "title": "New Title",
            "version": {"number": 6},
        }

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.put", return_value=mock_response) as mock_put,
        ):
            result = confluence_api.update_page_properties(
                "12345", 5, "page", "New Title", "NEWSPACE", "67890"
            )

        assert result["title"] == "New Title"
        # Verify space and ancestors were included
        call_kwargs = mock_put.call_args[1]
        assert "space" in call_kwargs["json"]
        assert "ancestors" in call_kwargs["json"]

    def test_returns_none_on_error(self, mock_confluence):
        """Returns None when update fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.put", return_value=mock_response),
        ):
            result = confluence_api.update_page_properties("12345", 1, "page", "Title")

        assert result is None


class TestDownloadAttachmentWithRequests:
    """Tests for download_attachment with mocked requests."""

    def test_downloads_successfully(self, mock_confluence, tmp_path):
        """Downloads attachment via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.content = b"file content"

        dest = tmp_path / "downloaded.txt"

        with (
            patch("zaira.confluence_api.load_credentials", return_value={"email": "user", "api_token": "token"}),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.download_attachment(
                "https://confluence.example.com/download/123",
                dest
            )

        assert result is True
        assert dest.read_bytes() == b"file content"

    def test_returns_false_on_error(self, mock_confluence, tmp_path):
        """Returns False when download fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        dest = tmp_path / "failed.txt"

        with (
            patch("zaira.confluence_api.load_credentials", return_value={"email": "user", "api_token": "token"}),
            patch("requests.get", return_value=mock_response),
        ):
            result = confluence_api.download_attachment("https://example.com/fail", dest)

        assert result is False


class TestUpdateAttachmentWithRequests:
    """Tests for update_attachment with mocked requests."""

    def test_updates_successfully(self, mock_confluence, tmp_path):
        """Updates attachment via API."""
        from unittest.mock import patch, MagicMock

        test_file = tmp_path / "updated.txt"
        test_file.write_text("new content")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": "att456", "title": "updated.txt"}

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response),
        ):
            result = confluence_api.update_attachment("12345", "att456", test_file)

        assert result["id"] == "att456"

    def test_returns_none_on_error(self, mock_confluence, tmp_path):
        """Returns None when update fails."""
        from unittest.mock import patch, MagicMock

        test_file = tmp_path / "failed.txt"
        test_file.write_text("content")

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.post", return_value=mock_response),
        ):
            result = confluence_api.update_attachment("12345", "att456", test_file)

        assert result is None


class TestRemovePageLabelWithRequests:
    """Tests for remove_page_label with mocked requests."""

    def test_removes_successfully(self, mock_confluence):
        """Removes label via API."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = True

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.delete", return_value=mock_response),
        ):
            result = confluence_api.remove_page_label("12345", "old-label")

        assert result is True

    def test_returns_false_on_error(self, mock_confluence):
        """Returns False when removal fails."""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.ok = False

        with (
            patch("zaira.confluence_api._get_auth", return_value=("https://base", MagicMock())),
            patch("requests.delete", return_value=mock_response),
        ):
            result = confluence_api.remove_page_label("12345", "label")

        assert result is False
