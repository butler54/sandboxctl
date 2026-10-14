"""Tests for running policy drift detection."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

from sandboxctl.config import SandboxctlConfig
from sandboxctl.doctor import check_policy_drift, fix_policy_drift


def _config_with_policy(tmp_path: Path) -> SandboxctlConfig:
    profiles = tmp_path / "profiles" / "dev"
    profiles.mkdir(parents=True)
    (tmp_path / "profiles" / "dev.toml").write_text("[sandbox]\n")
    (profiles / "policy.yaml").write_text("network_policies:\n  example: {binaries: [/usr/bin/curl]}\n")
    return SandboxctlConfig(config_dir=tmp_path, profiles_dir=tmp_path / "profiles")


def test_policy_drift_passes_when_active_network_policy_matches(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    active = {"policy": {"network_policies": {"example": {"binaries": [{"path": "/usr/bin/curl"}]}}}}
    with patch("sandboxctl.doctor.osh.policy_get_base", return_value=json.dumps(active)):
        result = check_policy_drift("dev", config)
    assert result.passed


def test_policy_drift_reports_stale_active_policy(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    active = {"policy": {"network_policies": {}}}
    with patch("sandboxctl.doctor.osh.policy_get_base", return_value=json.dumps(active)):
        result = check_policy_drift("dev", config)
    assert not result.passed
    assert "differs" in result.details


def test_policy_drift_flags_filesystem_changes_for_recreation(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    policy_path = tmp_path / "profiles" / "dev" / "policy.yaml"
    policy_path.write_text("network_policies: {}\nfilesystem_policy: {read_only: [/usr]}\n")
    active = {"policy": {"network_policies": {}, "filesystem_policy": {"read_only": ["/bin"]}}}
    with patch("sandboxctl.doctor.osh.policy_get_base", return_value=json.dumps(active)):
        result = check_policy_drift("dev", config)
    assert not result.passed
    assert "recreation required" in result.details


def test_fix_policy_drift_reloads_network_only_changes(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    drifted = {"policy": {"network_policies": {}}}
    # fix_policy_drift verifies the reload by re-reading the active policy, so
    # the second policy_get_base call observes the reloaded (current) policy.
    current = {"policy": {"network_policies": {"example": {"binaries": [{"path": "/usr/bin/curl"}]}}}}
    with (
        patch(
            "sandboxctl.doctor.osh.policy_get_base",
            side_effect=[json.dumps(drifted), json.dumps(current)],
        ),
        patch("sandboxctl.doctor.osh.policy_set") as policy_set,
    ):
        result = fix_policy_drift("dev", config)
    assert result.success
    assert "reloaded" in result.details
    policy_set.assert_called_once()


def test_fix_policy_drift_fails_when_reload_verification_mismatches(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    active = {"policy": {"network_policies": {}}}
    with (
        patch("sandboxctl.doctor.osh.policy_get_base", return_value=json.dumps(active)),
        patch("sandboxctl.doctor.osh.policy_set"),
    ):
        result = fix_policy_drift("dev", config)
    assert not result.success
    assert result.details == "policy reload verification failed"


def test_fix_policy_drift_does_not_reload_filesystem_changes(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    policy_path = tmp_path / "profiles" / "dev" / "policy.yaml"
    policy_path.write_text("network_policies: {}\nfilesystem_policy: {read_only: [/usr]}\n")
    active = {"policy": {"network_policies": {}, "filesystem_policy": {"read_only": ["/bin"]}}}
    with (
        patch("sandboxctl.doctor.osh.policy_get_base", return_value=json.dumps(active)),
        patch("sandboxctl.doctor.osh.policy_set") as policy_set,
    ):
        result = fix_policy_drift("dev", config)
    assert not result.success
    assert "recreation required" in result.details
    policy_set.assert_not_called()


def test_fix_policy_drift_reports_policy_set_failure(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    active = {"policy": {"network_policies": {}}}
    with (
        patch("sandboxctl.doctor.osh.policy_get_base", return_value=json.dumps(active)),
        patch("sandboxctl.doctor.osh.policy_set", side_effect=subprocess.CalledProcessError(1, "openshell")),
    ):
        result = fix_policy_drift("dev", config)
    assert not result.success
    assert result.details == "policy reload failed"


def test_fix_policy_drift_renders_openshell_binary_objects(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    policy_path = tmp_path / "profiles" / "dev" / "policy.yaml"
    policy_path.write_text("network_policies:\n  opencode:\n    binaries:\n      - { path: /usr/local/bin/opencode }\n")
    active = {"policy": {"network_policies": {}}}

    captured: dict[str, str] = {}

    def capture_policy(_name: str, path: Path) -> None:
        captured["content"] = path.read_text()

    def get_base(_name: str) -> str:
        # After policy_set captures the rendered YAML, the verification read
        # observes the sandbox running exactly that policy.
        if "content" in captured:
            return json.dumps({"policy": yaml.safe_load(captured["content"])})
        return json.dumps(active)

    with (
        patch("sandboxctl.doctor.osh.policy_get_base", side_effect=get_base),
        patch("sandboxctl.doctor.osh.policy_set", side_effect=capture_policy),
    ):
        result = fix_policy_drift("dev", config)

    assert result.success
    assert "- path: /usr/lib/node_modules/opencode-ai/**" in captured["content"]
    assert "- path: /usr/lib/node_modules/@opencode/**" in captured["content"]
