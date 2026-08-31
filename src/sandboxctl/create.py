"""Sandbox creation: staging, build, post-launch setup, repo cloning."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import typer

from sandboxctl import mlflow_cmd
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


def _stage_selected(src: Path, dst: Path, allowlist: list[str]) -> None:
    """Copy src → dst. When allowlist is non-empty, copy only the named entries.

    Names match top-level files or directories under src (e.g. skill/agent names).
    Missing names are skipped silently — a profile may list entries not present on
    every host.
    """
    if not allowlist:
        shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True)
        return
    dst.mkdir(parents=True, exist_ok=True)
    for name in allowlist:
        entry = src / name
        if entry.is_dir():
            shutil.copytree(entry, dst / name, symlinks=False, dirs_exist_ok=True)
        elif entry.exists():
            shutil.copy2(entry, dst / name)


def stage_skills(stage_dir: Path, allowlist: list[str] | None = None) -> int:
    skills_src = Path.home() / ".claude" / "skills"
    if not skills_src.exists():
        return 0
    skills_dst = stage_dir / ".claude" / "skills"
    _stage_selected(skills_src, skills_dst, allowlist or [])
    return len(list(skills_dst.iterdir())) if skills_dst.exists() else 0


def stage_agents(stage_dir: Path, allowlist: list[str] | None = None) -> int:
    agents_src = Path.home() / ".claude" / "agents"
    if not agents_src.exists():
        return 0
    agents_dst = stage_dir / ".claude" / "agents"
    _stage_selected(agents_src, agents_dst, allowlist or [])
    return len(list(agents_dst.iterdir())) if agents_dst.exists() else 0


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


def stage_opencode_config(stage_dir: Path, config: SandboxctlConfig) -> bool:
    """Stage opencode config from host if present.

    Checks config.json, opencode.jsonc, and opencode.json (opencode reads all three).
    Vertex auth is handled purely via GOOGLE_VERTEX_PROJECT / GOOGLE_VERTEX_LOCATION env
    vars injected by post_launch_setup — no generated config file needed for that path.
    """
    opencode_config_dir = Path.home() / ".config" / "opencode"
    for filename in ("config.json", "opencode.jsonc", "opencode.json"):
        host_file = opencode_config_dir / filename
        if host_file.exists():
            dest_dir = stage_dir / ".config" / "opencode"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(host_file, dest_dir / filename)
            return True
    return False


def stage_opencode_plugins(stage_dir: Path) -> int:
    """Stage opencode plugins from host ~/.config/opencode/plugins/."""
    plugins_src = Path.home() / ".config" / "opencode" / "plugins"
    if not plugins_src.exists():
        return 0
    plugins_dst = stage_dir / ".config" / "opencode" / "plugins"
    plugins_dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugins_src, plugins_dst, symlinks=False, dirs_exist_ok=True)
    return len(list(plugins_dst.iterdir()))


def stage_opencode_agents(stage_dir: Path) -> int:
    """Stage opencode custom agents from host ~/.config/opencode/agent(s)/.

    opencode accepts either directory name (`agent` or `agents`) and does not
    auto-discover Claude's ~/.claude/agents (unlike skills), so these must be
    copied explicitly. Returns the count of staged *.md agent files.
    """
    opencode_dir = Path.home() / ".config" / "opencode"
    for dirname in ("agent", "agents"):
        agents_src = opencode_dir / dirname
        if agents_src.exists():
            agents_dst = stage_dir / ".config" / "opencode" / dirname
            agents_dst.mkdir(parents=True, exist_ok=True)
            shutil.copytree(agents_src, agents_dst, symlinks=False, dirs_exist_ok=True)
            return len(list(agents_dst.glob("*.md")))
    return 0


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

    drawio_src = config.config_dir / "drawio-libs"
    if drawio_src.exists() and any(drawio_src.iterdir()):
        drawio_dst = stage_dir / ".drawio-libs"
        drawio_dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(drawio_src, drawio_dst, dirs_exist_ok=True)
        staged.append("draw.io libraries")

    return staged


def resolve_build_context(
    profile: Profile,
    config: SandboxctlConfig,
) -> tuple[Path | str, Path | None]:
    if profile.sandbox.image:
        return profile.sandbox.image, None

    containerfile = profile.sandbox.containerfile
    profiles_dir = config.profiles_dir or config.config_dir / "profiles"

    # Detect image references used in the containerfile field (e.g. ghcr.io/org/img:tag)
    if "/" in containerfile and ":" in containerfile:
        return containerfile, None

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


def _ensure_vertex_provider_yaml(config_dir: Path) -> Path:
    """Ensure Vertex provider profile YAML exists with tls:skip on OAuth endpoints.

    This overrides OpenShell's auto-generated provider policy which includes
    oauth2.googleapis.com and accounts.google.com WITHOUT tls:skip, causing
    BadSignature errors when Google rejects the proxy certificate.
    """
    providers_dir = config_dir / "providers"
    providers_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = providers_dir / "vertex-claude.yaml"
    yaml_content = """\
id: vertex-claude
display_name: Vertex Claude
endpoints:
  - host: oauth2.googleapis.com
    port: 443
    protocol: rest
    tls: skip
    enforcement: enforce
    access: read-write
  - host: accounts.google.com
    port: 443
    protocol: rest
    tls: skip
    enforcement: enforce
    access: read-write
"""
    # Regenerate if missing or if it has an old format (missing `id:` or the
    # now-required `display_name:` field — #120).
    existing = yaml_path.read_text() if yaml_path.exists() else ""
    if "id:" not in existing or "display_name:" not in existing:
        yaml_path.write_text(yaml_content)
    return yaml_path


def setup_providers(config: SandboxctlConfig) -> list[str]:
    """Register providers with OpenShell. Returns list of provider names to attach."""
    providers = ["github"]

    if config.vertex_project_id:
        osh.settings_set("providers_v2_enabled", "true")
        # Provider type must be a real OpenShell provider profile id ("google-vertex-ai"),
        # not the provider *name* — the previous "vertex-claude" type made provider_create's
        # upsert fail silently (delete succeeds, create is rejected: "unsupported provider
        # type"), so the provider was never actually refreshed here. Project ID isn't a
        # secret and isn't part of this profile's credential schema (token-only:
        # service_account_key/service_account_token/gcloud_adc_token), so it's exported
        # directly into the sandbox's .bashrc in post_launch_setup instead.
        osh.provider_create("vertex-claude", "google-vertex-ai", from_gcloud_adc=True)
        providers.append("vertex-claude")

        # Ensure provider profile YAML exists with tls:skip on OAuth endpoints (fixes #69)
        yaml_path = _ensure_vertex_provider_yaml(config.config_dir)
        osh.provider_profile_import(yaml_path)
    else:
        api_key = get_credential(config.keychain_github, "anthropic-api-key") or ""
        if api_key:
            osh.provider_create("anthropic-direct", "anthropic", f"ANTHROPIC_API_KEY={api_key}")
            providers.append("anthropic-direct")

    return providers


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

    from sandboxctl.context import restore_claude_context

    if restore_claude_context(name, config):
        typer.echo("  Claude context: restored from backup")

    # Always build CA bundle — OpenShell proxy CA is needed for tls:terminate endpoints
    osh.sandbox_exec_pipe(
        name,
        "cat /etc/openshell-tls/ca-bundle.pem > /sandbox/.ca-bundle.pem 2>/dev/null; "
        "cat /etc/openshell-tls/openshell-ca.pem >> /sandbox/.ca-bundle.pem 2>/dev/null; "
        'echo "CA bundle: OpenShell CAs"',
    )
    # Append custom CAs from config
    ca_sources: list[Path] = []
    if config.ca_bundle and config.ca_bundle.exists():
        ca_sources.append(config.ca_bundle)
    ca_sources.extend(p for p in config.ca_paths if p.exists())
    if ca_sources:
        combined = "\n".join(p.read_text() for p in ca_sources)
        encoded_ca = base64.b64encode(combined.encode()).decode()
        osh.sandbox_exec_pipe(
            name,
            f"echo {encoded_ca} | base64 -d >> /sandbox/.ca-bundle.pem; "
            f'echo "CA bundle: +{len(ca_sources)} custom CA(s)"',
        )
    osh.sandbox_exec_pipe(
        name,
        "grep -q GIT_SSL_CAINFO /sandbox/.bashrc 2>/dev/null || "
        'echo "export GIT_SSL_CAINFO=/sandbox/.ca-bundle.pem\n'
        "export SSL_CERT_FILE=/sandbox/.ca-bundle.pem\n"
        "export CURL_CA_BUNDLE=/sandbox/.ca-bundle.pem\n"
        "export REQUESTS_CA_BUNDLE=/sandbox/.ca-bundle.pem\n"
        'export GH_SSL_CAINFO=/sandbox/.ca-bundle.pem" >> /sandbox/.bashrc; '
        'echo "CA env vars: configured"',
    )

    if config.vertex_project_id:
        vertex_region = config.vertex_region
        vertex_project_id = config.vertex_project_id
        osh.sandbox_exec_pipe(
            name,
            "grep -q CLAUDE_CODE_USE_VERTEX /sandbox/.bashrc 2>/dev/null || "
            'echo "export CLAUDE_CODE_USE_VERTEX=1\n'
            f"export CLOUD_ML_REGION={vertex_region}\n"
            f"export ANTHROPIC_VERTEX_PROJECT_ID={vertex_project_id}\n"
            # OpenCode reads GOOGLE_VERTEX_PROJECT / GOOGLE_VERTEX_LOCATION to
            # auto-detect the google-vertex-anthropic provider — no config file needed.
            f"export GOOGLE_VERTEX_PROJECT={vertex_project_id}\n"
            f'export GOOGLE_VERTEX_LOCATION={vertex_region}"'
            " >> /sandbox/.bashrc; "
            'echo "Vertex AI env: configured"',
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

    # Git identity injection (#80) — inject from [identity] config when set
    if config.git_user_name:
        osh.sandbox_exec_pipe(
            name,
            f'git config --global user.name "{config.git_user_name}" && '
            f'git config --global user.email "{config.git_user_email}" && '
            "git config --global gpg.format ssh && "
            "git config --global commit.gpgsign true && "
            "git config --global user.signingkey /sandbox/.ssh/id_ed25519 && "
            'echo "Git identity: configured"',
        )

    gitlab_token = get_credential(config.keychain_gitlab, os.environ.get("USER", "sandboxctl"))
    if gitlab_token:
        encoded_token = base64.b64encode(gitlab_token.encode()).decode()
        osh.sandbox_exec_pipe(
            name,
            "grep -q GITLAB_TOKEN /sandbox/.bashrc 2>/dev/null || "
            "{ printf 'export GITLAB_TOKEN=' >> /sandbox/.bashrc && "
            f"echo {encoded_token} | base64 -d >> /sandbox/.bashrc && "
            "echo >> /sandbox/.bashrc; }; "
            'echo "GitLab token: configured"',
        )
        gitlab_servers = list(profile.credentials.gitlab_servers)
        if not gitlab_servers:
            gitlab_servers = [s for s in profile.repos if s != "github"]
        for server in gitlab_servers:
            _validate_repo_ref(server)
            osh.sandbox_exec_pipe(
                name,
                f"git config --global credential.https://{server}.helper "
                '\'!f() { echo "username=oauth2"; echo "password=$GITLAB_TOKEN"; }; f\' && '
                f'echo "  GitLab git ({server}): configured"',
            )

    # MLflow tracking server integration (MLFLOW-05: validate-then-start + fail-closed URI injection)
    if profile.mlflow:
        if config.mlflow.managed:
            # Managed mode: health-check localhost, (re)start if down, fail if still down
            tracking_uri_check = f"http://localhost:{config.mlflow.port}"
            if not mlflow_cmd.check_mlflow_health(tracking_uri_check):
                typer.echo("MLflow tracking server is down, attempting to start...")
                mlflow_cmd.start_mlflow_container(config.mlflow.data_dir, config.mlflow.port)
                # Re-check after start attempt
                if not mlflow_cmd.check_mlflow_health(tracking_uri_check):
                    msg = (
                        f"MLflow tracking server is not responding at {tracking_uri_check} "
                        "after start attempt. Create aborted (fail-closed)."
                    )
                    raise RuntimeError(msg)
            # Inject gateway IP URI (not localhost — 10.200.0.1 is the host gateway reachable from sandbox)
            injected_uri = f"http://10.200.0.1:{config.mlflow.port}"
        else:
            # External mode (D-12): health-check user URI, fail if unreachable, inject user URI
            if not mlflow_cmd.check_mlflow_health(config.mlflow.tracking_uri):
                msg = f"External MLflow server ({config.mlflow.tracking_uri}) is not reachable. Create aborted."
                raise RuntimeError(msg)
            injected_uri = config.mlflow.tracking_uri

        # Idempotent bashrc injection (D-08)
        osh.sandbox_exec_pipe(
            name,
            "grep -q MLFLOW_TRACKING_URI /sandbox/.bashrc 2>/dev/null || "
            f'echo "export MLFLOW_TRACKING_URI={injected_uri}" >> /sandbox/.bashrc; '
            'echo "MLflow tracking: configured"',
        )

        # TRACE-01/02: Inject experiment name and enable tracing (idempotent append, per D-04/D-02)
        osh.sandbox_exec_pipe(
            name,
            "grep -q MLFLOW_EXPERIMENT_NAME /sandbox/.bashrc 2>/dev/null || "
            f'echo "export MLFLOW_EXPERIMENT_NAME=sandbox/{name}" >> /sandbox/.bashrc; '
            "grep -q MLFLOW_CLAUDE_TRACING_ENABLED /sandbox/.bashrc 2>/dev/null || "
            'echo "export MLFLOW_CLAUDE_TRACING_ENABLED=true" >> /sandbox/.bashrc; '
            'echo "MLflow tracing: env vars configured"',
        )

        # TRACE-01: Install Claude Code tracing plugin (fail-closed per D-07).
        # Source .bashrc so CA env vars (GIT_SSL_CAINFO, SSL_CERT_FILE, etc.) are active
        # for the git sparse-clone that `claude plugin marketplace add` performs.
        # Redirect stderr to stdout so failures are captured and visible in the error message.
        result = osh.sandbox_exec_pipe(
            name,
            "source /sandbox/.bashrc 2>/dev/null; "
            "claude plugin marketplace add mlflow/mlflow --sparse .claude-plugin 2>&1 && "
            "claude plugin install mlflow-tracing@mlflow-plugins 2>&1 && "
            'echo "MLflow tracing: plugin installed"',
        )
        if "plugin installed" not in result:
            raise RuntimeError(
                f"MLflow Claude Code tracing plugin install failed. Create aborted (fail-closed).\n{result}"
            )

    # Stage gcloud ADC for Vertex AI
    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if adc_path.exists():
        osh.sandbox_exec_pipe(name, "mkdir -p /sandbox/.config/gcloud")
        osh.sandbox_upload(name, adc_path, "/sandbox/.config/gcloud/application_default_credentials.json")
        typer.echo("  gcloud ADC: staged")

    # Stage GWS credentials
    gws_client_secret = Path.home() / ".config" / "gws" / "client_secret.json"
    if shutil.which("gws") and gws_client_secret.exists():
        osh.sandbox_exec_pipe(name, "mkdir -p /sandbox/.config/gws")
        osh.sandbox_upload(name, gws_client_secret, "/sandbox/.config/gws/client_secret.json")
        try:
            export_result = subprocess.run(
                ["gws", "auth", "export", "--unmasked"],
                capture_output=True,
                text=True,
                check=True,
            )
            if export_result.stdout.strip():
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                    f.write(export_result.stdout)
                    creds_tmp = Path(f.name)
                try:
                    osh.sandbox_upload(name, creds_tmp, "/sandbox/.config/gws/credentials.json")
                finally:
                    creds_tmp.unlink(missing_ok=True)
                typer.echo("  GWS credentials: staged (live export)")
            else:
                typer.echo("  GWS credentials: client_secret only (export empty)")
        except (subprocess.CalledProcessError, FileNotFoundError):
            typer.echo("  GWS credentials: client_secret only (auth export failed)")
        osh.sandbox_exec_pipe(
            name,
            "grep -q GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND /sandbox/.bashrc 2>/dev/null || "
            'echo "export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file" >> /sandbox/.bashrc; '
            'echo "  GWS keyring backend: configured"',
        )

    # Stage MCP OAuth credentials
    mcp_servers = list(profile.credentials.mcp.servers)
    if mcp_servers:
        from sandboxctl.mcp_credentials import stage_mcp_credentials

        staged = stage_mcp_credentials(name, mcp_servers)
        if staged:
            typer.echo(f"  MCP OAuth: staged ({', '.join(staged)})")
        else:
            typer.echo("  MCP OAuth: no credentials found in host keychain")

    # GSD runtime — opt-in via profile.gsd.enabled (#111)
    if profile.gsd.enabled:
        gsd_check = osh.sandbox_exec_pipe(name, "test -d /sandbox/.claude/gsd-core && echo 'present' || echo 'missing'")
        if "present" in gsd_check:
            typer.echo("  GSD runtime: present")
        else:
            typer.echo("  GSD runtime: installing...")
            osh.sandbox_exec_pipe(
                name,
                "npx -y @opengsd/gsd-core@latest --claude --global 2>&1 | tail -1",
            )

        if profile.gsd.model_profile:
            import json

            defaults = json.dumps({"model_profile": profile.gsd.model_profile})
            osh.sandbox_exec_pipe(
                name,
                f"mkdir -p /sandbox/.gsd && printf '%s' '{defaults}' > /sandbox/.gsd/defaults.json && "
                f'echo "GSD model profile: {profile.gsd.model_profile}"',
            )


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

    # Remote-SSH settings for reconnection (VSCODE-05)
    settings["remote.SSH.connectTimeout"] = 120
    settings["remote.SSH.useLocalServer"] = False

    # Extension recommendations: full declared list (remote + local per D-06)
    extensions = {"recommendations": list(profile.extensions.extensions_list)}

    workspace = json.dumps({"folders": folders, "settings": settings, "extensions": extensions})
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
        skill_count = stage_skills(stage_dir, profile.skills)
        if skill_count:
            typer.echo(f"  Skills: {skill_count} (symlinks dereferenced)")

        agent_count = stage_agents(stage_dir, profile.agents)
        if agent_count:
            typer.echo(f"  Agents: {agent_count} (symlinks dereferenced)")

        stage_claude_settings(stage_dir, profile, config)
        typer.echo(f"  Claude settings: staged (model: {model})")

        stage_claude_state(stage_dir)
        typer.echo("  Claude state: staged (skip onboarding)")

        if stage_opencode_config(stage_dir, config):
            typer.echo("  OpenCode config: staged")
        n_oc_plugins = stage_opencode_plugins(stage_dir)
        if n_oc_plugins:
            typer.echo(f"  OpenCode plugins: {n_oc_plugins} staged")
        n_oc_agents = stage_opencode_agents(stage_dir)
        if n_oc_agents:
            typer.echo(f"  OpenCode agents: {n_oc_agents} staged")

        creds = stage_credentials(stage_dir, config)
        for c in creds:
            typer.echo(f"  {c}: staged")

        build_from, cleanup_dir = resolve_build_context(profile, config)
        policy_path = (config.profiles_dir or config.config_dir / "profiles") / profile.name / profile.sandbox.policy

        providers = setup_providers(config)
        typer.echo(f"  Providers: {', '.join(providers)}")

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

    osh.update_local_ssh_config(name)
    typer.echo("  SSH config: updated")

    if policy_path.exists():
        osh.policy_set(name, policy_path)
        typer.echo("  Policy re-applied (TLS directives active)")

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
