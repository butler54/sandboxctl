"""Tests for profile policy fragment rendering."""

from pathlib import Path

import pytest

from sandboxctl.policy import PolicyIncludeError, render_policy


def test_render_policy_includes_fragment(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    shared = profiles / "_shared"
    profile = profiles / "dev"
    shared.mkdir(parents=True)
    profile.mkdir()
    (shared / "opencode.yaml").write_text("binaries:\n  - /usr/local/bin/opencode\n")
    policy = profile / "policy.yaml"
    policy.write_text("network_policies:\n  opencode: !include ../_shared/opencode.yaml\n")

    assert render_policy(policy, profiles) == (
        "network_policies:\n"
        "  opencode:\n"
        "    binaries:\n"
        "    - /usr/local/bin/opencode\n"
        "    - /usr/lib/node_modules/opencode-ai/bin/opencode.exe\n"
    )


def test_render_policy_adds_opencode_kernel_path(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "dev"
    profile.mkdir(parents=True)
    policy = profile / "policy.yaml"
    policy.write_text("network_policies:\n  opencode:\n    binaries:\n      - /usr/local/bin/opencode\n")

    rendered = render_policy(policy, profiles)
    assert rendered.count("/usr/lib/node_modules/opencode-ai/bin/opencode.exe") == 1


def test_render_policy_rejects_include_outside_profiles(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "dev"
    profile.mkdir(parents=True)
    (tmp_path / "secret.yaml").write_text("secret: value\n")
    policy = profile / "policy.yaml"
    policy.write_text("network_policies: !include ../../secret.yaml\n")

    with pytest.raises(PolicyIncludeError, match="outside profiles directory"):
        render_policy(policy, profiles)


def test_render_policy_rejects_recursive_include(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "dev"
    profile.mkdir(parents=True)
    policy = profile / "policy.yaml"
    policy.write_text("network_policies: !include policy.yaml\n")

    with pytest.raises(PolicyIncludeError, match="Recursive policy include"):
        render_policy(policy, profiles)
