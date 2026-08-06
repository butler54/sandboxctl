"""Tests for extension management (classification, validation, installation)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sandboxctl.config import load_config
from sandboxctl.extensions import classify_remote_extensions
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
