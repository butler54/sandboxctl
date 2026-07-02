"""Claude context backup and restore for sandbox lifecycle."""

from __future__ import annotations

import base64
from pathlib import Path

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig

_BACKUP_PATHS = (
    ".claude/memory",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/projects",
    ".claude/CLAUDE.md",
)


def _backup_dir(name: str, config: SandboxctlConfig) -> Path:
    return config.config_dir / "backups" / name


def backup_claude_context(name: str, config: SandboxctlConfig) -> Path | None:
    """Back up Claude memory and settings from a running sandbox.

    Returns the backup path, or None if the sandbox has no Claude context.
    """
    paths = " ".join(_BACKUP_PATHS)
    encoded = osh.sandbox_exec_pipe(
        name,
        f"cd /sandbox && tar czf - {paths} 2>/dev/null | base64",
    )
    if not encoded.strip():
        return None

    try:
        data = base64.b64decode(encoded)
    except Exception:  # noqa: BLE001
        return None

    if len(data) < 50:
        return None

    backup_path = _backup_dir(name, config)
    backup_path.mkdir(parents=True, exist_ok=True)
    tarball = backup_path / "claude-context.tar.gz"
    tarball.write_bytes(data)
    return backup_path


def restore_claude_context(name: str, config: SandboxctlConfig) -> bool:
    """Restore Claude memory and settings into a running sandbox.

    Returns True if a backup was found and restored, False otherwise.
    """
    tarball = _backup_dir(name, config) / "claude-context.tar.gz"
    if not tarball.exists():
        return False

    encoded = base64.b64encode(tarball.read_bytes()).decode()
    osh.sandbox_exec_pipe(
        name,
        f"echo {encoded} | base64 -d | tar xzf - -C /sandbox",
    )
    return True
