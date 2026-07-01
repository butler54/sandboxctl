"""Sandbox creation: staging, build, post-launch setup, repo cloning."""

from __future__ import annotations

import base64
import json
import re
import shutil
import tempfile
from pathlib import Path

import typer

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig
from sandboxctl.credentials import get_credential
from sandboxctl.models import ClaudePermissions, ClaudeSettings, ClaudeState, Profile

_REPO_RE = re.compile(r"^[a-zA-Z0-9._/-]+$")


def _validate_repo_ref(value: str) -> str:
    """Validate a server or repo reference for safe shell interpolation."""
    if not _REPO_RE.match(value):
        msg = f"Invalid repo reference: {value}"
        raise ValueError(msg)
    return value


def stage_skills(stage_dir: Path) -> int:
    skills_src = Path.home() / ".claude" / "skills"
    if not skills_src.exists():
        return 0
    skills_dst = stage_dir / ".claude" / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skills_src, skills_dst, symlinks=False, dirs_exist_ok=True)
    return len(list(skills_dst.iterdir()))


def stage_claude_settings(stage_dir: Path, profile: Profile, config: SandboxctlConfig) -> None:
    claude_dir = stage_dir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    model = profile.sandbox.model or config.default_model
    theme = profile.workspace.theme or config.default_theme
    settings = ClaudeSettings(
        permissions=ClaudePermissions(),
        theme=theme,
        model=model,
    )
    (claude_dir / "settings.json").write_text(json.dumps(settings.model_dump(), indent=2) + "\n")


def stage_claude_state(stage_dir: Path) -> None:
    state = ClaudeState()
    (stage_dir / ".claude.json").write_text(json.dumps(state.model_dump(), indent=2) + "\n")


def stage_credentials(stage_dir: Path, config: SandboxctlConfig) -> list[str]:
    staged: list[str] = []

    if config.ssh_key.exists():
        ssh_dst = stage_dir / ".ssh"
        ssh_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config.ssh_key, ssh_dst / "id_ed25519")
        (ssh_dst / "id_ed25519").chmod(0o600)
        pub = config.ssh_key.with_suffix(".pub")
        if pub.exists():
            shutil.copy2(pub, ssh_dst / "id_ed25519.pub")
        staged.append("SSH key")

    ssh_config = Path.home() / ".ssh" / "config"
    if ssh_config.exists():
        ssh_dst = stage_dir / ".ssh"
        ssh_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ssh_config, ssh_dst / "config")
        staged.append("SSH config")

    return staged


def resolve_build_context(
    profile: Profile,
    config: SandboxctlConfig,
) -> tuple[Path | str, Path | None]:
    if profile.sandbox.image:
        return profile.sandbox.image, None

    containerfile = profile.sandbox.containerfile
    profiles_dir = config.profiles_dir or config.config_dir / "profiles"

    if containerfile == "Containerfile":
        default_path = profiles_dir / profile.name / "Containerfile"
        if default_path.exists():
            return default_path.parent, None
        msg = f"Containerfile not found: {default_path}"
        raise FileNotFoundError(msg)

    custom_path = profiles_dir / profile.name / containerfile
    if not custom_path.exists():
        msg = f"Containerfile not found: {custom_path}"
        raise FileNotFoundError(msg)

    build_ctx = Path(tempfile.mkdtemp())
    profile_dir = profiles_dir / profile.name
    for item in profile_dir.iterdir():
        dst = build_ctx / item.name
        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)
    dockerfile = build_ctx / "Dockerfile"
    dockerfile.unlink(missing_ok=True)
    dockerfile.symlink_to(containerfile)
    return build_ctx, build_ctx


def generate_provider_yaml(config: SandboxctlConfig, tmp_dir: Path) -> Path:
    if config.vertex_project_id:
        content = (
            "name: vertex-claude\n"
            "type: vertex\n"
            "credentials:\n"
            "  CLAUDE_CODE_USE_VERTEX: '1'\n"
            f"  CLOUD_ML_REGION: '{config.providers.vertex_region}'\n"
            f"  ANTHROPIC_VERTEX_PROJECT_ID: '{config.vertex_project_id}'\n"
        )
    else:
        api_key = get_credential(config.keychain_github, "anthropic-api-key") or ""
        content = f"name: anthropic-direct\ntype: anthropic\ncredentials:\n  ANTHROPIC_API_KEY: '{api_key}'\n"
    path = tmp_dir / "provider.yaml"
    path.write_text(content)
    return path


def post_launch_setup(
    name: str,
    profile: Profile,
    config: SandboxctlConfig,
) -> None:
    typer.echo("Placing uploaded files...")
    osh.sandbox_exec_pipe(
        name,
        "SRC=$(ls -d /sandbox/sandbox 2>/dev/null); "
        'if [ -d "$SRC" ]; then cp -r "$SRC/." /sandbox/ && rm -rf "$SRC" '
        '&& echo "done"; else echo "no staging dir found"; fi',
    )

    osh.sandbox_exec_pipe(name, "chmod 600 /sandbox/.ssh/id_ed25519 2>/dev/null; echo ok")

    if config.ca_bundle and config.ca_bundle.exists():
        ca_data = config.ca_bundle.read_text()
        encoded_ca = base64.b64encode(ca_data.encode()).decode()
        osh.sandbox_exec_pipe(
            name,
            "cat /etc/openshell-tls/ca-bundle.pem > /sandbox/.ca-bundle.pem 2>/dev/null; "
            "cat /etc/openshell-tls/openshell-ca.pem >> /sandbox/.ca-bundle.pem 2>/dev/null; "
            f"echo {encoded_ca} | base64 -d >> /sandbox/.ca-bundle.pem; "
            'echo "CA bundle: injected"',
        )
        osh.sandbox_exec_pipe(
            name,
            'echo "export GIT_SSL_CAINFO=/sandbox/.ca-bundle.pem\n'
            "export SSL_CERT_FILE=/sandbox/.ca-bundle.pem\n"
            "export CURL_CA_BUNDLE=/sandbox/.ca-bundle.pem\n"
            'export REQUESTS_CA_BUNDLE=/sandbox/.ca-bundle.pem" >> /sandbox/.bashrc; '
            'echo "CA env vars: configured"',
        )

    if profile.ssh:
        typer.echo("Configuring SSH proxy hosts...")
        ssh_lines: list[str] = []
        for host, cfg in profile.ssh.items():
            proxy_target = cfg.proxy_host or host
            ssh_lines.append(f"\nHost {host}")
            ssh_lines.append(f"  User {cfg.user}")
            ssh_lines.append(f"  ProxyCommand nc -X connect -x 10.200.0.1:3128 {proxy_target} %p")
            ssh_lines.append("  StrictHostKeyChecking no")
        ssh_block = "\n".join(ssh_lines)
        encoded_ssh = base64.b64encode(ssh_block.encode()).decode()
        osh.sandbox_exec_pipe(
            name,
            f"echo {encoded_ssh} | base64 -d >> /sandbox/.ssh/config; "
            f'echo "  SSH hosts: {len(profile.ssh)} configured"',
        )

    osh.sandbox_exec_pipe(
        name,
        'gh auth setup-git 2>/dev/null && echo "GitHub git: configured"',
    )

    gitlab_token = get_credential(config.keychain_gitlab, "gitlab")
    if gitlab_token:
        osh.sandbox_exec_pipe(
            name,
            "git config --global credential.helper "
            '\'!f() { echo "username=oauth2"; echo "password=$GITLAB_TOKEN"; }; f\' && '
            'echo "GitLab git: configured"',
        )

    # Stage gcloud ADC for Vertex AI
    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if adc_path.exists():
        osh.sandbox_exec_pipe(name, "mkdir -p /sandbox/.config/gcloud")
        osh.sandbox_upload(name, adc_path, "/sandbox/.config/gcloud/application_default_credentials.json")
        typer.echo("  gcloud ADC: staged")

    # Stage GWS credentials
    gws_client_secret = Path.home() / ".config" / "gws" / "client_secret.json"
    gws_creds = Path.home() / ".config" / "gws" / "credentials.json"
    if gws_client_secret.exists():
        osh.sandbox_exec_pipe(name, "mkdir -p /sandbox/.config/gws")
        osh.sandbox_upload(name, gws_client_secret, "/sandbox/.config/gws/client_secret.json")
        if gws_creds.exists():
            osh.sandbox_upload(name, gws_creds, "/sandbox/.config/gws/credentials.json")
        typer.echo("  GWS credentials: staged")

    # Set GWS keyring backend for container environment
    if gws_client_secret.exists():
        osh.sandbox_exec_pipe(
            name,
            "grep -q GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND /sandbox/.bashrc 2>/dev/null || "
            'echo "export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file" >> /sandbox/.bashrc; '
            'echo "  GWS keyring backend: configured"',
        )

    # Verify GSD runtime
    gsd_check = osh.sandbox_exec_pipe(name, "test -d /sandbox/.claude/gsd-core && echo 'present' || echo 'missing'")
    if "present" in gsd_check:
        typer.echo("  GSD runtime: present")
    else:
        typer.echo("  GSD runtime: not found (install with: npx -y @opengsd/gsd-core@latest --claude --global)")


def clone_repos(name: str, profile: Profile) -> list[str]:
    if not profile.repos:
        return []

    typer.echo("\nCloning repos...")
    osh.sandbox_exec_pipe(name, "mkdir -p /sandbox/workspace")

    repo_names: list[str] = []
    for server, repos in profile.repos.items():
        for repo in repos:
            repo_name = repo.rsplit("/", 1)[-1]
            repo_names.append(repo_name)
            typer.echo(f"  [{server}] {repo}...")

            if server == "github":
                osh.sandbox_exec(
                    name,
                    ["gh", "repo", "clone", repo, f"/sandbox/workspace/{repo_name}"],
                )
            else:
                _validate_repo_ref(server)
                _validate_repo_ref(repo)
                osh.sandbox_exec_pipe(
                    name,
                    "source /sandbox/.bashrc && "
                    "GIT_SSL_CAINFO=/sandbox/.ca-bundle.pem "
                    f'git clone "https://{server}/{repo}.git" '
                    f'"/sandbox/workspace/{repo_name}" 2>&1',
                )
    return repo_names


def generate_workspace(
    name: str,
    sandbox_name: str,
    profile: Profile,
    repo_names: list[str],
) -> None:
    if not repo_names:
        return

    workspace_path = f"/sandbox/workspace/{sandbox_name}.code-workspace"
    typer.echo(f"\nGenerating workspace: {workspace_path}")
    folders = [{"name": n, "path": n} for n in repo_names]
    settings: dict[str, object] = {}
    if profile.workspace.theme:
        settings["workbench.colorTheme"] = profile.workspace.theme
    if profile.workspace.zoom != -1:
        settings["window.zoomLevel"] = profile.workspace.zoom

    workspace = json.dumps({"folders": folders, "settings": settings})
    encoded_ws = base64.b64encode(workspace.encode()).decode()
    osh.sandbox_exec_pipe(
        name,
        f"echo {encoded_ws} | base64 -d > {workspace_path}",
    )
    typer.echo(f"  Workspace: {len(repo_names)} folders")


def create_sandbox(
    profile: Profile,
    config: SandboxctlConfig,
    sandbox_name: str | None = None,
    ephemeral: bool = False,
    open_editor: bool = True,
) -> str:
    name = sandbox_name or profile.name

    model = profile.sandbox.model or config.default_model
    typer.echo(f"{'=' * 40}")
    typer.echo(f"Creating sandbox: {name}")
    typer.echo(f"Profile: {profile.name}")
    typer.echo(f"Model: {model}")
    typer.echo(f"{'=' * 40}\n")

    with tempfile.TemporaryDirectory() as stage_root:
        stage_dir = Path(stage_root) / "sandbox"
        stage_dir.mkdir()

        typer.echo("Staging upload contents...")
        skill_count = stage_skills(stage_dir)
        if skill_count:
            typer.echo(f"  Skills: {skill_count} (symlinks dereferenced)")

        stage_claude_settings(stage_dir, profile, config)
        typer.echo(f"  Claude settings: staged (model: {model})")

        stage_claude_state(stage_dir)
        typer.echo("  Claude state: staged (skip onboarding)")

        creds = stage_credentials(stage_dir, config)
        for c in creds:
            typer.echo(f"  {c}: staged")

        build_from, cleanup_dir = resolve_build_context(profile, config)
        policy_path = (config.profiles_dir or config.config_dir / "profiles") / profile.name / profile.sandbox.policy

        provider_yaml = generate_provider_yaml(config, Path(stage_root))
        osh.provider_profile_import(provider_yaml)
        typer.echo("  Provider profile: imported")

        providers = ["github"]
        if config.vertex_project_id:
            providers.append("vertex-claude")
        else:
            providers.append("anthropic-direct")

        typer.echo("\nCreating sandbox...")
        try:
            osh.sandbox_create(
                name=name,
                from_path=build_from,
                policy=policy_path,
                providers=providers,
                upload=stage_dir,
                no_keep=ephemeral,
            )
        finally:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)

    typer.echo(f"\nSandbox '{name}' created.")

    post_launch_setup(name, profile, config)
    repo_names = clone_repos(name, profile)
    generate_workspace(name, name, profile, repo_names)

    typer.echo(f"\n{'=' * 40}")
    typer.echo(f"Sandbox ready: {name}")
    typer.echo(f"{'=' * 40}\n")
    typer.echo(f"Connect:  sandboxctl open {name}")
    typer.echo(f"Shell:    sandboxctl open {name} --shell")
    typer.echo(f"Delete:   sandboxctl delete {name}")

    if open_editor:
        from sandboxctl.open_cmd import open_sandbox

        open_sandbox(name, config)

    return name
