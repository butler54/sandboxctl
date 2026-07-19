"""Skill management: parsing, installation, validation."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$")
_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class SkillHooks(BaseModel):
    """Lifecycle hooks for skill operations."""

    on_create: str = ""
    on_delete: str = ""

    model_config = {"extra": "ignore"}


class SkillMeta(BaseModel):
    """Skill metadata from SKILL.md frontmatter."""

    name: str
    description: str
    version: str = ""
    author: str = ""
    license: str = ""
    tags: list[str] = []
    requires: str = ""
    dependencies: list[str] = []
    hooks: SkillHooks = SkillHooks()

    model_config = {"extra": "ignore"}

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate version is semver if provided."""
        if v and not _SEMVER_RE.match(v):
            msg = f"Invalid semver version: {v}"
            raise ValueError(msg)
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate skill name contains only allowed characters."""
        if not _SKILL_NAME_RE.match(v):
            msg = f"Invalid skill name '{v}': must contain only alphanumeric, dots, hyphens, underscores"
            raise ValueError(msg)
        return v


def parse_skill_frontmatter(path: Path) -> SkillMeta:
    """Parse SKILL.md YAML frontmatter into SkillMeta.

    Args:
        path: Path to SKILL.md file

    Returns:
        SkillMeta object with parsed metadata

    Raises:
        ValueError: If frontmatter is missing or invalid
    """
    content = path.read_text()

    # Find frontmatter delimiters
    parts = content.split("---", 2)
    if len(parts) < 3:
        msg = "SKILL.md missing frontmatter delimiters (---)"
        raise ValueError(msg)

    # Parse YAML between first and second ---
    frontmatter_text = parts[1].strip()
    if not frontmatter_text:
        msg = "SKILL.md frontmatter is empty"
        raise ValueError(msg)

    data = yaml.safe_load(frontmatter_text)
    if not isinstance(data, dict):
        msg = "SKILL.md frontmatter must be a YAML dict"
        raise ValueError(msg)

    # Check required fields
    if "name" not in data:
        msg = "SKILL.md frontmatter missing required field: name"
        raise ValueError(msg)
    if "description" not in data:
        msg = "SKILL.md frontmatter missing required field: description"
        raise ValueError(msg)

    # Parse hooks if present
    if "hooks" in data and isinstance(data["hooks"], dict):
        data["hooks"] = SkillHooks(**data["hooks"])

    return SkillMeta(**data)


def get_skills_dir() -> Path:
    """Return the skills directory path.

    Returns:
        Path to ~/.claude/skills
    """
    return Path.home() / ".claude" / "skills"


def validate_skill(path: Path) -> list[str]:
    """Validate a skill directory against the packaging spec.

    Args:
        path: Path to skill directory

    Returns:
        List of error/warning strings (empty if valid)
    """
    errors: list[str] = []

    # Check it's a directory
    if not path.is_dir():
        errors.append(f"{path} is not a directory")
        return errors

    # Check SKILL.md exists
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        errors.append("SKILL.md not found")
        return errors

    # Parse frontmatter
    try:
        parse_skill_frontmatter(skill_md)
    except ValueError as e:
        errors.append(f"Invalid SKILL.md: {e}")
        return errors

    # Check references/ exists if mentioned in SKILL.md
    content = skill_md.read_text()
    if "@references/" in content or "references/" in content:
        refs_dir = path / "references"
        if not refs_dir.exists():
            errors.append("SKILL.md references @references/ but references/ directory does not exist")

    return errors


def list_skills(skills_dir: Path | None = None) -> list[SkillMeta]:
    """List all installed skills.

    Args:
        skills_dir: Skills directory (defaults to ~/.claude/skills)

    Returns:
        List of SkillMeta objects sorted by name
    """
    if skills_dir is None:
        skills_dir = get_skills_dir()

    if not skills_dir.exists():
        return []

    skills: list[SkillMeta] = []
    for skill_path in skills_dir.iterdir():
        if not skill_path.is_dir():
            continue
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            meta = parse_skill_frontmatter(skill_md)
            skills.append(meta)
        except ValueError:
            # Skip directories with invalid SKILL.md
            continue

    return sorted(skills, key=lambda s: s.name)


def install_skill(git_url: str, skills_dir: Path | None = None, *, force: bool = False) -> tuple[SkillMeta, list[str]]:
    """Install a skill from a git URL.

    Args:
        git_url: Git URL to clone
        skills_dir: Skills directory (defaults to ~/.claude/skills)
        force: If True, overwrite existing skill

    Returns:
        Tuple of (SkillMeta, list of warning strings)

    Raises:
        ValueError: If clone fails or repo has no SKILL.md
        FileExistsError: If skill exists and force=False
    """
    if skills_dir is None:
        skills_dir = get_skills_dir()

    # Ensure skills directory exists
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Clone to temp directory
    tmp_dir = tempfile.mkdtemp()
    try:
        subprocess.run(
            ["git", "clone", git_url, tmp_dir],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        msg = f"Git clone failed: {e.stderr}"
        raise ValueError(msg) from e

    # Look for SKILL.md in clone root
    skill_md = Path(tmp_dir) / "SKILL.md"
    if not skill_md.exists():
        # Check for subdirectories with SKILL.md (multi-skill repo)
        subdirs_with_skills = []
        for subdir in Path(tmp_dir).iterdir():
            if subdir.is_dir() and (subdir / "SKILL.md").exists():
                subdirs_with_skills.append(subdir.name)

        if subdirs_with_skills:
            msg = (
                f"Multi-skill repository detected. Install each skill individually: "
                f"git clone {git_url} then copy <subdir> to ~/.claude/skills/. "
                f"Found skills: {', '.join(subdirs_with_skills)}"
            )
            shutil.rmtree(tmp_dir)
            raise ValueError(msg)

        shutil.rmtree(tmp_dir)
        msg = "Cloned repository has no SKILL.md"
        raise ValueError(msg)

    # Parse SKILL.md to get name
    try:
        meta = parse_skill_frontmatter(skill_md)
    except ValueError:
        shutil.rmtree(tmp_dir)
        raise

    # Check if skill already exists
    target = skills_dir / meta.name
    if target.exists() and not force:
        shutil.rmtree(tmp_dir)
        msg = f"Skill '{meta.name}' already installed. Use --force to overwrite."
        raise FileExistsError(msg)

    # Remove existing if force=True
    if target.exists() and force:
        shutil.rmtree(target)

    # Move clone to target
    shutil.move(tmp_dir, str(target))

    # Check dependencies
    warnings: list[str] = []
    for dep in meta.dependencies:
        dep_path = skills_dir / dep
        if not dep_path.exists():
            warnings.append(f"Dependency '{dep}' is not installed")

    return meta, warnings


def remove_skill(name: str, skills_dir: Path | None = None) -> bool:
    """Remove an installed skill.

    Args:
        name: Skill name
        skills_dir: Skills directory (defaults to ~/.claude/skills)

    Returns:
        True if skill was removed, False if not found
    """
    if skills_dir is None:
        skills_dir = get_skills_dir()

    skill_path = skills_dir / name
    if not skill_path.exists():
        return False

    # Try to run on_delete hook
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        try:
            meta = parse_skill_frontmatter(skill_md)
            if meta.hooks.on_delete:
                # Per threat model T-12-03: Hook execution is accepted risk
                subprocess.run(  # noqa: S602
                    meta.hooks.on_delete,
                    shell=True,
                    cwd=skill_path,
                    check=False,
                    capture_output=True,
                    text=True,
                )
        except Exception:  # noqa: S110
            # Continue with removal even if hook fails
            pass

    # Remove skill directory
    shutil.rmtree(skill_path)
    return True


def update_skill(name: str, skills_dir: Path | None = None) -> SkillMeta:
    """Update a skill via git pull.

    Args:
        name: Skill name
        skills_dir: Skills directory (defaults to ~/.claude/skills)

    Returns:
        Updated SkillMeta

    Raises:
        FileNotFoundError: If skill not found
        ValueError: If skill directory is not a git repo
    """
    if skills_dir is None:
        skills_dir = get_skills_dir()

    skill_path = skills_dir / name
    if not skill_path.exists():
        msg = f"Skill '{name}' not found"
        raise FileNotFoundError(msg)

    # Check if it's a git repo
    git_dir = skill_path / ".git"
    if not git_dir.exists():
        msg = "Not a git repository. Skill may have been installed manually."
        raise ValueError(msg)

    # Run git pull
    subprocess.run(
        ["git", "pull"],
        cwd=skill_path,
        check=True,
        capture_output=True,
        text=True,
    )

    # Re-parse SKILL.md
    skill_md = skill_path / "SKILL.md"
    return parse_skill_frontmatter(skill_md)
