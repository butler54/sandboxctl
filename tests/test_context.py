"""Tests for Claude context backup and restore."""

from __future__ import annotations

import base64
import tarfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from sandboxctl.context import backup_claude_context, restore_claude_context


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
        encoded = base64.b64encode(fake_tar).decode()

        with patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value=encoded):
            result = backup_claude_context("mybox", config)

        assert result is not None
        tarball = result / "claude-context.tar.gz"
        assert tarball.exists()
        assert tarball.read_bytes() == fake_tar

    def test_backup_returns_none_when_empty(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)

        with patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value=""):
            result = backup_claude_context("mybox", config)

        assert result is None

    def test_backup_returns_none_on_invalid_base64(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)

        with patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value="not-valid-base64!!!"):
            result = backup_claude_context("mybox", config)

        assert result is None

    def test_backup_dir_structure(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)
        fake_tar = _make_fake_tar()
        encoded = base64.b64encode(fake_tar).decode()

        with patch("sandboxctl.context.osh.sandbox_exec_pipe", return_value=encoded):
            result = backup_claude_context("docs", config)

        assert result == tmp_path / "backups" / "docs"


class TestRestoreClaudeContext:
    def test_restore_uploads_and_extracts(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)
        backup_dir = tmp_path / "backups" / "mybox"
        backup_dir.mkdir(parents=True)
        fake_tar = _make_fake_tar()
        (backup_dir / "claude-context.tar.gz").write_bytes(fake_tar)

        with patch("sandboxctl.context.osh.sandbox_exec_pipe") as mock_pipe:
            result = restore_claude_context("mybox", config)

        assert result is True
        mock_pipe.assert_called_once()
        script = mock_pipe.call_args[0][1]
        assert "base64 -d" in script
        assert "tar xzf" in script

    def test_restore_returns_false_when_no_backup(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)

        result = restore_claude_context("mybox", config)

        assert result is False

    def test_restore_sends_correct_data(self, tmp_path: Path) -> None:
        config = MagicMock(config_dir=tmp_path)
        backup_dir = tmp_path / "backups" / "mybox"
        backup_dir.mkdir(parents=True)
        fake_tar = _make_fake_tar()
        (backup_dir / "claude-context.tar.gz").write_bytes(fake_tar)
        expected_b64 = base64.b64encode(fake_tar).decode()

        with patch("sandboxctl.context.osh.sandbox_exec_pipe") as mock_pipe:
            restore_claude_context("mybox", config)

        script = mock_pipe.call_args[0][1]
        assert expected_b64 in script
