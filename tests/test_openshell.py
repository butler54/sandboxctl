"""Integration tests for openshell subprocess wrappers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sandboxctl.openshell import (
    SandboxError,
    gateway_status,
    provider_create,
    sandbox_create,
    sandbox_delete,
    sandbox_exec,
    sandbox_exec_pipe,
    sandbox_get,
    sandbox_list,
)

pytestmark = pytest.mark.integration


class TestSandboxCreate:
    def test_basic_create(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            sandbox_create(
                name="test",
                from_path=Path("/tmp/ctx"),
                policy=Path("/tmp/policy.yaml"),
                providers=["github"],
                upload=Path("/tmp/upload"),
            )
            cmd = mock_run.call_args[0][0]
            assert "openshell" in cmd
            assert "--name" in cmd
            assert "test" in cmd
            assert "--provider" in cmd
            assert "github" in cmd

    def test_create_with_multiple_providers(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            sandbox_create(
                name="test",
                from_path=Path("/tmp/ctx"),
                policy=Path("/tmp/policy.yaml"),
                providers=["github", "vertex"],
                upload=Path("/tmp/upload"),
            )
            cmd = mock_run.call_args[0][0]
            provider_indices = [i for i, x in enumerate(cmd) if x == "--provider"]
            assert len(provider_indices) == 2

    def test_create_failure_raises(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with pytest.raises(SandboxError, match="sandbox create failed"):
                sandbox_create(
                    name="test",
                    from_path=Path("/tmp/ctx"),
                    policy=Path("/tmp/policy.yaml"),
                    providers=[],
                    upload=Path("/tmp/upload"),
                )


class TestSandboxExec:
    def test_exec_without_tty(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(stdout="output")
            result = sandbox_exec("test", ["echo", "hello"])
            cmd = mock_run.call_args[0][0]
            assert "--tty" not in cmd
            assert "echo" in cmd
            assert result == "output"

    def test_exec_with_tty(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(stdout="")
            sandbox_exec("test", ["bash"], tty=True)
            cmd = mock_run.call_args[0][0]
            assert "--tty" in cmd


class TestSandboxExecPipe:
    def test_pipes_script(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(stdout="  result  ")
            result = sandbox_exec_pipe("test", "echo hello")
            assert result == "result"
            assert mock_run.call_args[1]["stdin_data"] == "echo hello"


class TestSandboxDelete:
    def test_delete(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            sandbox_delete("test")
            cmd = mock_run.call_args[0][0]
            assert cmd == ["openshell", "sandbox", "delete", "test"]


class TestSandboxList:
    def test_parses_output(self) -> None:
        output = (
            "NAME       CREATED              PHASE\n"
            "test1      2026-06-18 10:00     Running\n"
            "test2      2026-06-18 11:00     Stopped\n"
        )
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            result = sandbox_list()
            assert len(result) == 2
            assert result[0]["name"] == "test1"
            assert result[1]["name"] == "test2"

    def test_empty_output(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = sandbox_list()
            assert result == []


class TestSandboxGet:
    def test_exists(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert sandbox_get("test") is True

    def test_not_exists(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert sandbox_get("test") is False


class TestGatewayStatus:
    def test_parses_status(self) -> None:
        output = "Gateway: running\nServer: localhost:8080\nStatus: Connected\nVersion: 1.2.3\n"
        with patch("sandboxctl.openshell._run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            result = gateway_status()
            assert result["gateway"] == "running"
            assert result["status"] == "Connected"
            assert result["version"] == "1.2.3"


class TestProviderCreate:
    def test_creates_provider(self) -> None:
        with patch("sandboxctl.openshell._run") as mock_run:
            provider_create("github", "github-app", "token123")
            cmd = mock_run.call_args[0][0]
            assert "--name" in cmd
            assert "github" in cmd
            assert "--type" in cmd
            assert "--credential" in cmd
