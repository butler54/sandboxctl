"""Tests for HTTP validation utilities."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

from sandboxctl.http_utils import validate_github_token, validate_gitlab_token


class TestValidateGithubToken:
    def test_valid_token(self) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"login": "testuser"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("sandboxctl.http_utils.urllib.request.urlopen", return_value=mock_resp):
            assert validate_github_token("ghp_test") == "testuser"

    def test_invalid_token(self) -> None:
        with patch(
            "sandboxctl.http_utils.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("", 401, "", {}, None),
        ):
            assert validate_github_token("bad") is None

    def test_network_error(self) -> None:
        with patch(
            "sandboxctl.http_utils.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            assert validate_github_token("ghp_test") is None


class TestValidateGitlabToken:
    def test_valid_token(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("sandboxctl.http_utils.urllib.request.urlopen", return_value=mock_resp):
            assert validate_gitlab_token("gitlab.com", "glpat-test") is True

    def test_invalid_token(self) -> None:
        with patch(
            "sandboxctl.http_utils.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("", 401, "", {}, None),
        ):
            assert validate_gitlab_token("gitlab.com", "bad") is False
