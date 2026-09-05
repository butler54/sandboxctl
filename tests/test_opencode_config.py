"""Tests for sandboxctl-controlled OpenCode runtime configuration."""

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from sandboxctl.config import OpencodeConfig, SandboxctlConfig
from sandboxctl.create import _inject_opencode_auth_content, _opencode_runtime_config


def test_runtime_config_is_empty_by_default(tmp_path: Path) -> None:
    assert _opencode_runtime_config(SandboxctlConfig(config_dir=tmp_path)) == {}


def test_runtime_config_limits_providers_and_models(tmp_path: Path) -> None:
    config = SandboxctlConfig(
        config_dir=tmp_path,
        opencode=OpencodeConfig(
            enabled_providers=["vertex", "openai-work"],
            disabled_providers=["github-copilot"],
            model="vertex/claude-sonnet",
            build_model="openai-work/gpt-5.6",
            plan_model="vertex/claude-opus",
        ),
    )

    assert _opencode_runtime_config(config) == {
        "enabled_providers": ["vertex", "openai-work"],
        "disabled_providers": ["github-copilot"],
        "model": "vertex/claude-sonnet",
        "agent": {
            "build": {"model": "openai-work/gpt-5.6"},
            "plan": {"model": "vertex/claude-opus"},
        },
    }


def test_runtime_config_ignores_partial_mock_attributes() -> None:
    """Existing callers may provide a partial config mock while testing setup."""
    config = MagicMock()
    config.opencode.openai_accounts = []

    assert _opencode_runtime_config(config) == {}


def test_go_auth_uses_opencode_runtime_auth_override() -> None:
    with patch("sandboxctl.create.osh.sandbox_exec_pipe") as sandbox_exec:
        _inject_opencode_auth_content("test", {"opencode-go": {"type": "api", "key": "secret"}})

    script = sandbox_exec.call_args.args[1]
    encoded = script.split("echo ")[1].split(" |", 1)[0]
    assert json.loads(base64.b64decode(encoded)) == {"opencode-go": {"type": "api", "key": "secret"}}
    assert "OPENCODE_AUTH_CONTENT=$(echo" in script
