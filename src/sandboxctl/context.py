"""Claude context backup and restore for sandbox lifecycle."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig

_BACKUP_PATHS = (
    ".claude/memory",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/projects",
    ".claude/CLAUDE.md",
    ".claude/.credentials.json",
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

    Uses openshell download to transfer the tarball, avoiding base64 shell
    argument limits that silently fail on large backups (>8MB).
    Rotates existing backups, keeping up to 10 copies.
    Returns the backup path, or None if the sandbox has no Claude context.
    """
    all_paths = list(_BACKUP_PATHS) + list(config.backup_extra_paths)
    paths = " ".join(all_paths)
    remote_tar = "/sandbox/claude-context-backup.tar.gz"  # noqa: S108

    osh.sandbox_exec_pipe(
        name,
        f"cd /sandbox && tar czf {remote_tar} {paths} 2>/dev/null; test -s {remote_tar} && echo 'ok' || echo 'empty'",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_tar = Path(tmp_dir) / "claude-context.tar.gz"
        try:
            osh.sandbox_download(name, remote_tar, local_tar)
        except Exception:  # noqa: BLE001
            return None
        finally:
            osh.sandbox_exec_pipe(name, f"rm -f {remote_tar}")

        if not local_tar.exists() or local_tar.stat().st_size < 50:
            return None

        backup_path = _backup_dir(name, config)
        backup_path.mkdir(parents=True, exist_ok=True)
        _rotate_backups(backup_path)
        tarball = backup_path / f"{_BACKUP_NAME}.tar.gz"
        tarball.write_bytes(local_tar.read_bytes())

    return backup_path


def restore_claude_context(name: str, config: SandboxctlConfig) -> bool:
    """Restore Claude memory and settings into a running sandbox.

    Uses openshell upload to transfer the tarball, avoiding base64 shell
    argument limits that silently fail on large backups (>8MB).
    Restores the most recent backup (claude-context.tar.gz).
    Returns True if a backup was found and restored, False otherwise.
    """
    tarball = _backup_dir(name, config) / f"{_BACKUP_NAME}.tar.gz"
    if not tarball.exists():
        return False

    remote_tar = "/sandbox/claude-context-restore.tar.gz"  # noqa: S108
    osh.sandbox_upload(name, tarball, remote_tar)
    osh.sandbox_exec_pipe(
        name,
        f"tar xzf {remote_tar} -C /sandbox && rm -f {remote_tar}",
    )
    return True
