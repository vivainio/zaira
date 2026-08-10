"""Tests for the Xray Cloud integration."""

import argparse
from unittest.mock import MagicMock, call, patch

import pytest

from zaira import xray


class TestCredentials:
    def test_wincred_uses_distinct_targets(self) -> None:
        with (
            patch.object(xray.wincred, "is_wsl", return_value=True),
            patch.object(xray.wincred, "set_password") as set_password,
        ):
            xray.save_credentials("client-id", "client-secret")

        assert set_password.call_args_list == [
            call(xray.XRAY_CLIENT_ID_TARGET, "xray", "client-id"),
            call(xray.XRAY_CLIENT_SECRET_TARGET, "xray", "client-secret"),
        ]

    def test_load_credentials_requires_both_values(self) -> None:
        with (
            patch.object(xray.wincred, "is_wsl", return_value=True),
            patch.object(xray.wincred, "get_password", side_effect=["client-id", None]),
            pytest.raises(xray.XrayCredentialsNotConfigured),
        ):
            xray.load_credentials()


class TestApi:
    def test_authenticate_returns_token(self) -> None:
        response = MagicMock()
        response.json.return_value = "jwt-token"
        with patch.object(xray.requests, "post", return_value=response) as post:
            result = xray.authenticate("client-id", "client-secret")

        assert result == "jwt-token"
        post.assert_called_once_with(
            f"{xray.XRAY_BASE_URL}/authenticate",
            json={"client_id": "client-id", "client_secret": "client-secret"},
            timeout=30,
        )

    def test_fetch_test_steps_uses_graphql_variables(self) -> None:
        response = MagicMock()
        response.json.return_value = {
            "data": {
                "getTests": {
                    "results": [
                        {
                            "steps": [
                                {
                                    "id": "1",
                                    "action": "Open page",
                                    "data": "Example",
                                    "result": "Page opens",
                                }
                            ]
                        }
                    ]
                }
            }
        }
        with patch.object(xray.requests, "post", return_value=response) as post:
            result = xray.fetch_test_steps("TEST-1", "jwt-token")

        assert result[0]["action"] == "Open page"
        request = post.call_args.kwargs
        assert request["json"]["variables"] == {"jql": 'key = "TEST-1"'}
        assert request["headers"] == {"Authorization": "Bearer jwt-token"}

    def test_fetch_definition_includes_all_test_kinds(self) -> None:
        response = MagicMock()
        response.json.return_value = {
            "data": {
                "getTests": {
                    "results": [
                        {
                            "testType": {"name": "Cucumber", "kind": "Gherkin"},
                            "steps": [],
                            "gherkin": "Scenario: Example",
                            "unstructured": None,
                        }
                    ]
                }
            }
        }
        with patch.object(xray.requests, "post", return_value=response):
            result = xray.fetch_test_definition("TEST-1", "jwt-token")

        assert result["testType"]["kind"] == "Gherkin"
        assert result["gherkin"] == "Scenario: Example"

    def test_add_steps_authenticates_once(self) -> None:
        tests = [{"key": "TEST-1"}, {"key": "TEST-2"}]
        with (
            patch.object(xray, "load_credentials", return_value=("id", "secret")),
            patch.object(xray, "authenticate", return_value="token") as authenticate,
            patch.object(
                xray,
                "fetch_test_steps",
                side_effect=[[{"id": "1"}], [{"id": "2"}]],
            ),
        ):
            xray.add_steps(tests)

        authenticate.assert_called_once_with("id", "secret")
        assert tests[0]["steps"] == [{"id": "1"}]
        assert tests[1]["steps"] == [{"id": "2"}]


class TestInitCommand:
    def test_prompts_and_stores_credentials_on_wsl(self) -> None:
        with (
            patch.object(xray.wincred, "is_wsl", return_value=True),
            patch.object(xray.wincred, "backend_info", return_value=("v1", "path")),
            patch("builtins.input", side_effect=["client-id", "client-secret"]),
            patch.object(xray, "save_credentials") as save_credentials,
        ):
            xray.init_xray_command(argparse.Namespace())

        save_credentials.assert_called_once_with("client-id", "client-secret")


class TestMarkdown:
    ticket = {
        "key": "TEST-1",
        "summary": "Example test",
        "issuetype": "Test",
        "status": "Ready",
        "assignee": "qa@example.com",
        "reporter": "author@example.com",
        "description": "Test description",
    }

    def test_formats_manual_steps_as_table(self) -> None:
        definition = {
            "testType": {"name": "Manual", "kind": "Steps"},
            "steps": [
                {
                    "action": "Open | page",
                    "data": "First\nline",
                    "result": "Page opens",
                }
            ],
        }
        with patch("zaira.jira_client.get_jira_site", return_value="jira.example.com"):
            result = xray.format_test_markdown(
                self.ticket, definition, "2026-08-10T12:00:00"
            )

        assert "test_type: Manual" in result
        assert "## Steps" in result
        assert "| 1 | Open \\| page | First<br>line | Page opens |" in result

    def test_formats_gherkin_in_fenced_block(self) -> None:
        definition = {
            "testType": {"name": "Cucumber", "kind": "Gherkin"},
            "gherkin": "Scenario: Example\n  Given a condition",
        }
        with patch("zaira.jira_client.get_jira_site", return_value="jira.example.com"):
            result = xray.format_test_markdown(
                self.ticket, definition, "2026-08-10T12:00:00"
            )

        assert "test_type: Cucumber" in result
        assert "```gherkin\nScenario: Example\n  Given a condition\n```" in result

    def test_formats_unstructured_definition(self) -> None:
        definition = {
            "testType": {"name": "Generic", "kind": "Unstructured"},
            "unstructured": "Run the automated test suite.",
        }
        with patch("zaira.jira_client.get_jira_site", return_value="jira.example.com"):
            result = xray.format_test_markdown(
                self.ticket, definition, "2026-08-10T12:00:00"
            )

        assert "## Definition\n\nRun the automated test suite." in result


class TestExtractCommand:
    def test_writes_standalone_markdown_file(self, tmp_path) -> None:
        args = argparse.Namespace(keys=["test-1"], output=str(tmp_path))
        ticket = {
            "key": "TEST-1",
            "summary": "Manual test",
            "issuetype": "Test",
            "status": "Ready",
            "assignee": "qa@example.com",
            "reporter": "author@example.com",
            "description": "Description",
        }
        definition = {
            "testType": {"name": "Manual", "kind": "Steps"},
            "steps": [],
        }
        with (
            patch.object(xray, "load_credentials", return_value=("id", "secret")),
            patch.object(xray, "authenticate", return_value="token"),
            patch.object(xray, "fetch_test_definition", return_value=definition),
            patch("zaira.export.get_ticket", return_value=ticket),
            patch("zaira.jira_client.get_jira_site", return_value="jira.example.com"),
        ):
            xray.extract_command(args)

        output = tmp_path / "TEST-1.md"
        assert output.exists()
        assert "# TEST-1: Manual test" in output.read_text()
        assert "_No manual steps._" in output.read_text()
