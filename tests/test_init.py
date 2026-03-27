"""Tests for init module."""

from unittest.mock import MagicMock


from zaira.init import (
    slugify,
    generate_config,
    discover_components,
    discover_labels,
    discover_boards,
)


class TestSlugify:
    """Tests for slugify function (pure)."""

    def test_lowercase(self):
        """Converts to lowercase."""
        assert slugify("Hello World") == "hello-world"

    def test_replaces_spaces(self):
        """Replaces spaces with hyphens."""
        assert slugify("my board name") == "my-board-name"

    def test_removes_parentheses(self):
        """Removes parentheses."""
        assert slugify("Board (Scrum)") == "board-scrum"

    def test_combined(self):
        """Handles combined cases."""
        assert slugify("My Project (Dev)") == "my-project-dev"

    def test_strips_ampersand(self):
        """Strips & and other special chars that break TOML bare keys."""
        assert slugify("DevOps Epics & Studies") == "devops-epics-studies"

    def test_strips_special_characters(self):
        """Strips all non-alphanumeric/dash/underscore characters."""
        assert slugify("Board #1 @test!") == "board-1-test"


class TestGenerateConfig:
    """Tests for generate_config function (pure)."""

    def test_basic_config(self):
        """Generates basic config structure."""
        result = generate_config(
            projects=["TEST"],
            all_boards={},
            all_components={},
        )

        assert "[project]" not in result
        assert "[boards]" in result
        assert "[queries]" in result

    def test_includes_boards(self):
        """Includes boards in config."""
        result = generate_config(
            projects=["PROJ"],
            all_boards={
                "PROJ": [
                    {"id": 123, "name": "Kanban Board", "type": "kanban"},
                    {"id": 456, "name": "Sprint Board", "type": "scrum"},
                ]
            },
            all_components={},
        )

        assert "kanban-board = 123" in result
        assert "sprint-board = 456" in result

    def test_no_boards_placeholder(self):
        """Shows placeholder when no boards."""
        result = generate_config(
            projects=["TEST"],
            all_boards={},
            all_components={},
        )

        assert "# No boards found" in result

    def test_multiple_projects(self):
        """Handles multiple projects."""
        result = generate_config(
            projects=["PROJ1", "PROJ2"],
            all_boards={},
            all_components={
                "PROJ1": ["Backend", "Frontend"],
                "PROJ2": ["API"],
            },
        )

        assert "PROJ1" in result
        assert "PROJ2" in result

    def test_no_duplicate_board_keys(self):
        """Deduplicates board keys when projects share board names."""
        result = generate_config(
            projects=["P1", "P2"],
            all_boards={
                "P1": [{"id": 100, "name": "Kanban", "type": "kanban"}],
                "P2": [{"id": 200, "name": "Kanban", "type": "kanban"}],
            },
            all_components={},
        )

        assert "kanban = 100" in result
        assert "kanban-2 = 200" in result

    def test_no_duplicate_report_keys(self):
        """Deduplicates report keys when projects share board names."""
        result = generate_config(
            projects=["P1", "P2"],
            all_boards={
                "P1": [{"id": 100, "name": "Board", "type": "kanban"}],
                "P2": [{"id": 200, "name": "Board", "type": "scrum"}],
            },
            all_components={},
        )

        # Reports section should have deduplicated keys
        lines = result.split("\n")
        report_keys = []
        in_reports = False
        for line in lines:
            if line == "[reports]":
                in_reports = True
                continue
            if in_reports and line.startswith("["):
                break
            if in_reports and "=" in line and not line.startswith("#"):
                key = line.split("=")[0].strip()
                report_keys.append(key)

        assert len(report_keys) == len(set(report_keys)), (
            f"Duplicate report keys found: {report_keys}"
        )

    def test_valid_toml_output(self):
        """Generated config is valid TOML."""
        import tomllib

        result = generate_config(
            projects=["P1", "P2"],
            all_boards={
                "P1": [{"id": 100, "name": "Kanban", "type": "kanban"}],
                "P2": [{"id": 200, "name": "Kanban", "type": "kanban"}],
            },
            all_components={
                "P1": ["API", "Backend"],
                "P2": ["API"],
            },
        )

        # Should not raise
        tomllib.loads(result)


class TestDiscoverComponents:
    """Tests for discover_components with mocked Jira."""

    def test_returns_component_names(self, mock_jira):
        """Returns sorted list of component names."""
        mock_proj = MagicMock()
        mock_jira.project.return_value = mock_proj

        comp1 = MagicMock()
        comp1.name = "Backend"
        comp2 = MagicMock()
        comp2.name = "API"
        comp3 = MagicMock()
        comp3.name = "Frontend"

        mock_jira.project_components.return_value = [comp1, comp2, comp3]

        result = discover_components("TEST")

        assert result == ["API", "Backend", "Frontend"]  # sorted

    def test_filters_empty_names(self, mock_jira):
        """Filters out components with empty names."""
        mock_proj = MagicMock()
        mock_jira.project.return_value = mock_proj

        comp1 = MagicMock()
        comp1.name = "Valid"
        comp2 = MagicMock()
        comp2.name = ""
        comp3 = MagicMock()
        comp3.name = None

        mock_jira.project_components.return_value = [comp1, comp2, comp3]

        result = discover_components("TEST")

        assert result == ["Valid"]

    def test_returns_empty_on_error(self, mock_jira):
        """Returns empty list on error."""
        mock_jira.project.side_effect = Exception("Not found")

        result = discover_components("INVALID")

        assert result == []


class TestDiscoverLabels:
    """Tests for discover_labels with mocked Jira."""

    def test_returns_labels_from_issues(self, mock_jira):
        """Returns sorted unique labels from issues."""
        issue1 = MagicMock()
        issue1.fields.labels = ["bug", "urgent"]
        issue2 = MagicMock()
        issue2.fields.labels = ["bug", "feature"]
        issue3 = MagicMock()
        issue3.fields.labels = []

        mock_jira.search_issues.return_value = [issue1, issue2, issue3]

        result = discover_labels("TEST")

        assert result == ["bug", "feature", "urgent"]  # sorted, unique

    def test_handles_none_labels(self, mock_jira):
        """Handles issues with None labels."""
        issue1 = MagicMock()
        issue1.fields.labels = None

        mock_jira.search_issues.return_value = [issue1]

        result = discover_labels("TEST")

        assert result == []

    def test_returns_empty_on_error(self, mock_jira):
        """Returns empty list on error."""
        mock_jira.search_issues.side_effect = Exception("Error")

        result = discover_labels("TEST")

        assert result == []


class TestDiscoverBoards:
    """Tests for discover_boards with mocked Jira."""

    def test_returns_board_info(self, mock_jira):
        """Returns list of board dicts."""
        board1 = MagicMock()
        board1.id = 100
        board1.name = "Kanban"
        board1.type = "kanban"

        board2 = MagicMock()
        board2.id = 200
        board2.name = "Scrum"
        board2.type = "scrum"

        mock_jira.boards.return_value = [board1, board2]

        result = discover_boards("TEST")

        assert len(result) == 2
        assert result[0] == {"id": 100, "name": "Kanban", "type": "kanban"}
        assert result[1] == {"id": 200, "name": "Scrum", "type": "scrum"}

    def test_returns_empty_on_error(self, mock_jira):
        """Returns empty list on error."""
        mock_jira.boards.side_effect = Exception("Error")

        result = discover_boards("TEST")

        assert result == []
