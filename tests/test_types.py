"""Tests for types module utility functions."""

from unittest.mock import MagicMock

import pytest

from zaira.types import get_user_identifier, yaml_quote


class TestGetUserIdentifier:
    """Tests for get_user_identifier function."""

    def test_returns_none_for_none(self):
        """Returns None for None input."""
        assert get_user_identifier(None) is None

    def test_returns_none_for_empty(self):
        """Returns None for empty/falsy input."""
        assert get_user_identifier("") is None
        assert get_user_identifier([]) is None

    def test_prefers_email_address(self):
        """Prefers emailAddress over other attributes."""
        user = MagicMock()
        user.emailAddress = "user@example.com"
        user.displayName = "User Name"
        user.name = "username"
        user.accountId = "12345"

        result = get_user_identifier(user)
        assert result == "user@example.com"

    def test_falls_back_to_display_name(self):
        """Falls back to displayName when no email."""
        user = MagicMock()
        user.emailAddress = None
        user.displayName = "John Doe"
        user.name = "jdoe"

        result = get_user_identifier(user)
        assert result == "John Doe"

    def test_falls_back_to_name(self):
        """Falls back to name when no email or displayName."""
        user = MagicMock()
        user.emailAddress = None
        user.displayName = None
        user.name = "jdoe"

        result = get_user_identifier(user)
        assert result == "jdoe"

    def test_falls_back_to_account_id(self):
        """Falls back to accountId when other fields unavailable."""
        user = MagicMock()
        user.emailAddress = None
        user.displayName = None
        user.name = None
        user.accountId = "5f1234567890abcdef123456"

        result = get_user_identifier(user)
        assert result == "5f1234567890abcdef123456"

    def test_returns_unknown_when_no_attributes(self):
        """Returns 'Unknown' when no attributes available."""
        user = MagicMock()
        user.emailAddress = None
        user.displayName = None
        user.name = None
        user.accountId = None

        result = get_user_identifier(user)
        assert result == "Unknown"

    def test_handles_attribute_errors(self):
        """Handles objects missing attributes gracefully."""
        user = object()  # Has no attributes

        result = get_user_identifier(user)
        assert result == "Unknown"


class TestYamlQuote:
    """Tests for yaml_quote function."""

    def test_simple_string_unchanged(self):
        """Simple strings without special characters are unchanged."""
        assert yaml_quote("hello") == "hello"
        assert yaml_quote("Simple text") == "Simple text"
        assert yaml_quote("NoSpecialChars123") == "NoSpecialChars123"

    def test_quotes_colon(self):
        """Strings with colons are quoted."""
        result = yaml_quote("key: value")
        assert result == '"key: value"'

    def test_quotes_brackets(self):
        """Strings with brackets are quoted."""
        assert yaml_quote("[item]") == '"[item]"'
        assert yaml_quote("{key}") == '"{key}"'

    def test_quotes_ampersand(self):
        """Strings with ampersand are quoted."""
        assert yaml_quote("a & b") == '"a & b"'

    def test_quotes_asterisk(self):
        """Strings with asterisk are quoted."""
        assert yaml_quote("*important") == '"*important"'

    def test_quotes_hash(self):
        """Strings with hash are quoted."""
        assert yaml_quote("# comment") == '"# comment"'

    def test_quotes_question_mark(self):
        """Strings with question mark are quoted."""
        assert yaml_quote("is this?") == '"is this?"'

    def test_quotes_pipe(self):
        """Strings with pipe are quoted."""
        assert yaml_quote("a | b") == '"a | b"'

    def test_quotes_dash(self):
        """Strings with dash are quoted."""
        assert yaml_quote("- item") == '"- item"'

    def test_quotes_comparison_operators(self):
        """Strings with comparison operators are quoted."""
        assert yaml_quote("a > b") == '"a > b"'
        assert yaml_quote("a < b") == '"a < b"'
        assert yaml_quote("a = b") == '"a = b"'

    def test_quotes_exclamation(self):
        """Strings with exclamation are quoted."""
        assert yaml_quote("!important") == '"!important"'

    def test_quotes_percent(self):
        """Strings with percent are quoted."""
        assert yaml_quote("50%") == '"50%"'

    def test_quotes_at_symbol(self):
        """Strings with @ are quoted."""
        assert yaml_quote("@mention") == '"@mention"'

    def test_quotes_backslash(self):
        """Strings with backslash are quoted."""
        assert yaml_quote("path\\to\\file") == '"path\\to\\file"'

    def test_quotes_existing_quotes(self):
        """Strings with quotes are quoted and escaped."""
        result = yaml_quote('say "hello"')
        assert result == '"say \\"hello\\""'

    def test_quotes_newlines(self):
        """Strings with newlines are quoted."""
        result = yaml_quote("line1\nline2")
        assert result == '"line1\nline2"'

    def test_empty_string_unchanged(self):
        """Empty string is unchanged."""
        assert yaml_quote("") == ""
