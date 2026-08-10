"""Tests for Claude context backup and restore."""

from __future__ import annotations

import tarfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from sandboxctl.context import (
    _BACKUP_NAME,
    _MAX_BACKUPS,
    _rotate_backups,
    backup_claude_context,
    restore_claude_context,
)


def _make_fake_tar() -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b'{"model": "claude-sonnet-4-20250514"}'
        info = tarfile.TarInfo(name=".claude/settings.json")
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    return buf.getvalue()


class TestBackupClaudeContext:
    def test_backup_creates_tarball(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)
        fake_tar = _make_fake_tar()

        def fake_download(_name: str, _remote: str, local: Path) -> None:
            local.write_bytes(fake_tar)

        with (
            patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="ok"),
            patch("sandboxctl.context.osh.sandbox_download", side_effect=fake_download),
        ):
            result = backup_claude_context("mybox", config)

        assert result is not None
        tarball = result / f"{_BACKUP_NAME}.tar.gz"
        assert tarball.exists()
        assert tarball.read_bytes() == fake_tar

    def test_backup_returns_none_when_download_fails(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)

        with (
            patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="empty"),
            patch("sandboxctl.context.osh.sandbox_download", side_effect=RuntimeError("download failed")),
        ):
            result = backup_claude_context("mybox", config)

        assert result is None

    def test_backup_dir_structure(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)
        fake_tar = _make_fake_tar()

        def fake_download(_name: str, _remote: str, local: Path) -> None:
            local.write_bytes(fake_tar)

        with (
            patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="ok"),
            patch("sandboxctl.context.osh.sandbox_download", side_effect=fake_download),
        ):
            result = backup_claude_context("docs", config)

        assert result == tmp_path / "backups" / "docs"

    def test_backup_includes_claude_mem(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path, backup_extra_paths=[])
        fake_tar = _make_fake_tar()

        def fake_download(_name: str, _remote: str, local: Path) -> None:
            local.write_bytes(fake_tar)

        with (
            patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="ok") as mock_pipe,
            patch("sandboxctl.context.osh.sandbox_download", side_effect=fake_download),
        ):
            backup_claude_context("mybox", config)

        script = mock_pipe.call_args_list[0][0][1]
        assert ".claude-mem" in script

    def test_backup_includes_extra_paths(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path, backup_extra_paths=[".my-plugin", ".other-data"])
        fake_tar = _make_fake_tar()

        def fake_download(_name: str, _remote: str, local: Path) -> None:
            local.write_bytes(fake_tar)

        with (
            patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="ok") as mock_pipe,
            patch("sandboxctl.context.osh.sandbox_download", side_effect=fake_download),
        ):
            backup_claude_context("mybox", config)

        script = mock_pipe.call_args_list[0][0][1]
        assert ".my-plugin" in script
        assert ".other-data" in script

    def test_backup_includes_mcp_credentials(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path, backup_extra_paths=[])
        fake_tar = _make_fake_tar()

        def fake_download(_name: str, _remote: str, local: Path) -> None:
            local.write_bytes(fake_tar)

        with (
            patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="ok") as mock_pipe,
            patch("sandboxctl.context.osh.sandbox_download", side_effect=fake_download),
        ):
            backup_claude_context("mybox", config)

        script = mock_pipe.call_args_list[0][0][1]
        assert ".claude/.credentials.json" in script


class TestRotateBackups:
    def test_rotates_existing_backup(self, tmp_path: Path) -> None:
        (tmp_path / f"{_BACKUP_NAME}.tar.gz").write_text("current")
        _rotate_backups(tmp_path)

        assert not (tmp_path / f"{_BACKUP_NAME}.tar.gz").exists()
        assert (tmp_path / f"{_BACKUP_NAME}.1.tar.gz").read_text() == "current"

    def test_shifts_indexed_backups(self, tmp_path: Path) -> None:
        (tmp_path / f"{_BACKUP_NAME}.tar.gz").write_text("current")
        (tmp_path / f"{_BACKUP_NAME}.1.tar.gz").write_text("prev1")
        (tmp_path / f"{_BACKUP_NAME}.2.tar.gz").write_text("prev2")

        _rotate_backups(tmp_path)

        assert (tmp_path / f"{_BACKUP_NAME}.1.tar.gz").read_text() == "current"
        assert (tmp_path / f"{_BACKUP_NAME}.2.tar.gz").read_text() == "prev1"
        assert (tmp_path / f"{_BACKUP_NAME}.3.tar.gz").read_text() == "prev2"

    def test_drops_oldest_at_max(self, tmp_path: Path) -> None:
        for i in range(1, _MAX_BACKUPS + 1):
            (tmp_path / f"{_BACKUP_NAME}.{i}.tar.gz").write_text(f"backup-{i}")
        (tmp_path / f"{_BACKUP_NAME}.tar.gz").write_text("current")

        _rotate_backups(tmp_path)

        assert not (tmp_path / f"{_BACKUP_NAME}.{_MAX_BACKUPS + 1}.tar.gz").exists()
        assert (tmp_path / f"{_BACKUP_NAME}.1.tar.gz").read_text() == "current"
        assert (tmp_path / f"{_BACKUP_NAME}.{_MAX_BACKUPS}.tar.gz").read_text() == f"backup-{_MAX_BACKUPS - 1}"

    def test_noop_when_no_backups(self, tmp_path: Path) -> None:
        _rotate_backups(tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_multiple_backups_accumulate(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)
        fake_tar = _make_fake_tar()

        def fake_download(_name: str, _remote: str, local: Path) -> None:
            local.write_bytes(fake_tar)

        with (
            patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="ok"),
            patch("sandboxctl.context.osh.sandbox_download", side_effect=fake_download),
        ):
            backup_claude_context("mybox", config)
            backup_claude_context("mybox", config)
            backup_claude_context("mybox", config)

        backup_dir = tmp_path / "backups" / "mybox"
        assert (backup_dir / f"{_BACKUP_NAME}.tar.gz").exists()
        assert (backup_dir / f"{_BACKUP_NAME}.1.tar.gz").exists()
        assert (backup_dir / f"{_BACKUP_NAME}.2.tar.gz").exists()


class TestRestoreClaudeContext:
    def test_restore_uploads_and_extracts(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)
        backup_dir = tmp_path / "backups" / "mybox"
        backup_dir.mkdir(parents=True)
        fake_tar = _make_fake_tar()
        (backup_dir / f"{_BACKUP_NAME}.tar.gz").write_bytes(fake_tar)

        with (
            patch("sandboxctl.context.osh.sandbox_upload") as mock_upload,
            patch("sandboxctl.context.osh.sandbox_exec_pipe") as mock_pipe,
        ):
            result = restore_claude_context("mybox", config)

        assert result is True
        mock_upload.assert_called_once()
        upload_args = mock_upload.call_args
        assert str(upload_args[0][1]).endswith(f"{_BACKUP_NAME}.tar.gz")
        mock_pipe.assert_called_once()
        script = mock_pipe.call_args[0][1]
        assert "tar xzf" in script

    def test_restore_returns_false_when_no_backup(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)

        result = restore_claude_context("mybox", config)

        assert result is False


def test_backup_paths_exclude_settings_json() -> None:
    """settings.json is managed by sandboxctl and must not be overwritten on restore (#91)."""
    from sandboxctl.context import _BACKUP_PATHS

    assert ".claude/settings.json" not in _BACKUP_PATHS
    # settings.local.json (user customizations) is preserved
    assert ".claude/settings.local.json" in _BACKUP_PATHS
