"""Tests for the policy command group and sandbox/profile association store."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from sandboxctl.cli import app
from sandboxctl.config import SandboxctlConfig
from sandboxctl.open_cmd import open_sandbox
from sandboxctl.policy import (
    fix_policy_drift,
    lookup_policy_association,
    policy_drift_state,
    record_policy_association,
    remove_policy_association,
    resolve_policy_profile,
    sandbox_policy_drift_state,
)

runner = CliRunner()

_DRIFTED = json.dumps({"policy": {"network_policies": {}}})
_CURRENT = json.dumps({"policy": {"network_policies": {"example": {"binaries": [{"path": "/usr/bin/curl"}]}}}})


def _config_with_policy(tmp_path: Path) -> SandboxctlConfig:
    profiles = tmp_path / "profiles" / "dev"
    profiles.mkdir(parents=True)
    (tmp_path / "profiles" / "dev.toml").write_text("[sandbox]\n")
    (profiles / "policy.yaml").write_text("network_policies:\n  example: {binaries: [/usr/bin/curl]}\n")
    return SandboxctlConfig(config_dir=tmp_path, profiles_dir=tmp_path / "profiles")


class TestAssociationStore:
    def test_round_trip_and_remove(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        record_policy_association(config, "box", "dev")
        assert lookup_policy_association(config, "box") == "dev"
        remove_policy_association(config, "box")
        assert lookup_policy_association(config, "box") is None

    def test_missing_file_reads_empty(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        assert lookup_policy_association(config, "box") is None

    def test_corrupt_file_reads_empty_and_recovers(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        (tmp_path / "sandboxes.json").write_text("not json {")
        assert lookup_policy_association(config, "box") is None
        record_policy_association(config, "box", "dev")
        assert lookup_policy_association(config, "box") == "dev"

    def test_remove_unknown_name_is_a_noop(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        remove_policy_association(config, "ghost")
        assert not (tmp_path / "sandboxes.json").exists()


class TestResolvePolicyProfile:
    def test_association_wins(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        (tmp_path / "profiles" / "prod.toml").write_text("[sandbox]\n")
        record_policy_association(config, "prod", "dev")
        assert resolve_policy_profile("prod", config) == "dev"

    def test_name_as_profile_fallback(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        assert resolve_policy_profile("dev", config) == "dev"

    def test_none_otherwise(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        assert resolve_policy_profile("nope", config) is None


class TestPolicyDriftState:
    def test_current(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with patch("sandboxctl.policy.osh.policy_get_base", return_value=_CURRENT):
            state = policy_drift_state("dev", "dev", config)
        assert state.status == "current"
        assert not state.hot_reloadable

    def test_network_drift(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED):
            state = policy_drift_state("dev", "dev", config)
        assert state.status == "network-drift"
        assert state.hot_reloadable
        assert state.rendered is not None
        assert "differs" in state.details

    def test_filesystem_drift(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        (tmp_path / "profiles" / "dev" / "policy.yaml").write_text(
            "network_policies: {}\nfilesystem_policy: {read_only: [/usr]}\n"
        )
        active = json.dumps({"policy": {"network_policies": {}, "filesystem_policy": {"read_only": ["/bin"]}}})
        with patch("sandboxctl.policy.osh.policy_get_base", return_value=active):
            state = policy_drift_state("dev", "dev", config)
        assert state.status == "filesystem-drift"
        assert not state.hot_reloadable

    def test_unknown_when_active_policy_unreadable(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with patch("sandboxctl.policy.osh.policy_get_base", return_value="not json {"):
            state = policy_drift_state("dev", "dev", config)
        assert state.status == "unknown"
        assert "could not retrieve the active base policy" in state.details

    def test_unknown_when_policy_file_missing(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        (tmp_path / "profiles" / "dev" / "policy.yaml").unlink()
        state = policy_drift_state("dev", "dev", config)
        assert state.status == "unknown"
        assert "profile policy not found" in state.details

    def test_unknown_when_profile_unloadable(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        state = policy_drift_state("dev", "ghost", config)
        assert state.status == "unknown"
        assert "could not load profile" in state.details

    def test_no_profile(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        state = sandbox_policy_drift_state("nope", config)
        assert state.status == "no-profile"


class TestFixPolicyDrift:
    def test_reload_and_verify_success(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.policy.osh.policy_get_base", side_effect=[_DRIFTED, _CURRENT]),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = fix_policy_drift("dev", config)
        assert result.success
        assert "reloaded" in result.details
        policy_set.assert_called_once()

    def test_verification_mismatch_fails(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = fix_policy_drift("dev", config)
        assert not result.success
        assert result.details == "policy reload verification failed"
        policy_set.assert_called_once()

    def test_filesystem_drift_refuses_reload(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        (tmp_path / "profiles" / "dev" / "policy.yaml").write_text(
            "network_policies: {}\nfilesystem_policy: {read_only: [/usr]}\n"
        )
        active = json.dumps({"policy": {"network_policies": {}, "filesystem_policy": {"read_only": ["/bin"]}}})
        with (
            patch("sandboxctl.policy.osh.policy_get_base", return_value=active),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = fix_policy_drift("dev", config)
        assert not result.success
        assert "recreation required" in result.details
        policy_set.assert_not_called()


class TestPolicyShowCommand:
    def test_show_network_drift(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED),
        ):
            result = runner.invoke(app, ["policy", "show", "dev"])
        assert result.exit_code == 0
        assert "network-drift" in result.output
        assert "added: example" in result.output

    def test_show_current(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_CURRENT),
        ):
            result = runner.invoke(app, ["policy", "show", "dev"])
        assert result.exit_code == 0
        assert "current" in result.output

    def test_show_no_profile_is_informational(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with patch("sandboxctl.cli.load_config", return_value=config):
            result = runner.invoke(app, ["policy", "show", "nope"])
        assert result.exit_code == 0
        assert "no associated profile" in result.output


class TestPolicySyncCommand:
    def test_sync_dry_run_does_not_mutate(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = runner.invoke(app, ["policy", "sync", "dev", "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output
        assert "added: example" in result.output
        policy_set.assert_not_called()

    def test_sync_yes_reloads_and_echoes_result(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", side_effect=[_DRIFTED, _DRIFTED, _CURRENT]),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = runner.invoke(app, ["policy", "sync", "dev", "--yes"])
        assert result.exit_code == 0
        assert "reloaded" in result.output
        policy_set.assert_called_once()

    def test_sync_confirm_abort_does_not_mutate(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = runner.invoke(app, ["policy", "sync", "dev"], input="n\n")
        assert result.exit_code == 1
        policy_set.assert_not_called()

    def test_sync_current_is_a_noop(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_CURRENT),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = runner.invoke(app, ["policy", "sync", "dev", "--yes"])
        assert result.exit_code == 0
        assert "nothing to do" in result.output
        policy_set.assert_not_called()

    def test_sync_filesystem_drift_refuses(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        (tmp_path / "profiles" / "dev" / "policy.yaml").write_text(
            "network_policies: {}\nfilesystem_policy: {read_only: [/usr]}\n"
        )
        active = json.dumps({"policy": {"network_policies": {}, "filesystem_policy": {"read_only": ["/bin"]}}})
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=active),
            patch("sandboxctl.policy.osh.policy_set") as policy_set,
        ):
            result = runner.invoke(app, ["policy", "sync", "dev", "--yes"])
        assert result.exit_code == 1
        assert "restart dev" in result.output
        policy_set.assert_not_called()

    def test_sync_no_profile_errors(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with patch("sandboxctl.cli.load_config", return_value=config):
            result = runner.invoke(app, ["policy", "sync", "nope", "--yes"])
        assert result.exit_code == 1
        assert "no associated profile" in result.output

    def test_sync_with_profile_records_association(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED),
        ):
            result = runner.invoke(app, ["policy", "sync", "custom", "--profile", "dev", "--dry-run"])
        assert result.exit_code == 0
        assert lookup_policy_association(config, "custom") == "dev"


class TestLifecycleIntegration:
    def test_list_shows_policy_column(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        sandboxes = [{"name": "dev", "created": "today", "phase": "Running"}]
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.openshell.sandbox_list", return_value=sandboxes),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED),
        ):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Policy" in result.output
        assert "network-drift" in result.output

    def test_list_survives_gateway_error_for_one_sandbox(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        sandboxes = [{"name": "dev", "created": "today", "phase": "Running"}]
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.openshell.sandbox_list", return_value=sandboxes),
            patch("sandboxctl.policy.osh.policy_get_base", side_effect=RuntimeError("boom")),
        ):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "dev" in result.output
        assert "unknown" in result.output

    def test_delete_removes_association(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        record_policy_association(config, "dev", "dev")
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.openshell.sandbox_delete"),
            patch("sandboxctl.context.backup_claude_context", return_value=None),
        ):
            result = runner.invoke(app, ["delete", "dev"], input="y\n")
        assert result.exit_code == 0
        assert lookup_policy_association(config, "dev") is None

    def test_record_failure_does_not_fail_delete(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.openshell.sandbox_delete"),
            patch("sandboxctl.context.backup_claude_context", return_value=None),
            patch("sandboxctl.policy.remove_policy_association", side_effect=OSError("disk full")),
        ):
            result = runner.invoke(app, ["delete", "dev"], input="y\n")
        assert result.exit_code == 0

    def test_open_warns_on_network_drift(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config_with_policy(tmp_path)
        report = MagicMock(healthy=True)
        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive"),
            patch("sandboxctl.open_cmd.osh.sandbox_connect"),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_DRIFTED),
        ):
            open_sandbox("dev", config, mode="shell")
        out = capsys.readouterr().out
        assert "WARNING: profile policy differs from this sandbox" in out
        assert "sandboxctl policy sync dev" in out

    def test_open_warns_on_filesystem_drift(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config_with_policy(tmp_path)
        (tmp_path / "profiles" / "dev" / "policy.yaml").write_text(
            "network_policies: {}\nfilesystem_policy: {read_only: [/usr]}\n"
        )
        active = json.dumps({"policy": {"network_policies": {}, "filesystem_policy": {"read_only": ["/bin"]}}})
        report = MagicMock(healthy=True)
        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive"),
            patch("sandboxctl.open_cmd.osh.sandbox_connect"),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=active),
        ):
            open_sandbox("dev", config, mode="shell")
        out = capsys.readouterr().out
        assert "WARNING: profile filesystem policy differs" in out
        assert "sandboxctl restart dev" in out

    def test_open_silent_when_current(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config = _config_with_policy(tmp_path)
        report = MagicMock(healthy=True)
        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive"),
            patch("sandboxctl.open_cmd.osh.sandbox_connect"),
            patch("sandboxctl.policy.osh.policy_get_base", return_value=_CURRENT),
        ):
            open_sandbox("dev", config, mode="shell")
        out = capsys.readouterr().out
        assert "WARNING" not in out

    def test_open_never_fails_on_drift_errors(self, tmp_path: Path) -> None:
        config = _config_with_policy(tmp_path)
        report = MagicMock(healthy=True)
        with (
            patch("sandboxctl.open_cmd.diagnose", return_value=report),
            patch("sandboxctl.open_cmd.osh.ensure_ssh_keepalive"),
            patch("sandboxctl.open_cmd.osh.sandbox_connect") as connect,
            patch("sandboxctl.policy.osh.policy_get_base", side_effect=RuntimeError("boom")),
        ):
            open_sandbox("dev", config, mode="shell")
        connect.assert_called_once_with("dev")
