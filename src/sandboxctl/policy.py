"""Profile policy rendering, drift detection, and sandbox policy lifecycle."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

from sandboxctl import openshell as osh
from sandboxctl.config import SandboxctlConfig
from sandboxctl.profile import list_profiles, load_profile

_OPENCODE_LAUNCHERS = {"/usr/local/bin/opencode", "/usr/bin/opencode"}
# The opencode launcher spawns a compiled binary inside its npm package
# directory and requires_binary_identity matches the kernel exec path, not the
# launcher. The package layout differs per image generation (opencode-ai on the
# 0.x image, the scoped @opencode/cli on the v2 image — #142, #204), and the
# binary sit inside each package root, so allowlist each known package root as a
# glob instead of pinning a per-layout executable path.
_OPENCODE_COMPILED_BINARIES = (
    "/usr/lib/node_modules/opencode-ai/**",
    "/usr/lib/node_modules/@opencode/**",
)
# Public superset of OpenCode's launcher and compiled-binary paths, for use by
# sandboxctl-managed OpenShell resources (see provider_profiles.py).
OPENCODE_POLICY_BINARIES = sorted(_OPENCODE_LAUNCHERS | set(_OPENCODE_COMPILED_BINARIES))
_NPM_LAUNCHERS = {"/usr/local/bin/npm", "/usr/bin/npm"}
_NPM_CLI = "/usr/lib/node_modules/npm/bin/npm-cli.js"
_CLAUDE_LAUNCHER = "/usr/local/bin/claude"


class PolicyIncludeError(ValueError):
    """A policy fragment is invalid or outside the configured profiles directory."""


def _binary_path(entry: object) -> str | None:
    """Return a binary path from OpenShell's canonical object or a legacy string."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        path = entry.get("path")
        return path if isinstance(path, str) else None
    return None


def _normalize_endpoint_compatibility(endpoint: object) -> None:
    """Apply OpenShell 0.1 compatibility defaults to one policy endpoint."""
    if not isinstance(endpoint, dict):
        return
    # OpenShell 0.1 makes automatic TLS termination the implicit default and
    # rejects the legacy explicit value. Keep tls:skip and future values intact.
    if endpoint.get("tls") == "terminate":
        endpoint.pop("tls")
    # OpenShell 0.1 rejects a provider attachment when credentials can reach a
    # legacy L4-only endpoint unless that weaker boundary is explicitly
    # acknowledged. Existing sandboxctl profiles expressed L4 endpoints by
    # omitting protocol, so preserve their behavior with the required opt-in.
    if "host" in endpoint and "protocol" not in endpoint and "allow_uninspected_credentials" not in endpoint:
        endpoint["allow_uninspected_credentials"] = True
    # npm encodes the slash in scoped package names (for example,
    # @mlflow%2Fopencode). OpenShell otherwise rejects these metadata requests
    # at L7, causing OpenCode package resolution to retry during boot.
    if endpoint.get("host") == "registry.npmjs.org":
        endpoint.setdefault("allow_encoded_slash", True)


def prepare_policy_for_apply(path: Path, profiles_dir: Path, target_dir: Path) -> Path:
    """Return a policy path ready for OpenShell, rendering when required."""
    root = profiles_dir.resolve()
    source_path = path.resolve()
    if not source_path.is_relative_to(root):
        raise PolicyIncludeError(f"Policy outside profiles directory: {path}")
    if not source_path.exists():
        return source_path
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "policy.yaml"
    target.write_text(render_policy(source_path, profiles_dir))
    return target


def render_policy(path: Path, profiles_dir: Path) -> str:
    """Render a policy, resolving ``!include`` paths relative to each YAML file.

    Included files must remain under ``profiles_dir`` so a profile cannot cause
    sandboxctl to read arbitrary host files into the policy sent to OpenShell.
    """
    root = profiles_dir.resolve()
    active_includes: set[Path] = set()

    def load(source: Path) -> object:
        resolved = source.resolve()
        if not resolved.is_relative_to(root):
            raise PolicyIncludeError(f"Policy include outside profiles directory: {source}")
        if resolved in active_includes:
            raise PolicyIncludeError(f"Recursive policy include: {source}")
        if len(active_includes) >= 16:
            raise PolicyIncludeError("Policy include depth exceeds 16 files")
        active_includes.add(resolved)

        class Loader(yaml.SafeLoader):
            pass

        def include(loader: Loader, node: yaml.ScalarNode) -> object:
            relative = loader.construct_scalar(node)
            include_path = (resolved.parent / relative).resolve()
            if include_path.suffix not in {".yaml", ".yml"}:
                raise PolicyIncludeError(f"Policy include must be a YAML file: {relative}")
            return load(include_path)

        Loader.add_constructor("!include", include)
        try:
            # Loader subclasses SafeLoader and only adds the scalar !include tag.
            return yaml.load(resolved.read_text(), Loader=Loader)  # noqa: S506
        except yaml.YAMLError as exc:
            raise PolicyIncludeError(f"Invalid policy YAML: {source}") from exc
        finally:
            active_includes.remove(resolved)

    data = load(path)
    if not isinstance(data, dict):
        raise PolicyIncludeError(f"Policy root must be a mapping: {path}")
    network_policies = data.get("network_policies", {})
    if not isinstance(network_policies, dict):
        raise PolicyIncludeError("network_policies must be a mapping")
    for policy in network_policies.values():
        if not isinstance(policy, dict):
            continue
        _normalize_endpoint_compatibility(policy)
        endpoints = policy.get("endpoints")
        if isinstance(endpoints, list):
            for endpoint in endpoints:
                _normalize_endpoint_compatibility(endpoint)
        binaries = policy.get("binaries")
        if binaries is None and "binaries" not in policy:
            continue
        if not isinstance(binaries, list):
            raise PolicyIncludeError("Policy binaries must be a list")
        # OpenShell's schema requires binary objects. Normalize legacy scalar
        # entries before rendering so a policy is never emitted with mixed types.
        normalized: list[object] = []
        for entry in binaries:
            path = _binary_path(entry)
            if not path or not path.strip():
                raise PolicyIncludeError("Policy binary entries must have a non-empty path")
            normalized.append({"path": path} if isinstance(entry, str) else entry)
        binaries = normalized
        policy["binaries"] = binaries
        paths = {path for entry in binaries if (path := _binary_path(entry)) is not None}
        if _OPENCODE_LAUNCHERS.intersection(paths):
            for compiled in _OPENCODE_COMPILED_BINARIES:
                if compiled not in paths:
                    binaries.append({"path": compiled})
        # npm's launcher is a script, so OpenShell identifies direct npm
        # connections as npm-cli.js and Claude-managed plugin installs as the
        # Claude launcher. Preserve the user's explicit npm allowlist while
        # permitting only those canonical executables.
        if _NPM_LAUNCHERS.intersection(paths):
            if _NPM_CLI not in paths:
                binaries.append({"path": _NPM_CLI})
            if _CLAUDE_LAUNCHER not in paths:
                binaries.append({"path": _CLAUDE_LAUNCHER})
    return yaml.safe_dump(data, sort_keys=False)


# ---------------------------------------------------------------------------
# Result dataclasses (shared with doctor.py)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CheckResult:
    """Outcome of a single host-side check."""

    passed: bool
    name: str
    details: str
    fix_hint: str | None = None


@dataclasses.dataclass
class FixResult:
    """Outcome of a fix applied to a running sandbox."""

    success: bool
    name: str
    details: str


@dataclasses.dataclass(frozen=True)
class PolicyDriftState:
    """Snapshot of how a sandbox's active policy compares to its profile."""

    status: str  # "current" | "network-drift" | "filesystem-drift" | "unknown" | "no-profile"
    details: str
    rendered: str | None = None  # rendered desired policy YAML when computable
    hot_reloadable: bool = False


# ---------------------------------------------------------------------------
# Sandbox → profile association store
# ---------------------------------------------------------------------------


def _associations_path(config: SandboxctlConfig) -> Path:
    return config.config_dir / "sandboxes.json"


def _load_associations(config: SandboxctlConfig) -> dict[str, dict[str, str]]:
    """Read the association store; a corrupt or missing file reads as empty."""
    try:
        data = json.loads(_associations_path(config).read_text())
    except (OSError, ValueError, TypeError):
        return {}
    sandboxes = data.get("sandboxes") if isinstance(data, dict) else None
    return sandboxes if isinstance(sandboxes, dict) else {}


def _store_associations(config: SandboxctlConfig, sandboxes: dict[str, dict[str, str]]) -> None:
    """Write the association store atomically via a temp file and os.replace."""
    path = _associations_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".sandboxes-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump({"sandboxes": sandboxes}, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def record_policy_association(config: SandboxctlConfig, sandbox_name: str, profile_name: str) -> None:
    """Persist which profile a sandbox was created from."""
    sandboxes = _load_associations(config)
    sandboxes[sandbox_name] = {"profile": profile_name}
    _store_associations(config, sandboxes)


def lookup_policy_association(config: SandboxctlConfig, sandbox_name: str) -> str | None:
    """Return the profile recorded for a sandbox, or None."""
    entry = _load_associations(config).get(sandbox_name)
    if not isinstance(entry, dict):
        return None
    profile = entry.get("profile")
    return profile if isinstance(profile, str) and profile else None


def remove_policy_association(config: SandboxctlConfig, sandbox_name: str) -> None:
    """Drop a sandbox's association (e.g. after deletion)."""
    sandboxes = _load_associations(config)
    if sandbox_name in sandboxes:
        del sandboxes[sandbox_name]
        _store_associations(config, sandboxes)


def resolve_policy_profile(sandbox_name: str, config: SandboxctlConfig) -> str | None:
    """Resolve the profile a sandbox's policy is compared against."""
    association = lookup_policy_association(config, sandbox_name)
    if association:
        return association
    if sandbox_name in list_profiles(config):
        return sandbox_name
    return None


# ---------------------------------------------------------------------------
# Drift detection and reconciliation
# ---------------------------------------------------------------------------

_FILESYSTEM_POLICY_KEYS = ("filesystem", "filesystem_policy", "landlock")


def policy_drift_state(sandbox_name: str, profile_name: str, config: SandboxctlConfig) -> PolicyDriftState:
    """Compare a sandbox's active base policy to the rendered profile policy."""
    try:
        profile = load_profile(profile_name, config)
    except Exception as exc:  # noqa: BLE001
        return PolicyDriftState("unknown", f"could not load profile '{profile_name}': {exc}")

    path = config.profiles_dir / profile.name / profile.sandbox.policy
    if not path.exists():
        return PolicyDriftState("unknown", f"profile policy not found: {path}")
    try:
        rendered = render_policy(path, config.profiles_dir)
        desired = yaml.safe_load(rendered) or {}
    except PolicyIncludeError as exc:
        return PolicyDriftState("unknown", str(exc))

    output = osh.policy_get_base(sandbox_name)
    try:
        active = json.loads(output)["policy"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return PolicyDriftState("unknown", "could not retrieve the active base policy")

    network_drift = active.get("network_policies", {}) != desired.get("network_policies", {})
    filesystem_drift = any(active.get(key) != desired.get(key) for key in _FILESYSTEM_POLICY_KEYS)
    if not network_drift and not filesystem_drift:
        return PolicyDriftState(
            "current",
            "active network policy matches profile",
            rendered,
        )
    if filesystem_drift:
        return PolicyDriftState(
            "filesystem-drift",
            f"filesystem policy differs from profile; recreation required — run 'sandboxctl restart {sandbox_name}'",
            rendered,
        )
    return PolicyDriftState(
        "network-drift",
        "active network policy differs from profile; run 'sandboxctl policy sync "
        f"{sandbox_name}' or 'sandboxctl restart {sandbox_name}'",
        rendered,
        hot_reloadable=True,
    )


def sandbox_policy_drift_state(sandbox_name: str, config: SandboxctlConfig) -> PolicyDriftState:
    """Resolve the sandbox's profile and compute its drift state."""
    profile_name = resolve_policy_profile(sandbox_name, config)
    if profile_name is None:
        return PolicyDriftState("no-profile", "skipped (no profile with the sandbox name)")
    return policy_drift_state(sandbox_name, profile_name, config)


def summarize_network_drift(active: dict, desired: dict) -> str:
    """Compact added/removed/changed summary of network_policies rule names."""
    active_rules = active.get("network_policies", {}) if isinstance(active, dict) else {}
    desired_rules = desired.get("network_policies", {}) if isinstance(desired, dict) else {}
    added = sorted(set(desired_rules) - set(active_rules))
    removed = sorted(set(active_rules) - set(desired_rules))
    shared = set(active_rules) & set(desired_rules)
    changed = sorted(name for name in shared if active_rules[name] != desired_rules[name])
    parts = []
    if added:
        parts.append(f"added: {', '.join(added)}")
    if removed:
        parts.append(f"removed: {', '.join(removed)}")
    if changed:
        parts.append(f"changed: {', '.join(changed)}")
    return "; ".join(parts) or "rule contents differ"


def check_policy_drift(sandbox_name: str, config: SandboxctlConfig) -> CheckResult:
    """Compare the resolved profile's desired network policy to the active base policy."""
    state = sandbox_policy_drift_state(sandbox_name, config)
    if state.status == "no-profile":
        return CheckResult(True, "Policy drift", state.details)
    return CheckResult(state.status == "current", "Policy drift", state.details)


def fix_policy_drift(sandbox_name: str, config: SandboxctlConfig) -> FixResult:
    """Hot-reload network-only policy drift; filesystem drift requires recreation."""
    state = sandbox_policy_drift_state(sandbox_name, config)
    if state.status in ("no-profile", "current"):
        return FixResult(True, "Policy drift", "no reload needed")
    if state.status != "network-drift" or not state.rendered:
        return FixResult(False, "Policy drift", state.details)

    profile_name = resolve_policy_profile(sandbox_name, config) or sandbox_name
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.yaml"
            path.write_text(state.rendered)
            osh.policy_set(sandbox_name, path)
    except (OSError, subprocess.CalledProcessError):
        return FixResult(False, "Policy drift", "policy reload failed")

    verified = policy_drift_state(sandbox_name, profile_name, config)
    if verified.status != "current":
        return FixResult(False, "Policy drift", "policy reload verification failed")
    return FixResult(True, "Policy drift", "network policy reloaded")
