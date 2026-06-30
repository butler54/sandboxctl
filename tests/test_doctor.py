"""Tests for the doctor module: credential checks, fix operations, and orchestration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from sandboxctl.cli import app
from sandboxctl.doctor import (
    ALL_CHECKS,
    CABundleCheck,
    CheckResult,
    FixResult,
    GCloudADCCheck,
    GitHubPATCheck,
    GitLabPATCheck,
    GWSCredentialCheck,
    SSHKeyCheck,
    check_host_credentials,
    fix_sandbox_credentials,
)
from sandboxctl.models import CredentialConfig

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides: object) -> MagicMock:
    """Build a MagicMock that behaves like SandboxctlConfig."""
    cfg = MagicMock()
    cfg.keychain_github = overrides.get("keychain_github", "sandboxctl-github-token")
    cfg.keychain_gitlab = overrides.get("keychain_gitlab", "sandboxctl-gitlab-token")
    cfg.ssh_key = overrides.get("ssh_key", Path("/home/testuser/.ssh/sandboxctl_ed25519"))
    cfg.ca_bundle = overrides.get("ca_bundle", None)
    cfg.ca_paths = overrides.get("ca_paths", [])
    return cfg


# =========================================================================
# TestCheckResult
# =========================================================================


class TestCheckResult:
    def test_check_result_passed(self) -> None:
        r = CheckResult(passed=True, name="test-check", details="all good")
        assert r.passed is True
        assert r.name == "test-check"
        assert r.details == "all good"
        assert r.fix_hint is None

    def test_check_result_failed_with_hint(self) -> None:
        r = CheckResult(
            passed=False,
            name="test-check",
            details="missing credential",
            fix_hint="Run: sandboxctl setup",
        )
        assert r.passed is False
        assert r.fix_hint is not None
        assert "setup" in r.fix_hint


# =========================================================================
# TestGitHubPATCheck
# =========================================================================


class TestGitHubPATCheck:
    def test_no_token_stored(self) -> None:
        cfg = _make_config()
        chk = GitHubPATCheck()
        with patch("sandboxctl.doctor.get_credential", return_value=None):
            result = chk.check(cfg)
        assert result.passed is False
        assert result.fix_hint is not None
        assert "setup" in result.fix_hint.lower()

    def test_token_valid(self) -> None:
        cfg = _make_config()
        chk = GitHubPATCheck()
        mock_proc = MagicMock(returncode=0, stdout="testuser\n", stderr="")
        with (
            patch("sandboxctl.doctor.get_credential", return_value="ghp_testtoken"),
            patch("sandboxctl.doctor.subprocess.run", return_value=mock_proc),
        ):
            result = chk.check(cfg)
        assert result.passed is True
        assert "testuser" in result.details

    def test_token_expired(self) -> None:
        cfg = _make_config()
        chk = GitHubPATCheck()
        mock_proc = MagicMock(returncode=1, stdout="", stderr="Bad credentials")
        with (
            patch("sandboxctl.doctor.get_credential", return_value="ghp_expired"),
            patch("sandboxctl.doctor.subprocess.run", return_value=mock_proc),
        ):
            result = chk.check(cfg)
        assert result.passed is False
        assert "expired" in result.fix_hint.lower()

    def test_gh_cli_not_found(self) -> None:
        cfg = _make_config()
        chk = GitHubPATCheck()
        with (
            patch("sandboxctl.doctor.get_credential", return_value="ghp_token"),
            patch("sandboxctl.doctor.subprocess.run", side_effect=FileNotFoundError),
        ):
            result = chk.check(cfg)
        assert result.passed is False
        assert "not found" in result.details.lower()

    def test_gh_cli_timeout(self) -> None:
        cfg = _make_config()
        chk = GitHubPATCheck()
        with (
            patch("sandboxctl.doctor.get_credential", return_value="ghp_token"),
            patch(
                "sandboxctl.doctor.subprocess.run",
                side_effect=subprocess.TimeoutExpired("gh", 10),
            ),
        ):
            result = chk.check(cfg)
        assert result.passed is False
        assert "timed out" in result.details.lower()

    def test_fix_injects_token(self) -> None:
        cfg = _make_config()
        chk = GitHubPATCheck()
        with (
            patch("sandboxctl.doctor.get_credential", return_value="ghp_mytoken"),
            patch("sandboxctl.doctor.osh.sandbox_exec_pipe") as mock_pipe,
        ):
            result = chk.fix("mybox", cfg)
        assert result.success is True
        mock_pipe.assert_called_once()
        assert "ghp_mytoken" in mock_pipe.call_args[0][1]

    def test_fix_no_token(self) -> None:
        cfg = _make_config()
        chk = GitHubPATCheck()
        with patch("sandboxctl.doctor.get_credential", return_value=None):
            result = chk.fix("mybox", cfg)
        assert result.success is False

    def test_required_by_default(self) -> None:
        chk = GitHubPATCheck()
        cred_config = CredentialConfig()
        assert chk.required_by(cred_config) is True

    def test_not_required_when_disabled(self) -> None:
        chk = GitHubPATCheck()
        cred_config = CredentialConfig(github=False)
        assert chk.required_by(cred_config) is False


# =========================================================================
# TestGitLabPATCheck
# =========================================================================


class TestGitLabPATCheck:
    def test_no_token_stored(self) -> None:
        cfg = _make_config()
        chk = GitLabPATCheck()
        with patch("sandboxctl.doctor.get_credential", return_value=None):
            result = chk.check(cfg)
        assert result.passed is False
        assert "setup" in result.fix_hint.lower()

    def test_token_present_no_servers(self) -> None:
        """Token exists but no servers configured in profiles."""
        cfg = _make_config()
        chk = GitLabPATCheck()
        with (
            patch("sandboxctl.doctor.get_credential", return_value="glpat-test"),
            patch("sandboxctl.doctor.list_profiles", return_value=[]),
        ):
            result = chk.check(cfg)
        assert result.passed is True
        assert "no gitlab servers" in result.details.lower()

    def test_server_token_valid(self) -> None:
        cfg = _make_config()
        chk = GitLabPATCheck()
        profile = MagicMock()
        profile.repos = {"gitlab.example.com": ["repo1"]}
        profile.credentials.gitlab_servers = []
        mock_proc = MagicMock(returncode=0, stdout='{"username":"testuser"}', stderr="")
        with (
            patch("sandboxctl.doctor.get_credential", return_value="glpat-test"),
            patch("sandboxctl.doctor.list_profiles", return_value=["dev"]),
            patch("sandboxctl.doctor.load_profile", return_value=profile),
            patch("sandboxctl.doctor.subprocess.run", return_value=mock_proc),
        ):
            result = chk.check(cfg)
        assert result.passed is True
        assert "1 server" in result.details

    def test_server_token_invalid(self) -> None:
        cfg = _make_config()
        chk = GitLabPATCheck()
        profile = MagicMock()
        profile.repos = {"gitlab.example.com": ["repo1"]}
        profile.credentials.gitlab_servers = []
        mock_proc = MagicMock(returncode=22, stdout="", stderr="Unauthorized")
        with (
            patch("sandboxctl.doctor.get_credential", return_value="glpat-bad"),
            patch("sandboxctl.doctor.list_profiles", return_value=["dev"]),
            patch("sandboxctl.doctor.load_profile", return_value=profile),
            patch("sandboxctl.doctor.subprocess.run", return_value=mock_proc),
        ):
            result = chk.check(cfg)
        assert result.passed is False
        assert "expired" in result.fix_hint.lower() or "scope" in result.fix_hint.lower()

    def test_required_by_checks_flag(self) -> None:
        chk = GitLabPATCheck()
        assert chk.required_by(CredentialConfig(gitlab=True)) is True
        assert chk.required_by(CredentialConfig()) is False


# =========================================================================
# TestGCloudADCCheck
# =========================================================================


class TestGCloudADCCheck:
    def test_no_adc_file(self, tmp_path: Path) -> None:
        chk = GCloudADCCheck()
        chk._ADC_PATH = tmp_path / "nonexistent.json"
        cfg = _make_config()
        result = chk.check(cfg)
        assert result.passed is False
        assert "not found" in result.details.lower()
        assert "login" in result.fix_hint.lower()

    def test_adc_valid(self, tmp_path: Path) -> None:
        adc_file = tmp_path / "adc.json"
        adc_file.write_text('{"type": "authorized_user"}')
        chk = GCloudADCCheck()
        chk._ADC_PATH = adc_file
        cfg = _make_config()
        mock_proc = MagicMock(returncode=0, stdout="ya29.token\n", stderr="")
        with patch("sandboxctl.doctor.subprocess.run", return_value=mock_proc):
            result = chk.check(cfg)
        assert result.passed is True
        assert "valid" in result.details.lower()

    def test_adc_token_invalid(self, tmp_path: Path) -> None:
        adc_file = tmp_path / "adc.json"
        adc_file.write_text('{"type": "authorized_user"}')
        chk = GCloudADCCheck()
        chk._ADC_PATH = adc_file
        cfg = _make_config()
        mock_proc = MagicMock(returncode=1, stdout="", stderr="invalid grant")
        with patch("sandboxctl.doctor.subprocess.run", return_value=mock_proc):
            result = chk.check(cfg)
        assert result.passed is False
        assert "login" in result.fix_hint.lower()

    def test_gcloud_missing(self, tmp_path: Path) -> None:
        adc_file = tmp_path / "adc.json"
        adc_file.write_text('{"type": "authorized_user"}')
        chk = GCloudADCCheck()
        chk._ADC_PATH = adc_file
        cfg = _make_config()
        with patch("sandboxctl.doctor.subprocess.run", side_effect=FileNotFoundError):
            result = chk.check(cfg)
        assert result.passed is False
        assert "not found" in result.details.lower()

    def test_required_by_checks_flag(self) -> None:
        chk = GCloudADCCheck()
        assert chk.required_by(CredentialConfig(gcloud_adc=True)) is True
        assert chk.required_by(CredentialConfig()) is False


# =========================================================================
# TestGWSCredentialCheck
# =========================================================================


class TestGWSCredentialCheck:
    def test_no_client_secret(self, tmp_path: Path) -> None:
        chk = GWSCredentialCheck()
        chk._GWS_DIR = tmp_path / "gws"
        chk._GWS_DIR.mkdir()
        cfg = _make_config()
        result = chk.check(cfg)
        assert result.passed is False
        assert "client_secret" in result.details.lower()

    def test_valid_credentials(self, tmp_path: Path) -> None:
        gws_dir = tmp_path / "gws"
        gws_dir.mkdir()
        (gws_dir / "client_secret.json").write_text('{"installed": {}}')
        (gws_dir / "credentials.json").write_text(json.dumps({"refresh_token": "rt_123"}))
        chk = GWSCredentialCheck()
        chk._GWS_DIR = gws_dir
        cfg = _make_config()
        result = chk.check(cfg)
        assert result.passed is True
        assert "refresh_token" in result.details.lower()

    def test_no_refresh_token(self, tmp_path: Path) -> None:
        gws_dir = tmp_path / "gws"
        gws_dir.mkdir()
        (gws_dir / "client_secret.json").write_text('{"installed": {}}')
        (gws_dir / "credentials.json").write_text(json.dumps({"access_token": "at_only"}))
        chk = GWSCredentialCheck()
        chk._GWS_DIR = gws_dir
        cfg = _make_config()
        result = chk.check(cfg)
        assert result.passed is False
        assert "refresh_token" in result.details.lower()

    def test_no_credentials_file(self, tmp_path: Path) -> None:
        gws_dir = tmp_path / "gws"
        gws_dir.mkdir()
        (gws_dir / "client_secret.json").write_text('{"installed": {}}')
        chk = GWSCredentialCheck()
        chk._GWS_DIR = gws_dir
        cfg = _make_config()
        result = chk.check(cfg)
        assert result.passed is False
        assert "not found" in result.details.lower() or "not authenticated" in result.details.lower()

    def test_required_by_checks_flag(self) -> None:
        chk = GWSCredentialCheck()
        assert chk.required_by(CredentialConfig(gws=True)) is True
        assert chk.required_by(CredentialConfig()) is False


# =========================================================================
# TestSSHKeyCheck
# =========================================================================


class TestSSHKeyCheck:
    def test_key_exists(self, tmp_path: Path) -> None:
        key = tmp_path / "id_ed25519"
        key.write_text("private key content")
        pub = tmp_path / "id_ed25519.pub"
        pub.write_text("public key content")
        cfg = _make_config(ssh_key=key)
        chk = SSHKeyCheck()
        result = chk.check(cfg)
        assert result.passed is True

    def test_key_missing(self, tmp_path: Path) -> None:
        key = tmp_path / "nonexistent_key"
        cfg = _make_config(ssh_key=key)
        chk = SSHKeyCheck()
        result = chk.check(cfg)
        assert result.passed is False
        assert "not found" in result.details.lower()

    def test_pub_key_missing(self, tmp_path: Path) -> None:
        key = tmp_path / "id_ed25519"
        key.write_text("private key content")
        cfg = _make_config(ssh_key=key)
        chk = SSHKeyCheck()
        result = chk.check(cfg)
        assert result.passed is False
        assert "public" in result.details.lower()

    def test_fix_uploads_key(self, tmp_path: Path) -> None:
        key = tmp_path / "id_ed25519"
        key.write_text("private key content")
        pub = tmp_path / "id_ed25519.pub"
        pub.write_text("public key content")
        cfg = _make_config(ssh_key=key)
        chk = SSHKeyCheck()
        with (
            patch("sandboxctl.doctor.osh.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.doctor.osh.sandbox_upload") as mock_upload,
        ):
            result = chk.fix("mybox", cfg)
        assert result.success is True
        assert mock_upload.call_count >= 1
        mock_pipe.assert_called()

    def test_fix_no_key(self, tmp_path: Path) -> None:
        key = tmp_path / "nonexistent_key"
        cfg = _make_config(ssh_key=key)
        chk = SSHKeyCheck()
        result = chk.fix("mybox", cfg)
        assert result.success is False

    def test_required_by_checks_flag(self) -> None:
        chk = SSHKeyCheck()
        assert chk.required_by(CredentialConfig()) is True
        assert chk.required_by(CredentialConfig(ssh_key=False)) is False


# =========================================================================
# TestCABundleCheck
# =========================================================================


class TestCABundleCheck:
    def test_no_ca_configured(self) -> None:
        cfg = _make_config(ca_bundle=None, ca_paths=[])
        chk = CABundleCheck()
        result = chk.check(cfg)
        assert result.passed is True
        assert "no custom" in result.details.lower() or "default" in result.details.lower()

    def test_ca_file_exists(self, tmp_path: Path) -> None:
        ca = tmp_path / "custom-ca.pem"
        ca.write_text("-----BEGIN CERTIFICATE-----\n...")
        cfg = _make_config(ca_paths=[ca])
        chk = CABundleCheck()
        result = chk.check(cfg)
        assert result.passed is True
        assert "1" in result.details

    def test_ca_file_missing(self, tmp_path: Path) -> None:
        missing_ca = tmp_path / "nonexistent-ca.pem"
        cfg = _make_config(ca_paths=[missing_ca])
        chk = CABundleCheck()
        result = chk.check(cfg)
        assert result.passed is False
        assert "missing" in result.details.lower()

    def test_ca_bundle_exists(self, tmp_path: Path) -> None:
        bundle = tmp_path / "ca-bundle.pem"
        bundle.write_text("-----BEGIN CERTIFICATE-----\n...")
        cfg = _make_config(ca_bundle=bundle)
        chk = CABundleCheck()
        result = chk.check(cfg)
        assert result.passed is True

    def test_ca_bundle_missing(self, tmp_path: Path) -> None:
        missing_bundle = tmp_path / "missing-bundle.pem"
        cfg = _make_config(ca_bundle=missing_bundle)
        chk = CABundleCheck()
        result = chk.check(cfg)
        assert result.passed is False

    def test_required_always(self) -> None:
        chk = CABundleCheck()
        assert chk.required_by(CredentialConfig()) is True
        assert chk.required_by(CredentialConfig(github=False, ssh_key=False)) is True


# =========================================================================
# TestOrchestration
# =========================================================================


class TestOrchestration:
    def test_check_host_credentials_runs_all(self) -> None:
        """Verify check_host_credentials returns results for all 6 checks."""
        cfg = _make_config()
        with (
            patch("sandboxctl.doctor.get_credential", return_value=None),
            patch("sandboxctl.doctor.list_profiles", return_value=[]),
        ):
            results = check_host_credentials(cfg)
        assert len(results) == len(ALL_CHECKS)
        names = {r.name for r in results}
        expected_names = {chk.check_name for chk in ALL_CHECKS}
        assert names == expected_names

    def test_fix_sandbox_unhealthy_aborts(self) -> None:
        """When diagnose returns unhealthy, fix returns pre-flight failure."""
        cfg = _make_config()
        health_report = MagicMock(
            healthy=False,
            recovery_action="container_missing_needs_recreate",
            details=["Container: missing"],
        )
        with patch("sandboxctl.doctor.diagnose", return_value=health_report):
            results = fix_sandbox_credentials("mybox", cfg)
        assert len(results) == 1
        assert results[0].success is False
        assert "pre-flight" in results[0].name

    def test_fix_sandbox_healthy_runs_all(self) -> None:
        """When sandbox is healthy, all checks run their fix method."""
        cfg = _make_config()
        health_report = MagicMock(healthy=True)
        with (
            patch("sandboxctl.doctor.diagnose", return_value=health_report),
            patch("sandboxctl.doctor.get_credential", return_value=None),
            patch("sandboxctl.doctor.osh.sandbox_exec_pipe"),
            patch("sandboxctl.doctor.osh.sandbox_upload"),
            patch("sandboxctl.doctor.list_profiles", return_value=[]),
        ):
            results = fix_sandbox_credentials("mybox", cfg)
        assert len(results) == len(ALL_CHECKS)

    def test_fix_sandbox_best_effort(self) -> None:
        """One fix succeeds, another raises — both are returned."""
        cfg = _make_config()
        health_report = MagicMock(healthy=True)

        # Use only two checks to keep it simple
        ok_check = MagicMock()
        ok_check.check_name = "ok-check"
        ok_check.fix.return_value = FixResult(success=True, name="ok-check", details="done")

        fail_check = MagicMock()
        fail_check.check_name = "fail-check"
        fail_check.fix.side_effect = RuntimeError("injection error")

        with patch("sandboxctl.doctor.diagnose", return_value=health_report):
            results = fix_sandbox_credentials("mybox", cfg, checks=[ok_check, fail_check])

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert "injection error" in results[1].details


# =========================================================================
# TestDoctorCLI
# =========================================================================


class TestDoctorCLI:
    def _mock_host_checks(self) -> list[CheckResult]:
        """Return a mix of pass/fail host checks."""
        return [
            CheckResult(passed=True, name="GitHub PAT", details="Authenticated as user"),
            CheckResult(passed=False, name="GitLab PAT", details="No token", fix_hint="Run setup"),
            CheckResult(passed=True, name="gcloud ADC", details="Valid"),
            CheckResult(passed=True, name="GWS credentials", details="Valid"),
            CheckResult(passed=True, name="SSH key", details="Present"),
            CheckResult(passed=True, name="CA bundle", details="System defaults"),
        ]

    def test_doctor_help(self) -> None:
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "--fix" in result.output

    def test_doctor_shows_host_checks(self) -> None:
        health_report = MagicMock(
            healthy=True,
            details=["Gateway: running", "Container: running"],
            recovery_action="none",
        )
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch("sandboxctl.doctor.check_host_credentials", return_value=self._mock_host_checks()),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
            patch("sandboxctl.health.diagnose", return_value=health_report),
        ):
            result = runner.invoke(app, ["doctor", "mybox"])
        assert result.exit_code == 0
        assert "Host Credentials" in result.output
        assert "GitHub PAT" in result.output
        assert "GitLab PAT" in result.output

    def test_doctor_fix_flag(self) -> None:
        health_report = MagicMock(
            healthy=True,
            details=["Gateway: running", "Container: running"],
            recovery_action="none",
        )
        fix_results = [
            FixResult(success=True, name="GitHub PAT", details="Injected"),
            FixResult(success=False, name="GitLab PAT", details="No token"),
        ]
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch("sandboxctl.doctor.check_host_credentials", return_value=self._mock_host_checks()),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
            patch("sandboxctl.health.diagnose", return_value=health_report),
            patch("sandboxctl.doctor.fix_sandbox_credentials", return_value=fix_results),
        ):
            result = runner.invoke(app, ["doctor", "mybox", "--fix"])
        assert result.exit_code == 0
        assert "Fix: Credential Injection" in result.output
        assert "Injected" in result.output

    def test_doctor_no_sandbox_name(self) -> None:
        """Running doctor without a sandbox name lists sandboxes."""
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch("sandboxctl.doctor.check_host_credentials", return_value=self._mock_host_checks()),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
            patch("sandboxctl.openshell.sandbox_list", return_value=[]),
        ):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "No running sandboxes" in result.output

    def test_doctor_profile_readiness(self) -> None:
        readiness = {"dev": [], "prod": ["GitHub PAT", "SSH key"]}
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch("sandboxctl.doctor.check_host_credentials", return_value=self._mock_host_checks()),
            patch("sandboxctl.doctor.check_profile_readiness", return_value=readiness),
            patch("sandboxctl.openshell.sandbox_list", return_value=[]),
        ):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Profile Readiness" in result.output
        assert "dev" in result.output
        assert "ready" in result.output
        assert "prod" in result.output
        assert "GitHub PAT" in result.output
