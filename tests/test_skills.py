"""Tests for zaira install-skills command."""

import argparse


def test_install_skills_copies_files(tmp_path):
    """install_skills_command copies SKILL.md and CONFLUENCE.md to target dir."""
    from zaira.skills import install_skills_command

    args = argparse.Namespace(skills_dir=str(tmp_path))
    install_skills_command(args)

    dest = tmp_path / "zaira"
    assert (dest / "SKILL.md").exists()
    assert (dest / "CONFLUENCE.md").exists()


def test_install_skills_creates_target_dir(tmp_path):
    """install_skills_command creates the target directory if it doesn't exist."""
    from zaira.skills import install_skills_command

    target = tmp_path / "nested" / "skills"
    args = argparse.Namespace(skills_dir=str(target))
    install_skills_command(args)

    assert (target / "zaira" / "SKILL.md").exists()


def test_install_skills_skill_md_has_name(tmp_path):
    """Installed SKILL.md contains the skill name front matter."""
    from zaira.skills import install_skills_command

    args = argparse.Namespace(skills_dir=str(tmp_path))
    install_skills_command(args)

    content = (tmp_path / "zaira" / "SKILL.md").read_text()
    assert "name: zaira" in content
