"""Bundle install/update commands for distributing rules files."""

import datetime
import io
import urllib.request
import zipfile
from pathlib import Path

import yaml

from zaira.jira_client import CONFIG_DIR

BUNDLE_META = CONFIG_DIR / "bundle.yaml"
ALLOWED_DIRS = {"rules"}


def _install_from_zip(data: bytes, source_url: str | None) -> None:
    """Validate zip contents, extract to config dir, write bundle.yaml."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()

        # Strip single top-level wrapper dir (GitHub convention)
        top_dirs = {n.split("/")[0] for n in names if n.strip("/")}
        if len(top_dirs) == 1:
            wrapper = top_dirs.pop() + "/"
            if all(n.startswith(wrapper) for n in names):
                names = [n[len(wrapper):] for n in names]

        # Determine actual top-level dirs in (possibly stripped) listing
        actual_top = {n.split("/")[0] for n in names if "/" in n and n.split("/")[0]}
        unknown = actual_top - ALLOWED_DIRS
        if unknown:
            raise SystemExit(
                f"Bundle contains unexpected directories: {unknown!r}. Only {ALLOWED_DIRS} is allowed."
            )

    # Extract, stripping wrapper prefix if present
    with zipfile.ZipFile(io.BytesIO(data)) as zf2:
        all_names = zf2.namelist()
        top_dirs2 = {n.split("/")[0] for n in all_names if n.strip("/")}
        prefix = ""
        if len(top_dirs2) == 1:
            candidate = top_dirs2.pop() + "/"
            if all(n.startswith(candidate) for n in all_names):
                prefix = candidate

        for member in zf2.infolist():
            rel = member.filename
            if prefix:
                if not rel.startswith(prefix):
                    continue
                rel = rel[len(prefix):]
            if not rel or rel.endswith("/"):
                continue  # skip dirs
            dest = CONFIG_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf2.read(member.filename))

    if source_url:
        BUNDLE_META.write_text(
            yaml.dump({"source": source_url, "installed_at": datetime.datetime.utcnow().isoformat()})
        )


def bundle_install_command(args) -> None:
    source = args.source
    if source.startswith("http://") or source.startswith("https://"):
        print(f"Downloading {source} ...")
        with urllib.request.urlopen(source) as resp:
            data = resp.read()
        _install_from_zip(data, source_url=source)
        print(f"Bundle installed from {source}")
    else:
        path = Path(source)
        if not path.exists():
            raise SystemExit(f"File not found: {path}")
        data = path.read_bytes()
        _install_from_zip(data, source_url=None)
        print(f"Bundle installed from {path}")


def bundle_update_command(args) -> None:
    if not BUNDLE_META.exists():
        raise SystemExit("No bundle installed. Run 'zaira bundle install <url>' first.")
    meta = yaml.safe_load(BUNDLE_META.read_text())
    source = meta.get("source")
    if not source:
        raise SystemExit(
            "Installed bundle has no recorded source URL (was installed from a local file)."
        )
    print(f"Re-fetching {source} ...")
    with urllib.request.urlopen(source) as resp:
        data = resp.read()
    _install_from_zip(data, source_url=source)
    print(f"Bundle updated from {source}")
