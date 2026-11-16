"""Tests for WSL detection and wincred.exe discovery."""

from pathlib import Path
from unittest.mock import patch

import pytest

from zaira import wincred


def test_is_wsl_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WSL_INTEROP", "/run/WSL/1_interop")
    assert wincred.is_wsl()


def test_is_wsl_falls_back_to_kernel_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Launchers like herdr don't pass WSL_* env vars through."""
    monkeypatch.delenv("WSL_INTEROP", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    release = tmp_path / "osrelease"
    release.write_text("6.18.58.1-microsoft-standard-WSL2\n")
    with patch.object(wincred, "Path", side_effect=lambda *_a: release):
        assert wincred.is_wsl()
    release.write_text("6.8.0-generic\n")
    with patch.object(wincred, "Path", side_effect=lambda *_a: release):
        assert not wincred.is_wsl()


def test_find_binary_uses_windows_profile_from_cmd_exe(tmp_path: Path) -> None:
    exe = tmp_path / ".local" / "bin" / "wincred.exe"
    exe.parent.mkdir(parents=True)
    exe.touch()
    with (
        patch.object(wincred.shutil, "which", return_value=None),
        patch.object(wincred, "_windows_profile_dir", return_value=tmp_path),
    ):
        assert wincred.find_binary() == str(exe)


def test_find_binary_none_when_profile_unknown() -> None:
    with (
        patch.object(wincred.shutil, "which", return_value=None),
        patch.object(wincred, "_windows_profile_dir", return_value=None),
    ):
        assert wincred.find_binary() is None
