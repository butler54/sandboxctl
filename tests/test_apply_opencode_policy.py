"""Tests for the profile policy migration script."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    script = Path(__file__).parents[1] / "scripts" / "apply_opencode_policy.py"
    spec = importlib.util.spec_from_file_location("apply_opencode_policy", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_apply_policy_adds_required_opencode_rules() -> None:
    script = _load_script()
    policy = {
        "network_policies": {
            "npm": {"endpoints": [{"host": "registry.npmjs.org", "port": 443}]},
            "copilot": {"endpoints": [{"host": "api.githubcopilot.com", "port": 443}]},
        }
    }

    changes = script.apply_policy(policy)

    npm_endpoint = policy["network_policies"]["npm"]["endpoints"][0]
    assert npm_endpoint["allow_encoded_slash"] is True
    assert policy["network_policies"]["matilda"]["endpoints"] == [script.MATILDA_ENDPOINT]
    assert {entry["path"] for entry in policy["network_policies"]["matilda"]["binaries"]} == set(
        script.OPENCODE_BINARIES
    )
    assert {entry["path"] for entry in policy["network_policies"]["copilot"]["binaries"]} == set(
        script.OPENCODE_BINARIES
    )
    assert changes


def test_apply_policy_is_idempotent() -> None:
    script = _load_script()
    policy = {"network_policies": {}}

    script.apply_policy(policy)

    assert script.apply_policy(policy) == []


def test_policy_paths_includes_yamlc(tmp_path: Path) -> None:
    script = _load_script()
    (tmp_path / "nested").mkdir()
    yamlc = tmp_path / "nested" / "policy.yamlc"
    yamlc.touch()

    assert script.policy_paths(tmp_path) == [yamlc]
