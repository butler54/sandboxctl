"""Scoped token generation for GitHub and GitLab per-profile credentials."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from sandboxctl.credentials import get_credential


@dataclass
class ScopedToken:
    """A scoped access token for a Git provider."""

    provider: str
    token: str
    repos: list[str]
    scope_description: str


class GitHubTokenManager:
    """Generate and manage GitHub fine-grained PATs scoped to profile repos.

    Requires the `gh` CLI to be authenticated.
    Fine-grained PATs provide repo-level read/write for listed repos
    and read-only access elsewhere.
    """

    def _gh_api(self, endpoint: str, method: str = "GET", data: dict | None = None) -> dict | list:
        """Call the GitHub API via gh CLI."""
        cmd = ["gh", "api", endpoint, "--method", method]
        if data:
            cmd.extend(["--input", "-"])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            input=json.dumps(data) if data else None,
        )
        return json.loads(result.stdout)

    def validate_repos(self, repos: list[str]) -> list[str]:
        """Validate that repos exist and are accessible. Returns list of invalid repos."""
        invalid = []
        for repo in repos:
            try:
                self._gh_api(f"/repos/{repo}")
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                invalid.append(repo)
        return invalid

    def get_authenticated_user(self) -> str:
        """Get the authenticated GitHub username."""
        result = self._gh_api("/user")
        if isinstance(result, dict):
            return result.get("login", "")
        return ""


class GitLabTokenManager:
    """Generate and manage GitLab project/group access tokens.

    Supports both gitlab.com and private GitLab instances.
    Token strategy (project vs group) is determined by the profile.
    """

    def __init__(self, server: str = "https://gitlab.com", token: str = "") -> None:
        if not server.startswith("https://"):
            server = f"https://{server}"
        self.server = server.rstrip("/")
        self.token = token

    def _api(self, endpoint: str, method: str = "GET", data: dict | None = None) -> dict | list:
        """Call the GitLab REST API."""
        import urllib.request

        url = f"{self.server}/api/v4{endpoint}"
        headers = {"PRIVATE-TOKEN": self.token, "Content-Type": "application/json"}
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return json.loads(resp.read().decode())

    def validate_server(self) -> bool:
        """Check connectivity to the GitLab instance."""
        try:
            result = self._api("/user")
            return isinstance(result, dict) and "id" in result
        except Exception:
            return False

    def validate_projects(self, projects: list[str]) -> list[str]:
        """Validate project paths exist. Returns list of invalid projects."""
        import urllib.parse

        invalid = []
        for project in projects:
            try:
                encoded = urllib.parse.quote(project, safe="")
                self._api(f"/projects/{encoded}")
            except Exception:
                invalid.append(project)
        return invalid


def resolve_token_strategy(
    repos: dict[str, list[str]],
    github_token_manager: GitHubTokenManager | None = None,
    gitlab_managers: dict[str, GitLabTokenManager] | None = None,
) -> list[ScopedToken]:
    """Resolve scoped tokens for all providers in a profile's repo list.

    Falls back to generic credentials from the credential backend
    when scoped token generation is unavailable.
    """
    tokens: list[ScopedToken] = []

    for server, repo_list in repos.items():
        if server == "github" or server == "github.com":
            generic = get_credential("sandboxctl-github-token", "default")
            if generic:
                tokens.append(
                    ScopedToken(
                        provider="github",
                        token=generic,
                        repos=repo_list,
                        scope_description="generic PAT (scoped tokens require gh CLI auth)",
                    )
                )
        else:
            service_name = f"sandboxctl-gitlab-{server.replace('.', '-')}"
            generic = get_credential(service_name, "default")
            if not generic:
                generic = get_credential("sandboxctl-gitlab-token", "default")
            if generic:
                tokens.append(
                    ScopedToken(
                        provider=f"gitlab:{server}",
                        token=generic,
                        repos=repo_list,
                        scope_description=f"generic PAT for {server}",
                    )
                )

    return tokens
