"""Profile policy rendering, including sandboxctl-managed YAML fragments."""

from __future__ import annotations

from pathlib import Path

import yaml

_OPENCODE_LAUNCHERS = {"/usr/local/bin/opencode", "/usr/bin/opencode"}
_OPENCODE_COMPILED_BINARY = "/usr/lib/node_modules/opencode-ai/bin/opencode.exe"


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
        if _OPENCODE_LAUNCHERS.intersection(paths) and _OPENCODE_COMPILED_BINARY not in paths:
            binaries.append({"path": _OPENCODE_COMPILED_BINARY})
    return yaml.safe_dump(data, sort_keys=False)
