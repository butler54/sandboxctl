#!/usr/bin/env python3
"""Apply OpenCode network-policy compatibility rules to every profile.

The script is dry-run by default. Pass ``--write`` to update policy YAML files
and retain a ``.bak`` copy of each original file. Policies using custom YAML
tags (such as ``!include``) are skipped so their source structure is never
silently flattened.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

OPENCODE_BINARIES = (
    "/usr/local/bin/opencode",
    "/usr/lib/node_modules/opencode-ai/bin/opencode.exe",
)
MATILDA_ENDPOINT = {"host": "matilda.maincode.com", "port": 443}


def _binary_path(entry: object) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        path = entry.get("path")
        return path if isinstance(path, str) else None
    return None


def _ensure_binaries(rule: dict[str, Any], binaries: tuple[str, ...]) -> bool:
    entries = rule.setdefault("binaries", [])
    if not isinstance(entries, list):
        raise ValueError("binaries must be a list")
    existing = {_binary_path(entry) for entry in entries}
    changed = False
    for binary in binaries:
        if binary not in existing:
            entries.append({"path": binary})
            changed = True
    return changed


def _endpoints(rule: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    if isinstance(rule.get("host"), str):
        endpoints.append(rule)
    nested = rule.get("endpoints")
    if isinstance(nested, list):
        endpoints.extend(endpoint for endpoint in nested if isinstance(endpoint, dict))
    return endpoints


def apply_policy(data: dict[str, Any]) -> list[str]:
    """Apply the required compatibility rules and return descriptions of changes."""
    policies = data.get("network_policies")
    if not isinstance(policies, dict):
        raise ValueError("network_policies must be a mapping")

    changes: list[str] = []
    for name, rule in policies.items():
        if not isinstance(rule, dict):
            continue
        for endpoint in _endpoints(rule):
            if endpoint.get("host") == "registry.npmjs.org" and not endpoint.get("allow_encoded_slash"):
                endpoint["allow_encoded_slash"] = True
                changes.append(f"{name}: allow encoded slashes for npm scoped packages")

        if name == "copilot" and _ensure_binaries(rule, OPENCODE_BINARIES):
            changes.append("copilot: allow OpenCode's compiled executable")

    matilda = policies.get("matilda")
    if matilda is None:
        matilda = {"name": "matilda", "endpoints": [MATILDA_ENDPOINT.copy()]}
        policies["matilda"] = matilda
        changes.append("matilda: add endpoint")
    if not isinstance(matilda, dict):
        raise ValueError("matilda policy must be a mapping")

    endpoints = _endpoints(matilda)
    if not any(endpoint.get("host") == MATILDA_ENDPOINT["host"] and endpoint.get("port") == 443 for endpoint in endpoints):
        matilda.setdefault("endpoints", []).append(MATILDA_ENDPOINT.copy())
        changes.append("matilda: add endpoint")
    if _ensure_binaries(matilda, OPENCODE_BINARIES):
        changes.append("matilda: allow OpenCode's compiled executable")
    return changes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path.home() / ".config" / "sandboxctl" / "profiles",
        help="sandboxctl profiles directory (default: %(default)s)",
    )
    parser.add_argument("--write", action="store_true", help="write changes and create .bak backups")
    return parser.parse_args()


def policy_paths(profiles_dir: Path) -> list[Path]:
    """Return supported policy files, including the local ``.yamlc`` convention."""
    return sorted(
        {
            *profiles_dir.rglob("policy*.yaml"),
            *profiles_dir.rglob("policy*.yml"),
            *profiles_dir.rglob("policy*.yamlc"),
        }
    )


def main() -> int:
    args = parse_args()
    profiles_dir = args.profiles_dir.expanduser()
    policies = policy_paths(profiles_dir)
    if not policies:
        print(f"No policy YAML files found under {profiles_dir}", file=sys.stderr)
        return 1

    changed = 0
    skipped = 0
    for path in policies:
        source = path.read_text()
        if "!include" in source:
            print(f"SKIP {path}: contains !include; update its referenced fragment manually")
            skipped += 1
            continue
        try:
            data = yaml.safe_load(source)
            if not isinstance(data, dict):
                raise ValueError("policy root must be a mapping")
            changes = apply_policy(data)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"SKIP {path}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        if not changes:
            print(f"OK   {path}")
            continue

        changed += 1
        print(f"{'APPLY' if args.write else 'WOULD'} {path}: {'; '.join(changes)}")
        if args.write:
            backup = path.with_suffix(f"{path.suffix}.bak")
            shutil.copy2(path, backup)
            path.write_text(yaml.safe_dump(data, sort_keys=False))

    print(f"Processed {len(policies)} policy file(s): {changed} changed, {skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
