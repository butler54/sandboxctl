"""Typed wrapper around the openshell CLI."""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class SandboxError(Exception):
    """Raised when an openshell command fails."""


@dataclass(frozen=True)
class ExecOutcome:
    """Result of a non-interactive sandbox execution (004 FR-001/FR-002).

    Carries the exit code the legacy stdout-only helpers discarded.
    """

    exit_code: int
    stdout: str
    stderr: str


def _dispatch[T](sdk_op: Callable[[], T], cli_op: Callable[[], T]) -> T:
    """Run an operation on the SDK backend, falling back to the CLI.

    004 (research.md R-3): fallback applies ONLY at client acquisition —
    import or construction failure routes the operation to the CLI. Once an
    operation dispatches to a backend, failures raise SandboxError and are
    never retried on the other backend: an exec that failed mid-flight may
    have already run server-side.
    """
    from sandboxctl import openshell_sdk as sdk

    if sdk.sdk_enabled():
        try:
            return sdk_op()
        except sdk.SdkUnavailable:
            pass
    return cli_op()


# ---------------------------------------------------------------------------
# Gateway routing (005): resolution + CLI env injection — single points.
# ---------------------------------------------------------------------------


def _target_gateway(name: str, gateway: str | None) -> str | None:
    """Resolve the openshell gateway name for a sandbox operation (005).

    An explicit ``gateway`` (already an openshell name, resolved by the
    caller via the gateways seam) wins; otherwise the sandbox's recorded
    association resolves through the seam; no association = None (the
    CLI-active gateway, FR-001). A recorded-but-unconfigured key raises
    loudly (FR-008) — never a silent redirect to the active gateway.
    """
    if gateway is not None:
        return gateway
    from sandboxctl import gateways

    try:
        from sandboxctl.config import load_config

        config = load_config()
    except Exception:  # noqa: BLE001 — config unloadable = no gateway knowledge
        return None
    return gateways.resolve_gateway_for_sandbox(name, config)


def _cli_env(gateway: str | None) -> dict[str, str] | None:
    """Subprocess env for CLI calls targeting a non-active gateway (R-1).

    None (inherit the environment untouched) when the target is the active
    gateway or unspecified — byte-identical invocations (FR-011). This is
    the single OPENSHELL_GATEWAY injection point (seam audit, FR-010).
    """
    if gateway is None:
        return None
    from sandboxctl import gateways

    if gateway == gateways.active_gateway_name():
        return None
    return {**os.environ, "OPENSHELL_GATEWAY": gateway}


def _run_checked_status(
    args: list[str],
    action: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a read-only OpenShell command and retain meaningful failure details."""
    try:
        result = _run(args, check=False, env=env)
    except FileNotFoundError as exc:
        raise SandboxError("openshell executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"{action} timed out") from exc
    except OSError as exc:
        raise SandboxError(f"{action} could not start: {exc}") from exc

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        message = f"{action} failed (exit {result.returncode})"
        if details:
            message = f"{message}: {details}"
        raise SandboxError(message)
    if result.stderr.strip():
        raise SandboxError(f"{action} reported an error: {result.stderr.strip()}")
    return result


def _run(
    args: list[str],
    check: bool = True,
    capture: bool = True,
    stdin_data: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        text=True,
        input=stdin_data,
        env=env,
    )


def sandbox_create(
    name: str,
    from_path: Path,
    policy: Path,
    providers: list[str],
    upload: Path,
    no_keep: bool = False,
    no_git_ignore: bool = True,
    *,
    gateway: str | None = None,
) -> None:
    cmd = [
        "openshell",
        "sandbox",
        "create",
        "--name",
        name,
        "--from",
        str(from_path),
        "--policy",
        str(policy),
    ]
    for p in providers:
        cmd.extend(["--provider", p])
    cmd.extend(["--upload", f"{upload}:/sandbox"])
    if no_keep:
        cmd.append("--no-keep")
    if no_git_ignore:
        cmd.append("--no-git-ignore")
    # OpenShell 0.1 rejects --upload combined with a trailing command because
    # the upload completes after the canonical process starts. Detach starts
    # that process without attaching a command and leaves the sandbox ready for
    # post-launch setup.
    cmd.append("--detach")
    result = subprocess.run(cmd, check=False, capture_output=True, text=True, env=_cli_env(gateway))
    if result.returncode != 0:
        msg = f"sandbox create failed (exit {result.returncode})"
        details = result.stderr.strip() or result.stdout.strip()
        if details:
            msg = f"{msg}: {details}"
        raise SandboxError(msg)


def sandbox_exec(
    name: str,
    command: list[str],
    tty: bool = False,
    *,
    gateway: str | None = None,
) -> str:
    return _exec_outcome(name, command, None, tty=tty, gateway=gateway).stdout


def sandbox_exec_pipe(name: str, script: str, *, gateway: str | None = None) -> str:
    return _exec_outcome(name, ["bash"], script, gateway=gateway).stdout.strip()


def sandbox_exec_pipe_result(name: str, script: str, *, gateway: str | None = None) -> ExecOutcome:
    """Like ``sandbox_exec_pipe`` but returns exit code and stderr too.

    Raw (unstripped) streams; use for sites that must detect failures the
    stdout-only helper silently discards (004 FR-002).
    """
    return _exec_outcome(name, ["bash"], script, gateway=gateway)


def _exec_outcome(
    name: str,
    command: list[str],
    stdin_data: str | None,
    tty: bool = False,
    gateway: str | None = None,
) -> ExecOutcome:
    """Execute a command in a sandbox on the SDK backend (CLI fallback)."""
    gw = _target_gateway(name, gateway)

    def sdk_op() -> ExecOutcome:
        from sandboxctl import openshell_sdk as sdk

        stdin = stdin_data.encode() if stdin_data is not None else None
        result = sdk.exec_command(name, command, stdin=stdin, gateway=gw)
        return ExecOutcome(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def cli_op() -> ExecOutcome:
        cmd = ["openshell", "sandbox", "exec", "-n", name]
        if tty:
            cmd.append("--tty")
        cmd.append("--")
        cmd.extend(command)
        result = _run(cmd, check=False, capture=True, stdin_data=stdin_data, env=_cli_env(gw))
        return ExecOutcome(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return _dispatch(sdk_op, cli_op)


def sandbox_exec_interactive(name: str, command: str, *, gateway: str | None = None) -> int:
    cmd = [
        "openshell",
        "sandbox",
        "exec",
        "-n",
        name,
        "--tty",
        "--",
        "bash",
        "-lc",
        command,
    ]
    result = subprocess.run(cmd, check=False, env=_cli_env(_target_gateway(name, gateway)))
    return result.returncode


def sandbox_delete(name: str, *, gateway: str | None = None) -> None:
    gw = _target_gateway(name, gateway)

    def sdk_op() -> None:
        from sandboxctl import openshell_sdk as sdk

        sdk.delete_sandbox(name, gateway=gw)

    def cli_op() -> None:
        _run(
            ["openshell", "sandbox", "delete", name],
            check=False,
            capture=False,
            env=_cli_env(gw),
        )

    _dispatch(sdk_op, cli_op)


def sandbox_wait_deleted(name: str, timeout_seconds: float = 60.0, *, gateway: str | None = None) -> None:
    """Block until a sandbox is gone (restart re-creates after this)."""
    gw = _target_gateway(name, gateway)

    def sdk_op() -> None:
        from sandboxctl import openshell_sdk as sdk

        sdk.wait_deleted(name, timeout_seconds=timeout_seconds, gateway=gw)

    def cli_op() -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            result = _run(
                ["openshell", "sandbox", "get", name],
                check=False,
                capture=True,
                env=_cli_env(gw),
            )
            if result.returncode != 0:
                return
            time.sleep(1.0)
        raise SandboxError(f"wait for deletion of sandbox '{name}' failed: timed out after {timeout_seconds:.0f}s")

    _dispatch(sdk_op, cli_op)


def sandbox_list(gateway: str | None = None) -> list[dict[str, str]]:
    """List sandboxes on a gateway (``gateway`` is an openshell gateway name;
    None = the active gateway — today's behavior)."""
    result = _run_checked_status(["openshell", "sandbox", "list"], "sandbox list", env=_cli_env(gateway))
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    sandboxes: list[dict[str, str]] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 3:
            sandboxes.append(
                {
                    "name": parts[0],
                    "created": f"{parts[1]} {parts[2]}",
                    "phase": parts[3] if len(parts) > 3 else "Unknown",
                }
            )
    return sandboxes


def sandbox_get(name: str, *, gateway: str | None = None) -> bool:
    result = _run(
        ["openshell", "sandbox", "get", name],
        check=False,
        capture=True,
        env=_cli_env(_target_gateway(name, gateway)),
    )
    return result.returncode == 0


def sandbox_connect(name: str, editor: str | None = None, *, gateway: str | None = None) -> None:
    cmd = ["openshell", "sandbox", "connect", name]
    if editor:
        cmd.extend(["--editor", editor])
    subprocess.run(cmd, check=False, env=_cli_env(_target_gateway(name, gateway)))


def sandbox_upload(name: str, local: Path, remote: str, *, gateway: str | None = None) -> None:
    _run(
        ["openshell", "sandbox", "upload", name, str(local), remote],
        check=True,
        capture=False,
        env=_cli_env(_target_gateway(name, gateway)),
    )


def sandbox_download(name: str, remote: str, local: Path, *, gateway: str | None = None) -> None:
    _run(
        ["openshell", "sandbox", "download", name, remote, str(local)],
        check=True,
        capture=False,
        env=_cli_env(_target_gateway(name, gateway)),
    )


def policy_set(name: str, policy_path: Path, *, gateway: str | None = None) -> None:
    _run(
        ["openshell", "policy", "set", name, "--policy", str(policy_path), "--wait"],
        check=True,
        capture=False,
        env=_cli_env(_target_gateway(name, gateway)),
    )


def policy_get_base(name: str, *, gateway: str | None = None) -> str:
    """Return the active, non-provider-composed policy as JSON."""
    result = _run(
        ["openshell", "policy", "get", name, "--base", "--output", "json"],
        check=False,
        capture=True,
        env=_cli_env(_target_gateway(name, gateway)),
    )
    return result.stdout if result.returncode == 0 else ""


def gateway_status(gateway: str | None = None) -> dict[str, str]:
    """Gateway status (``gateway`` is an openshell gateway name; None = active)."""
    result = _run_checked_status(["openshell", "status"], "gateway status", env=_cli_env(gateway))
    info: dict[str, str] = {}
    for line in result.stdout.split("\n"):
        line = line.strip()
        if "Gateway:" in line:
            info["gateway"] = line.split(":")[-1].strip()
        elif "Server:" in line:
            info["server"] = line.split("Server:")[-1].strip()
        elif "Status:" in line:
            info["status"] = "Connected" if "Connected" in line else "Disconnected"
        elif "Version:" in line:
            info["version"] = line.split(":")[-1].strip()
    return info


def provider_list(gateway: str | None = None) -> str:
    result = _run(["openshell", "provider", "list"], check=False, env=_cli_env(gateway))
    return result.stdout


def provider_create(
    name: str,
    provider_type: str,
    credential: str = "",
    *,
    from_gcloud_adc: bool = False,
    gateway: str | None = None,
) -> None:
    env = _cli_env(gateway)
    # Delete first so stale credentials are never inherited (upsert semantics).
    # No-op when the provider does not exist (check=False).
    _run(["openshell", "provider", "delete", name], check=False, capture=True, env=env)
    cmd = ["openshell", "provider", "create", "--name", name, "--type", provider_type]
    cmd += ["--from-gcloud-adc"] if from_gcloud_adc else ["--credential", credential]
    # Capture output so we can suppress the benign "already exists" case (#121):
    # the preceding delete can no-op when the provider is still attached to a running
    # sandbox, leaving the create to report an already-exists error. That's harmless —
    # the existing provider is reused — so it should not surface as a raw error. Any
    # other failure is surfaced to the user.
    result = _run(cmd, check=False, capture=True, env=env)
    if result.returncode != 0:
        combined = f"{result.stdout}\n{result.stderr}"
        if "already exists" in combined:
            return
        details = combined.strip()
        message = f"provider create failed for '{name}'"
        if details:
            message = f"{message}: {details}"
        raise SandboxError(message)


def provider_delete(name: str, *, gateway: str | None = None) -> None:
    _run(
        ["openshell", "provider", "delete", name],
        check=False,
        capture=True,
        env=_cli_env(gateway),
    )


def provider_profile_import(path: Path, profile_id: str, *, gateway: str | None = None) -> None:
    """Import or update a sandboxctl-managed platform provider profile."""
    env = _cli_env(gateway)
    import_cmd = ["openshell", "provider", "profile", "import", "-f", str(path), "--global"]
    result = _run(import_cmd, check=False, capture=True, env=env)
    if result.returncode == 0:
        return

    combined = f"{result.stdout}\n{result.stderr}"
    if "already exists" in combined:
        export_cmd = [
            "openshell",
            "provider",
            "profile",
            "export",
            "--global",
            "--output",
            "yaml",
            profile_id,
        ]
        exported = _run(export_cmd, check=False, capture=True, env=env)
        if exported.returncode != 0:
            details = exported.stderr.strip() or exported.stdout.strip()
            message = f"provider profile '{profile_id}' could not be exported for update"
            if details:
                message = f"{message}: {details}"
            raise SandboxError(message)

        version_match = re.search(r"^resource_version:\s*(\d+)\s*$", exported.stdout, re.MULTILINE)
        if version_match is None or int(version_match.group(1)) == 0:
            raise SandboxError(f"provider profile '{profile_id}' export did not include a resource_version")

        profile_text = path.read_text()
        resource_version = f"resource_version: {version_match.group(1)}"
        if re.search(r"^resource_version:\s*\d+\s*$", profile_text, re.MULTILINE):
            profile_text = re.sub(
                r"^resource_version:\s*\d+\s*$",
                resource_version,
                profile_text,
                flags=re.MULTILINE,
            )
        else:
            profile_text = re.sub(r"^(id:.*\n)", rf"\1{resource_version}\n", profile_text, count=1)
        path.write_text(profile_text)

        update_cmd = [
            "openshell",
            "provider",
            "profile",
            "update",
            "--file",
            str(path),
            "--global",
            profile_id,
        ]
        result = _run(update_cmd, check=False, capture=True, env=env)
        if result.returncode == 0:
            return
        combined = f"{result.stdout}\n{result.stderr}"

    details = combined.strip()
    message = f"provider profile '{profile_id}' could not be installed"
    if details:
        message = f"{message}: {details}"
    raise SandboxError(message)


def sandbox_ssh_config(name: str, *, gateway: str | None = None) -> str:
    result = _run(
        ["openshell", "sandbox", "ssh-config", name],
        check=False,
        env=_cli_env(_target_gateway(name, gateway)),
    )
    return result.stdout


def update_local_ssh_config(name: str, *, gateway: str | None = None) -> None:
    ssh_config_dir = Path.home() / ".config" / "openshell"
    ssh_config_dir.mkdir(parents=True, exist_ok=True)
    ssh_config_path = ssh_config_dir / "ssh_config"

    new_block = sandbox_ssh_config(name, gateway=gateway)
    if not new_block.strip():
        return

    existing = ssh_config_path.read_text() if ssh_config_path.exists() else ""
    if f"openshell-{name}" in existing:
        return

    with ssh_config_path.open("a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(new_block)


def ensure_ssh_keepalive() -> None:
    """Write SSH keepalive directives for VS Code Remote-SSH resilience.

    Creates an idempotent 'Host openshell-*' block in ~/.config/openshell/ssh_config
    with keepalive settings to survive network blips (VSCODE-04 layer 1).

    Settings:
    - ServerAliveInterval 60: Send keepalive every 60s to prevent NAT timeout
    - ServerAliveCountMax 3: Disconnect after 3 missed probes (180s total)
    - TCPKeepAlive yes: OS-level keepalive as additional layer
    - ConnectTimeout 10: Reasonable timeout for initial connection

    Idempotency: Re-running does NOT duplicate the block (substring guard).
    """
    ssh_config_dir = Path.home() / ".config" / "openshell"
    ssh_config_dir.mkdir(parents=True, exist_ok=True)
    ssh_config_path = ssh_config_dir / "ssh_config"

    keepalive_block = """Host openshell-*
  ServerAliveInterval 60
  ServerAliveCountMax 3
  TCPKeepAlive yes
  ConnectTimeout 10
"""

    existing = ssh_config_path.read_text() if ssh_config_path.exists() else ""

    # Idempotency guard: only append if marker not present
    if "Host openshell-*" in existing:
        return

    with ssh_config_path.open("a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(keepalive_block)


def settings_set(key: str, value: str, *, gateway: str | None = None) -> None:
    _run(
        ["openshell", "settings", "set", "--global", "--key", key, "--value", value, "--yes"],
        check=False,
        capture=True,
        env=_cli_env(gateway),
    )
