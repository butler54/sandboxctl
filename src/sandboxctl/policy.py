"""Profile policy rendering, including sandboxctl-managed YAML fragments."""

from __future__ import annotations

from pathlib import Path

import yaml

_OPENCODE_LAUNCHERS = {"/usr/local/bin/opencode", "/usr/bin/opencode"}
_OPENCODE_COMPILED_BINARY = "/usr/lib/node_modules/opencode-ai/bin/opencode.exe"


class PolicyIncludeError(ValueError):
    """A policy fragment is invalid or outside the configured profiles directory."""


def prepare_policy_for_apply(path: Path, profiles_dir: Path, target_dir: Path) -> Path:
    """Return a policy path ready for OpenShell, rendering when required."""
    root = profiles_dir.resolve()
    source_path = path.resolve()
    if not source_path.is_relative_to(root):
        raise PolicyIncludeError(f"Policy outside profiles directory: {path}")
    if not source_path.exists():
        return source_path
    source = source_path.read_text()
    if "!include" not in source and not any(launcher in source for launcher in _OPENCODE_LAUNCHERS):
        return source_path
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
        if isinstance(binaries, list) and _OPENCODE_LAUNCHERS.intersection(binaries):
            if _OPENCODE_COMPILED_BINARY not in binaries:
                binaries.append(_OPENCODE_COMPILED_BINARY)
    return yaml.safe_dump(data, sort_keys=False)
