"""Tests for open_cmd module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
    def test_spawns_external_terminal(self) -> None:
        """Claude mode spawns external terminal instead of in-place exec."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.workspace.terminal_app = "iTerm"

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.spawn_terminal_with_claude") as mock_spawn,
        ):
            open_sandbox("mybox", config, mode="claude")

        mock_spawn.assert_called_once_with("mybox", "iTerm")

    def test_auto_detects_terminal_when_no_profile(self) -> None:
        """Auto-detects terminal app when no profile found."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.find_terminal_app", return_value="Terminal"),
            patch("sandboxctl.open_cmd.spawn_terminal_with_claude") as mock_spawn,
        ):
            open_sandbox("mybox", config, mode="claude")

        mock_spawn.assert_called_once_with("mybox", "Terminal")


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
    """Tests for external terminal launching (replaced --continue fallback chain)."""

    def test_claude_spawns_terminal_not_exec(self) -> None:
        """Claude mode now spawns external terminal instead of sandbox_exec_interactive."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.find_terminal_app", return_value="iTerm"),
            patch("sandboxctl.open_cmd.spawn_terminal_with_claude") as mock_spawn,
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive") as mock_exec,
        ):
            open_sandbox("mybox", config, mode="claude")

        # New behavior: spawn terminal, NOT sandbox_exec_interactive
        mock_spawn.assert_called_once()
        mock_exec.assert_not_called()


class TestKeepaliveWiring:
    """Tests for ensure_ssh_keepalive() wiring into open_sandbox()."""

    def test_open_calls_ensure_keepalive_before_vscode(self) -> None:
        """open_sandbox calls ensure_ssh_keepalive before launching VS Code."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.open_cmd.subprocess.run"),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive") as mock_keepalive,
        ):
            open_sandbox("mybox", config, mode="code")

        mock_keepalive.assert_called_once()

    def test_open_calls_ensure_keepalive_in_both_mode(self) -> None:
        """open_sandbox calls ensure_ssh_keepalive in both mode."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.workspace.terminal_app = "iTerm"

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.open_cmd.subprocess.run"),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.spawn_terminal_with_claude"),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive") as mock_keepalive,
        ):
            open_sandbox("mybox", config, mode="both")

        mock_keepalive.assert_called_once()

    def test_diagnose_still_runs_before_keepalive(self) -> None:
        """Diagnose with auto_recover=True runs before ensure_ssh_keepalive (layer 2 before layer 1)."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        mock_calls: list[str] = []

        def track_diagnose(*args: object, **kwargs: object) -> MagicMock:
            mock_calls.append("diagnose")
            return report

        def track_keepalive() -> None:
            mock_calls.append("keepalive")

        with (
            patch("sandboxctl.open_cmd.diagnose", side_effect=track_diagnose),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.open_cmd.subprocess.run"),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive", side_effect=track_keepalive),
        ):
            open_sandbox("mybox", config, mode="code")

        # Diagnose runs first (layer 2: container recovery), then keepalive (layer 1: SSH resilience)
        assert mock_calls == ["diagnose", "keepalive"]


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


class TestExtensionInstallHook:
    """Tests for extension installation in open_sandbox() before GUI launch (Task 1 - Phase 20)."""

    def test_install_before_gui_launch(self) -> None:
        """install_extensions is called BEFORE workspace GUI subprocess.run."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.extensions.extensions_list = ["ms-python.python"]
        profile.extensions.local_only = []

        mock_calls: list[str] = []

        def track_install(*args: object, **kwargs: object) -> MagicMock:
            mock_calls.append("install")
            return MagicMock(installed=["ms-python.python"], skipped_invalid=[], failed=[])

        def track_launch(*args: object, **kwargs: object) -> int:
            mock_calls.append("launch")
            return 0

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.classify_remote_extensions", return_value=["ms-python.python"]),
            patch("sandboxctl.open_cmd.install_extensions", side_effect=track_install),
            patch("sandboxctl.open_cmd.subprocess.run", side_effect=track_launch),
        ):
            open_sandbox("mybox", config, mode="code")

        # Assert call order: install before launch
        assert mock_calls == ["install", "launch"]

    def test_empty_extensions_skips_install(self) -> None:
        """Empty extensions list does not call install_extensions, but GUI still launches."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.extensions.extensions_list = []
        profile.extensions.local_only = []

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.classify_remote_extensions", return_value=[]),
            patch("sandboxctl.open_cmd.install_extensions") as mock_install,
            patch("sandboxctl.open_cmd.subprocess.run") as mock_run,
        ):
            open_sandbox("mybox", config, mode="code")

        # install_extensions NOT called
        mock_install.assert_not_called()
        # GUI launch still runs
        mock_run.assert_called_once()

    def test_profile_not_found_swallows_error(self) -> None:
        """Profile FileNotFoundError is swallowed and GUI launch still runs."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.install_extensions") as mock_install,
            patch("sandboxctl.open_cmd.subprocess.run") as mock_run,
        ):
            open_sandbox("mybox", config, mode="code")

        # install_extensions NOT called
        mock_install.assert_not_called()
        # GUI launch still runs
        mock_run.assert_called_once()

    def test_install_failures_do_not_raise(self) -> None:
        """install_extensions report with failed list does not raise, GUI launch proceeds."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.extensions.extensions_list = ["ms-python.python", "bad.extension"]
        profile.extensions.local_only = []

        install_report = MagicMock(
            installed=["ms-python.python"],
            skipped_invalid=[],
            failed=[("bad.extension", "Not found")],
        )

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.classify_remote_extensions", return_value=["ms-python.python", "bad.extension"]),
            patch("sandboxctl.open_cmd.install_extensions", return_value=install_report),
            patch("sandboxctl.open_cmd.subprocess.run") as mock_run,
        ):
            open_sandbox("mybox", config, mode="code")

        # GUI launch still runs even with failures
        mock_run.assert_called_once()

    def test_install_hook_calls_classify_remote(self) -> None:
        """Install hook calls classify_remote_extensions with profile.extensions."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.extensions.extensions_list = ["ms-python.python"]
        profile.extensions.local_only = []

        install_report = MagicMock(installed=[], skipped_invalid=[], failed=[])
        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.classify_remote_extensions") as mock_classify,
            patch("sandboxctl.open_cmd.install_extensions", return_value=install_report),
            patch("sandboxctl.open_cmd.subprocess.run"),
        ):
            mock_classify.return_value = []
            open_sandbox("mybox", config, mode="code")

        # classify_remote_extensions called with profile.extensions
        mock_classify.assert_called_once_with(profile.extensions)
