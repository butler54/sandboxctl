"""Tests for profile policy fragment rendering."""

from pathlib import Path

import pytest
import yaml

from sandboxctl.policy import PolicyIncludeError, prepare_policy_for_apply, render_policy


def test_render_policy_includes_fragment(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    shared = profiles / "_shared"
    profile = profiles / "dev"
    shared.mkdir(parents=True)
    profile.mkdir()
    (shared / "opencode.yaml").write_text("binaries:\n  - { path: /usr/local/bin/opencode }\n")
    policy = profile / "policy.yaml"
    policy.write_text("network_policies:\n  opencode: !include ../_shared/opencode.yaml\n")

    assert render_policy(policy, profiles) == (
        "network_policies:\n"
        "  opencode:\n"
        "    binaries:\n"
        "    - path: /usr/local/bin/opencode\n"
        "    - path: /usr/lib/node_modules/opencode-ai/bin/opencode.exe\n"
    )


def test_render_policy_adds_opencode_kernel_path(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "dev"
    profile.mkdir(parents=True)
    policy = profile / "policy.yaml"
    policy.write_text("network_policies:\n  opencode:\n    binaries:\n      - { path: /usr/local/bin/opencode }\n")

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


def test_prepare_policy_for_apply_renders_plain_policy(tmp_path: Path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("network_policies: {}\n")
    rendered = prepare_policy_for_apply(policy, tmp_path, tmp_path / "rendered")
    assert rendered == tmp_path / "rendered" / "policy.yaml"
    assert yaml.safe_load(rendered.read_text()) == {"network_policies": {}}


def test_prepare_policy_for_apply_renders_opencode_policy(tmp_path: Path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("network_policies:\n  opencode: {binaries: [{path: /usr/bin/opencode}]}\n")
    target_dir = tmp_path / "rendered"
    target_dir.mkdir()
    rendered = prepare_policy_for_apply(policy, tmp_path, target_dir)
    assert rendered == target_dir / "policy.yaml"
    assert "/usr/lib/node_modules/opencode-ai/bin/opencode.exe" in rendered.read_text()


def test_prepare_policy_for_apply_normalizes_non_opencode_legacy_binary(tmp_path: Path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("network_policies:\n  pypi: {binaries: [/usr/bin/curl]}\n")
    target_dir = tmp_path / "rendered"
    target_dir.mkdir()

    rendered = prepare_policy_for_apply(policy, tmp_path, target_dir)
    assert yaml.safe_load(rendered.read_text())["network_policies"]["pypi"]["binaries"] == [{"path": "/usr/bin/curl"}]


def test_render_policy_handles_openshell_binary_objects(tmp_path: Path) -> None:
    """Regression: OpenShell policies use mappings, not bare binary-path strings."""
    profiles = tmp_path / "profiles"
    profile = profiles / "fw"
    profile.mkdir(parents=True)
    policy = profile / "policy-fw.yaml"
    policy.write_text(
        "network_policies:\n"
        "  nvidia_inference:\n"
        "    binaries:\n"
        "      - { path: /usr/bin/curl }\n"
        "      - { path: /usr/local/bin/opencode }\n"
    )

    rendered = yaml.safe_load(render_policy(policy, profiles))
    assert rendered["network_policies"]["nvidia_inference"]["binaries"] == [
        {"path": "/usr/bin/curl"},
        {"path": "/usr/local/bin/opencode"},
        {"path": "/usr/lib/node_modules/opencode-ai/bin/opencode.exe"},
    ]


def test_render_policy_does_not_duplicate_existing_binary_object(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "fw"
    profile.mkdir(parents=True)
    policy = profile / "policy-fw.yaml"
    policy.write_text(
        "network_policies:\n"
        "  opencode:\n"
        "    binaries:\n"
        "      - { path: /usr/local/bin/opencode }\n"
        "      - { path: /usr/lib/node_modules/opencode-ai/bin/opencode.exe }\n"
    )

    assert render_policy(policy, profiles).count("/usr/lib/node_modules/opencode-ai/bin/opencode.exe") == 1


def test_render_policy_normalizes_legacy_binary_strings(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "legacy"
    profile.mkdir(parents=True)
    policy = profile / "policy.yaml"
    policy.write_text("network_policies:\n  opencode: {binaries: [/usr/bin/opencode]}\n")

    rendered = yaml.safe_load(render_policy(policy, profiles))
    assert rendered["network_policies"]["opencode"]["binaries"] == [
        {"path": "/usr/bin/opencode"},
        {"path": "/usr/lib/node_modules/opencode-ai/bin/opencode.exe"},
    ]


@pytest.mark.parametrize("entry", [None, 42, [], {}, {"path": ""}, {"path": "  "}])
def test_render_policy_rejects_malformed_binary_entries(tmp_path: Path, entry: object) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "invalid"
    profile.mkdir(parents=True)
    policy = profile / "policy.yaml"
    policy.write_text(yaml.safe_dump({"network_policies": {"bad": {"binaries": [entry]}}}))

    with pytest.raises(PolicyIncludeError, match="non-empty path"):
        render_policy(policy, profiles)


@pytest.mark.parametrize("binaries", [None, 42, {}])
def test_render_policy_rejects_non_list_binaries(tmp_path: Path, binaries: object) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "invalid"
    profile.mkdir(parents=True)
    policy = profile / "policy.yaml"
    policy.write_text(yaml.safe_dump({"network_policies": {"bad": {"binaries": binaries}}}))

    with pytest.raises(PolicyIncludeError, match="binaries must be a list"):
        render_policy(policy, profiles)


def test_prepare_policy_for_apply_rejects_quoted_malformed_binary_key(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profile = profiles / "invalid"
    profile.mkdir(parents=True)
    policy = profile / "policy.yaml"
    policy.write_text('network_policies:\n  bad:\n    "binaries": [null]\n')

    with pytest.raises(PolicyIncludeError, match="non-empty path"):
        prepare_policy_for_apply(policy, profiles, tmp_path / "rendered")


def test_prepare_policy_for_apply_rejects_path_outside_profiles(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    policy = tmp_path / "outside.yaml"
    policy.write_text("network_policies: {}\n")

    with pytest.raises(PolicyIncludeError, match="outside profiles directory"):
        prepare_policy_for_apply(policy, profiles, tmp_path)
