"""Full-stack health validation: credentials, TLS, and sandbox readiness."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig
from sandboxctl.credentials import get_credential
from sandboxctl.health import diagnose
from sandboxctl.models import CredentialConfig
from sandboxctl.policy import PolicyIncludeError, render_policy
from sandboxctl.profile import list_profiles, load_profile

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Outcome of a single host-side credential check."""

    passed: bool
    name: str
    details: str
    fix_hint: str | None = None


@dataclass
class FixResult:
    """Outcome of injecting a credential into a running sandbox."""

    success: bool
    name: str
    details: str


@dataclass
class DoctorReport:
    """Aggregated report from a full doctor run."""

    sandbox_name: str | None
    host_checks: list[CheckResult] = field(default_factory=list)
    sandbox_fixes: list[FixResult] = field(default_factory=list)
    profile_readiness: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class CredentialCheck(ABC):
    """Single credential check with host validation and sandbox injection."""

    @property
    @abstractmethod
    def check_name(self) -> str:
        """Human-readable name for this check."""

    @abstractmethod
    def check(self, config: SandboxctlConfig) -> CheckResult:
        """Validate the credential on the host side."""

    @abstractmethod
    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        """Inject / repair the credential inside a running sandbox."""

    def required_by(self, cred_config: CredentialConfig) -> bool:
        """Return True if this check is required by the given config."""
        return True


# ---------------------------------------------------------------------------
# 1. GitHub PAT
# ---------------------------------------------------------------------------


class GitHubPATCheck(CredentialCheck):
    """Validate and inject GitHub personal access token."""

    @property
    def check_name(self) -> str:
        return "GitHub PAT"

    def check(self, config: SandboxctlConfig) -> CheckResult:
        account = os.environ.get("USER", "")
        token = get_credential(config.keychain_github, account)
        if not token:
            return CheckResult(
                passed=False,
                name=self.check_name,
                details="No GitHub token found in credential store",
                fix_hint="Run: sandboxctl setup --github-token",
            )
        from sandboxctl.http_utils import validate_github_token

        login = validate_github_token(token)
        if login:
            return CheckResult(
                passed=True,
                name=self.check_name,
                details=f"Authenticated as {login}",
            )
        return CheckResult(
            passed=False,
            name=self.check_name,
            details="Token validation failed",
            fix_hint="Token may be expired — re-run: sandboxctl setup --github-token",
        )

    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        account = os.environ.get("USER", "")
        token = get_credential(config.keychain_github, account)
        if not token:
            return FixResult(
                success=False,
                name=self.check_name,
                details="No GitHub token available to inject",
            )
        encoded = base64.b64encode(token.encode()).decode()
        script = f"echo {encoded} | base64 -d | gh auth login --with-token && gh auth setup-git"
        osh.sandbox_exec_pipe(sandbox_name, script)
        return FixResult(
            success=True,
            name=self.check_name,
            details="GitHub token injected and git credential helper configured",
        )

    def required_by(self, cred_config: CredentialConfig) -> bool:
        return cred_config.github


# ---------------------------------------------------------------------------
# 2. GitLab PAT
# ---------------------------------------------------------------------------


class GitLabPATCheck(CredentialCheck):
    """Validate and inject GitLab personal access token."""

    @property
    def check_name(self) -> str:
        return "GitLab PAT"

    def _discover_servers(self, config: SandboxctlConfig) -> list[str]:
        """Discover GitLab servers from profiles and config."""
        servers: set[str] = set()
        for profile_name in list_profiles(config):
            try:
                profile = load_profile(profile_name, config)
            except Exception:  # noqa: BLE001, S112
                continue
            # Check repos dict keys for GitLab servers
            for server_key in profile.repos:
                if "gitlab" in server_key.lower():
                    servers.add(server_key)
            # Check explicit gitlab_servers in credentials config
            for srv in profile.credentials.gitlab_servers:
                servers.add(srv)
        return sorted(servers)

    def check(self, config: SandboxctlConfig) -> CheckResult:
        account = os.environ.get("USER", "")
        token = get_credential(config.keychain_gitlab, account)
        if not token:
            return CheckResult(
                passed=False,
                name=self.check_name,
                details="No GitLab token found in credential store",
                fix_hint="Run: sandboxctl setup --gitlab-token",
            )
        servers = self._discover_servers(config)
        if not servers:
            return CheckResult(
                passed=True,
                name=self.check_name,
                details="Token present but no GitLab servers configured in profiles",
            )
        from sandboxctl.http_utils import validate_gitlab_token

        errors: list[str] = []
        for server in servers:
            if not validate_gitlab_token(server, token):
                errors.append(f"{server}: token invalid or expired")
        if errors:
            return CheckResult(
                passed=False,
                name=self.check_name,
                details="; ".join(errors),
                fix_hint="Token may be expired or lack API scope",
            )
        return CheckResult(
            passed=True,
            name=self.check_name,
            details=f"Validated against {len(servers)} server(s)",
        )

    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        account = os.environ.get("USER", "")
        token = get_credential(config.keychain_gitlab, account)
        if not token:
            return FixResult(
                success=False,
                name=self.check_name,
                details="No GitLab token available to inject",
            )
        servers = self._discover_servers(config)
        # Inject GITLAB_TOKEN env var and configure git credential helper per server
        env_line = f'export GITLAB_TOKEN="{token}"'
        encoded_env = base64.b64encode(env_line.encode()).decode()
        script_parts = [
            f"grep -q GITLAB_TOKEN /sandbox/.bashrc 2>/dev/null || echo {encoded_env} | base64 -d >> /sandbox/.bashrc",
        ]
        for server in servers:
            script_parts.append(
                f"git config --global credential.https://{server}.helper "
                f'\'!f() {{ echo "username=oauth2"; echo "password=$GITLAB_TOKEN"; }}; f\''
            )
        script = " && ".join(script_parts)
        osh.sandbox_exec_pipe(sandbox_name, script)
        return FixResult(
            success=True,
            name=self.check_name,
            details=f"GitLab token injected, credential helpers for {len(servers)} server(s)",
        )

    def required_by(self, cred_config: CredentialConfig) -> bool:
        return cred_config.gitlab


# ---------------------------------------------------------------------------
# 3. Google Cloud ADC
# ---------------------------------------------------------------------------


class GCloudADCCheck(CredentialCheck):
    """Validate and inject gcloud application-default credentials."""

    _ADC_PATH = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"

    @property
    def check_name(self) -> str:
        return "gcloud ADC"

    def check(self, config: SandboxctlConfig) -> CheckResult:
        if not self._ADC_PATH.exists():
            return CheckResult(
                passed=False,
                name=self.check_name,
                details=f"ADC file not found: {self._ADC_PATH}",
                fix_hint="Run: gcloud auth application-default login",
            )
        try:
            result = subprocess.run(
                ["gcloud", "auth", "application-default", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return CheckResult(
                    passed=True,
                    name=self.check_name,
                    details="ADC file present and access token valid",
                )
            return CheckResult(
                passed=False,
                name=self.check_name,
                details=f"ADC token validation failed: {result.stderr.strip()[:120]}",
                fix_hint="Run: gcloud auth application-default login",
            )
        except FileNotFoundError:
            return CheckResult(
                passed=False,
                name=self.check_name,
                details="gcloud CLI not found on host",
                fix_hint="Install the Google Cloud SDK",
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                passed=False,
                name=self.check_name,
                details="gcloud token validation timed out",
                fix_hint="Check network connectivity to Google Cloud",
            )

    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        if not self._ADC_PATH.exists():
            return FixResult(
                success=False,
                name=self.check_name,
                details="ADC file not found on host — cannot inject",
            )
        # Ensure remote directory exists
        osh.sandbox_exec_pipe(sandbox_name, "mkdir -p /sandbox/.config/gcloud")
        osh.sandbox_upload(
            sandbox_name,
            self._ADC_PATH,
            "/sandbox/.config/gcloud/application_default_credentials.json",
        )
        return FixResult(
            success=True,
            name=self.check_name,
            details="ADC file uploaded to sandbox",
        )

    def required_by(self, cred_config: CredentialConfig) -> bool:
        return cred_config.gcloud_adc


# ---------------------------------------------------------------------------
# 4. Google Workspace CLI credentials
# ---------------------------------------------------------------------------


class GWSCredentialCheck(CredentialCheck):
    """Validate and inject Google Workspace CLI credentials."""

    _GWS_DIR = Path.home() / ".config" / "gws"

    @property
    def check_name(self) -> str:
        return "GWS credentials"

    def check(self, config: SandboxctlConfig) -> CheckResult:
        client_secret = self._GWS_DIR / "client_secret.json"
        creds_json = self._GWS_DIR / "credentials.json"
        creds_enc = self._GWS_DIR / "credentials.enc"
        if not client_secret.exists():
            return CheckResult(
                passed=False,
                name=self.check_name,
                details=f"client_secret.json not found: {client_secret}",
                fix_hint="Set up GWS CLI: https://github.com/nickmaheshwari/gws",
            )
        if creds_json.exists():
            try:
                creds_data = json.loads(creds_json.read_text())
                if "refresh_token" not in str(creds_data):
                    return CheckResult(
                        passed=False,
                        name=self.check_name,
                        details="credentials.json missing refresh_token",
                        fix_hint="Re-authenticate: gws auth login",
                    )
            except (json.JSONDecodeError, OSError) as exc:
                return CheckResult(
                    passed=False,
                    name=self.check_name,
                    details=f"Failed to parse credentials.json: {exc}",
                    fix_hint="Re-authenticate: gws auth login",
                )
            return CheckResult(
                passed=True,
                name=self.check_name,
                details="client_secret.json and credentials.json present with refresh_token",
            )
        if creds_enc.exists():
            try:
                result = subprocess.run(
                    ["gws", "auth", "export", "--unmasked"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=15,
                )
                if "refresh_token" in result.stdout:
                    return CheckResult(
                        passed=True,
                        name=self.check_name,
                        details="credentials.enc present, export valid",
                    )
                return CheckResult(
                    passed=False,
                    name=self.check_name,
                    details="credentials.enc present but export missing refresh_token",
                    fix_hint="Re-authenticate: gws auth login",
                )
            except FileNotFoundError:
                return CheckResult(
                    passed=False,
                    name=self.check_name,
                    details="credentials.enc present but gws CLI not found",
                    fix_hint="Install GWS CLI to validate encrypted credentials",
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                return CheckResult(
                    passed=False,
                    name=self.check_name,
                    details="credentials.enc present but export failed",
                    fix_hint="Re-authenticate: gws auth login",
                )
        return CheckResult(
            passed=False,
            name=self.check_name,
            details="No credentials found (neither credentials.json nor credentials.enc)",
            fix_hint="Run: gws auth login",
        )

    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        client_secret = self._GWS_DIR / "client_secret.json"
        if not client_secret.exists():
            return FixResult(
                success=False,
                name=self.check_name,
                details="client_secret.json not found on host — cannot inject",
            )

        osh.sandbox_exec_pipe(sandbox_name, "mkdir -p /sandbox/.config/gws")
        osh.sandbox_upload(
            sandbox_name,
            client_secret,
            "/sandbox/.config/gws/client_secret.json",
        )

        # Try to export fresh credentials via gws CLI
        if shutil.which("gws"):
            try:
                result = subprocess.run(
                    ["gws", "auth", "export", "--unmasked"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=15,
                )
                stdout = result.stdout
                # Filter out non-JSON log lines
                if "Using keyring" in stdout:
                    stdout = "\n".join(line for line in stdout.split("\n") if not line.startswith("Using keyring"))
                fd, tmp_name = tempfile.mkstemp(suffix=".json")
                tmp_path = Path(tmp_name)
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "w") as tmp:
                    tmp.write(stdout.strip() + "\n")
                try:
                    osh.sandbox_upload(
                        sandbox_name,
                        tmp_path,
                        "/sandbox/.config/gws/credentials.json",
                    )
                finally:
                    tmp_path.unlink(missing_ok=True)

                # Set keyring backend for file-based usage in sandbox
                osh.sandbox_exec_pipe(
                    sandbox_name,
                    "grep -q GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND /sandbox/.bashrc 2>/dev/null || "
                    'echo "export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file" >> /sandbox/.bashrc',
                )
                self._bootstrap_token_cache(sandbox_name)
                return FixResult(
                    success=True,
                    name=self.check_name,
                    details="GWS client_secret + fresh credentials exported and uploaded + token cache bootstrapped",
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        # Fallback: upload existing credentials.json if available
        creds_file = self._GWS_DIR / "credentials.json"
        if creds_file.exists():
            osh.sandbox_upload(
                sandbox_name,
                creds_file,
                "/sandbox/.config/gws/credentials.json",
            )
            osh.sandbox_exec_pipe(
                sandbox_name,
                "grep -q GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND /sandbox/.bashrc 2>/dev/null || "
                'echo "export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file" >> /sandbox/.bashrc',
            )
            self._bootstrap_token_cache(sandbox_name)
            return FixResult(
                success=True,
                name=self.check_name,
                details="GWS client_secret + existing credentials.json uploaded + token cache bootstrapped",
            )

        return FixResult(
            success=False,
            name=self.check_name,
            details="client_secret uploaded but no credentials available (gws CLI not found)",
        )

    @staticmethod
    def _bootstrap_token_cache(sandbox_name: str) -> None:
        """Bootstrap token_cache.json inside the sandbox via headless OAuth2 token exchange.

        gws auth login requires a browser redirect, which sandboxes can't provide.
        This exchanges the refresh_token from credentials.json for an access_token
        and writes token_cache.json so gws auth status reports token_cache_exists: true.
        """
        script = (
            'python3 -c "'
            "import json, urllib.request, urllib.parse, sys\\n"
            "creds_path = '/sandbox/.config/gws/credentials.json'\\n"
            "cache_path = '/sandbox/.config/gws/token_cache.json'\\n"
            "try:\\n"
            "    creds = json.load(open(creds_path))\\n"
            "    rt = creds.get('refresh_token', '')\\n"
            "    cid = creds.get('client_id', '')\\n"
            "    cs = creds.get('client_secret', '')\\n"
            "    if not all([rt, cid, cs]):\\n"
            "        print('skip: missing fields')\\n"
            "        sys.exit(0)\\n"
            "    data = urllib.parse.urlencode({\\n"
            "        'client_id': cid, 'client_secret': cs,\\n"
            "        'refresh_token': rt, 'grant_type': 'refresh_token',\\n"
            "    }).encode()\\n"
            "    req = urllib.request.Request('https://oauth2.googleapis.com/token', data)\\n"
            "    resp = json.load(urllib.request.urlopen(req, timeout=15))\\n"
            "    cache = {\\n"
            "        'access_token': resp['access_token'],\\n"
            "        'token_type': resp.get('token_type', 'Bearer'),\\n"
            "        'expires_in': resp.get('expires_in', 3600),\\n"
            "        'scope': resp.get('scope', ''),\\n"
            "        'refresh_token': rt,\\n"
            "    }\\n"
            "    with open(cache_path, 'w') as f:\\n"
            "        json.dump(cache, f)\\n"
            "    print('token_cache.json created')\\n"
            "except Exception as e:\\n"
            "    print(f'token_cache bootstrap skipped: {e}')\\n"
            '"'
        )
        try:
            osh.sandbox_exec_pipe(sandbox_name, script)
        except Exception:  # noqa: BLE001, S110
            pass

    def required_by(self, cred_config: CredentialConfig) -> bool:
        return cred_config.gws


# ---------------------------------------------------------------------------
# 5. SSH key
# ---------------------------------------------------------------------------


class SSHKeyCheck(CredentialCheck):
    """Validate and inject SSH key pair."""

    @property
    def check_name(self) -> str:
        return "SSH key"

    def check(self, config: SandboxctlConfig) -> CheckResult:
        key_path = config.ssh_key
        pub_path = key_path.with_suffix(".pub")
        if not key_path.exists():
            return CheckResult(
                passed=False,
                name=self.check_name,
                details=f"Private key not found: {key_path}",
                fix_hint=f"Generate: ssh-keygen -t ed25519 -f {key_path}",
            )
        if not pub_path.exists():
            return CheckResult(
                passed=False,
                name=self.check_name,
                details=f"Public key not found: {pub_path}",
                fix_hint=f"Generate public key: ssh-keygen -y -f {key_path} > {pub_path}",
            )
        return CheckResult(
            passed=True,
            name=self.check_name,
            details=f"Key pair present: {key_path}",
        )

    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        key_path = config.ssh_key
        pub_path = key_path.with_suffix(".pub")
        if not key_path.exists():
            return FixResult(
                success=False,
                name=self.check_name,
                details="Private key not found on host — cannot inject",
            )
        osh.sandbox_exec_pipe(sandbox_name, "mkdir -p /sandbox/.ssh && chmod 700 /sandbox/.ssh")
        osh.sandbox_upload(sandbox_name, key_path, "/sandbox/.ssh/id_ed25519")
        osh.sandbox_exec_pipe(sandbox_name, "chmod 600 /sandbox/.ssh/id_ed25519")
        if pub_path.exists():
            osh.sandbox_upload(sandbox_name, pub_path, "/sandbox/.ssh/id_ed25519.pub")
        return FixResult(
            success=True,
            name=self.check_name,
            details="SSH key pair uploaded to sandbox",
        )

    def required_by(self, cred_config: CredentialConfig) -> bool:
        return cred_config.ssh_key


# ---------------------------------------------------------------------------
# 6. CA bundle
# ---------------------------------------------------------------------------


class CABundleCheck(CredentialCheck):
    """Validate CA certificate files and inject a merged bundle."""

    @property
    def check_name(self) -> str:
        return "CA bundle"

    def check(self, config: SandboxctlConfig) -> CheckResult:
        missing: list[str] = []
        if config.ca_bundle and not config.ca_bundle.exists():
            missing.append(str(config.ca_bundle))
        for ca_path in config.ca_paths:
            if not ca_path.exists():
                missing.append(str(ca_path))
        if missing:
            return CheckResult(
                passed=False,
                name=self.check_name,
                details=f"Missing CA files: {', '.join(missing)}",
                fix_hint="Check paths in config.toml [paths] ca_bundle and [tls] ca_paths",
            )
        sources = []
        if config.ca_bundle:
            sources.append(str(config.ca_bundle))
        sources.extend(str(p) for p in config.ca_paths)
        if not sources:
            return CheckResult(
                passed=True,
                name=self.check_name,
                details="No custom CA files configured (will use OpenShell default CAs)",
            )
        return CheckResult(
            passed=True,
            name=self.check_name,
            details=f"{len(sources)} CA source(s) present",
        )

    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        return build_and_inject_ca_bundle(sandbox_name, config)

    def required_by(self, cred_config: CredentialConfig) -> bool:
        return True


# ---------------------------------------------------------------------------
# Shared CA bundle builder
# ---------------------------------------------------------------------------


def build_and_inject_ca_bundle(
    sandbox_name: str,
    config: SandboxctlConfig,
) -> FixResult:
    """Build a merged CA bundle and inject it into a running sandbox.

    Concatenates:
    1. OpenShell platform CAs (from /etc/openshell-tls/ inside sandbox)
    2. config.ca_bundle (if configured)
    3. config.ca_paths (additional CA files)

    Then uploads to /sandbox/.ca-bundle.pem and sets environment variables.
    """
    # Start with OpenShell's own CAs from inside the sandbox
    script_parts = [
        "cat /etc/openshell-tls/ca-bundle.pem /etc/openshell-tls/openshell-ca.pem "
        "2>/dev/null > /sandbox/.ca-bundle.pem || true",
    ]

    # Append host-side CA files
    ca_sources: list[Path] = []
    if config.ca_bundle and config.ca_bundle.exists():
        ca_sources.append(config.ca_bundle)
    for ca_path in config.ca_paths:
        if ca_path.exists():
            ca_sources.append(ca_path)

    if ca_sources:
        # Concatenate all host CA data into a heredoc for injection
        ca_data_parts: list[str] = []
        for src in ca_sources:
            try:
                ca_data_parts.append(src.read_text())
            except OSError:
                continue
        if ca_data_parts:
            combined_ca = "\n".join(ca_data_parts)
            encoded = base64.b64encode(combined_ca.encode()).decode()
            script_parts.append(f"echo {encoded} | base64 -d >> /sandbox/.ca-bundle.pem")

    # Set TLS environment variables idempotently
    env_block = (
        "export GIT_SSL_CAINFO=/sandbox/.ca-bundle.pem\n"
        "export SSL_CERT_FILE=/sandbox/.ca-bundle.pem\n"
        "export CURL_CA_BUNDLE=/sandbox/.ca-bundle.pem\n"
        "export REQUESTS_CA_BUNDLE=/sandbox/.ca-bundle.pem\n"
        "export GH_SSL_CAINFO=/sandbox/.ca-bundle.pem"
    )
    script_parts.append(
        f'grep -q GIT_SSL_CAINFO /sandbox/.bashrc 2>/dev/null || echo "{env_block}" >> /sandbox/.bashrc'
    )

    script = " && ".join(script_parts)
    osh.sandbox_exec_pipe(sandbox_name, script)

    source_count = len(ca_sources)
    return FixResult(
        success=True,
        name="CA bundle",
        details=f"Bundle built with OpenShell CAs + {source_count} host CA source(s), env vars set",
    )


# ---------------------------------------------------------------------------
# Registry and orchestration
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 7. MCP OAuth credentials
# ---------------------------------------------------------------------------


class MCPOAuthCheck(CredentialCheck):
    """Validate and inject MCP OAuth credentials from host keychain."""

    @property
    def check_name(self) -> str:
        return "MCP OAuth"

    def _get_configured_servers(self, config: SandboxctlConfig) -> list[str]:
        """Discover MCP servers from profiles."""
        servers: set[str] = set()
        for profile_name in list_profiles(config):
            try:
                profile = load_profile(profile_name, config)
            except Exception:  # noqa: BLE001, S112
                continue
            servers.update(profile.credentials.mcp.servers)
        return sorted(servers)

    def check(self, config: SandboxctlConfig) -> CheckResult:
        from sandboxctl.mcp_credentials import extract_mcp_credentials

        configured = self._get_configured_servers(config)
        if not configured:
            return CheckResult(
                passed=True,
                name=self.check_name,
                details="No MCP servers configured in profiles",
            )

        available = extract_mcp_credentials(configured)
        missing = [s for s in configured if s not in available]
        if missing:
            return CheckResult(
                passed=False,
                name=self.check_name,
                details=f"Missing credentials for: {', '.join(missing)}",
                fix_hint="Run: claude mcp login <server-name>",
            )
        return CheckResult(
            passed=True,
            name=self.check_name,
            details=f"{len(available)} server(s) have credentials",
        )

    def fix(self, sandbox_name: str, config: SandboxctlConfig) -> FixResult:
        from sandboxctl.mcp_credentials import stage_mcp_credentials

        configured = self._get_configured_servers(config)
        staged = stage_mcp_credentials(sandbox_name, configured or None)
        if staged:
            return FixResult(
                success=True,
                name=self.check_name,
                details=f"Staged credentials for: {', '.join(staged)}",
            )
        return FixResult(
            success=False,
            name=self.check_name,
            details="No MCP OAuth credentials available in host keychain",
        )

    def required_by(self, cred_config: CredentialConfig) -> bool:
        return bool(cred_config.mcp.servers)


ALL_CHECKS: list[CredentialCheck] = [
    GitHubPATCheck(),
    GitLabPATCheck(),
    GCloudADCCheck(),
    GWSCredentialCheck(),
    SSHKeyCheck(),
    CABundleCheck(),
    MCPOAuthCheck(),
]


def check_host_credentials(config: SandboxctlConfig) -> list[CheckResult]:
    """Run all credential checks on the host.

    Returns a list of CheckResult for each check, regardless of pass/fail.
    """
    results: list[CheckResult] = []
    for chk in ALL_CHECKS:
        results.append(chk.check(config))
    return results


def check_profile_readiness(config: SandboxctlConfig) -> dict[str, list[str]]:
    """Check which credentials each profile requires and flag missing ones.

    Returns a dict mapping profile name to a list of failing check names.
    """
    readiness: dict[str, list[str]] = {}
    for profile_name in list_profiles(config):
        try:
            profile = load_profile(profile_name, config)
        except Exception:  # noqa: BLE001
            readiness[profile_name] = ["profile-load-error"]
            continue
        cred_config = profile.credentials
        missing: list[str] = []
        for chk in ALL_CHECKS:
            if chk.required_by(cred_config):
                result = chk.check(config)
                if not result.passed:
                    missing.append(chk.check_name)
        readiness[profile_name] = missing
    return readiness


def check_policy_drift(sandbox_name: str, config: SandboxctlConfig) -> CheckResult:
    """Compare a named profile's desired network policy to the active base policy."""
    if sandbox_name not in list_profiles(config):
        return CheckResult(
            passed=True,
            name="Policy drift",
            details="skipped (no profile with the sandbox name)",
        )
    try:
        profile = load_profile(sandbox_name, config)
    except FileNotFoundError:
        return CheckResult(
            passed=True,
            name="Policy drift",
            details="skipped (no profile with the sandbox name)",
        )

    path = config.profiles_dir / profile.name / profile.sandbox.policy
    if not path.exists():
        return CheckResult(False, "Policy drift", f"profile policy not found: {path}")
    try:
        desired = yaml.safe_load(render_policy(path, config.profiles_dir)) or {}
    except PolicyIncludeError as exc:
        return CheckResult(False, "Policy drift", str(exc))

    output = osh.policy_get_base(sandbox_name)
    try:
        active = json.loads(output)["policy"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return CheckResult(False, "Policy drift", "could not retrieve the active base policy")

    if active.get("network_policies", {}) == desired.get("network_policies", {}):
        return CheckResult(True, "Policy drift", "active network policy matches profile")
    return CheckResult(
        False,
        "Policy drift",
        "active network policy differs from profile; run 'sandboxctl restart "
        f"{sandbox_name}' or 'openshell policy set --wait {sandbox_name}' to reload",
    )


def fix_sandbox_credentials(
    sandbox_name: str,
    config: SandboxctlConfig,
    checks: list[CredentialCheck] | None = None,
) -> list[FixResult]:
    """Inject credentials into a running sandbox.

    Runs a health pre-flight check first. If the sandbox is not healthy
    (and cannot be auto-recovered), returns early with a pre-flight failure.

    Args:
        sandbox_name: Name of the target sandbox.
        config: Loaded sandboxctl configuration.
        checks: Subset of checks to run; defaults to ALL_CHECKS.

    Returns:
        List of FixResult for each attempted injection.
    """
    # Pre-flight: ensure the sandbox is alive
    health = diagnose(sandbox_name, auto_recover=True)
    if not health.healthy:
        return [
            FixResult(
                success=False,
                name="pre-flight",
                details=f"Sandbox not healthy: {health.recovery_action}. Details: {'; '.join(health.details)}",
            )
        ]

    target_checks = checks if checks is not None else ALL_CHECKS
    results: list[FixResult] = []
    for chk in target_checks:
        try:
            results.append(chk.fix(sandbox_name, config))
        except Exception as exc:  # noqa: BLE001
            results.append(
                FixResult(
                    success=False,
                    name=chk.check_name,
                    details=f"Injection failed: {exc}",
                )
            )
    return results
