"""Tests for open_cmd module."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from sandboxctl.open_cmd import open_sandbox, spawn_terminal_with_claude


class TestOpenSandboxHealth:
    def test_unhealthy_exits(self) -> None:
        report = MagicMock(healthy=False, details=["Container: stopped"], recovery_action="container_recovery_failed")
        config = MagicMock()

        with (
            pytest.raises((SystemExit, RuntimeError)),
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

        # First call is --continue, using /sandbox as base_dir (no profile)
        cmd = mock_exec.call_args[0][1]
        assert "claude --continue" in cmd
        assert "/sandbox" in cmd

    def test_nonzero_exit_reconnects(self) -> None:
        """When both --continue and fresh session fail, fall back to shell."""
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


class TestClaudeContinueHardening:
    """Tests for the --continue → fresh → shell fallback chain."""

    def test_continue_succeeds_first_try(self) -> None:
        """--continue returns 0 on first call; no second call made."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0) as mock_exec,
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as mock_connect,
        ):
            open_sandbox("mybox", config, mode="claude")

        # Only one call (--continue succeeded)
        assert mock_exec.call_count == 1
        assert "--continue" in mock_exec.call_args[0][1]
        mock_connect.assert_not_called()

    def test_continue_fails_fresh_succeeds(self) -> None:
        """--continue returns non-zero, fresh session returns 0."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        # First call (--continue) returns 1, second call (fresh) returns 0
        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch(
                "sandboxctl.open_cmd.osh.sandbox_exec_interactive",
                side_effect=[1, 0],
            ) as mock_exec,
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as mock_connect,
        ):
            open_sandbox("mybox", config, mode="claude")

        assert mock_exec.call_count == 2
        first_cmd = mock_exec.call_args_list[0][0][1]
        second_cmd = mock_exec.call_args_list[1][0][1]
        assert "--continue" in first_cmd
        assert "--continue" not in second_cmd
        assert "claude" in second_cmd
        mock_connect.assert_not_called()

    def test_both_fail_fallback_to_shell(self) -> None:
        """Both --continue and fresh return non-zero; falls back to sandbox_connect."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch(
                "sandboxctl.open_cmd.osh.sandbox_exec_interactive",
                side_effect=[1, 1],
            ) as mock_exec,
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as mock_connect,
        ):
            open_sandbox("mybox", config, mode="claude")

        assert mock_exec.call_count == 2
        mock_connect.assert_called_once_with("mybox")


class TestTerminalSpawn:
    """Tests for spawn_terminal_with_claude() and external terminal launching."""

    def test_spawn_iterm_runs_osascript(self) -> None:
        """Spawning with iTerm runs osascript with iTerm2 AppleScript."""
        with patch("sandboxctl.open_cmd.subprocess.run") as mock_run:
            spawn_terminal_with_claude("mybox", "iTerm")

        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert args[1] == "-e"
        script = args[2]
        assert "iTerm2" in script
        assert "openshell sandbox connect mybox" in script
        assert "claude" in script

    def test_spawn_terminal_runs_osascript(self) -> None:
        """Spawning with Terminal runs osascript with Terminal.app AppleScript."""
        with patch("sandboxctl.open_cmd.subprocess.run") as mock_run:
            spawn_terminal_with_claude("mybox", "Terminal")

        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert args[1] == "-e"
        script = args[2]
        assert "Terminal" in script
        assert "do script" in script
        assert "openshell sandbox connect mybox" in script
        assert "claude" in script

    def test_spawn_none_prints_manual_command(self, capsys: pytest.CaptureFixture) -> None:
        """Spawning with None prints the manual command and does not call subprocess."""
        with patch("sandboxctl.open_cmd.subprocess.run") as mock_run:
            spawn_terminal_with_claude("mybox", None)

        mock_run.assert_not_called()
        captured = capsys.readouterr()
        assert "openshell sandbox connect mybox" in captured.out
        assert "claude" in captured.out

    def test_both_mode_spawns_terminal_and_vscode(self) -> None:
        """Mode 'both' launches VS Code AND spawns external terminal."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.workspace.terminal_app = "iTerm"

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.open_cmd.subprocess.run") as mock_run,
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.spawn_terminal_with_claude") as mock_spawn,
        ):
            open_sandbox("mybox", config, mode="both")

        # VS Code launched
        vscode_calls = [c for c in mock_run.call_args_list if "--remote" in str(c)]
        assert len(vscode_calls) >= 1

        # Terminal spawned
        mock_spawn.assert_called_once_with("mybox", "iTerm")

    def test_terminal_app_resolution_order(self) -> None:
        """Terminal app resolved from profile.workspace.terminal_app, then auto-detect."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.workspace.terminal_app = ""  # Empty means auto-detect

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.find_terminal_app", return_value="Terminal") as mock_find,
            patch("sandboxctl.open_cmd.spawn_terminal_with_claude") as mock_spawn,
        ):
            open_sandbox("mybox", config, mode="claude")

        # Auto-detect was called
        mock_find.assert_called_once()
        # Spawned with auto-detected terminal
        mock_spawn.assert_called_once_with("mybox", "Terminal")
