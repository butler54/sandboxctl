"""Tests for all CLI commands via Typer CliRunner."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from sandboxctl.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "sandboxctl" in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sandboxctl" in result.output


class TestConfigCommands:
    def test_config_init_creates_file(self, tmp_path: Path) -> None:
        cfg = MagicMock(config_dir=tmp_path, profiles_dir=tmp_path / "profiles")
        with patch("sandboxctl.cli.load_config", return_value=cfg):
            result = runner.invoke(app, ["config", "init"])
            assert result.exit_code == 0
            assert "Created" in result.output
            assert (tmp_path / "config.toml").exists()

    def test_config_init_already_exists(self, tmp_path: Path) -> None:
        (tmp_path / "config.toml").write_text("existing")
        cfg = MagicMock(config_dir=tmp_path, profiles_dir=tmp_path / "profiles")
        with patch("sandboxctl.cli.load_config", return_value=cfg):
            result = runner.invoke(app, ["config", "init"])
            assert result.exit_code == 1
            assert "already exists" in result.output

    def test_config_show(self, tmp_path: Path) -> None:
        cfg = MagicMock(
            config_dir=tmp_path,
            profiles_dir=tmp_path / "profiles",
            ssh_key=tmp_path / ".ssh" / "key",
            git_user_name="",
            git_user_email="",
            default_model="claude-test",
            default_theme="dark",
            vertex_project_id="",
        )
        with patch("sandboxctl.cli.load_config", return_value=cfg):
            result = runner.invoke(app, ["config", "show"])
            assert result.exit_code == 0
            assert "(not set)" in result.output
            assert "claude-test" in result.output

    def test_config_path(self, tmp_path: Path) -> None:
        cfg = MagicMock(config_dir=tmp_path)
        with patch("sandboxctl.cli.load_config", return_value=cfg):
            result = runner.invoke(app, ["config", "path"])
            assert result.exit_code == 0
            assert "config.toml" in result.output


class TestListCommand:
    def test_list_with_profiles(self) -> None:
        cfg = MagicMock()
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.list_profiles", return_value=["dev", "prod"]),
            patch("sandboxctl.openshell.sandbox_list", return_value=[]),
        ):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "dev" in result.output

    def test_list_no_profiles(self) -> None:
        cfg = MagicMock()
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.list_profiles", return_value=[]),
            patch("sandboxctl.openshell.sandbox_list", return_value=[]),
        ):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "No profiles found" in result.output

    def test_list_openshell_error(self) -> None:
        cfg = MagicMock()
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.list_profiles", return_value=[]),
            patch("sandboxctl.openshell.sandbox_list", side_effect=Exception("not running")),
        ):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "Could not list" in result.output


class TestStatusCommand:
    def test_status_with_gateway(self) -> None:
        gw = {"gateway": "running", "version": "1.0"}
        with patch("sandboxctl.openshell.gateway_status", return_value=gw):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0

    def test_status_unreachable(self) -> None:
        with patch("sandboxctl.openshell.gateway_status", side_effect=Exception("down")):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "Could not reach" in result.output


class TestDeleteCommand:
    def test_delete_confirmed(self) -> None:
        with patch("sandboxctl.openshell.sandbox_delete") as mock_del:
            result = runner.invoke(app, ["delete", "mybox"], input="y\n")
            assert result.exit_code == 0
            assert "Deleted" in result.output
            mock_del.assert_called_once_with("mybox")

    def test_delete_aborted(self) -> None:
        with patch("sandboxctl.openshell.sandbox_delete") as mock_del:
            result = runner.invoke(app, ["delete", "mybox"], input="n\n")
            assert result.exit_code != 0
            mock_del.assert_not_called()


class TestValidateCommand:
    def test_validate_healthy(self) -> None:
        report = MagicMock(healthy=True)
        with (
            patch("sandboxctl.health.diagnose", return_value=report),
            patch("sandboxctl.openshell.sandbox_exec_pipe", return_value="ok 1 - test\n"),
        ):
            result = runner.invoke(app, ["validate", "mybox"])
            assert result.exit_code == 0
            assert "Running validation" in result.output

    def test_validate_unhealthy(self) -> None:
        report = MagicMock(healthy=False)
        with patch("sandboxctl.health.diagnose", return_value=report):
            result = runner.invoke(app, ["validate", "mybox"])
            assert result.exit_code == 1
            assert "not healthy" in result.output


class TestInitCommand:
    def test_init_creates_profile(self, tmp_path: Path) -> None:
        cfg = MagicMock(profiles_dir=tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.init_profile", return_value=tmp_path / "test.toml"),
        ):
            result = runner.invoke(app, ["init", "test"])
            assert result.exit_code == 0
            assert "Created profile" in result.output

    def test_init_already_exists(self, tmp_path: Path) -> None:
        cfg = MagicMock(profiles_dir=tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.init_profile", side_effect=FileExistsError("exists")),
        ):
            result = runner.invoke(app, ["init", "test"])
            assert result.exit_code == 1


class TestUpgradeCommand:
    def test_upgrade_calls_openshell(self) -> None:
        with patch("subprocess.run") as mock_run:
            result = runner.invoke(app, ["upgrade"])
            assert result.exit_code == 0
            assert "Upgrading" in result.output
            mock_run.assert_called_once()


class TestDoctorCommand:
    def _mock_host_checks(self) -> list:
        from sandboxctl.doctor import CheckResult

        return [
            CheckResult(passed=True, name="GitHub PAT", details="Authenticated"),
            CheckResult(passed=True, name="GitLab PAT", details="No servers"),
            CheckResult(passed=True, name="gcloud ADC", details="Valid"),
            CheckResult(passed=True, name="GWS credentials", details="Valid"),
            CheckResult(passed=True, name="SSH key", details="Present"),
            CheckResult(passed=True, name="CA bundle", details="System defaults"),
        ]

    def test_doctor_healthy(self) -> None:
        report = MagicMock(healthy=True, details=["Gateway: running", "Container: running"], recovery_action="none")
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch("sandboxctl.doctor.check_host_credentials", return_value=self._mock_host_checks()),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
            patch("sandboxctl.health.diagnose", return_value=report),
        ):
            result = runner.invoke(app, ["doctor", "mybox"])
            assert result.exit_code == 0
            assert "all checks passed" in result.output

    def test_doctor_unhealthy(self) -> None:
        report = MagicMock(
            healthy=False,
            details=["Gateway: running", "Container: stopped"],
            recovery_action="container_missing_needs_recreate",
        )
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch("sandboxctl.doctor.check_host_credentials", return_value=self._mock_host_checks()),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
            patch("sandboxctl.health.diagnose", return_value=report),
        ):
            result = runner.invoke(app, ["doctor", "mybox"])
            assert result.exit_code == 0
            assert "container_missing_needs_recreate" in result.output

    def test_doctor_no_recover(self) -> None:
        report = MagicMock(healthy=False, details=["Gateway: stopped"], recovery_action="gateway_not_running")
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch("sandboxctl.doctor.check_host_credentials", return_value=self._mock_host_checks()),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
            patch("sandboxctl.health.diagnose", return_value=report) as mock_diag,
        ):
            result = runner.invoke(app, ["doctor", "mybox", "--no-recover"])
            assert result.exit_code == 0
            mock_diag.assert_called_once_with("mybox", auto_recover=False)


class TestCreateCommand:
    def test_create_help(self) -> None:
        result = runner.invoke(app, ["create", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--profile" in output
        assert "--ephemeral" in output
        assert "--no-editor" in output

    def test_create_missing_profile(self, tmp_path: Path) -> None:
        cfg = MagicMock(config_dir=tmp_path, profiles_dir=tmp_path / "profiles")
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError("not found")),
            patch("sandboxctl.profile.list_profiles", return_value=[]),
        ):
            result = runner.invoke(app, ["create", "--profile", "nonexistent"])
            assert result.exit_code == 1
            assert "not found" in result.output.lower()


class TestOpenCommand:
    def test_open_help(self) -> None:
        result = runner.invoke(app, ["open", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--shell" in output
        assert "--code" in output
        assert "--code-only" in output
        assert "--claude-only" in output
