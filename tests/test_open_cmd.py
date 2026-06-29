"""Tests for open_cmd module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.exceptions import Exit

from sandboxctl.open_cmd import open_sandbox


class TestOpenSandboxHealth:
    def test_unhealthy_exits(self) -> None:
        report = MagicMock(healthy=False, details=["Container: stopped"], recovery_action="container_recovery_failed")
        config = MagicMock()

        with (
            pytest.raises(Exit),
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
        ):
            open_sandbox("mybox", config)

    def test_healthy_proceeds(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
        ):
            open_sandbox("mybox", config, mode="claude")


class TestOpenShellMode:
    def test_shell_calls_connect(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as mock_connect,
        ):
            open_sandbox("mybox", config, mode="shell")

        mock_connect.assert_called_once_with("mybox")


class TestOpenClaudeMode:
    def test_with_default_repo(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.sandbox.default_repo = "my-repo"

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0) as mock_exec,
        ):
            open_sandbox("mybox", config, mode="claude")

        cmd = mock_exec.call_args[0][1]
        assert "my-repo" in cmd
        assert "claude" in cmd

    def test_without_default_repo(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0) as mock_exec,
        ):
            open_sandbox("mybox", config, mode="claude")

        assert mock_exec.call_args[0][1] == "claude"

    def test_nonzero_exit_reconnects(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=1),
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as mock_connect,
        ):
            open_sandbox("mybox", config, mode="claude")

        mock_connect.assert_called_once_with("mybox")


class TestOpenCodeMode:
    def test_vscode_not_found(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value=None),
        ):
            open_sandbox("mybox", config, mode="code")

    def test_vscode_with_workspace(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.open_cmd.subprocess.run") as mock_run,
        ):
            open_sandbox("mybox", config, mode="code")

        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "--remote" in args

    def test_vscode_no_workspace(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="no"),
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as mock_connect,
        ):
            open_sandbox("mybox", config, mode="code")

        mock_connect.assert_called_once_with("mybox", editor="vscode")
