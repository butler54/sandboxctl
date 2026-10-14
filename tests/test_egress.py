"""Tests for egress deny diagnostics (#206): matching, resolution, analysis, doctor wiring."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from sandboxctl.cli import app
from sandboxctl.doctor import CheckResult
from sandboxctl.egress import (
    EgressFinding,
    analyze_egress,
    any_policy_path_matches,
    egress_report,
    policy_path_matches,
    recent_denies,
    resolve_sandbox_executables,
)

runner = CliRunner()

_V2_EXE = "/usr/lib/node_modules/@opencode/cli/bin/opencode.exe"
_LEGACY_EXE = "/usr/lib/node_modules/opencode-ai/bin/opencode.exe"


# =========================================================================
# policy_path_matches
# =========================================================================


class TestPolicyPathMatches:
    def test_exact_match(self) -> None:
        assert policy_path_matches("/usr/bin/git", "/usr/bin/git") is True

    def test_exact_mismatch(self) -> None:
        assert policy_path_matches("/usr/bin/git", "/usr/bin/gitk") is False
        assert policy_path_matches("/usr/bin/git", "/usr/sbin/git") is False

    def test_star_within_segment(self) -> None:
        assert policy_path_matches("/usr/bin/gi*", "/usr/bin/git") is True
        assert policy_path_matches("/usr/bin/*", "/usr/bin/git") is True

    def test_star_does_not_cross_segments(self) -> None:
        assert policy_path_matches("/usr/bin/*", "/usr/bin/x/git") is False
        assert policy_path_matches("/usr/*/git", "/usr/bin/git") is True

    def test_double_star_zero_segments(self) -> None:
        assert policy_path_matches("/usr/lib/node_modules/@opencode/**", "/usr/lib/node_modules/@opencode") is True

    def test_double_star_one_segment(self) -> None:
        assert policy_path_matches("/usr/lib/node_modules/@opencode/**", "/usr/lib/node_modules/@opencode/cli") is True

    def test_double_star_many_segments(self) -> None:
        assert policy_path_matches("/usr/lib/node_modules/@opencode/**", _V2_EXE) is True

    def test_double_star_does_not_leak_to_sibling(self) -> None:
        # Regression guard for #206: the @opencode glob must not match
        # @opencode-ai or other sibling package roots.
        pattern = "/usr/lib/node_modules/@opencode/**"
        assert policy_path_matches(pattern, "/usr/lib/node_modules/@opencode-ai/cli") is False
        assert policy_path_matches(pattern, "/usr/lib/node_modules/@opencode-ai/cli/bin/opencode.exe") is False

    def test_double_star_mid_pattern(self) -> None:
        assert policy_path_matches("/usr/**/bin/opencode.exe", _V2_EXE) is True
        assert policy_path_matches("/usr/**/bin/opencode.exe", "/usr/bin/opencode.exe") is True

    def test_non_matching_suffix(self) -> None:
        assert policy_path_matches("/a/*/c", "/a/b/c") is True
        assert policy_path_matches("/a/*/c", "/a/b/d") is False
        assert policy_path_matches("/a/b/**", "/a/x/c") is False

    def test_shorter_and_longer_paths(self) -> None:
        assert policy_path_matches("/a/b", "/a/b/c") is False
        assert policy_path_matches("/a/b/c", "/a/b") is False


class TestAnyPolicyPathMatches:
    def test_any_matches(self) -> None:
        patterns = ["/usr/bin/git", "/usr/lib/node_modules/@opencode/**"]
        assert any_policy_path_matches(patterns, _V2_EXE) is True
        assert any_policy_path_matches(patterns, "/usr/bin/git") is True

    def test_none_match(self) -> None:
        patterns = ["/usr/bin/git", "/usr/lib/node_modules/opencode-ai/**"]
        assert any_policy_path_matches(patterns, _V2_EXE) is False

    def test_empty_patterns(self) -> None:
        assert any_policy_path_matches([], "/usr/bin/git") is False


# =========================================================================
# resolve_sandbox_executables
# =========================================================================


class TestResolveSandboxExecutables:
    def test_parses_lines_and_ignores_garbage(self) -> None:
        output = "\n".join(
            [
                f"opencode={_V2_EXE}",
                "",
                "garbage line without equals",
                "node==not-a-path",  # resolved value lacks leading slash
                "unknown-tool=/usr/bin/thing",  # not a known launcher
                "git=/usr/bin/git",
            ]
        )
        with patch("sandboxctl.egress.osh.sandbox_exec_pipe", return_value=output):
            result = resolve_sandbox_executables("mybox")
        assert result == {"opencode": _V2_EXE, "git": "/usr/bin/git"}

    def test_empty_output(self) -> None:
        with patch("sandboxctl.egress.osh.sandbox_exec_pipe", return_value=""):
            assert resolve_sandbox_executables("mybox") == {}

    def test_exec_failure_returns_empty(self) -> None:
        with patch("sandboxctl.egress.osh.sandbox_exec_pipe", side_effect=RuntimeError("boom")):
            assert resolve_sandbox_executables("mybox") == {}


# =========================================================================
# analyze_egress
# =========================================================================


class TestAnalyzeEgress:
    def test_empty_executables_is_upstream_limited(self) -> None:
        findings = analyze_egress("mybox", {}, {"network_policies": {}})
        assert len(findings) == 1
        assert findings[0].kind == "upstream-limited"
        assert findings[0].severity == "info"

    def test_v2_image_with_legacy_literal_policy(self) -> None:
        """Regression for the #204 scenario: v2 layout, legacy literal allowlist."""
        policy = {
            "network_policies": {
                "main": {
                    "binaries": [{"path": _LEGACY_EXE}],
                    "endpoints": [{"host": "example.com"}],
                }
            }
        }
        findings = analyze_egress("mybox", {"opencode": _V2_EXE}, policy)
        by_kind = {}
        for finding in findings:
            by_kind.setdefault(finding.kind, []).append(finding)
        warning = by_kind["binary-not-covered"][0]
        assert warning.severity == "warning"
        assert _V2_EXE in warning.message
        assert "default-deny" in warning.message
        stale = by_kind["allowlist-unmatched"][0]
        assert stale.severity == "info"
        assert _LEGACY_EXE in stale.message
        assert "'main'" in stale.message

    def test_glob_pattern_covers_v2_image(self) -> None:
        """The fixed policy from #204: the @opencode glob covers the v2 layout."""
        policy = {
            "network_policies": {
                "main": {
                    "binaries": [
                        {"path": "/usr/lib/node_modules/opencode-ai/**"},
                        {"path": "/usr/lib/node_modules/@opencode/**"},
                    ],
                    "endpoints": [],
                }
            }
        }
        findings = analyze_egress("mybox", {"opencode": _V2_EXE}, policy)
        assert findings == []

    def test_dict_and_string_binary_entries_both_handled(self) -> None:
        policy = {
            "network_policies": {
                "dict-rule": {"binaries": [{"path": "/usr/bin/git"}]},
                "str-rule": {"binaries": ["/usr/bin/npm"]},
            }
        }
        executables = {"git": "/usr/bin/git", "npm": "/usr/bin/npm"}
        assert analyze_egress("mybox", executables, policy) == []

    def test_glob_entries_never_flagged_unmatched(self) -> None:
        policy = {
            "network_policies": {
                "main": {
                    "binaries": [
                        "/usr/bin/git",
                        "/usr/lib/node_modules/@opencode/**",
                        "/usr/bin/some-*",
                    ]
                }
            }
        }
        findings = analyze_egress("mybox", {"git": "/usr/bin/git"}, policy)
        assert all(f.kind != "allowlist-unmatched" for f in findings)

    def test_multiple_uncovered_executables(self) -> None:
        policy = {"network_policies": {"main": {"binaries": ["/usr/bin/git"]}}}
        executables = {"git": "/usr/bin/git", "curl": "/usr/bin/curl"}
        findings = analyze_egress("mybox", executables, policy)
        warnings = [f for f in findings if f.kind == "binary-not-covered"]
        assert len(warnings) == 1
        assert "/usr/bin/curl" in warnings[0].message


# =========================================================================
# recent_denies
# =========================================================================


class TestRecentDenies:
    def _mock_run(self, help_rc: int, tail_stdout: str = "DENIED staged connection") -> MagicMock:
        def run(args: list[str], **kwargs: object) -> MagicMock:
            proc = MagicMock()
            if "--help" in args:
                proc.returncode = help_rc
                proc.stdout = "usage: openshell logs"
            else:
                proc.returncode = 0
                proc.stdout = tail_stdout
            return proc

        return MagicMock(side_effect=run)

    def test_logs_subcommand_missing_returns_none(self) -> None:
        mock_run = self._mock_run(help_rc=1)
        with patch("sandboxctl.egress.subprocess.run", mock_run):
            assert recent_denies() is None

    def test_logs_subcommand_present_returns_tail(self) -> None:
        mock_run = self._mock_run(help_rc=0, tail_stdout="DENIED staged connection x2")
        with patch("sandboxctl.egress.subprocess.run", mock_run):
            assert recent_denies() == "DENIED staged connection x2"

    def test_openshell_missing_returns_none(self) -> None:
        with patch("sandboxctl.egress.subprocess.run", side_effect=FileNotFoundError):
            assert recent_denies() is None

    def test_subprocess_timeout_returns_none(self) -> None:
        with patch("sandboxctl.egress.subprocess.run", side_effect=subprocess.TimeoutExpired("openshell", 10)):
            assert recent_denies() is None


# =========================================================================
# egress_report
# =========================================================================


class TestEgressReport:
    def test_static_findings_and_upstream_limitation(self) -> None:
        policy_json = json.dumps({"policy": {"network_policies": {"main": {"binaries": [{"path": _LEGACY_EXE}]}}}})
        with (
            patch(
                "sandboxctl.egress.resolve_sandbox_executables",
                return_value={"opencode": _V2_EXE},
            ),
            patch("sandboxctl.egress.osh.policy_get_base", return_value=policy_json),
            patch("sandboxctl.egress.recent_denies", return_value=None),
        ):
            findings = egress_report("mybox")
        kinds = [f.kind for f in findings]
        assert "binary-not-covered" in kinds
        assert "allowlist-unmatched" in kinds
        assert kinds.count("upstream-limited") == 1
        assert "observed-deny" not in kinds

    def test_observed_denies_appended_verbatim(self) -> None:
        policy_json = json.dumps({"policy": {"network_policies": {"main": {"binaries": ["/usr/bin/git"]}}}})
        tail = "t1 DENIED staged connection\nt2 DENIED staged connection"
        with (
            patch("sandboxctl.egress.resolve_sandbox_executables", return_value={"git": "/usr/bin/git"}),
            patch("sandboxctl.egress.osh.policy_get_base", return_value=policy_json),
            patch("sandboxctl.egress.recent_denies", return_value=tail),
        ):
            findings = egress_report("mybox")
        observed = [f.message for f in findings if f.kind == "observed-deny"]
        assert observed == ["t1 DENIED staged connection", "t2 DENIED staged connection"]

    def test_everything_unavailable_degrades_to_info(self) -> None:
        with (
            patch("sandboxctl.egress.resolve_sandbox_executables", return_value={}),
            patch("sandboxctl.egress.osh.policy_get_base", side_effect=RuntimeError("boom")),
            patch("sandboxctl.egress.recent_denies", side_effect=RuntimeError("boom")),
        ):
            findings = egress_report("mybox")
        assert findings
        assert all(f.severity == "info" for f in findings)
        assert all(f.kind == "upstream-limited" for f in findings)

    def test_policy_unavailable_with_executables(self) -> None:
        with (
            patch("sandboxctl.egress.resolve_sandbox_executables", return_value={"git": "/usr/bin/git"}),
            patch("sandboxctl.egress.osh.policy_get_base", return_value=""),
            patch("sandboxctl.egress.recent_denies", return_value=None),
        ):
            findings = egress_report("mybox")
        assert not any(f.kind == "binary-not-covered" for f in findings)
        assert any("active base policy" in f.message for f in findings)


# =========================================================================
# Doctor CLI wiring
# =========================================================================


class TestDoctorEgressCLI:
    def _mock_health(self) -> MagicMock:
        return MagicMock(healthy=True, details=["Gateway: running"], recovery_action="none")

    def _invoke(self, findings: list[EgressFinding]):  # noqa: ANN202
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch(
                "sandboxctl.doctor.check_host_credentials",
                return_value=[CheckResult(passed=True, name="GitHub PAT", details="ok")],
            ),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
            patch("sandboxctl.health.diagnose", return_value=self._mock_health()),
            patch("sandboxctl.egress.egress_report", return_value=findings),
        ):
            return runner.invoke(app, ["doctor", "mybox"])

    def test_doctor_prints_egress_findings(self) -> None:
        findings = [
            EgressFinding(
                "binary-not-covered",
                "warning",
                f"executable {_V2_EXE} (opencode) matches no allowlist in any network rule "
                "— all its egress is denied by the default-deny posture",
            ),
            EgressFinding(
                "allowlist-unmatched",
                "info",
                f"allowlist entry {_LEGACY_EXE} in rule 'main' matches no executable found "
                "in this sandbox (stale layout?)",
            ),
        ]
        result = self._invoke(findings)
        assert result.exit_code == 0
        assert "Egress Diagnostics" in result.output
        assert f"! mybox: executable {_V2_EXE}" in result.output
        assert f"i mybox: allowlist entry {_LEGACY_EXE}" in result.output

    def test_doctor_prints_observed_denies(self) -> None:
        findings = [
            EgressFinding("observed-deny", "info", "t1 DENIED staged connection"),
            EgressFinding("upstream-limited", "info", "could not resolve sandbox executables"),
        ]
        result = self._invoke(findings)
        assert result.exit_code == 0
        assert "observed (upstream log tail):" in result.output
        assert "t1 DENIED staged connection" in result.output

    def test_doctor_skips_egress_section_without_sandboxes(self) -> None:
        with (
            patch("sandboxctl.cli.load_config", return_value=MagicMock()),
            patch(
                "sandboxctl.doctor.check_host_credentials",
                return_value=[CheckResult(passed=True, name="GitHub PAT", details="ok")],
            ),
            patch("sandboxctl.doctor.check_profile_readiness", return_value={}),
        ):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Egress Diagnostics" not in result.output
