"""Tests for running policy drift detection."""

import json
from pathlib import Path
from unittest.mock import patch

from sandboxctl.config import SandboxctlConfig
from sandboxctl.doctor import check_policy_drift


def _config_with_policy(tmp_path: Path) -> SandboxctlConfig:
    profiles = tmp_path / "profiles" / "dev"
    profiles.mkdir(parents=True)
    (tmp_path / "profiles" / "dev.toml").write_text("[sandbox]\n")
    (profiles / "policy.yaml").write_text("network_policies:\n  example: {binaries: [/usr/bin/curl]}\n")
    return SandboxctlConfig(config_dir=tmp_path, profiles_dir=tmp_path / "profiles")


def test_policy_drift_passes_when_active_network_policy_matches(tmp_path: Path) -> None:
    config = _config_with_policy(tmp_path)
    active = {"policy": {"network_policies": {"example": {"binaries": ["/usr/bin/curl"]}}}}
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
