"""Tests for MCP OAuth credential extraction and staging."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from sandboxctl.mcp_credentials import extract_mcp_credentials, stage_mcp_credentials


class TestExtractMcpCredentials:
    def test_returns_empty_on_non_darwin(self) -> None:
        with patch("sandboxctl.mcp_credentials.sys") as mock_sys:
            mock_sys.platform = "linux"
            result = extract_mcp_credentials()
        assert result == {}

    def test_returns_empty_when_no_keychain_entry(self) -> None:
        with (
            patch("sandboxctl.mcp_credentials.sys") as mock_sys,
            patch("sandboxctl.mcp_credentials.subprocess.run", side_effect=FileNotFoundError),
        ):
            mock_sys.platform = "darwin"
            result = extract_mcp_credentials()
        assert result == {}

    def test_extracts_all_servers(self) -> None:
        keychain_data = json.dumps(
            {
                "mcpOAuth": {
                    "atlassian": {"refreshToken": "rt_123", "clientId": "cid"},
                    "linear": {"refreshToken": "rt_456", "clientId": "cid2"},
                },
            }
        )
        mock_proc = MagicMock(stdout=keychain_data)
        with (
            patch("sandboxctl.mcp_credentials.sys") as mock_sys,
            patch("sandboxctl.mcp_credentials.subprocess.run", return_value=mock_proc),
        ):
            mock_sys.platform = "darwin"
            result = extract_mcp_credentials()
        assert "atlassian" in result
        assert "linear" in result

    def test_filters_by_server_names(self) -> None:
        keychain_data = json.dumps(
            {
                "mcpOAuth": {
                    "atlassian": {"refreshToken": "rt_123"},
                    "linear": {"refreshToken": "rt_456"},
                },
            }
        )
        mock_proc = MagicMock(stdout=keychain_data)
        with (
            patch("sandboxctl.mcp_credentials.sys") as mock_sys,
            patch("sandboxctl.mcp_credentials.subprocess.run", return_value=mock_proc),
        ):
            mock_sys.platform = "darwin"
            result = extract_mcp_credentials(["atlassian"])
        assert "atlassian" in result
        assert "linear" not in result

    def test_returns_empty_when_no_mcp_oauth(self) -> None:
        keychain_data = json.dumps({"someOtherKey": "value"})
        mock_proc = MagicMock(stdout=keychain_data)
        with (
            patch("sandboxctl.mcp_credentials.sys") as mock_sys,
            patch("sandboxctl.mcp_credentials.subprocess.run", return_value=mock_proc),
        ):
            mock_sys.platform = "darwin"
            result = extract_mcp_credentials()
        assert result == {}


class TestStageMcpCredentials:
    def test_stages_credentials_into_sandbox(self) -> None:
        keychain_data = json.dumps(
            {
                "mcpOAuth": {
                    "atlassian": {"refreshToken": "rt_123"},
                },
            }
        )
        mock_proc = MagicMock(stdout=keychain_data)
        with (
            patch("sandboxctl.mcp_credentials.sys") as mock_sys,
            patch("sandboxctl.mcp_credentials.subprocess.run", return_value=mock_proc),
            patch("sandboxctl.mcp_credentials.osh.sandbox_exec_pipe"),
            patch("sandboxctl.mcp_credentials.osh.sandbox_upload") as mock_upload,
        ):
            mock_sys.platform = "darwin"
            result = stage_mcp_credentials("mybox", ["atlassian"])

        assert result == ["atlassian"]
        mock_upload.assert_called_once()
        upload_args = mock_upload.call_args[0]
        assert upload_args[0] == "mybox"
        assert upload_args[2] == "/sandbox/.claude/.credentials.json"

    def test_returns_empty_when_no_credentials(self) -> None:
        with (
            patch("sandboxctl.mcp_credentials.sys") as mock_sys,
            patch("sandboxctl.mcp_credentials.subprocess.run", side_effect=FileNotFoundError),
        ):
            mock_sys.platform = "darwin"
            result = stage_mcp_credentials("mybox")
        assert result == []
