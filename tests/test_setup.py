"""Tests for setup and restart commands."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from sandboxctl.bundled_profiles import PROFILES
from sandboxctl.cli import app
from sandboxctl.setup_cmd import (
    _check_prerequisites,
    _install_profiles,
    _setup_github_pat,
    _setup_ssh_key,
)

runner = CliRunner()


class TestSetupHelp:
    def test_setup_help(self) -> None:
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output.lower()
        assert "prerequisites" in result.output.lower() or "first-time" in result.output.lower()


class TestCheckPrerequisites:
    def test_check_prerequisites_all_present(self) -> None:
        def which_side_effect(name: str) -> str | None:
            if name == "openshell":
                return "/usr/local/bin/openshell"
            if name == "podman":
                return "/usr/bin/podman"
            return None

        mock_openshell_result = MagicMock(
            stdout="openshell 1.2.3",
            stderr="",
        )
        mock_podman_result = MagicMock(
            stdout="podman version 4.0.0",
            stderr="",
        )

        def run_side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            if cmd == ["openshell", "version"]:
                return mock_openshell_result
            if cmd == ["podman", "--version"]:
                return mock_podman_result
            return MagicMock(stdout="", stderr="")

        with (
            patch("sandboxctl.setup_cmd.shutil.which", side_effect=which_side_effect),
            patch("sandboxctl.setup_cmd.subprocess.run", side_effect=run_side_effect),
            patch(
                "sandboxctl.setup_cmd.gateway_status",
                return_value={"status": "Connected"},
            ),
        ):
            # Should not raise
            _check_prerequisites()

    def test_check_prerequisites_missing_openshell(self) -> None:
        def which_side_effect(name: str) -> str | None:
            if name == "podman":
                return "/usr/bin/podman"
            return None

        with (
            patch("sandboxctl.setup_cmd.shutil.which", side_effect=which_side_effect),
            patch("sandboxctl.setup_cmd.subprocess.run"),
            patch("sandboxctl.setup_cmd.gateway_status", return_value={"status": "Connected"}),
            pytest.raises((SystemExit, RuntimeError)),
        ):
            _check_prerequisites()

    def test_check_prerequisites_missing_podman(self) -> None:
        def which_side_effect(name: str) -> str | None:
            if name == "openshell":
                return "/usr/local/bin/openshell"
            return None

        with (
            patch("sandboxctl.setup_cmd.shutil.which", side_effect=which_side_effect),
            patch(
                "sandboxctl.setup_cmd.subprocess.run",
                return_value=MagicMock(stdout="openshell 1.0", stderr=""),
            ),
            patch("sandboxctl.setup_cmd.gateway_status", return_value={"status": "Connected"}),
            pytest.raises((SystemExit, RuntimeError)),
        ):
            _check_prerequisites()


class TestInstallProfiles:
    def test_install_profiles_fresh(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        cfg = MagicMock(profiles_dir=profiles_dir)

        _install_profiles(cfg)

        for name in PROFILES:
            dest = profiles_dir / f"{name}.toml"
            assert dest.exists(), f"Profile {name} was not installed"
            content = dest.read_text()
            # Verify valid TOML
            tomllib.loads(content)

    def test_install_profiles_idempotent(self, tmp_path: Path) -> None:
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        cfg = MagicMock(profiles_dir=profiles_dir)

        # Pre-create profile files with known content
        original_contents: dict[str, str] = {}
        for name, content in PROFILES.items():
            dest = profiles_dir / f"{name}.toml"
            dest.write_text(content)
            original_contents[name] = content

        _install_profiles(cfg)

        for name in PROFILES:
            dest = profiles_dir / f"{name}.toml"
            assert dest.read_text() == original_contents[name], (
                f"Profile {name} was modified when it should have been left unchanged"
            )


class TestSetupSshKey:
    def test_setup_ssh_key_exists(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test_key"
        key_path.write_text("existing key")
        cfg = MagicMock(ssh_key=key_path)

        with patch("sandboxctl.setup_cmd.subprocess.run") as mock_run:
            _setup_ssh_key(cfg)
            # ssh-keygen should NOT be called when the key already exists
            mock_run.assert_not_called()

    def test_setup_ssh_key_generated(self, tmp_path: Path) -> None:
        key_path = tmp_path / "nonexistent_key"
        cfg = MagicMock(ssh_key=key_path)

        with patch("sandboxctl.setup_cmd.subprocess.run") as mock_run:
            _setup_ssh_key(cfg)
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "ssh-keygen" in cmd
            assert str(key_path) in cmd


class TestSetupGithubPat:
    def test_github_pat_valid_in_keychain(self) -> None:
        cfg = MagicMock(keychain_github="sandboxctl-github-token")

        mock_result = subprocess.CompletedProcess(
            args=["gh", "api", "user", "--jq", ".login"],
            returncode=0,
            stdout="testuser\n",
            stderr="",
        )

        with (
            patch("sandboxctl.setup_cmd.get_credential", return_value="ghp_testtoken"),
            patch("sandboxctl.setup_cmd.subprocess.run", return_value=mock_result),
        ):
            token = _setup_github_pat(cfg)
            assert token == "ghp_testtoken"

    def test_github_pat_skip(self) -> None:
        cfg = MagicMock(keychain_github="sandboxctl-github-token")

        with (
            patch("sandboxctl.setup_cmd.get_credential", return_value=None),
            patch("sandboxctl.setup_cmd.typer.prompt", return_value=""),
        ):
            token = _setup_github_pat(cfg)
            assert token is None


class TestRestartCommand:
    def test_restart_help(self) -> None:
        result = runner.invoke(app, ["restart", "--help"])
        assert result.exit_code == 0
        assert "restart" in result.output.lower() or "recreate" in result.output.lower()

    def test_restart_confirmation_abort(self) -> None:
        cfg = MagicMock()
        prof = MagicMock()

        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", return_value=prof),
            patch("sandboxctl.openshell.sandbox_delete") as mock_delete,
        ):
            result = runner.invoke(app, ["restart", "mybox"], input="n\n")
            assert result.exit_code == 1
            mock_delete.assert_not_called()

    def test_restart_yes_flag(self) -> None:
        cfg = MagicMock()
        prof = MagicMock()

        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", return_value=prof),
            patch("sandboxctl.openshell.sandbox_delete") as mock_delete,
            patch("sandboxctl.create.create_sandbox") as mock_create,
        ):
            result = runner.invoke(app, ["restart", "mybox", "--yes"])
            assert result.exit_code == 0
            mock_delete.assert_called_once_with("mybox")
            mock_create.assert_called_once()

    def test_restart_missing_profile(self) -> None:
        cfg = MagicMock()

        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError("not found")),
            patch("sandboxctl.profile.list_profiles", return_value=[]),
        ):
            result = runner.invoke(app, ["restart", "nonexistent", "--yes"])
            assert result.exit_code == 1
            assert "not found" in result.output.lower()


class TestBundledProfiles:
    def test_bundled_profiles_parse(self) -> None:
        assert len(PROFILES) == 3
        for name, content in PROFILES.items():
            parsed = tomllib.loads(content)
            assert isinstance(parsed, dict), f"Profile '{name}' did not parse to a dict"
