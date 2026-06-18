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
    credential: str,
) -> None:
    _run(
        [
            "openshell",
            "provider",
            "create",
            "--name",
            name,
            "--type",
            provider_type,
            "--credential",
            credential,
        ],
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


def settings_set(key: str, value: str) -> None:
    _run(
        ["openshell", "settings", "set", "--global", "--key", key, "--value", value, "--yes"],
        check=False,
        capture=True,
    )
