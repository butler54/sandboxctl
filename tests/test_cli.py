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
        with (
            patch("sandboxctl.openshell.sandbox_delete") as mock_del,
            patch("sandboxctl.context.backup_claude_context", return_value=None),
        ):
            result = runner.invoke(app, ["delete", "mybox"], input="y\n")
            assert result.exit_code == 0
            assert "Deleted" in result.output
            mock_del.assert_called_once_with("mybox")

    def test_delete_aborted(self) -> None:
        with patch("sandboxctl.openshell.sandbox_delete") as mock_del:
            result = runner.invoke(app, ["delete", "mybox"], input="n\n")
            assert result.exit_code != 0
            mock_del.assert_not_called()

    def test_delete_backs_up_context(self, tmp_path: Path) -> None:
        with (
            patch("sandboxctl.openshell.sandbox_delete"),
            patch("sandboxctl.context.backup_claude_context", return_value=tmp_path) as mock_backup,
        ):
            result = runner.invoke(app, ["delete", "mybox"], input="y\n")
            assert result.exit_code == 0
            assert "backed up" in result.output.lower()
            mock_backup.assert_called_once()


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
    def test_detects_homebrew(self) -> None:
        def which_side_effect(cmd: str) -> str | None:
            return "/opt/homebrew/bin/brew" if cmd == "brew" else None

        def run_side_effect(cmd: list, **kwargs: object) -> object:  # noqa: ARG001
            from unittest.mock import MagicMock

            mock_result = MagicMock()
            if cmd == ["brew", "list", "openshell"]:
                mock_result.returncode = 0
            elif cmd == ["brew", "upgrade", "openshell"]:
                mock_result.returncode = 0
            else:
                mock_result.returncode = 1
            return mock_result

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = runner.invoke(app, ["upgrade"])
            assert result.exit_code == 0
            assert "upgraded via Homebrew" in result.output
            assert "restart" in result.output

    def test_fallback_to_pip(self) -> None:
        def which_side_effect(cmd: str) -> str | None:
            return "/usr/bin/pip3" if cmd == "pip3" else None

        def run_side_effect(cmd: list, **kwargs: object) -> object:  # noqa: ARG001
            from unittest.mock import MagicMock

            mock_result = MagicMock()
            if cmd == ["pip3", "show", "openshell"]:
                mock_result.returncode = 0
            elif cmd == ["pip3", "install", "--upgrade", "openshell"]:
                mock_result.returncode = 0
            else:
                mock_result.returncode = 1
            return mock_result

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = runner.invoke(app, ["upgrade"])
            assert result.exit_code == 0
            assert "upgraded via pip" in result.output

    def test_manual_fallback(self) -> None:
        with (
            patch("shutil.which", return_value=None),
            patch("subprocess.run") as mock_run,
        ):
            result = runner.invoke(app, ["upgrade"])
            assert result.exit_code == 0
            assert "No supported installation method" in result.output
            assert "curl" in result.output
            mock_run.assert_not_called()

    def test_brew_upgrade_failure(self) -> None:
        def which_side_effect(cmd: str) -> str | None:
            return "/opt/homebrew/bin/brew" if cmd == "brew" else None

        def run_side_effect(cmd: list, **kwargs: object) -> object:  # noqa: ARG001
            from unittest.mock import MagicMock

            mock_result = MagicMock()
            if cmd == ["brew", "list", "openshell"]:
                mock_result.returncode = 0
            elif cmd == ["brew", "upgrade", "openshell"]:
                mock_result.returncode = 1
            else:
                mock_result.returncode = 1
            return mock_result

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = runner.invoke(app, ["upgrade"])
            assert result.exit_code == 0
            assert "failed" in result.output

    def test_gateway_advisory_after_success(self) -> None:
        def which_side_effect(cmd: str) -> str | None:
            return "/opt/homebrew/bin/brew" if cmd == "brew" else None

        def run_side_effect(cmd: list, **kwargs: object) -> object:  # noqa: ARG001
            from unittest.mock import MagicMock

            mock_result = MagicMock()
            if cmd == ["brew", "list", "openshell"]:
                mock_result.returncode = 0
            elif cmd == ["brew", "upgrade", "openshell"]:
                mock_result.returncode = 0
            else:
                mock_result.returncode = 1
            return mock_result

        with (
            patch("shutil.which", side_effect=which_side_effect),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            result = runner.invoke(app, ["upgrade"])
            assert result.exit_code == 0
            assert "restart" in result.output
            assert "openshell" in result.output


class TestRecoverCommand:
    def test_recover_help(self) -> None:
        result = runner.invoke(app, ["recover", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "recover" in output.lower()

    def test_recover_single(self) -> None:
        with (
            patch("sandboxctl.health.check_container_state") as mock_state,
            patch("sandboxctl.health.recover_container", return_value=True),
        ):
            from sandboxctl.health import ContainerState

            mock_state.return_value = ContainerState.STOPPED
            result = runner.invoke(app, ["recover", "mybox"])
        assert result.exit_code == 0
        assert "recovered" in result.output

    def test_recover_already_running(self) -> None:
        with patch("sandboxctl.health.check_container_state") as mock_state:
            from sandboxctl.health import ContainerState

            mock_state.return_value = ContainerState.RUNNING
            result = runner.invoke(app, ["recover", "mybox"])
        assert result.exit_code == 0
        assert "already running" in result.output


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
            CheckResult(passed=True, name="MCP OAuth", details="No servers configured"),
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


class TestBackupCommand:
    def test_backup_success(self, tmp_path: Path) -> None:
        with patch("sandboxctl.context.backup_claude_context", return_value=tmp_path):
            result = runner.invoke(app, ["backup", "mybox"])
            assert result.exit_code == 0
            assert "Backed up" in result.output

    def test_backup_no_context(self) -> None:
        with patch("sandboxctl.context.backup_claude_context", return_value=None):
            result = runner.invoke(app, ["backup", "mybox"])
            assert result.exit_code == 0
            assert "No Claude context" in result.output

    def test_backup_all(self, tmp_path: Path) -> None:
        sandboxes = [{"name": "a", "created": "now", "phase": "Ready"}]
        with (
            patch("sandboxctl.openshell.sandbox_list", return_value=sandboxes),
            patch("sandboxctl.context.backup_claude_context", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["backup", "--all"])
            assert result.exit_code == 0
            assert "1/1" in result.output

    def test_backup_all_with_name_rejected(self) -> None:
        result = runner.invoke(app, ["backup", "mybox", "--all"])
        assert result.exit_code == 1
        assert "Cannot use --all" in result.output

    def test_backup_no_args(self) -> None:
        result = runner.invoke(app, ["backup"])
        assert result.exit_code == 1
        assert "Provide a sandbox name or use --all" in result.output


class TestRestoreCommand:
    def test_restore_success(self) -> None:
        with patch("sandboxctl.context.restore_claude_context", return_value=True):
            result = runner.invoke(app, ["restore", "mybox"])
            assert result.exit_code == 0
            assert "restored" in result.output.lower()

    def test_restore_no_backup(self) -> None:
        with patch("sandboxctl.context.restore_claude_context", return_value=False):
            result = runner.invoke(app, ["restore", "mybox"])
            assert result.exit_code == 0
            assert "No backup" in result.output


class TestOpenCommand:
    def test_open_help(self) -> None:
        result = runner.invoke(app, ["open", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--shell" in output
        assert "--code" in output
        assert "--code-only" in output
        assert "--claude-only" in output


class TestBundledProfiles:
    def test_bundled_profiles_parse_toml(self) -> None:
        """Verify bundled profile templates are valid TOML with Extensions model."""
        import tomllib

        from sandboxctl.bundled_profiles import PROFILES
        from sandboxctl.models import Extensions

        for profile_name, toml_content in PROFILES.items():
            # Parse TOML
            data = tomllib.loads(toml_content)

            # Verify extensions section parses into Extensions model (if present)
            if "extensions" in data:
                ext = Extensions(**data["extensions"])
                # Verify field names are correct (list -> extensions_list, local_only)
                assert isinstance(ext.extensions_list, list)
                assert isinstance(ext.local_only, list)

                # Verify extension IDs are valid
                from sandboxctl.extensions import validate_extension_id

                for ext_id in ext.extensions_list:
                    assert validate_extension_id(ext_id), f"Invalid extension ID in {profile_name}: {ext_id}"

    def test_generic_dev_has_extensions_section(self) -> None:
        """generic-dev profile has [extensions] section."""
        from sandboxctl.bundled_profiles import PROFILES

        assert "[extensions]" in PROFILES["generic-dev"]

    def test_ai_assisted_has_extensions_section(self) -> None:
        """ai-assisted profile has [extensions] section."""
        from sandboxctl.bundled_profiles import PROFILES

        assert "[extensions]" in PROFILES["ai-assisted"]

    def test_minimal_has_no_extensions_section(self) -> None:
        """minimal profile has no [extensions] section (keep it minimal)."""
        from sandboxctl.bundled_profiles import PROFILES

        assert "[extensions]" not in PROFILES["minimal"]


class TestExtensionsCommand:
    def test_extensions_help(self) -> None:
        result = runner.invoke(app, ["extensions", "--help"])
        assert result.exit_code == 0
        assert "extensions" in result.output.lower()

    def test_extensions_install_help(self) -> None:
        result = runner.invoke(app, ["extensions", "install", "--help"])
        assert result.exit_code == 0
        assert "install" in result.output.lower()

    def test_extensions_install_missing_profile(self) -> None:
        cfg = MagicMock()
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", side_effect=FileNotFoundError),
        ):
            result = runner.invoke(app, ["extensions", "install", "mybox"])
            assert result.exit_code == 1
            assert "not found" in result.output.lower()

    def test_extensions_install_no_vscode(self) -> None:
        cfg = MagicMock()
        profile = MagicMock()
        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.config.find_vscode_bin", return_value=None),
        ):
            result = runner.invoke(app, ["extensions", "install", "mybox"])
            assert result.exit_code == 1
            assert "code" in result.output.lower() or "vscode" in result.output.lower()

    def test_extensions_install_success(self) -> None:
        from pathlib import Path

        from sandboxctl.extensions import InstallReport
        from sandboxctl.models import Extensions

        cfg = MagicMock()
        profile = MagicMock()
        ext_list = ["ms-python.python", "rust-lang.rust-analyzer"]
        profile.extensions = Extensions(extensions_list=ext_list)
        vscode_bin = Path("/usr/bin/code")
        report = InstallReport(installed=ext_list)

        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.config.find_vscode_bin", return_value=vscode_bin),
            patch("sandboxctl.extensions.classify_remote_extensions", return_value=ext_list),
            patch("sandboxctl.extensions.install_extensions", return_value=report) as mock_install,
        ):
            result = runner.invoke(app, ["extensions", "install", "mybox"])
            assert result.exit_code == 0
            mock_install.assert_called_once_with("mybox", ext_list, vscode_bin)
            assert "2" in result.output  # 2 installed

    def test_extensions_install_failures_exit_zero(self) -> None:
        from pathlib import Path

        from sandboxctl.extensions import InstallReport
        from sandboxctl.models import Extensions

        cfg = MagicMock()
        profile = MagicMock()
        profile.extensions = Extensions(extensions_list=["valid.ext"])
        vscode_bin = Path("/usr/bin/code")
        report = InstallReport(installed=[], failed=[("valid.ext", "network error")])

        with (
            patch("sandboxctl.cli.load_config", return_value=cfg),
            patch("sandboxctl.profile.load_profile", return_value=profile),
            patch("sandboxctl.config.find_vscode_bin", return_value=vscode_bin),
            patch("sandboxctl.extensions.classify_remote_extensions", return_value=["valid.ext"]),
            patch("sandboxctl.extensions.install_extensions", return_value=report),
        ):
            result = runner.invoke(app, ["extensions", "install", "mybox"])
            assert result.exit_code == 0  # warn-and-continue
            assert "1" in result.output  # 1 failed
