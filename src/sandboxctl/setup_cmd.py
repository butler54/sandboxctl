"""First-run onboarding: prerequisites, credentials, and provider setup."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import typer

from sandboxctl.config import SandboxctlConfig, ensure_config_dir, find_vscode_bin
from sandboxctl.credentials import get_credential, store_credential
from sandboxctl.openshell import gateway_status, provider_create, provider_delete, settings_set
from sandboxctl.profile import list_profiles, load_profile


def _check_prerequisites() -> None:
    typer.echo("\n--- Prerequisites ---")

    openshell_ok = False
    openshell_bin = shutil.which("openshell")
    if openshell_bin:
        result = subprocess.run(
            ["openshell", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        version = result.stdout.strip() or result.stderr.strip() or "installed"
        typer.echo(f"  openshell: {version}")
        openshell_ok = True
    else:
        typer.echo("  openshell: NOT FOUND")
        typer.echo("  Install: curl -fsSL https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | bash")

    podman_ok = False
    podman_bin = shutil.which("podman")
    if podman_bin:
        result = subprocess.run(
            ["podman", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        typer.echo(f"  podman: {result.stdout.strip()}")
        podman_ok = True
    else:
        typer.echo("  podman: NOT FOUND")
        typer.echo("  Install podman before continuing.")

    try:
        gw = gateway_status()
        status = gw.get("status", "Unknown")
        typer.echo(f"  gateway: {status}")
        if status != "Connected":
            typer.echo("  WARNING: Gateway is not connected. Some features may not work.")
    except Exception:
        typer.echo("  gateway: could not reach (openshell may not be running)")

    if not openshell_ok or not podman_ok:
        typer.echo("\nMissing required tools. Install them and re-run setup.")
        raise typer.Exit(1)


def _install_profiles(config: SandboxctlConfig) -> None:
    typer.echo("\n--- Bundled Profiles ---")

    try:
        from sandboxctl.bundled_profiles import PROFILES
    except ImportError:
        typer.echo("  No bundled profiles available.")
        return

    for name, content in PROFILES.items():
        dest = config.profiles_dir / f"{name}.toml"
        if dest.exists():
            typer.echo(f"  Exists: {name}")
        else:
            dest.write_text(content)
            typer.echo(f"  Installed: {name}")


def _setup_cli_tools() -> None:
    typer.echo("\n--- CLI Tools ---")

    vscode_bin = find_vscode_bin()
    if vscode_bin:
        typer.echo(f"  VS Code: {vscode_bin}")
    else:
        typer.echo("  VS Code: not found (optional)")

    bin_dir = Path.home() / "bin"
    if bin_dir.is_dir():
        stale_scripts = ["sandbox-create", "sandbox-open"]
        for script in stale_scripts:
            link = bin_dir / script
            if link.is_symlink() and not link.resolve().exists():
                link.unlink()
                typer.echo(f"  Removed stale symlink: ~/bin/{script}")


def _setup_ssh_key(config: SandboxctlConfig) -> None:
    typer.echo("\n--- SSH Key ---")

    if config.ssh_key.exists():
        typer.echo(f"  Key exists: {config.ssh_key}")
        return

    config.ssh_key.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(config.ssh_key), "-N", "", "-C", "openshell-sandbox"],
        check=True,
        capture_output=True,
    )
    typer.echo(f"  Generated: {config.ssh_key}")

    pub_key = config.ssh_key.with_suffix(".pub")
    if pub_key.exists():
        typer.echo(f"  Public key:\n    {pub_key.read_text().strip()}")
    typer.echo("  Add as signing key: https://github.com/settings/ssh/new")


def _validate_github_token(token: str) -> str | None:
    """Validate a GitHub PAT and return the login, or None if invalid."""
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "GH_TOKEN": token},
        )
        login = result.stdout.strip()
        return login if login else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _setup_github_pat(config: SandboxctlConfig) -> str | None:
    typer.echo("\n--- GitHub PAT ---")

    account = os.environ.get("USER", "sandboxctl")
    token = get_credential(config.keychain_github, account)

    if token:
        login = _validate_github_token(token)
        if login:
            typer.echo(f"  Authenticated as: {login}")
            return token
        typer.echo("  Stored token is invalid or expired.")

    token = typer.prompt("  Paste GitHub PAT", hide_input=True, default="")
    if not token:
        typer.echo("  Skipped.")
        return None

    login = _validate_github_token(token)
    if login:
        store_credential(config.keychain_github, account, token)
        typer.echo(f"  Authenticated as: {login}")
        return token

    typer.echo("  Token validation failed. Not stored.")
    return None


def _setup_gitlab_pats(config: SandboxctlConfig) -> dict[str, str | None]:
    typer.echo("\n--- GitLab PATs ---")

    gitlab_urls: set[str] = set()
    profiles = list_profiles(config)
    for profile_name in profiles:
        try:
            prof = load_profile(profile_name, config)
            for server in prof.repos:
                if "gitlab" in server.lower():
                    gitlab_urls.add(server)
        except Exception:
            continue

    if not gitlab_urls:
        typer.echo("  No GitLab servers found in profiles.")
        account = os.environ.get("USER", "sandboxctl")
        token = get_credential(config.keychain_gitlab, account)
        if token:
            typer.echo(f"  Existing token found for {config.keychain_gitlab}")
            return {"gitlab": token}
        token = typer.prompt("  Paste GitLab PAT (or Enter to skip)", hide_input=True, default="")
        if token:
            store_credential(config.keychain_gitlab, account, token)
            typer.echo("  Token stored.")
            return {"gitlab": token}
        typer.echo("  Skipped.")
        return {}

    tokens: dict[str, str | None] = {}
    account = os.environ.get("USER", "sandboxctl")

    for server in sorted(gitlab_urls):
        service = f"sandboxctl-gitlab-{server}"
        full_url = f"https://{server}"
        typer.echo(f"\n  [{server}]")

        token = get_credential(service, account)
        if token:
            try:
                subprocess.run(
                    ["curl", "-sf", "-H", f"PRIVATE-TOKEN: {token}", f"{full_url}/api/v4/user"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                typer.echo("  Authenticated (stored token valid)")
                tokens[server] = token
                continue
            except (subprocess.CalledProcessError, FileNotFoundError):
                typer.echo("  Stored token is invalid or expired.")

        token = typer.prompt(f"  Paste PAT for {server} (or Enter to skip)", hide_input=True, default="")
        if not token:
            typer.echo("  Skipped.")
            tokens[server] = None
            continue

        try:
            subprocess.run(
                ["curl", "-sf", "-H", f"PRIVATE-TOKEN: {token}", f"{full_url}/api/v4/user"],
                capture_output=True,
                text=True,
                check=True,
            )
            store_credential(service, account, token)
            typer.echo("  Token validated and stored.")
            tokens[server] = token
        except (subprocess.CalledProcessError, FileNotFoundError):
            typer.echo("  Token validation failed. Not stored.")
            tokens[server] = None

    return tokens


def _setup_providers(config: SandboxctlConfig, github_token: str | None) -> None:
    typer.echo("\n--- Providers ---")

    settings_set("providers_v2_enabled", "true")
    typer.echo("  providers_v2_enabled: true")

    if config.providers.vertex_project_id:
        provider_create(
            "vertex-claude",
            "vertex-claude",
            f"ANTHROPIC_VERTEX_PROJECT_ID={config.providers.vertex_project_id}",
        )
        typer.echo(f"  vertex-claude: configured (project: {config.providers.vertex_project_id})")

    if github_token:
        provider_delete("github")
        provider_create("github", "github", f"GITHUB_TOKEN={github_token}")
        typer.echo("  github: configured")


def run_setup(config: SandboxctlConfig) -> None:
    """Orchestrate first-run onboarding."""
    typer.echo("=" * 40)
    typer.echo("sandboxctl setup")
    typer.echo("=" * 40)

    ensure_config_dir(config)

    _check_prerequisites()
    _install_profiles(config)
    _setup_cli_tools()
    _setup_ssh_key(config)
    github_token = _setup_github_pat(config)
    _setup_gitlab_pats(config)
    _setup_providers(config, github_token)

    typer.echo("\n" + "=" * 40)
    typer.echo("Setup complete.")
    typer.echo("=" * 40)
    typer.echo("\nNext steps:")
    typer.echo("  sandboxctl list          # view profiles")
    typer.echo("  sandboxctl create -p X   # create a sandbox")
