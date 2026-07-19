"""Tests for skill management module."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sandboxctl.skill import (
    get_skills_dir,
    install_skill,
    list_skills,
    parse_skill_frontmatter,
    remove_skill,
    update_skill,
    validate_skill,
)


def test_parse_skill_frontmatter_sandbox_network_debug() -> None:
    """Parse the real sandbox-network-debug SKILL.md."""
    skill_path = Path("/sandbox/skills_external/sandbox-network-debug/SKILL.md")
    meta = parse_skill_frontmatter(skill_path)
    assert meta.name == "sandbox-network-debug"
    assert meta.description.startswith("Diagnose and fix")


def test_parse_skill_frontmatter_sandbox_policy_lint() -> None:
    """Parse the real sandbox-policy-lint SKILL.md."""
    skill_path = Path("/sandbox/skills_external/sandbox-policy-lint/SKILL.md")
    meta = parse_skill_frontmatter(skill_path)
    assert meta.name == "sandbox-policy-lint"


def test_parse_skill_frontmatter_full(tmp_path: Path) -> None:
    """Parse SKILL.md with all frontmatter fields."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        """---
name: test-skill
description: Test skill description
version: 1.2.3
author: Test Author
license: MIT
tags:
  - testing
  - demo
requires: ">=1.0.0"
dependencies:
  - other-skill
hooks:
  on_create: echo create
  on_delete: echo delete
---

# Test Skill

Content here.
"""
    )
    meta = parse_skill_frontmatter(skill_md)
    assert meta.name == "test-skill"
    assert meta.description == "Test skill description"
    assert meta.version == "1.2.3"
    assert meta.author == "Test Author"
    assert meta.license == "MIT"
    assert meta.tags == ["testing", "demo"]
    assert meta.requires == ">=1.0.0"
    assert meta.dependencies == ["other-skill"]
    assert meta.hooks.on_create == "echo create"
    assert meta.hooks.on_delete == "echo delete"


def test_parse_skill_frontmatter_missing_name(tmp_path: Path) -> None:
    """Parse SKILL.md missing required name field."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        """---
description: Test skill
---

Content.
"""
    )
    with pytest.raises(ValueError, match="name"):
        parse_skill_frontmatter(skill_md)


def test_parse_skill_frontmatter_missing_description(tmp_path: Path) -> None:
    """Parse SKILL.md missing required description field."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        """---
name: test-skill
---

Content.
"""
    )
    with pytest.raises(ValueError, match="description"):
        parse_skill_frontmatter(skill_md)


def test_parse_skill_frontmatter_invalid_version(tmp_path: Path) -> None:
    """Parse SKILL.md with invalid semver version."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        """---
name: test-skill
description: Test
version: not-semver
---

Content.
"""
    )
    with pytest.raises(ValueError):
        parse_skill_frontmatter(skill_md)


def test_parse_skill_frontmatter_no_frontmatter(tmp_path: Path) -> None:
    """Parse file without frontmatter delimiters."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("# Just a markdown file\n\nNo frontmatter.")
    with pytest.raises(ValueError, match="frontmatter"):
        parse_skill_frontmatter(skill_md)


def test_parse_skill_frontmatter_backward_compat_no_version(tmp_path: Path) -> None:
    """Parse SKILL.md with only name and description (backward compat)."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        """---
name: legacy-skill
description: Legacy skill without version
---

Content.
"""
    )
    meta = parse_skill_frontmatter(skill_md)
    assert meta.name == "legacy-skill"
    assert meta.description == "Legacy skill without version"
    assert meta.version == ""


def test_validate_skill_valid(tmp_path: Path) -> None:
    """Validate a valid skill directory."""
    skill_dir = tmp_path / "valid-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: valid-skill
description: Valid test skill
---

Content.
"""
    )
    errors = validate_skill(skill_dir)
    assert errors == []


def test_validate_skill_missing_skill_md(tmp_path: Path) -> None:
    """Validate skill directory missing SKILL.md."""
    skill_dir = tmp_path / "invalid-skill"
    skill_dir.mkdir()
    errors = validate_skill(skill_dir)
    assert any("SKILL.md not found" in err for err in errors)


def test_validate_skill_missing_required_fields(tmp_path: Path) -> None:
    """Validate SKILL.md with missing required fields."""
    skill_dir = tmp_path / "incomplete-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: incomplete-skill
---

Missing description.
"""
    )
    errors = validate_skill(skill_dir)
    assert len(errors) > 0


def test_validate_skill_nonexistent_references(tmp_path: Path) -> None:
    """Validate SKILL.md referencing nonexistent references/ directory."""
    skill_dir = tmp_path / "skill-with-refs"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: skill-with-refs
description: Skill referencing nonexistent references
---

See @references/file.yaml for details.
"""
    )
    errors = validate_skill(skill_dir)
    # Should have a warning about missing references/ directory
    assert any("references" in err.lower() for err in errors)


def test_get_skills_dir() -> None:
    """get_skills_dir returns ~/.claude/skills."""
    expected = Path.home() / ".claude" / "skills"
    assert get_skills_dir() == expected


def test_list_skills_empty(tmp_path: Path) -> None:
    """List skills from empty directory."""
    skills = list_skills(skills_dir=tmp_path)
    assert skills == []


def test_list_skills(tmp_path: Path) -> None:
    """List installed skills."""
    # Create two skill directories
    skill1 = tmp_path / "skill-a"
    skill1.mkdir()
    (skill1 / "SKILL.md").write_text(
        """---
name: skill-a
description: First skill
---

Content.
"""
    )

    skill2 = tmp_path / "skill-b"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text(
        """---
name: skill-b
description: Second skill
---

Content.
"""
    )

    # Create a directory without SKILL.md (should be skipped)
    (tmp_path / "not-a-skill").mkdir()

    skills = list_skills(skills_dir=tmp_path)
    assert len(skills) == 2
    assert skills[0].name == "skill-a"
    assert skills[1].name == "skill-b"


def test_install_skill_basic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a skill from git URL."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Create a fake cloned directory
    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:  # noqa: ARG001
        # Simulate git clone by creating the target directory
        if cmd[0] == "git" and cmd[1] == "clone":
            clone_dir = Path(cmd[3])
            clone_dir.mkdir(parents=True, exist_ok=True)
            (clone_dir / "SKILL.md").write_text(
                """---
name: test-skill
description: Test skill from git
version: 1.0.0
---

Content.
"""
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)

    meta, warnings = install_skill("https://github.com/test/skill.git", skills_dir=skills_dir)
    assert meta.name == "test-skill"
    assert (skills_dir / "test-skill" / "SKILL.md").exists()
    assert warnings == []


def test_install_skill_no_skill_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install from repo with no SKILL.md raises ValueError."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:  # noqa: ARG001
        if cmd[0] == "git" and cmd[1] == "clone":
            clone_dir = Path(cmd[3])
            clone_dir.mkdir(parents=True, exist_ok=True)
            # No SKILL.md created
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(ValueError, match="no SKILL.md"):
        install_skill("https://github.com/test/no-skill.git", skills_dir=skills_dir)


def test_install_skill_already_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install when skill already exists raises FileExistsError."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Pre-create the skill directory
    (skills_dir / "test-skill").mkdir()

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:  # noqa: ARG001
        if cmd[0] == "git" and cmd[1] == "clone":
            clone_dir = Path(cmd[3])
            clone_dir.mkdir(parents=True, exist_ok=True)
            (clone_dir / "SKILL.md").write_text(
                """---
name: test-skill
description: Test
---

Content.
"""
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(FileExistsError, match="already installed"):
        install_skill("https://github.com/test/skill.git", skills_dir=skills_dir)


def test_install_skill_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install with force=True overwrites existing skill."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Pre-create the skill directory with old content
    old_skill = skills_dir / "test-skill"
    old_skill.mkdir()
    (old_skill / "old-file.txt").write_text("old content")

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:  # noqa: ARG001
        if cmd[0] == "git" and cmd[1] == "clone":
            clone_dir = Path(cmd[3])
            clone_dir.mkdir(parents=True, exist_ok=True)
            (clone_dir / "SKILL.md").write_text(
                """---
name: test-skill
description: Updated skill
version: 2.0.0
---

Content.
"""
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)

    meta, warnings = install_skill("https://github.com/test/skill.git", skills_dir=skills_dir, force=True)
    assert meta.name == "test-skill"
    assert meta.version == "2.0.0"
    assert not (skills_dir / "test-skill" / "old-file.txt").exists()
    assert (skills_dir / "test-skill" / "SKILL.md").exists()
    assert warnings == []


def test_install_skill_missing_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Install skill with missing dependencies returns warnings."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:  # noqa: ARG001
        if cmd[0] == "git" and cmd[1] == "clone":
            clone_dir = Path(cmd[3])
            clone_dir.mkdir(parents=True, exist_ok=True)
            (clone_dir / "SKILL.md").write_text(
                """---
name: test-skill
description: Test
dependencies:
  - missing-skill
  - another-missing-skill
---

Content.
"""
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)

    meta, warnings = install_skill("https://github.com/test/skill.git", skills_dir=skills_dir)
    assert len(warnings) == 2
    assert any("missing-skill" in w for w in warnings)
    assert any("another-missing-skill" in w for w in warnings)


def test_remove_skill(tmp_path: Path) -> None:
    """Remove an installed skill."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test
---

Content.
"""
    )

    result = remove_skill("test-skill", skills_dir=skills_dir)
    assert result is True
    assert not skill_dir.exists()


def test_remove_skill_not_found(tmp_path: Path) -> None:
    """Remove nonexistent skill returns False."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    result = remove_skill("nonexistent-skill", skills_dir=skills_dir)
    assert result is False


def test_remove_skill_with_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove skill with on_delete hook."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test
hooks:
  on_delete: echo cleanup
---

Content.
"""
    )

    # Mock subprocess.run to capture hook execution
    run_calls = []

    def mock_run(cmd: str | list[str], **kwargs: object) -> subprocess.CompletedProcess:
        run_calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd if isinstance(cmd, list) else [cmd], 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)

    result = remove_skill("test-skill", skills_dir=skills_dir)
    assert result is True
    assert not skill_dir.exists()
    # Verify hook was called
    assert any("echo cleanup" in str(call[0]) for call in run_calls)


def test_update_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Update a skill via git pull."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / ".git").mkdir()  # Make it look like a git repo
    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test skill
version: 1.0.0
---

Content.
"""
    )

    def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:  # noqa: ARG001
        # Simulate git pull by updating the SKILL.md
        if cmd[0] == "git" and cmd[1] == "pull":
            cwd = kwargs.get("cwd")
            if cwd:
                skill_md = Path(cwd) / "SKILL.md"
                skill_md.write_text(
                    """---
name: test-skill
description: Updated test skill
version: 2.0.0
---

Updated content.
"""
                )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", mock_run)

    meta = update_skill("test-skill", skills_dir=skills_dir)
    assert meta.name == "test-skill"
    assert meta.version == "2.0.0"
    assert meta.description == "Updated test skill"


def test_update_skill_not_found(tmp_path: Path) -> None:
    """Update nonexistent skill raises FileNotFoundError."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        update_skill("nonexistent-skill", skills_dir=skills_dir)


def test_update_skill_not_git_repo(tmp_path: Path) -> None:
    """Update skill that is not a git repo raises ValueError."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill_dir = skills_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: test-skill
description: Test
---

Content.
"""
    )
    # No .git directory

    with pytest.raises(ValueError, match="Not a git repository"):
        update_skill("test-skill", skills_dir=skills_dir)
