"""Install Claude Code skills bundled with zaira."""

import shutil
import sys
from importlib.resources import files
from pathlib import Path


def install_skills_command(args) -> None:
    skills_dir = (
        Path(args.skills_dir) if args.skills_dir else Path.home() / ".claude" / "skills"
    )
    src = files("zaira") / "skills" / "zaira"
    dest = skills_dir / "zaira"
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        dest_file = dest / item.name
        with item.open("rb") as f:
            dest_file.write_bytes(f.read())
        print(f"Installed {dest_file}")
    print(f"Skills installed to {dest}")
