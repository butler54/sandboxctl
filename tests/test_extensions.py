"""Tests for extension management (classification, validation, installation)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sandboxctl.config import load_config
from sandboxctl.extensions import classify_remote_extensions, is_denylisted, validate_extension_id
from sandboxctl.models import Extensions
from sandboxctl.profile import load_profile


def test_extensions_section_loads_into_profile():
    """[extensions] section in TOML loads into Profile.extensions and classify returns it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        profiles_dir = config_dir / "profiles"
        profiles_dir.mkdir()

        # Create a profile with an [extensions] section
        profile_toml = profiles_dir / "testprof.toml"
        profile_toml.write_text("""
[sandbox]
containerfile = "Containerfile"

[extensions]
list = ["ms-python.python", "github.copilot"]
local_only = ["dracula-theme.theme-dracula"]
""")

        config = load_config(config_dir)
        profile = load_profile("testprof", config)

        # Verify the extensions loaded
        assert profile.extensions.extensions_list == ["ms-python.python", "github.copilot"]
        assert profile.extensions.local_only == ["dracula-theme.theme-dracula"]

        # Verify classify returns the list (tracer behavior)
        remote_set = classify_remote_extensions(profile.extensions)
        assert remote_set == ["ms-python.python", "github.copilot"]


def test_denylisted_theme_excluded_from_remote_set():
    """Denylisted theme IDs are excluded from the remote set with no config."""
    ext = Extensions(extensions_list=["ms-python.python", "dracula-theme.theme-dracula", "github.copilot"])
    remote_set = classify_remote_extensions(ext)
    # dracula-theme.theme-dracula should be denylisted and excluded
    assert "dracula-theme.theme-dracula" not in remote_set
    assert "ms-python.python" in remote_set
    assert "github.copilot" in remote_set


def test_local_only_excluded_from_remote_set():
    """local_only IDs are excluded from the remote set."""
    ext = Extensions(
        extensions_list=["ms-python.python", "evil.icons", "github.copilot"],
        local_only=["evil.icons"],
    )
    remote_set = classify_remote_extensions(ext)
    assert "evil.icons" not in remote_set
    assert "ms-python.python" in remote_set
    assert "github.copilot" in remote_set


def test_validate_extension_id_rejects_leading_dash():
    """validate_extension_id rejects IDs starting with '-' (option injection)."""
    assert validate_extension_id("-evil") is False


def test_validate_extension_id_rejects_shell_metacharacters():
    """validate_extension_id rejects IDs containing shell metacharacters."""
    assert validate_extension_id("a.b; rm -rf /") is False
    assert validate_extension_id("foo|bar") is False
    assert validate_extension_id("foo&bar") is False
    assert validate_extension_id("foo$bar") is False
    assert validate_extension_id("foo`bar") is False
    assert validate_extension_id('foo"bar') is False
    assert validate_extension_id("foo'bar") is False
    assert validate_extension_id("foo<bar") is False
    assert validate_extension_id("foo>bar") is False
    assert validate_extension_id("foo(bar") is False
    assert validate_extension_id("foo)bar") is False


def test_validate_extension_id_accepts_valid_ids():
    """validate_extension_id accepts valid marketplace IDs."""
    assert validate_extension_id("ms-python.python") is True
    assert validate_extension_id("github.copilot") is True
    assert validate_extension_id("dracula-theme.theme-dracula") is True


def test_classify_deduplicates_and_preserves_order():
    """classify_remote_extensions de-duplicates and preserves order."""
    ext = Extensions(
        extensions_list=["ms-python.python", "github.copilot", "ms-python.python", "eamodio.gitlens"],
    )
    remote_set = classify_remote_extensions(ext)
    # Should be de-duplicated and preserve first occurrence order
    assert remote_set == ["ms-python.python", "github.copilot", "eamodio.gitlens"]


def test_is_denylisted_matches_case_insensitively():
    """is_denylisted performs case-insensitive matching."""
    # Assuming the denylist includes "theme" fragment
    assert is_denylisted("dracula-theme.theme-dracula") is True
    assert is_denylisted("DRACULA-THEME.THEME-DRACULA") is True


def test_classify_full_behavior():
    """Full classifier behavior: list - denylist - local_only - invalid."""
    ext = Extensions(
        extensions_list=[
            "ms-python.python",
            "dracula-theme.theme-dracula",  # denylisted
            "evil.icons",  # local_only
            "-badid",  # invalid
            "github.copilot",
        ],
        local_only=["evil.icons"],
    )
    remote_set = classify_remote_extensions(ext)
    # Should only contain ms-python.python and github.copilot
    assert remote_set == ["ms-python.python", "github.copilot"]
