"""Tests for scoped token management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sandboxctl.scoped_tokens import (
    GitHubTokenManager,
    GitLabTokenManager,
    ScopedToken,
    resolve_token_strategy,
)


class TestScopedToken:
    """Tests for the ScopedToken data class."""

    def test_creation(self) -> None:
        token = ScopedToken(
            provider="github",
            token="ghp_test",
            repos=["owner/repo1"],
            scope_description="test token",
        )
        assert token.provider == "github"
        assert token.repos == ["owner/repo1"]


class TestGitHubTokenManager:
    """Tests for GitHub token manager."""

    def test_get_authenticated_user(self) -> None:
        mgr = GitHubTokenManager()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout='{"login": "testuser"}')
            assert mgr.get_authenticated_user() == "testuser"

    def test_validate_repos_all_valid(self) -> None:
        mgr = GitHubTokenManager()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout='{"full_name": "owner/repo"}')
            invalid = mgr.validate_repos(["owner/repo"])
            assert invalid == []

    def test_validate_repos_some_invalid(self) -> None:
        mgr = GitHubTokenManager()
        from subprocess import CalledProcessError

        def side_effect(*args: object, **kwargs: object) -> MagicMock:
            cmd = args[0]
            if isinstance(cmd, list) and "/repos/owner/bad" in " ".join(cmd):
                raise CalledProcessError(1, cmd)
            return MagicMock(stdout='{"full_name": "owner/good"}')

        with patch("subprocess.run", side_effect=side_effect):
            invalid = mgr.validate_repos(["owner/good", "owner/bad"])
            assert invalid == ["owner/bad"]


class TestGitLabTokenManager:
    """Tests for GitLab token manager."""

    def test_validate_server_success(self) -> None:
        mgr = GitLabTokenManager(server="https://gitlab.com", token="test")
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"id": 1, "username": "test"}'
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            assert mgr.validate_server() is True

    def test_validate_server_failure(self) -> None:
        mgr = GitLabTokenManager(server="https://bad.example.com", token="test")
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            assert mgr.validate_server() is False

    def test_private_instance(self) -> None:
        mgr = GitLabTokenManager(server="https://gitlab.internal.example.com", token="glpat-test")
        assert mgr.server == "https://gitlab.internal.example.com"


class TestResolveTokenStrategy:
    """Tests for token resolution from profile repos."""

    def test_github_with_credential(self) -> None:
        repos = {"github": ["owner/repo1", "owner/repo2"]}
        with patch("sandboxctl.scoped_tokens.get_credential", return_value="ghp_stored"):
            tokens = resolve_token_strategy(repos)
            assert len(tokens) == 1
            assert tokens[0].provider == "github"
            assert tokens[0].token == "ghp_stored"
            assert len(tokens[0].repos) == 2

    def test_github_no_credential(self) -> None:
        repos = {"github": ["owner/repo1"]}
        with patch("sandboxctl.scoped_tokens.get_credential", return_value=None):
            tokens = resolve_token_strategy(repos)
            assert len(tokens) == 0

    def test_gitlab_with_server_specific_credential(self) -> None:
        repos = {"gitlab.example.com": ["group/project"]}

        def mock_get(service: str, account: str) -> str | None:
            if service == "sandboxctl-gitlab-gitlab-example-com":
                return "glpat-specific"
            return None

        with patch("sandboxctl.scoped_tokens.get_credential", side_effect=mock_get):
            tokens = resolve_token_strategy(repos)
            assert len(tokens) == 1
            assert tokens[0].provider == "gitlab:gitlab.example.com"

    def test_gitlab_falls_back_to_generic(self) -> None:
        repos = {"gitlab.com": ["group/project"]}

        def mock_get(service: str, account: str) -> str | None:
            if service == "sandboxctl-gitlab-token":
                return "glpat-generic"
            return None

        with patch("sandboxctl.scoped_tokens.get_credential", side_effect=mock_get):
            tokens = resolve_token_strategy(repos)
            assert len(tokens) == 1
            assert "generic PAT" in tokens[0].scope_description

    def test_mixed_providers(self) -> None:
        repos = {
            "github": ["owner/repo"],
            "gitlab.com": ["group/project"],
        }
        with patch("sandboxctl.scoped_tokens.get_credential", return_value="token123"):
            tokens = resolve_token_strategy(repos)
            assert len(tokens) == 2
            providers = {t.provider for t in tokens}
            assert "github" in providers
            assert "gitlab:gitlab.com" in providers

    def test_github_dot_com_alias(self) -> None:
        repos = {"github.com": ["owner/repo"]}
        with patch("sandboxctl.scoped_tokens.get_credential", return_value="ghp_test"):
            tokens = resolve_token_strategy(repos)
            assert len(tokens) == 1
            assert tokens[0].provider == "github"
