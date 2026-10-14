"""Tests for generic custom OpenAI-compatible providers (#178, #205)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from sandboxctl.config import (
    MATILDA_PROVIDER,
    CustomProviderConfig,
    OpencodeConfig,
    SandboxctlConfig,
    load_config,
    resolved_custom_providers,
)
from sandboxctl.create import _opencode_runtime_config, post_launch_setup, setup_providers
from sandboxctl.doctor import CustomProvidersCheck
from sandboxctl.models import Profile
from sandboxctl.provider_profiles import custom_provider_profile

MY_LLM = CustomProviderConfig(
    base_url="https://host.example.com/api/v1",
    display_name="My LLM",
    models=["llm-1", "llm-2"],
)


# ---------------------------------------------------------------------------
# Config parsing and validation
# ---------------------------------------------------------------------------


class TestCustomProviderConfig:
    def test_custom_provider_parses(self) -> None:
        oc = OpencodeConfig(
            custom_providers={
                "my-llm": CustomProviderConfig(
                    base_url="https://host.example.com/api/v1",
                    display_name="My LLM",
                    models=["llm-1"],
                    api_key_env="MY_OWN_KEY",
                    keychain_service="custom-service",
                )
            }
        )
        provider = oc.custom_providers["my-llm"]
        assert provider.base_url == "https://host.example.com/api/v1"
        assert provider.api_key_env == "MY_OWN_KEY"
        assert provider.keychain_service == "custom-service"

    def test_custom_provider_from_toml(self, tmp_path: Path) -> None:
        (tmp_path / "config.toml").write_text(
            "[opencode]\n"
            "[opencode.custom_providers.my-llm]\n"
            'base_url = "https://host.example.com/api/v1"\n'
            'display_name = "My LLM"\n'
            'models = ["llm-1", "llm-2"]\n'
            "[opencode.custom_providers.other]\n"
            'base_url = "https://other.example.com:8443/v1"\n'
        )
        cfg = load_config(config_dir=tmp_path)
        assert cfg.opencode.custom_providers["my-llm"].models == ["llm-1", "llm-2"]
        assert cfg.opencode.custom_providers["other"].base_url == "https://other.example.com:8443/v1"

    def test_http_base_url_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be an HTTPS URL"):
            OpencodeConfig(custom_providers={"my-llm": CustomProviderConfig(base_url="http://host.example.com/v1")})

    def test_url_without_host_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be an HTTPS URL"):
            OpencodeConfig(custom_providers={"my-llm": CustomProviderConfig(base_url="https://")})

    def test_invalid_provider_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid custom provider id"):
            OpencodeConfig(custom_providers={"My-LLM": CustomProviderConfig(base_url="https://host.example.com/v1")})
        with pytest.raises(ValueError, match="Invalid custom provider id"):
            OpencodeConfig(custom_providers={"a": CustomProviderConfig(base_url="https://host.example.com/v1")})
        with pytest.raises(ValueError, match="Invalid custom provider id"):
            OpencodeConfig(custom_providers={"a" * 40: CustomProviderConfig(base_url="https://host.example.com/v1")})

    def test_bad_api_key_env_rejected(self) -> None:
        with pytest.raises(ValueError, match="api_key_env"):
            OpencodeConfig(
                custom_providers={
                    "my-llm": CustomProviderConfig(base_url="https://host.example.com/v1", api_key_env="lowercase")
                }
            )

    def test_bad_keychain_service_rejected(self) -> None:
        with pytest.raises(ValueError, match="keychain_service"):
            OpencodeConfig(
                custom_providers={
                    "my-llm": CustomProviderConfig(
                        base_url="https://host.example.com/v1", keychain_service="svc; rm -rf"
                    )
                }
            )

    def test_invalid_model_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid model ID"):
            OpencodeConfig(
                custom_providers={
                    "my-llm": CustomProviderConfig(base_url="https://host.example.com/v1", models=["Bad Model"])
                }
            )

    def test_namespaced_model_ids_accepted(self) -> None:
        """Namespaced upstream IDs (e.g. EnMaaS rits/zai-org/glm-5-3) are valid."""
        oc = OpencodeConfig(
            custom_providers={
                "enmaas": CustomProviderConfig(
                    base_url="https://api.enmaas.devshift.net/v1", models=["rits/zai-org/glm-5-3"]
                )
            }
        )
        assert oc.custom_providers["enmaas"].models == ["rits/zai-org/glm-5-3"]

    def test_duplicate_model_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not contain duplicate"):
            OpencodeConfig(
                custom_providers={
                    "my-llm": CustomProviderConfig(base_url="https://host.example.com/v1", models=["m", "m"])
                }
            )

    def test_model_dump_round_trip(self) -> None:
        oc = OpencodeConfig(
            matilda=True,
            custom_providers={"my-llm": MY_LLM},
        )
        data = json.loads(oc.model_dump_json())
        restored = OpencodeConfig(**data)
        assert restored.custom_providers["my-llm"].base_url == "https://host.example.com/api/v1"
        assert restored.custom_providers["my-llm"].models == ["llm-1", "llm-2"]
        assert restored.matilda is True


# ---------------------------------------------------------------------------
# Resolution (including the matilda alias)
# ---------------------------------------------------------------------------


class TestResolvedCustomProviders:
    def test_defaults_materialized(self) -> None:
        oc = OpencodeConfig(custom_providers={"my-llm": CustomProviderConfig(base_url="https://host.example.com/v1")})
        provider = resolved_custom_providers(oc)["my-llm"]
        assert provider.display_name == "my-llm"
        assert provider.api_key_env == "MY_LLM_API_KEY"
        assert provider.keychain_service == "sandboxctl-my-llm-api-key"

    def test_matilda_flag_materializes_builtin(self) -> None:
        resolved = resolved_custom_providers(OpencodeConfig(matilda=True))
        matilda = resolved["matilda"]
        assert matilda == MATILDA_PROVIDER
        assert matilda.display_name == "Matilda"
        assert matilda.base_url == "https://matilda.maincode.com/api/v1/code"
        assert matilda.models == ("matilda-code-1.0",)
        assert matilda.api_key_env == "MATILDA_API_KEY"
        assert matilda.keychain_service == "sandboxctl-matilda-api-key"

    def test_explicit_matilda_declaration_overrides_alias(self) -> None:
        oc = OpencodeConfig(
            matilda=True,
            custom_providers={
                "matilda": CustomProviderConfig(
                    base_url="https://matilda.example.com/api/v1",
                    models=["my-matilda"],
                    api_key_env="MY_MATILDA_KEY",
                )
            },
        )
        resolved = resolved_custom_providers(oc)
        assert len(resolved) == 1
        matilda = resolved["matilda"]
        assert matilda.base_url == "https://matilda.example.com/api/v1"
        assert matilda.models == ("my-matilda",)
        assert matilda.api_key_env == "MY_MATILDA_KEY"
        assert matilda.display_name == "matilda"

    def test_declared_matilda_works_without_flag(self) -> None:
        oc = OpencodeConfig(
            matilda=False,
            custom_providers={"matilda": CustomProviderConfig(base_url="https://matilda.example.com/v1")},
        )
        assert resolved_custom_providers(oc)["matilda"].base_url == "https://matilda.example.com/v1"

    def test_no_providers(self) -> None:
        assert resolved_custom_providers(OpencodeConfig()) == {}

    def test_partial_mock_attributes_tolerated(self) -> None:
        """MagicMock-based configs (existing tests) resolve to no custom providers."""
        assert resolved_custom_providers(MagicMock()) == {}


# ---------------------------------------------------------------------------
# Provider profile builder
# ---------------------------------------------------------------------------


class TestCustomProviderProfile:
    def test_profile_schema(self) -> None:
        profile = yaml.safe_load(
            custom_provider_profile("my-llm", "My LLM", "https://host.example.com/api/v1", "MY_LLM_API_KEY")
        )
        assert profile["id"] == "my-llm"
        assert profile["display_name"] == "My LLM"
        assert profile["category"] == "inference"
        assert profile["inference_capable"] is True
        assert profile["credentials"][0]["env_vars"] == ["MY_LLM_API_KEY"]
        assert profile["credentials"][0]["auth_style"] == "bearer"
        assert profile["discovery"]["credentials"] == ["api_key"]
        # The URL path never lands in the endpoint — hostname parse only.
        assert profile["endpoints"] == [
            {
                "host": "host.example.com",
                "port": 443,
                "protocol": "rest",
                "access": "read-write",
                "enforcement": "enforce",
            }
        ]
        assert "/usr/local/bin/opencode" in profile["binaries"]

    def test_profile_explicit_port(self) -> None:
        profile = yaml.safe_load(custom_provider_profile("my-llm", "My LLM", "https://host.example.com:8443/v1", "K"))
        assert profile["endpoints"][0]["port"] == 8443

    def test_profile_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            custom_provider_profile("my-llm", "My LLM", "http://host.example.com/v1", "K")


# ---------------------------------------------------------------------------
# setup_providers registration
# ---------------------------------------------------------------------------


def _config_with_custom_providers(tmp_path: Path) -> MagicMock:
    config = MagicMock(
        vertex_project_id="",
        keychain_github="sandboxctl-github-token",
        config_dir=tmp_path,
    )
    config.opencode = OpencodeConfig(custom_providers={"my-llm": MY_LLM})
    return config


class TestSetupProviders:
    def test_custom_provider_imported_before_create(self, tmp_path: Path) -> None:
        config = _config_with_custom_providers(tmp_path)
        order: list[tuple[str, str]] = []

        def fake_import(path: Path, profile_id: str) -> None:
            order.append(("import", profile_id))

        def fake_create(name: str, profile_type: str, *_args: object, **_kwargs: object) -> None:
            order.append(("create", name))

        def credential_for(service: str, account: str) -> str | None:
            return "sk-custom" if service == "sandboxctl-my-llm-api-key" else None

        with (
            patch("sandboxctl.create.get_credential", side_effect=credential_for),
            patch("sandboxctl.create.osh.provider_profile_import", side_effect=fake_import),
            patch("sandboxctl.create.osh.provider_create", side_effect=fake_create) as mock_create,
        ):
            providers = setup_providers(config)

        assert "my-llm" in providers
        # OpenShell 0.1 requires the profile to exist before provider creation (#181).
        assert order.index(("import", "my-llm")) < order.index(("create", "my-llm"))
        mock_create.assert_any_call("my-llm", "my-llm", "MY_LLM_API_KEY=sk-custom")

        yaml_path = tmp_path / "providers" / "my-llm.yaml"
        assert yaml_path.exists()
        profile = yaml.safe_load(yaml_path.read_text())
        assert profile["id"] == "my-llm"
        assert profile["endpoints"][0]["host"] == "host.example.com"

    def test_missing_credential_fails_closed(self, tmp_path: Path) -> None:
        config = _config_with_custom_providers(tmp_path)
        with (
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.osh.provider_profile_import"),
            patch("sandboxctl.create.osh.provider_create") as mock_create,
            pytest.raises(RuntimeError, match="credential sandboxctl-my-llm-api-key was not found"),
        ):
            setup_providers(config)
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# post_launch_setup
# ---------------------------------------------------------------------------


def _post_launch_config(tmp_path: Path, opencode: OpencodeConfig) -> MagicMock:
    config = MagicMock(
        vertex_project_id="",
        vertex_region="global",
        providers=MagicMock(vertex_region="global"),
        ca_bundle=None,
        ca_paths=[],
        keychain_gitlab="sandboxctl-gitlab-token",
    )
    config.opencode = opencode
    return config


class TestPostLaunchSetup:
    def test_custom_provider_env_and_provider_block(self, tmp_path: Path) -> None:
        config = _post_launch_config(tmp_path, OpencodeConfig(custom_providers={"my-llm": MY_LLM}))
        profile = Profile(name="test", mlflow=False)

        def credential_for(service: str, account: str) -> str | None:
            return "sk-custom" if service == "sandboxctl-my-llm-api-key" else None

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", side_effect=credential_for),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        scripts = [call.args[1] for call in mock_pipe.call_args_list]
        # API key is injected as MY_LLM_API_KEY, base64-encoded (never plaintext).
        env_scripts = [s for s in scripts if "MY_LLM_API_KEY=" in s]
        assert len(env_scripts) == 1
        assert "sk-custom" not in env_scripts[0]

        # The provider block lands in the OPENCODE_CONFIG_CONTENT patch.
        cfg_script = next(s for s in scripts if "OPENCODE_CONFIG_CONTENT" in s)
        encoded = next(tok for tok in cfg_script.split() if tok.startswith("eyJ"))
        providers = json.loads(base64.b64decode(encoded))["provider"]
        block = providers["my-llm"]
        assert block["npm"] == "@ai-sdk/openai-compatible"
        assert block["name"] == "My LLM"
        assert block["options"]["baseURL"] == "https://host.example.com/api/v1"
        assert block["options"]["apiKey"] == "{env:MY_LLM_API_KEY}"
        assert list(block["models"]) == ["llm-1", "llm-2"]

    def test_matilda_flag_injects_and_registers(self, tmp_path: Path) -> None:
        config = _post_launch_config(tmp_path, OpencodeConfig(matilda=True))
        profile = Profile(name="test", mlflow=False)

        def credential_for(service: str, account: str) -> str | None:
            return "matilda-secret" if service == "sandboxctl-matilda-api-key" else None

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe") as mock_pipe,
            patch("sandboxctl.create.get_credential", side_effect=credential_for),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
        ):
            post_launch_setup("mybox", profile, config)

        scripts = [call.args[1] for call in mock_pipe.call_args_list]
        matilda_scripts = [s for s in scripts if "MATILDA_API_KEY" in s]
        assert len(matilda_scripts) == 1
        assert "matilda-secret" not in matilda_scripts[0]

        cfg_script = next(s for s in scripts if "OPENCODE_CONFIG_CONTENT" in s)
        encoded = next(tok for tok in cfg_script.split() if tok.startswith("eyJ"))
        block = json.loads(base64.b64decode(encoded))["provider"]["matilda"]
        assert block["options"]["baseURL"] == "https://matilda.maincode.com/api/v1/code"
        assert "matilda-code-1.0" in block["models"]

    def test_missing_credential_fails_closed(self, tmp_path: Path) -> None:
        config = _post_launch_config(tmp_path, OpencodeConfig(custom_providers={"my-llm": MY_LLM}))
        profile = Profile(name="test", mlflow=False)

        with (
            patch("sandboxctl.openshell.sandbox_exec_pipe"),
            patch("sandboxctl.create.get_credential", return_value=None),
            patch("sandboxctl.create.Path.home", return_value=tmp_path / "nohome"),
            patch("sandboxctl.context.restore_claude_context", return_value=False),
            pytest.raises(RuntimeError, match="Custom provider 'my-llm'.*sandboxctl-my-llm-api-key"),
        ):
            post_launch_setup("mybox", profile, config)


# ---------------------------------------------------------------------------
# setup_cmd provider registration mirror
# ---------------------------------------------------------------------------


class TestSetupCmdProviders:
    def test_custom_provider_registered(self, tmp_path: Path) -> None:
        from sandboxctl.setup_cmd import _setup_providers

        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(custom_providers={"my-llm": MY_LLM}),
        )
        order: list[tuple[str, str]] = []

        def fake_import(path: Path, profile_id: str) -> None:
            order.append(("import", profile_id))

        def fake_create(name: str, profile_type: str, *_args: object, **_kwargs: object) -> None:
            order.append(("create", name))

        with (
            patch("sandboxctl.setup_cmd.settings_set"),
            patch("sandboxctl.setup_cmd.provider_profile_import", side_effect=fake_import),
            patch("sandboxctl.setup_cmd.provider_delete") as mock_delete,
            patch("sandboxctl.setup_cmd.provider_create", side_effect=fake_create) as mock_create,
            patch("sandboxctl.setup_cmd.get_credential", return_value="sk-custom"),
            patch("sandboxctl.setup_cmd.typer.echo") as mock_echo,
        ):
            _setup_providers(config, None)

        assert order.index(("import", "my-llm")) < order.index(("create", "my-llm"))
        mock_delete.assert_called_once_with("my-llm")
        mock_create.assert_called_once_with("my-llm", "my-llm", "MY_LLM_API_KEY=sk-custom")
        assert (tmp_path / "providers" / "my-llm.yaml").exists()
        assert any("my-llm: configured" in str(call) for call in mock_echo.call_args_list)

    def test_custom_provider_skipped_without_credential(self, tmp_path: Path) -> None:
        from sandboxctl.setup_cmd import _setup_providers

        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(custom_providers={"my-llm": MY_LLM}),
        )
        with (
            patch("sandboxctl.setup_cmd.settings_set"),
            patch("sandboxctl.setup_cmd.provider_profile_import") as mock_import,
            patch("sandboxctl.setup_cmd.provider_create") as mock_create,
            patch("sandboxctl.setup_cmd.get_credential", return_value=None),
            patch("sandboxctl.setup_cmd.typer.echo") as mock_echo,
        ):
            _setup_providers(config, None)

        mock_import.assert_not_called()
        mock_create.assert_not_called()
        assert any("no keychain entry" in str(call) for call in mock_echo.call_args_list)


# ---------------------------------------------------------------------------
# _opencode_runtime_config model validation
# ---------------------------------------------------------------------------


class TestRuntimeConfigModelValidation:
    def test_listed_model_accepted(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(
                custom_providers={"my-llm": MY_LLM},
                model="my-llm/llm-1",
            ),
        )
        assert _opencode_runtime_config(config)["model"] == "my-llm/llm-1"

    def test_unlisted_model_rejected(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(
                custom_providers={"my-llm": MY_LLM},
                model="my-llm/llm-unknown",
            ),
        )
        with pytest.raises(
            ValueError,
            match="OpenCode model 'my-llm/llm-unknown' is not listed in opencode.custom_providers.my-llm.models",
        ):
            _opencode_runtime_config(config)

    def test_any_model_accepted_without_allowlist(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(
                custom_providers={"open": CustomProviderConfig(base_url="https://host.example.com/v1")},
                model="open/anything-goes",
            ),
        )
        assert _opencode_runtime_config(config)["model"] == "open/anything-goes"


# ---------------------------------------------------------------------------
# doctor check
# ---------------------------------------------------------------------------


class TestCustomProvidersCheck:
    def test_no_providers_passes(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(config_dir=tmp_path)
        result = CustomProvidersCheck().check(config)
        assert result.passed is True
        assert "No custom providers" in result.details

    def test_missing_credential_fails_with_hint(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(custom_providers={"my-llm": MY_LLM}),
        )
        with patch("sandboxctl.doctor.get_credential", return_value=None):
            result = CustomProvidersCheck().check(config)
        assert result.passed is False
        assert "sandboxctl-my-llm-api-key" in result.details
        assert result.fix_hint == "Run: sandboxctl setup"

    def test_present_credentials_pass(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(custom_providers={"my-llm": MY_LLM}),
        )
        with patch("sandboxctl.doctor.get_credential", return_value="sk-x"):
            result = CustomProvidersCheck().check(config)
        assert result.passed is True
        # The credential value is never reported.
        assert "sk-x" not in result.details

    def test_fix_injects_env_var(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(custom_providers={"my-llm": MY_LLM}),
        )
        with (
            patch("sandboxctl.doctor.get_credential", return_value="sk-x"),
            patch("sandboxctl.doctor.osh.sandbox_exec_pipe") as mock_pipe,
        ):
            result = CustomProvidersCheck().fix("mybox", config)
        assert result.success is True
        assert "MY_LLM_API_KEY" in result.details
        script = mock_pipe.call_args.args[1]
        assert "grep -q MY_LLM_API_KEY /sandbox/.bashrc" in script
        assert base64.b64encode(b'export MY_LLM_API_KEY="sk-x"').decode() in script

    def test_fix_missing_credential_fails(self, tmp_path: Path) -> None:
        config = SandboxctlConfig(
            config_dir=tmp_path,
            opencode=OpencodeConfig(custom_providers={"my-llm": MY_LLM}),
        )
        with patch("sandboxctl.doctor.get_credential", return_value=None):
            result = CustomProvidersCheck().fix("mybox", config)
        assert result.success is False
        assert "sandboxctl-my-llm-api-key" in result.details

    def test_required_by_always_true(self) -> None:
        from sandboxctl.models import CredentialConfig

        assert CustomProvidersCheck().required_by(CredentialConfig()) is True
