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
    ".claude-mem",
)

_MAX_BACKUPS = 10
_BACKUP_NAME = "claude-context"


def _backup_dir(name: str, config: SandboxctlConfig) -> Path:
    return config.config_dir / "backups" / name


def _rotate_backups(backup_path: Path) -> None:
    """Rotate existing backups using log-rotation style indexing.

    claude-context.tar.gz -> claude-context.1.tar.gz -> ... -> claude-context.10.tar.gz (deleted)
    """
    oldest = backup_path / f"{_BACKUP_NAME}.{_MAX_BACKUPS}.tar.gz"
    if oldest.exists():
        oldest.unlink()

    for i in range(_MAX_BACKUPS - 1, 0, -1):
        src = backup_path / f"{_BACKUP_NAME}.{i}.tar.gz"
        dst = backup_path / f"{_BACKUP_NAME}.{i + 1}.tar.gz"
        if src.exists():
            src.rename(dst)

    current = backup_path / f"{_BACKUP_NAME}.tar.gz"
    if current.exists():
        current.rename(backup_path / f"{_BACKUP_NAME}.1.tar.gz")


def backup_claude_context(name: str, config: SandboxctlConfig) -> Path | None:
    """Back up Claude memory and settings from a running sandbox.

    Rotates existing backups, keeping up to 10 copies.
    Returns the backup path, or None if the sandbox has no Claude context.
    """
    all_paths = list(_BACKUP_PATHS) + list(config.backup_extra_paths)
    paths = " ".join(all_paths)
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
    _rotate_backups(backup_path)
    tarball = backup_path / f"{_BACKUP_NAME}.tar.gz"
    tarball.write_bytes(data)
    return backup_path


def restore_claude_context(name: str, config: SandboxctlConfig) -> bool:
    """Restore Claude memory and settings into a running sandbox.

    Restores the most recent backup (claude-context.tar.gz).
    Returns True if a backup was found and restored, False otherwise.
    """
    tarball = _backup_dir(name, config) / f"{_BACKUP_NAME}.tar.gz"
    if not tarball.exists():
        return False

    encoded = base64.b64encode(tarball.read_bytes()).decode()
    osh.sandbox_exec_pipe(
        name,
        f"echo {encoded} | base64 -d | tar xzf - -C /sandbox",
    )
    return True
