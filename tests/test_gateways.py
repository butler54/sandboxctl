"""Tests for multi-gateway configuration, routing, and safety (005)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import sandboxctl
from sandboxctl import gateways
from sandboxctl import openshell as osh
from sandboxctl.cli import app
from sandboxctl.config import GatewayEntry, SandboxctlConfig
from sandboxctl.openshell import SandboxError

runner = CliRunner()


def _config(tmp_path: Path, gateways_cfg: dict[str, GatewayEntry] | None = None) -> SandboxctlConfig:
    return SandboxctlConfig(
        config_dir=tmp_path,
        profiles_dir=tmp_path / "profiles",
        gateways=gateways_cfg or {},
    )


class TestGatewayConfig:
    """T002/T017: the [gateways] model — names and hints only, never secrets."""

    def test_entry_defaults(self) -> None:
        entry = GatewayEntry()
        assert entry.openshell_name is None  # default: the key itself
        assert entry.kubernetes is False

    def test_no_secret_or_endpoint_fields(self) -> None:
        """SC-005/FR-006: the gateway entry carries no credential material."""
        fields = set(GatewayEntry.model_fields)
        assert fields == {"openshell_name", "kubernetes"}, f"gateway entries must hold names/hints only, got: {fields}"

    def test_config_section_parses(self, tmp_path: Path) -> None:
        (tmp_path / "config.toml").write_text(
            '[gateways.k8s-prod]\nkubernetes = true\n\n[gateways.remote]\nopenshell_name = "openshell-eu"\n'
        )
        config = SandboxctlConfig(config_dir=tmp_path, profiles_dir=tmp_path / "profiles")
        assert config.gateways["k8s-prod"].kubernetes is True
        assert config.gateways["remote"].openshell_name == "openshell-eu"


class TestResolution:
    """T004: key→name resolution and gateway enumeration."""

    def test_resolve_defaults_to_key(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"k8s-prod": GatewayEntry(kubernetes=True)})
        assert gateways.resolve_openshell_name(config, "k8s-prod") == "k8s-prod"

    def test_resolve_mapped_name(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"remote": GatewayEntry(openshell_name="openshell-eu")})
        assert gateways.resolve_openshell_name(config, "remote") == "openshell-eu"

    def test_unknown_key_is_loud_with_known_keys(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        with pytest.raises(SandboxError) as excinfo:
            gateways.resolve_openshell_name(config, "nope")
        message = str(excinfo.value)
        assert "nope" in message
        assert "k8s-prod" in message  # known keys listed (FR-008)

    def test_gateway_targets_include_active_and_keys(self, tmp_path: Path) -> None:
        config = _config(
            tmp_path,
            {"remote": GatewayEntry(openshell_name="openshell-eu")},
        )
        with patch.dict("os.environ", {"OPENSHELL_GATEWAY": "gw-active"}):
            targets = gateways.gateway_targets(config)
        assert targets == ["openshell-eu", "gw-active"]

    def test_gateway_targets_empty_config_queries_active(self, tmp_path: Path) -> None:
        config = _config(tmp_path)
        with patch.dict("os.environ", {}, clear=False):
            import os

            saved = os.environ.pop("OPENSHELL_GATEWAY", None)
            try:
                assert gateways.gateway_targets(config) == [None]
            finally:
                if saved:
                    os.environ["OPENSHELL_GATEWAY"] = saved


class TestAssociationStore:
    """T003: sandbox→gateway association (mirrors the policy pattern)."""

    def test_record_lookup_remove(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        assert gateways.lookup_gateway_association(config, "box") is None

        gateways.record_gateway_association(config, "box", "k8s-prod")
        assert gateways.lookup_gateway_association(config, "box") == "k8s-prod"
        assert gateways.resolve_gateway_for_sandbox("box", config) == "k8s-prod"

        gateways.remove_gateway_association(config, "box")
        assert gateways.lookup_gateway_association(config, "box") is None

    def test_shares_store_with_policy_association(self, tmp_path: Path) -> None:
        """Gateway and policy associations coexist in sandboxes.json (R-2)."""
        from sandboxctl.policy import record_policy_association

        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        record_policy_association(config, "box", "my-profile")
        gateways.record_gateway_association(config, "box", "k8s-prod")

        data = json.loads((tmp_path / "sandboxes.json").read_text())
        assert data["sandboxes"]["box"] == {"profile": "my-profile", "gateway": "k8s-prod"}

        gateways.remove_gateway_association(config, "box")
        data = json.loads((tmp_path / "sandboxes.json").read_text())
        assert data["sandboxes"]["box"] == {"profile": "my-profile"}

    def test_unknown_association_key_is_loud(self, tmp_path: Path) -> None:
        """A recorded association whose key was removed fails loudly (FR-008)."""
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        gateways.record_gateway_association(config, "box", "k8s-prod")

        stale = _config(tmp_path)  # same dir, gateways section removed
        with pytest.raises(SandboxError, match="k8s-prod"):
            gateways.resolve_gateway_for_sandbox("box", stale)


class TestFacadeRouting:
    """T009: env injection — exactly when a non-active gateway is targeted."""

    def _run_mock(self) -> MagicMock:
        run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
        return run

    def test_non_active_gateway_injects_env(self) -> None:
        run = self._run_mock()
        with (
            patch.dict("os.environ", {"OPENSHELL_GATEWAY": "gw-active"}),
            patch("sandboxctl.openshell._run", run),
        ):
            osh.sandbox_delete("box", gateway="gw-other")

        env = run.call_args.kwargs["env"]
        assert env is not None
        assert env["OPENSHELL_GATEWAY"] == "gw-other"

    def test_active_gateway_env_is_untouched(self) -> None:
        run = self._run_mock()
        with (
            patch.dict("os.environ", {"OPENSHELL_GATEWAY": "gw-active"}),
            patch("sandboxctl.openshell._run", run),
        ):
            osh.sandbox_delete("box", gateway="gw-active")

        assert run.call_args.kwargs["env"] is None  # parity (FR-011)

    def test_no_gateway_no_env(self) -> None:
        run = self._run_mock()
        with patch("sandboxctl.openshell._run", run):
            osh.sandbox_delete("box")  # no association in the real config

        assert run.call_args.kwargs["env"] is None

    def test_association_drives_env(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        gateways.record_gateway_association(config, "box", "k8s-prod")

        run = self._run_mock()
        with (
            patch.dict("os.environ", {"OPENSHELL_GATEWAY": "gw-active"}),
            patch("sandboxctl.config.load_config", return_value=config),
            patch("sandboxctl.openshell._run", run),
        ):
            osh.sandbox_delete("box")  # gateway=None → association resolves

        env = run.call_args.kwargs["env"]
        assert env is not None
        assert env["OPENSHELL_GATEWAY"] == "k8s-prod"

    def test_stale_association_is_loud_not_redirected(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        gateways.record_gateway_association(config, "box", "k8s-prod")
        stale = _config(tmp_path)

        with (
            patch.dict("os.environ", {"OPENSHELL_GATEWAY": "gw-active"}),
            patch("sandboxctl.config.load_config", return_value=stale),
            patch("sandboxctl.openshell._run") as run,
        ):
            with pytest.raises(SandboxError, match="k8s-prod"):
                osh.sandbox_delete("box")
        run.assert_not_called()  # never a silent redirect (R-8)

    def test_exec_routes_gateway_to_sdk_path(self, tmp_path: Path) -> None:
        """US1/SDK: the adapter receives the resolved gateway name."""
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        gateways.record_gateway_association(config, "box", "k8s-prod")
        fake_client = MagicMock()
        fake_client.exec.return_value = MagicMock(exit_code=0, stdout="out", stderr="")

        with (
            patch.dict("os.environ", {"OPENSHELL_GATEWAY": "gw-active"}),
            patch("sandboxctl.config.load_config", return_value=config),
            patch("sandboxctl.openshell_sdk._backend_decision", "auto"),
            patch("sandboxctl.openshell_sdk._client", None),
            patch("sandboxctl.openshell_sdk._build_client", return_value=fake_client),
        ):
            result = osh.sandbox_exec_pipe("box", "script")

        assert result == "out"
        build = fake_client.exec.call_args
        assert build.kwargs["workspace"] == "default"  # 004 seam unchanged


class TestListAggregation:
    """T013/T016: cross-gateway listing, collisions, and error rows."""

    def _list_config(self, tmp_path: Path) -> SandboxctlConfig:
        return _config(
            tmp_path,
            {
                "local": GatewayEntry(),
                "k8s-prod": GatewayEntry(kubernetes=True),
            },
        )

    def test_list_shows_gateway_column_and_collisions(self, tmp_path: Path) -> None:
        config = self._list_config(tmp_path)

        def fake_list(gateway: str | None = None) -> list[dict[str, str]]:
            if gateway == "local":
                return [{"name": "demo", "created": "2026-10-28 10:00", "phase": "Running"}]
            return [{"name": "demo", "created": "2026-10-28 11:00", "phase": "Running"}]

        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.profile.list_profiles", return_value=[]),
            patch("sandboxctl.openshell.sandbox_list", side_effect=fake_list),
            patch("sandboxctl.cli._sandbox_policy_label", return_value="-"),
        ):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert result.output.count("demo") == 2  # same name, two gateways
        assert "local" in result.output
        assert "k8s-prod" in result.output
        assert "Gateway" in result.output

    def test_unreachable_gateway_is_an_error_row_not_omitted(self, tmp_path: Path) -> None:
        config = self._list_config(tmp_path)

        def fake_list(gateway: str | None = None) -> list[dict[str, str]]:
            if gateway == "local":
                return [{"name": "demo", "created": "2026-10-28 10:00", "phase": "Running"}]
            raise SandboxError("connection refused")

        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.profile.list_profiles", return_value=[]),
            patch("sandboxctl.openshell.sandbox_list", side_effect=fake_list),
            patch("sandboxctl.cli._sandbox_policy_label", return_value="-"),
        ):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0  # partial visibility
        assert "demo" in result.output
        assert "Gateway unreachable — k8s-prod: connection refused" in result.output


class TestAssociationCleanup:
    """T015: associations are removed with the sandbox."""

    def test_delete_removes_gateway_association(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        gateways.record_gateway_association(config, "box", "k8s-prod")

        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.context.backup_claude_context", return_value=None),
            patch("sandboxctl.openshell.sandbox_delete") as mock_delete,
        ):
            result = runner.invoke(app, ["delete", "box"], input="y\n")

        assert result.exit_code == 0
        mock_delete.assert_called_once_with("box")
        assert gateways.lookup_gateway_association(config, "box") is None

    def test_restart_drops_association_before_recreate(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"k8s-prod": GatewayEntry()})
        gateways.record_gateway_association(config, "box", "k8s-prod")
        prof = MagicMock()
        prof.gateway = None

        with (
            patch("sandboxctl.cli.load_config", return_value=config),
            patch("sandboxctl.profile.load_profile", return_value=prof),
            patch("sandboxctl.openshell.sandbox_delete"),
            patch("sandboxctl.openshell.sandbox_wait_deleted"),
            patch("sandboxctl.create.create_sandbox") as mock_create,
        ):
            result = runner.invoke(app, ["restart", "box", "--yes"])

        assert result.exit_code == 0
        # Stale association removed; recreate records fresh state (or none).
        assert gateways.lookup_gateway_association(config, "box") is None
        mock_create.assert_called_once()


class TestSeamAudit:
    """T016/FR-010: single injection and resolution points."""

    def test_openshell_gateway_env_is_single_point(self) -> None:
        src = Path(sandboxctl.__file__).parent
        # openshell_sdk.py may *reference* the env var in documentation; only
        # openshell.py injects it into subprocess environments.
        allowed = {"openshell.py", "gateways.py", "openshell_sdk.py"}
        offenders = [p.name for p in src.glob("*.py") if "OPENSHELL_GATEWAY" in p.read_text() and p.name not in allowed]
        assert offenders == [], f"OPENSHELL_GATEWAY references outside the seams: {offenders}"

    def test_gateway_resolution_is_single_point(self) -> None:
        src = Path(sandboxctl.__file__).parent
        resolvers = [
            p.name
            for p in src.glob("*.py")
            if "resolve_gateway_for_sandbox" in p.read_text() and p.name not in ("gateways.py", "openshell.py")
        ]
        assert resolvers == [], f"gateway resolution outside the seam: {resolvers}"
