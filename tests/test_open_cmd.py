"""Tests for open_cmd module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sandboxctl.open_cmd import open_sandbox


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
    def test_resumes_session_with_continue_flag(self) -> None:
        """Claude mode tries claude --continue first to resume an existing session."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0) as mock_exec,
        ):
            open_sandbox("mybox", config, mode="claude")

        mock_exec.assert_called_once_with("mybox", "cd /sandbox && claude --continue")

    def test_falls_back_to_fresh_session_when_continue_fails(self) -> None:
        """When claude --continue returns non-zero, falls back to a fresh claude session."""
        report = MagicMock(healthy=True)
        config = MagicMock()

        exec_results = iter([1, 0])

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", side_effect=exec_results) as mock_exec,
        ):
            open_sandbox("mybox", config, mode="claude")

        assert mock_exec.call_count == 2
        first_cmd = mock_exec.call_args_list[0][0][1]
        second_cmd = mock_exec.call_args_list[1][0][1]
        assert "--continue" in first_cmd
        assert "--continue" not in second_cmd

    def test_uses_default_repo_when_set(self) -> None:
        """Claude mode cds into profile.sandbox.default_repo before launching."""
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.sandbox.default_repo = "my-project"

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0) as mock_exec,
        ):
            open_sandbox("mybox", config, mode="claude")

        cmd = mock_exec.call_args[0][1]
        assert "my-project" in cmd
        assert "--continue" in cmd


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
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
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
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as mock_connect,
        ):
            open_sandbox("mybox", config, mode="code")

        mock_connect.assert_called_once_with("mybox", editor="vscode")


class TestClaudeContinueHardening:
    """Tests for Claude reconnect fallback when exec returns non-zero."""

    def test_reconnects_via_shell_when_both_exec_attempts_fail(self) -> None:
        """When both --continue and fresh session return non-zero, falls back to sandbox_connect."""
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
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
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
        profile.sandbox.default_repo = ""

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.open_cmd.subprocess.run"),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0),
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
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
            patch("sandboxctl.open_cmd.subprocess.run"),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive", side_effect=track_keepalive),
        ):
            open_sandbox("mybox", config, mode="code")

        # Diagnose runs first (layer 2: container recovery), then keepalive (layer 1: SSH resilience)
        assert mock_calls == ["diagnose", "keepalive"]


class TestBothMode:
    """Mode 'both' opens VS Code AND runs Claude inline in current terminal."""

    def test_both_mode_opens_vscode_and_runs_claude(self) -> None:
        report = MagicMock(healthy=True)
        config = MagicMock()
        profile = MagicMock()
        profile.sandbox.default_repo = ""

        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.find_vscode_bin", return_value="/usr/bin/code"),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_pipe", return_value="yes"),
            patch("sandboxctl.open_cmd.subprocess.run") as mock_run,
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.open_cmd.osh.sandbox_exec_interactive", return_value=0) as mock_exec,
        ):
            open_sandbox("mybox", config, mode="both")

        # VS Code launched via subprocess
        vscode_calls = [c for c in mock_run.call_args_list if "--remote" in str(c)]
        assert len(vscode_calls) >= 1
        # Claude launched inline with --continue to resume session
        mock_exec.assert_called_once_with("mybox", "cd /sandbox && claude --continue")


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
            patch("sandboxctl.open_cmd.resolve_ssh_host", return_value="openshell-mybox.default"),
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
            patch("sandboxctl.open_cmd.resolve_ssh_host", return_value="openshell-mybox.default"),
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
            patch("sandboxctl.open_cmd.resolve_ssh_host", return_value="openshell-mybox.default"),
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
            patch("sandboxctl.open_cmd.resolve_ssh_host", return_value="openshell-mybox.default"),
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
