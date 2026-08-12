"""Typed wrapper around the openshell CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path


class SandboxError(Exception):
    """Raised when an openshell command fails."""


def _run(
    args: list[str],
    check: bool = True,
    capture: bool = True,
    stdin_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        capture_output=capture,
        text=True,
        input=stdin_data,
    )


def sandbox_create(
    name: str,
    from_path: Path,
    policy: Path,
    providers: list[str],
    upload: Path,
    no_keep: bool = False,
    no_git_ignore: bool = True,
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
    cmd.extend(["--", "true"])
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        msg = f"sandbox create failed (exit {result.returncode})"
        raise SandboxError(msg)


def sandbox_exec(
    name: str,
    command: list[str],
    tty: bool = False,
) -> str:
    cmd = ["openshell", "sandbox", "exec", "-n", name]
    if tty:
        cmd.append("--tty")
    cmd.append("--")
    cmd.extend(command)
    result = _run(cmd, check=False, capture=True)
    return result.stdout


def sandbox_exec_pipe(name: str, script: str) -> str:
    cmd = ["openshell", "sandbox", "exec", "-n", name, "--", "bash"]
    result = _run(cmd, check=False, capture=True, stdin_data=script)
    return result.stdout.strip()


def sandbox_exec_interactive(name: str, command: str) -> int:
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
    result = subprocess.run(cmd, check=False)
    return result.returncode


def sandbox_delete(name: str) -> None:
    _run(["openshell", "sandbox", "delete", name], check=False, capture=False)


def sandbox_list() -> list[dict[str, str]]:
    result = _run(["openshell", "sandbox", "list"], check=False)
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


def sandbox_get(name: str) -> bool:
    result = _run(["openshell", "sandbox", "get", name], check=False, capture=True)
    return result.returncode == 0


def sandbox_connect(name: str, editor: str | None = None) -> None:
    cmd = ["openshell", "sandbox", "connect", name]
    if editor:
        cmd.extend(["--editor", editor])
    subprocess.run(cmd, check=False)


def sandbox_upload(name: str, local: Path, remote: str) -> None:
    _run(
        ["openshell", "sandbox", "upload", name, str(local), remote],
        check=True,
        capture=False,
    )


def sandbox_download(name: str, remote: str, local: Path) -> None:
    _run(
        ["openshell", "sandbox", "download", name, remote, str(local)],
        check=True,
        capture=False,
    )


def policy_set(name: str, policy_path: Path) -> None:
    _run(
        ["openshell", "policy", "set", name, "--policy", str(policy_path), "--wait"],
        check=True,
        capture=False,
    )


def gateway_status() -> dict[str, str]:
    result = _run(["openshell", "status"], check=False)
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


def provider_list() -> str:
    result = _run(["openshell", "provider", "list"], check=False)
    return result.stdout


def provider_create(
    name: str,
    provider_type: str,
    credential: str = "",
    *,
    from_gcloud_adc: bool = False,
) -> None:
    # Delete first so stale credentials are never inherited (upsert semantics).
    # No-op when the provider does not exist (check=False).
    _run(["openshell", "provider", "delete", name], check=False, capture=True)
    cmd = ["openshell", "provider", "create", "--name", name, "--type", provider_type]
    cmd += ["--from-gcloud-adc"] if from_gcloud_adc else ["--credential", credential]
    _run(
        cmd,
        check=False,
        capture=False,
    )


def provider_delete(name: str) -> None:
    _run(["openshell", "provider", "delete", name], check=False, capture=True)


def provider_profile_import(path: Path) -> None:
    _run(
        ["openshell", "provider", "profile", "import", "-f", str(path)],
        check=False,
        capture=False,
    )


def sandbox_ssh_config(name: str) -> str:
    result = _run(["openshell", "sandbox", "ssh-config", name], check=False)
    return result.stdout


def update_local_ssh_config(name: str) -> None:
    ssh_config_dir = Path.home() / ".config" / "openshell"
    ssh_config_dir.mkdir(parents=True, exist_ok=True)
    ssh_config_path = ssh_config_dir / "ssh_config"

    new_block = sandbox_ssh_config(name)
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


def settings_set(key: str, value: str) -> None:
    _run(
        ["openshell", "settings", "set", "--global", "--key", key, "--value", value, "--yes"],
        check=False,
        capture=True,
    )
