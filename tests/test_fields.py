"""Tests for field mapping and value formatting."""

from unittest.mock import patch

from zaira.create import map_fields
from zaira.edit import format_field_value, _parse_number


class TestParseNumber:
    """Tests for _parse_number function."""

    def test_parse_integer(self):
        """Parse integer string."""
        assert _parse_number("5") == 5
        assert _parse_number("0") == 0
        assert _parse_number("-10") == -10

    def test_parse_float(self):
        """Parse float string."""
        assert _parse_number("3.14") == 3.14
        assert _parse_number("0.5") == 0.5

    def test_non_numeric_unchanged(self):
        """Non-numeric strings returned unchanged."""
        assert _parse_number("hello") == "hello"
        assert _parse_number("5 points") == "5 points"


class TestFormatFieldValue:
    """Tests for format_field_value function."""

    def test_number_field_converts_string(self):
        """Numeric field converts string to number."""
        with patch("zaira.edit.get_field_type", return_value="number"):
            assert format_field_value("customfield_123", "5") == 5
            assert format_field_value("customfield_123", "3.5") == 3.5

    def test_number_field_preserves_number(self):
        """Numeric field preserves existing number."""
        with patch("zaira.edit.get_field_type", return_value="number"):
            assert format_field_value("customfield_123", 5) == 5

    def test_option_field_wraps_value(self):
        """Option field wraps value in dict."""
        with patch("zaira.edit.get_field_type", return_value="option"):
            assert format_field_value("customfield_123", "High") == {"value": "High"}

    def test_dict_value_unchanged(self):
        """Dict values are not modified."""
        with patch("zaira.edit.get_field_type", return_value="option"):
            value = {"value": "Already formatted"}
            assert format_field_value("customfield_123", value) == value

    def test_unknown_field_unchanged(self):
        """Unknown field types return value unchanged."""
        with patch("zaira.edit.get_field_type", return_value=None):
            assert format_field_value("customfield_123", "unchanged") == "unchanged"


class TestMapFieldsCreate:
    """Tests for map_fields in create module."""

    def test_custom_field_uses_format_field_value(self):
        """Custom fields are formatted using format_field_value."""
        with (
            patch("zaira.create.get_field_id", return_value="customfield_10551"),
            patch("zaira.create.format_field_value") as mock_format,
        ):
            mock_format.return_value = 5  # Converted to int

            front_matter = {"storypoints": "5"}
            result = map_fields(front_matter, "")

            # Verify format_field_value was called
            mock_format.assert_called_once_with("customfield_10551", "5")
            assert result["customfield_10551"] == 5

    def test_custom_numeric_field_converted(self):
        """Custom numeric field string is converted to number."""
        with (
            patch("zaira.create.get_field_id", return_value="customfield_10551"),
            patch("zaira.edit.get_field_type", return_value="number"),
        ):
            front_matter = {"effort": "10"}
            result = map_fields(front_matter, "")

            # Value should be converted to int
            assert result["customfield_10551"] == 10

    def test_standard_fields_not_affected(self):
        """Standard fields are handled normally."""
        front_matter = {
            "project": "TEST",
            "summary": "Test ticket",
            "priority": "High",
        }
        result = map_fields(front_matter, "Description here")

        assert result["project"] == {"key": "TEST"}
        assert result["summary"] == "Test ticket"
        assert result["priority"] == {"name": "High"}
        assert result["description"] == "Description here"
