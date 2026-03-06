"""Utility functions."""

import difflib


def fuzzy_match(query: str, choices: list[str], n: int = 5) -> list[str]:
    """Fuzzy match a query string against a list of choices.

    Uses difflib.get_close_matches for similarity matching with a cutoff of 0.6.

    Args:
        query: String to search for
        choices: List of choices to match against
        n: Maximum number of matches to return (default: 5)

    Returns:
        List of matching choices, ordered by similarity
    """
    return difflib.get_close_matches(query, choices, n=n, cutoff=0.6)
