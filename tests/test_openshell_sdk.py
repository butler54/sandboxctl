"""Tests for the optional openshell SDK adapter and facade dispatch (004).

The suite forces the CLI backend by default (see conftest.py); these tests
opt into the SDK path explicitly by setting SANDBOXCTL_OPENSHELL_BACKEND=auto
and injecting a fake client.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sandboxctl
from sandboxctl import openshell as osh
from sandboxctl import openshell_sdk


class FakeExecResult:
    def __init__(self, exit_code: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class FakeClient:
    """Records calls; raises self.exec_error when set."""

    def __init__(self) -> None:
        self.exec_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self.wait_deleted_calls: list[dict] = []
        self.exec_result = FakeExecResult()
        self.exec_error: Exception | None = None

    def exec(  # noqa: A003
        self,
        name: str,
        command: list[str],
        *,
        workspace: str,
        stdin: bytes | None = None,
        **_: object,
    ) -> object:
        self.exec_calls.append({"name": name, "command": list(command), "workspace": workspace, "stdin": stdin})
        if self.exec_error is not None:
            raise self.exec_error
        return self.exec_result

    def delete(
        self,
        name: str,
        *,
        workspace: str,
        allow_missing: bool = False,
        **_: object,
    ) -> object:
        self.delete_calls.append({"name": name, "workspace": workspace, "allow_missing": allow_missing})
        return MagicMock(outcome=1)

    def wait_deleted(
        self,
        name: str,
        *,
        workspace: str,
        timeout_seconds: float = 60.0,
        **_: object,
    ) -> None:
        self.wait_deleted_calls.append({"name": name, "workspace": workspace, "timeout": timeout_seconds})


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "auto")
    monkeypatch.setattr(openshell_sdk, "_backend_decision", "auto")
    client = FakeClient()
    monkeypatch.setattr(openshell_sdk, "_client", client)
    return client


class TestAdapterOperations:
    """004 US1: SDK-backed exec/delete with structured results (T006)."""

    def test_exec_maps_argv_stdin_and_workspace(self, fake_client: FakeClient) -> None:
        outcome = osh.sandbox_exec_pipe_result("mybox", "echo hi")

        assert len(fake_client.exec_calls) == 1
        call = fake_client.exec_calls[0]
        assert call["name"] == "mybox"
        assert call["command"] == ["bash"]
        assert call["stdin"] == b"echo hi"
        assert call["workspace"] == "default"
        assert outcome.exit_code == fake_client.exec_result.exit_code

    def test_exec_pipe_returns_stripped_stdout(self, fake_client: FakeClient) -> None:
        fake_client.exec_result = FakeExecResult(stdout="  out  \n")
        assert osh.sandbox_exec_pipe("mybox", "script") == "out"

    def test_exec_pipe_result_returns_raw_streams(self, fake_client: FakeClient) -> None:
        fake_client.exec_result = FakeExecResult(exit_code=7, stdout=" out ", stderr="err")
        outcome = osh.sandbox_exec_pipe_result("mybox", "script")
        assert outcome.exit_code == 7
        assert outcome.stdout == " out "
        assert outcome.stderr == "err"

    def test_one_shot_exec_passes_argv(self, fake_client: FakeClient) -> None:
        fake_client.exec_result = FakeExecResult(stdout="cloned")
        result = osh.sandbox_exec("mybox", ["gh", "repo", "clone", "o/r"])
        assert result == "cloned"
        assert fake_client.exec_calls[0]["command"] == ["gh", "repo", "clone", "o/r"]
        assert fake_client.exec_calls[0]["stdin"] is None

    def test_delete_uses_allow_missing_and_workspace(self, fake_client: FakeClient) -> None:
        osh.sandbox_delete("mybox")
        assert fake_client.delete_calls == [{"name": "mybox", "workspace": "default", "allow_missing": True}]

    def test_wait_deleted_passes_workspace_and_timeout(self, fake_client: FakeClient) -> None:
        osh.sandbox_wait_deleted("mybox", timeout_seconds=5.0)
        assert fake_client.wait_deleted_calls == [{"name": "mybox", "workspace": "default", "timeout": 5.0}]


class TestAdapterErrorMapping:
    """004 FR-011/FR-010: SDK errors become loud facade SandboxErrors."""

    def test_sdk_error_maps_to_facade_sandbox_error(self, fake_client: FakeClient) -> None:
        fake_client.exec_error = RuntimeError("boom")
        with pytest.raises(osh.SandboxError) as excinfo:
            osh.sandbox_exec_pipe("mybox", "script")
        assert "exec in sandbox 'mybox' failed: boom" in str(excinfo.value)

    def test_workspace_mismatch_names_the_workspace(self, fake_client: FakeClient) -> None:
        """FR-010: a workspace mismatch is loud and names the mismatch."""
        fake_client.exec_error = RuntimeError("workspace not found")
        with pytest.raises(osh.SandboxError) as excinfo:
            osh.sandbox_exec_pipe("mybox", "script")
        message = str(excinfo.value)
        assert "workspace mismatch" in message
        assert "default" in message

    def test_sdk_types_do_not_leak(self, fake_client: FakeClient) -> None:
        fake_client.exec_error = RuntimeError("boom")
        with pytest.raises(osh.SandboxError):
            osh.sandbox_exec_pipe("mybox", "script")


class TestBackendSelection:
    """004 US2: fallback, override, and caching (T010)."""

    def test_construction_failure_falls_back_to_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "auto")
        monkeypatch.setattr(openshell_sdk, "_backend_decision", "auto")
        monkeypatch.setattr(openshell_sdk, "_client", None)

        def _no_gateway() -> None:
            raise RuntimeError("no gateway")

        monkeypatch.setattr(openshell_sdk, "_build_client", _no_gateway)
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="cli-out", stderr="")
            result = osh.sandbox_exec_pipe("mybox", "script")

        assert result == "cli-out"
        cmd = mock_run.call_args[0][0]
        assert cmd[:5] == ["openshell", "sandbox", "exec", "-n", "mybox"]

    def test_missing_sdk_falls_back_to_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "auto")
        monkeypatch.setattr(openshell_sdk, "_backend_decision", "auto")
        monkeypatch.setattr(openshell_sdk, "_client", None)

        def _no_module() -> None:
            raise ImportError("no module")

        monkeypatch.setattr(openshell_sdk, "_build_client", _no_module)
        with pytest.raises(openshell_sdk.SdkUnavailable):
            openshell_sdk.get_client()

    def test_cli_override_forces_legacy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "cli")
        monkeypatch.setattr(openshell_sdk, "_backend_decision", None)
        with (
            patch("sandboxctl.openshell._run") as mock_run,
            patch.object(openshell_sdk, "get_client", side_effect=AssertionError("must not run")),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="legacy", stderr="")
            result = osh.sandbox_exec_pipe("mybox", "script")

        assert result == "legacy"
        assert mock_run.call_args[0][0][:2] == ["openshell", "sandbox"]

    def test_backend_decision_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(openshell_sdk, "_backend_decision", None)
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "auto")
        assert openshell_sdk.sdk_enabled() is True
        # Changing the env var after the first resolution has no effect.
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "cli")
        assert openshell_sdk.sdk_enabled() is True

    def test_invalid_backend_value_defaults_to_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(openshell_sdk, "_backend_decision", None)
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "nonsense")
        assert openshell_sdk.sdk_enabled() is True


class TestPerGatewayClients:
    """005: per-gateway client cache (T009) — named gateways never redirect."""

    def test_named_gateway_client_cached_and_cluster_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "auto")
        monkeypatch.setattr(openshell_sdk, "_backend_decision", "auto")
        built: list[str | None] = []
        fake = MagicMock()

        def _build(gateway: str | None = None) -> MagicMock:
            built.append(gateway)
            return fake

        monkeypatch.setattr(openshell_sdk, "_build_client", _build)
        openshell_sdk._clients.clear()

        assert openshell_sdk.get_client("gw-a") is fake
        assert openshell_sdk.get_client("gw-a") is fake  # cached
        assert openshell_sdk.get_client("gw-b") is fake
        assert built == ["gw-a", "gw-b"]  # gw-a constructed once

    def test_named_gateway_failure_is_loud_not_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """R-8: a named gateway's construction failure never redirects."""
        from sandboxctl.openshell import SandboxError as FacadeSandboxError

        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "auto")
        monkeypatch.setattr(openshell_sdk, "_backend_decision", "auto")
        openshell_sdk._clients.clear()

        def _missing(gateway: str | None = None) -> object:
            raise RuntimeError(f"gateway '{gateway}' not found")

        monkeypatch.setattr(openshell_sdk, "_build_client", _missing)
        with pytest.raises(FacadeSandboxError) as excinfo:
            openshell_sdk.get_client("gw-a")
        assert "gw-a" in str(excinfo.value)
        assert not isinstance(excinfo.value, openshell_sdk.SdkUnavailable)

    def test_named_gateway_sdk_absent_is_backend_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SDK missing for a named gateway: CLI fallback (env-injected) applies."""
        monkeypatch.setenv("SANDBOXCTL_OPENSHELL_BACKEND", "auto")
        monkeypatch.setattr(openshell_sdk, "_backend_decision", "auto")
        openshell_sdk._clients.clear()

        def _no_sdk(gateway: str | None = None) -> object:
            raise ImportError("no module")

        monkeypatch.setattr(openshell_sdk, "_build_client", _no_sdk)
        with pytest.raises(openshell_sdk.SdkUnavailable):
            openshell_sdk.get_client("gw-a")


class TestWorkspaceSeam:
    """004 US3/SC-004: exactly one workspace resolution point (T013)."""

    def test_resolve_workspace_returns_default(self) -> None:
        assert openshell_sdk.resolve_workspace() == "default"
        assert openshell_sdk.DEFAULT_WORKSPACE == "default"

    def test_seam_is_the_only_workspace_reference(self) -> None:
        """No module outside openshell_sdk resolves or passes a gateway workspace.

        ``resolve_workspace``/``DEFAULT_WORKSPACE`` must appear only in the
        adapter, and only files that touch the SDK client may pass the
        ``workspace=`` keyword (profile.py's VS Code ``Workspace`` settings
        model is a different domain and contains no SDK client usage).
        """
        src_dir = Path(sandboxctl.__file__).parent
        offenders: list[str] = []
        for py in src_dir.glob("*.py"):
            if py.name == "openshell_sdk.py":
                continue
            text = py.read_text()
            if "resolve_workspace" in text or "DEFAULT_WORKSPACE" in text:
                offenders.append(py.name)
            elif "workspace=" in text and any(
                marker in text for marker in ("get_client", "SandboxClient", "openshell_sdk")
            ):
                offenders.append(py.name)
        assert offenders == [], f"workspace references outside the seam: {offenders}"
