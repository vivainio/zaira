"""Windows Credential Manager backend for WSL.

Wraps the `wincred.exe` CLI (https://github.com/vivainio/wincred) so zaira can
store its Jira API token in the Windows Credential Manager when running under
WSL, instead of the Linux keyring (which typically isn't a real secret store
on WSL distros).
"""

import os
import shutil
import subprocess

WINCRED_BINARY = "wincred.exe"
INSTALL_URL = "https://github.com/vivainio/wincred/releases/latest/download/wincred.exe"
INSTALL_HINT = (
    f"wincred.exe is required to use the Windows Credential Manager from WSL.\n"
    f"\n"
    f"Install it from PowerShell on the Windows side:\n"
    f"\n"
    f"    iwr {INSTALL_URL} -OutFile $HOME\\.local\\bin\\wincred.exe\n"
)


class WincredNotInstalled(RuntimeError):
    """Raised when wincred.exe cannot be found on PATH while running on WSL."""

    def __init__(self) -> None:
        super().__init__(INSTALL_HINT)


def is_wsl() -> bool:
    """Return True when running on WSL with Windows interop enabled."""
    return bool(os.environ.get("WSL_INTEROP"))


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [WINCRED_BINARY, *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise WincredNotInstalled() from e


def get_password(service: str, username: str) -> str | None:
    """Return the secret stored under `service`, or None if not stored.

    The `username` argument is accepted for keyring API parity, but the lookup
    is by service only — Windows Credential Manager stores at most one entry
    per target name. This matches Python `keyring`'s Windows backend, so
    entries set from Windows-side zaira are visible here.
    """
    del username
    r = _run(["get", service])
    if r.returncode == 1:
        return None
    if r.returncode != 0:
        raise RuntimeError(f"wincred get failed: {r.stderr.strip()}")
    return r.stdout.rstrip("\r\n")


def set_password(service: str, username: str, password: str) -> None:
    """Store the secret in Windows Credential Manager under `service`."""
    r = _run(["set", service, "--user", username], stdin=password)
    if r.returncode != 0:
        raise RuntimeError(f"wincred set failed: {r.stderr.strip()}")


def delete_password(service: str, username: str) -> None:
    """Remove the secret. No-op if it doesn't exist."""
    del username
    r = _run(["delete", service])
    if r.returncode not in (0, 1):
        raise RuntimeError(f"wincred delete failed: {r.stderr.strip()}")


def backend_info() -> tuple[str, str] | None:
    """Return (version, path) for the installed wincred.exe, or None if missing."""
    path = shutil.which(WINCRED_BINARY)
    if not path:
        return None
    try:
        r = subprocess.run(
            [WINCRED_BINARY, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return r.stdout.strip().replace("\r", ""), path


def install() -> str:
    """Download wincred.exe to a Windows-side .local/bin found on PATH.

    Returns the version string reported by `wincred.exe --version` after install.
    Raises RuntimeError if not running on WSL or if any step fails.
    """
    import urllib.request
    from pathlib import Path

    if not is_wsl():
        raise RuntimeError("--install-wincred only runs under WSL")

    install_dir = _windows_local_bin()
    install_dir.mkdir(parents=True, exist_ok=True)
    target = install_dir / "wincred.exe"
    urllib.request.urlretrieve(INSTALL_URL, target)

    try:
        v = subprocess.run(
            [WINCRED_BINARY, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            f"wincred.exe was downloaded to {target} but isn't on PATH. "
            "Add the dir to Windows PATH (uv handles this for %USERPROFILE%\\.local\\bin)."
        ) from e
    return v.stdout.strip().replace("\r", "")


def _windows_local_bin():
    """Find a .local/bin under /mnt/c on the inherited Windows PATH.

    Raises RuntimeError if none is found — installing somewhere not on PATH
    wouldn't make wincred.exe callable anyway.
    """
    from pathlib import Path

    for entry in os.environ.get("PATH", "").split(":"):
        if entry.startswith("/mnt/") and entry.rstrip("/").lower().endswith(
            "/.local/bin"
        ):
            return Path(entry.rstrip("/"))
    raise RuntimeError(
        "No Windows-side .local/bin found on PATH. Install uv on Windows first "
        "(it adds %USERPROFILE%\\.local\\bin to PATH), or add such a directory yourself."
    )
