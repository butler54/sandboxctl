"""Egress deny diagnostics: static policy correlation and bounded observed denies.

When the upstream egress proxy denies a connection it only logs
``DENIED staged connection`` — no destination, no executable. This module
provides two bounded signals instead of guessing:

1. Static correlation (#206): correlate the sandbox's real, kernel-resolved
   executables against the active network policy's binary allowlists and
   surface mismatches as actionable findings. This is the check that would
   have caught #204 (legacy ``opencode-ai`` literal on the v2 image) in one
   command.
2. Observed denies: a tail of whatever upstream actually exposes, never
   fabricated. When the ``openshell logs`` subcommand does not exist (today),
   the gap is reported as an explicit ``upstream-limited`` finding.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
import subprocess
from collections.abc import Iterable
from typing import Any

from sandboxctl import openshell as osh
from sandboxctl.policy import _binary_path

# Launchers probed inside the sandbox to build the executable inventory. The
# kernel resolves symlinks, so the allowlist identity is readlink -f output,
# not the PATH entry (see policy.py's _OPENCODE_COMPILED_BINARIES rationale).
_LAUNCHERS = ("opencode", "npm", "node", "git", "gh", "curl", "claude")

_RESOLVE_SCRIPT = (
    "for tool in " + " ".join(_LAUNCHERS) + "; do "
    'p=$(command -v "$tool" 2>/dev/null) || continue; '
    'r=$(readlink -f "$p" 2>/dev/null) || continue; '
    '[ -n "$r" ] && printf "%s=%s\\n" "$tool" "$r"; '
    "done"
)


@dataclasses.dataclass(frozen=True)
class EgressFinding:
    """One egress diagnostic finding surfaced by doctor."""

    kind: str  # "binary-not-covered" | "allowlist-unmatched" | "rule-unreachable"
    # | "upstream-limited" | "observed-deny"
    severity: str  # "warning" | "info"
    message: str  # human-readable, includes rule name and paths


# ---------------------------------------------------------------------------
# Glob/path semantic matching
# ---------------------------------------------------------------------------


def policy_path_matches(pattern: str, path: str) -> bool:
    """Return True if a policy binary allowlist pattern matches a resolved path.

    Both pattern and path are absolute POSIX paths. Semantics:

    - ``**`` as a whole segment consumes zero or more path segments (so
      ``/pkg/**`` also matches ``/pkg`` itself).
    - ``*`` (fnmatch) applies within a single segment only.
    - Anything else must match exactly per segment — globs never leak into
      sibling directories like ``@opencode-ai``.
    """
    pattern_segments = [segment for segment in pattern.split("/") if segment]
    path_segments = [segment for segment in path.split("/") if segment]

    def walk(pattern_index: int, path_index: int) -> bool:
        while pattern_index < len(pattern_segments):
            segment = pattern_segments[pattern_index]
            if segment == "**":
                remaining = len(path_segments) - path_index
                # ** consumes 0..remaining segments; try longest/lazy recursion.
                return any(walk(pattern_index + 1, path_index + skipped) for skipped in range(remaining + 1))
            if path_index >= len(path_segments):
                return False
            if not fnmatch.fnmatchcase(path_segments[path_index], segment):
                return False
            pattern_index += 1
            path_index += 1
        return path_index == len(path_segments)

    return walk(0, 0)


def any_policy_path_matches(patterns: Iterable[str], path: str) -> bool:
    """Return True if any allowlist pattern matches the resolved path."""
    return any(policy_path_matches(pattern, path) for pattern in patterns)


# ---------------------------------------------------------------------------
# Real executable resolution (inside the sandbox)
# ---------------------------------------------------------------------------


def resolve_sandbox_executables(sandbox_name: str) -> dict[str, str]:
    """Resolve the sandbox's known launchers to kernel-resolved executable paths.

    One bounded exec: for each known launcher, ``command -v`` then
    ``readlink -f``. Never reads /proc or the environment, so no secrets leak.
    Exec failure or an unknown sandbox returns {} — callers treat that as
    "unknown", not as an error.
    """
    try:
        output = osh.sandbox_exec_pipe(sandbox_name, _RESOLVE_SCRIPT)
    except Exception:  # noqa: BLE001
        return {}
    executables: dict[str, str] = {}
    for line in output.splitlines():
        name, separator, path = line.partition("=")
        if separator and name.strip() in _LAUNCHERS and path.strip().startswith("/"):
            executables[name.strip()] = path.strip()
    return executables


# ---------------------------------------------------------------------------
# Effective-policy correlation
# ---------------------------------------------------------------------------


def _rule_allowlists(policy: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (rule_name, binary_path) pairs for every allowlist entry."""
    network_policies = policy.get("network_policies") if isinstance(policy, dict) else None
    if not isinstance(network_policies, dict):
        return []
    allowlists: list[tuple[str, str]] = []
    for rule_name, rule in network_policies.items():
        if not isinstance(rule, dict):
            continue
        binaries = rule.get("binaries")
        if not isinstance(binaries, list):
            continue
        for entry in binaries:
            path = _binary_path(entry)
            if path:
                allowlists.append((rule_name, path))
    return allowlists


def analyze_egress(
    sandbox_name: str,
    executables: dict[str, str],
    policy: dict[str, Any],
) -> list[EgressFinding]:
    """Correlate resolved executables against the policy's binary allowlists."""
    if not executables:
        return [
            EgressFinding(
                "upstream-limited",
                "info",
                "could not resolve sandbox executables; static egress check unavailable",
            )
        ]

    findings: list[EgressFinding] = []
    allowlists = _rule_allowlists(policy)
    all_patterns = [pattern for _, pattern in allowlists]

    for name, resolved in sorted(executables.items()):
        if not any_policy_path_matches(all_patterns, resolved):
            findings.append(
                EgressFinding(
                    "binary-not-covered",
                    "warning",
                    f"executable {resolved} ({name}) matches no allowlist in any network rule "
                    "— all its egress is denied by the default-deny posture",
                )
            )

    for rule_name, pattern in allowlists:
        # Glob entries stay plausible against image layouts doctor cannot
        # enumerate; only literal paths can be confirmed stale.
        if any(char in pattern for char in "*?["):
            continue
        if not any(policy_path_matches(pattern, path) for path in executables.values()):
            findings.append(
                EgressFinding(
                    "allowlist-unmatched",
                    "info",
                    f"allowlist entry {pattern} in rule '{rule_name}' matches no executable "
                    "found in this sandbox (stale layout?)",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Observed denies (bounded, never fabricated)
# ---------------------------------------------------------------------------


def recent_denies(limit: int = 20) -> str | None:
    """Return the raw ``openshell logs`` tail, or None when unavailable.

    The existence of the ``logs`` subcommand is probed first via ``--help``;
    upstream releases without it return None so callers can label the gap
    instead of fabricating deny entries. Every subprocess call is bounded
    (check=False, capture_output, timeout=10).
    """
    try:
        probe = subprocess.run(
            ["openshell", "logs", "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if probe.returncode != 0:
        return None
    try:
        result = subprocess.run(
            ["openshell", "logs", "--tail", str(limit)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


# ---------------------------------------------------------------------------
# Orchestration for doctor
# ---------------------------------------------------------------------------


def egress_report(name: str) -> list[EgressFinding]:
    """Build the full egress finding list for one sandbox; never raises."""
    findings: list[EgressFinding] = []
    try:
        executables = resolve_sandbox_executables(name)
    except Exception:  # noqa: BLE001
        executables = {}

    try:
        output = osh.policy_get_base(name)
        fetched = json.loads(output)
        policy = fetched.get("policy") if isinstance(fetched, dict) else None
    except Exception:  # noqa: BLE001
        policy = None

    if not executables:
        findings.extend(analyze_egress(name, {}, {}))
    elif policy is None:
        findings.append(
            EgressFinding(
                "upstream-limited",
                "info",
                "could not fetch the active base policy; static policy correlation unavailable",
            )
        )
    else:
        findings.extend(analyze_egress(name, executables, policy))

    try:
        tail = recent_denies()
    except Exception:  # noqa: BLE001
        tail = None
    if tail is None:
        findings.append(
            EgressFinding(
                "upstream-limited",
                "info",
                "upstream supervisor logs do not expose denied destinations (host/exe) "
                "— surface above are from static policy correlation",
            )
        )
    else:
        for line in tail.splitlines():
            if line.strip():
                findings.append(EgressFinding("observed-deny", "info", line.strip()))
    return findings
