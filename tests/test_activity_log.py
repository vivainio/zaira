"""Tests for the activity log."""

import json
from pathlib import Path

from zaira import activity_log
from zaira.jira_client import token_fingerprint


def test_record_writes_to_isolated_log(isolated_activity_log: Path) -> None:
    """Tests must never touch the user's real activity log."""
    real_log = Path.home() / ".cache" / "zaira" / "activity.log"
    assert activity_log.LOG_FILE == isolated_activity_log
    assert activity_log.LOG_FILE != real_log

    activity_log.record("edit", "TEST-1", "title")

    entry = json.loads(isolated_activity_log.read_text())
    assert entry["key"] == "TEST-1"
    assert entry["token"] == "test0000"


def test_format_entries_shows_token() -> None:
    out = activity_log.format_entries(
        [
            {
                "ts": "2026-01-01T00:00:00Z",
                "op": "edit",
                "key": "A-1",
                "token": "abcd1234",
            }
        ]
    )
    assert "[token abcd1234]" in out


def test_token_fingerprint_is_stable_8_hex() -> None:
    fp = token_fingerprint("secret")
    assert fp == token_fingerprint("secret")
    assert len(fp) == 8
    assert fp != token_fingerprint("other")
    assert "secret" not in fp
