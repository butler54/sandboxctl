"""Tests for extension management (classification, validation, installation)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from sandboxctl.config import load_config
from sandboxctl.extensions import classify_remote_extensions, install_extensions, is_denylisted, validate_extension_id
from sandboxctl.models import Extensions
from sandboxctl.profile import load_profile


def test_extensions_section_loads_into_profile() -> None:
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


def test_denylisted_theme_excluded_from_remote_set() -> None:
    """Denylisted theme IDs are excluded from the remote set with no config."""
    ext = Extensions(extensions_list=["ms-python.python", "dracula-theme.theme-dracula", "github.copilot"])
    remote_set = classify_remote_extensions(ext)
    # dracula-theme.theme-dracula should be denylisted and excluded
    assert "dracula-theme.theme-dracula" not in remote_set
    assert "ms-python.python" in remote_set
    assert "github.copilot" in remote_set


def test_local_only_excluded_from_remote_set() -> None:
    """local_only IDs are excluded from the remote set."""
    ext = Extensions(
        extensions_list=["ms-python.python", "evil.icons", "github.copilot"],
        local_only=["evil.icons"],
    )
    remote_set = classify_remote_extensions(ext)
    assert "evil.icons" not in remote_set
    assert "ms-python.python" in remote_set
    assert "github.copilot" in remote_set


def test_validate_extension_id_rejects_leading_dash() -> None:
    """validate_extension_id rejects IDs starting with '-' (option injection)."""
    assert validate_extension_id("-evil") is False


def test_validate_extension_id_rejects_shell_metacharacters() -> None:
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


def test_validate_extension_id_accepts_valid_ids() -> None:
    """validate_extension_id accepts valid marketplace IDs."""
    assert validate_extension_id("ms-python.python") is True
    assert validate_extension_id("github.copilot") is True
    assert validate_extension_id("dracula-theme.theme-dracula") is True


def test_classify_deduplicates_and_preserves_order() -> None:
    """classify_remote_extensions de-duplicates and preserves order."""
    ext = Extensions(
        extensions_list=["ms-python.python", "github.copilot", "ms-python.python", "eamodio.gitlens"],
    )
    remote_set = classify_remote_extensions(ext)
    # Should be de-duplicated and preserve first occurrence order
    assert remote_set == ["ms-python.python", "github.copilot", "eamodio.gitlens"]


def test_is_denylisted_matches_case_insensitively() -> None:
    """is_denylisted performs case-insensitive matching."""
    # Assuming the denylist includes "theme" fragment
    assert is_denylisted("dracula-theme.theme-dracula") is True
    assert is_denylisted("DRACULA-THEME.THEME-DRACULA") is True


def test_classify_full_behavior() -> None:
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


# Task 3: Install helper tests


def test_install_extensions_uses_correct_subprocess_args() -> None:
    """install_extensions invokes code CLI with correct list args."""
    with patch("sandboxctl.extensions.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        vscode_bin = Path("/usr/bin/code")

        install_extensions("mybox", ["ms-python.python"], vscode_bin)

        # Verify subprocess.run was called with correct args
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == [
            str(vscode_bin),
            "--remote",
            "ssh-remote+openshell-mybox",
            "--install-extension",
            "ms-python.python",
        ]
        # Verify shell=True is never used
        assert kwargs.get("shell") is not True


def test_install_extensions_never_uses_shell() -> None:
    """install_extensions never passes shell=True to subprocess."""
    with patch("sandboxctl.extensions.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        vscode_bin = Path("/usr/bin/code")

        install_extensions("mybox", ["ms-python.python"], vscode_bin)

        # Verify shell keyword is not True
        _, kwargs = mock_run.call_args
        assert "shell" not in kwargs or kwargs["shell"] is False


def test_install_extensions_captures_failures() -> None:
    """install_extensions captures non-zero returncode and continues."""
    with patch("sandboxctl.extensions.subprocess.run") as mock_run:
        # First call fails, second succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="Extension not found"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        vscode_bin = Path("/usr/bin/code")

        report = install_extensions("mybox", ["bad.extension", "ms-python.python"], vscode_bin)

        # Verify both were attempted
        assert mock_run.call_count == 2
        # Verify failure captured
        assert len(report.failed) == 1
        assert report.failed[0][0] == "bad.extension"
        assert "Extension not found" in report.failed[0][1]
        # Verify success captured
        assert "ms-python.python" in report.installed


def test_install_extensions_skips_invalid_ids() -> None:
    """install_extensions skips invalid IDs and records them."""
    with patch("sandboxctl.extensions.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        vscode_bin = Path("/usr/bin/code")

        report = install_extensions("mybox", ["-badid", "ms-python.python"], vscode_bin)

        # Verify only valid ID was processed
        assert mock_run.call_count == 1
        # Verify invalid ID was skipped
        assert "-badid" in report.skipped_invalid
        assert "ms-python.python" in report.installed


def test_install_extensions_empty_list() -> None:
    """install_extensions with empty list invokes no subprocess."""
    with patch("sandboxctl.extensions.subprocess.run") as mock_run:
        vscode_bin = Path("/usr/bin/code")

        report = install_extensions("mybox", [], vscode_bin)

        # Verify no subprocess calls
        mock_run.assert_not_called()
        # Verify empty report
        assert len(report.installed) == 0
        assert len(report.skipped_invalid) == 0
        assert len(report.failed) == 0
