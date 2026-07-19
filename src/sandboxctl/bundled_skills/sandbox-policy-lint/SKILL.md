---
name: sandbox-policy-lint
description: Lint OpenShell sandbox network policies for TLS, duplicate host, and binary coverage issues before sandbox creation
---

# sandbox-policy-lint

Analyse OpenShell sandbox policy YAML files for misconfigurations that cause runtime failures. Run locally against policy files — never inside a sandbox. Sandbox recreation is destructive and expensive (IO storms kill the podman VM), so catching policy issues before creation is critical.

## When to use

- Before creating or recreating a sandbox
- When asked to review, check, or lint a sandbox policy
- After editing any `policy*.yaml` file
- When a sandbox has TLS/auth/connectivity failures

## Instructions

### Step 1: Identify policy files

Find all policy YAML files in the openshell directory:

```bash
find . -name 'policy*.yaml' -not -path './.venv/*'
```

### Step 2: Read the known-hosts reference

Read `skills/sandbox-policy-lint/references/known-hosts.yaml` to get the list of hosts requiring `tls: skip` and binary requirements for SSH/git endpoints.

### Step 3: Run checks on each policy file

For each policy file, parse the YAML `network_policies` section and run these checks:

#### Check 1: Duplicate hosts across sections (SEVERITY: ERROR)

Build a map of `host:port` → list of policy sections. Flag any host:port that appears in multiple sections with **different TLS settings**. This causes the first-match to win, potentially without `tls: skip`, while the author intended the other section's setting.

**What went wrong:** `oauth2.googleapis.com` appeared in `claude_code` (no tls:skip) and `google_workspace` (tls:skip). The first match won, breaking GWS auth with BadSignature errors. Fix was to extract shared Google auth endpoints into a dedicated `google_auth` section.

#### Check 2: Missing tls:skip on known hosts (SEVERITY: ERROR)

Cross-reference every endpoint against the `tls_skip_required` list in `known-hosts.yaml`. Flag any match that lacks `tls: skip`.

**What went wrong:** Google Workspace API calls failed with "invalid peer certificate: BadSignature" because the OpenShell proxy terminated TLS and re-encrypted with its own CA. GWS CLI, npm, and gcloud all reject the proxy certificate. GitLab internal also failed because its Red Hat CA wasn't in the proxy's trust store.

#### Check 3: SSH endpoints missing nc binaries (SEVERITY: WARN)

For any endpoint with `port: 22`, check that the binaries list includes `nc` and `nc.openbsd`. Without these, SSH proxy routing through `ProxyCommand nc -X connect -x 10.200.0.1:3128` fails.

**What went wrong:** SSH access to `user-jump.int.apac-tech-lab.net` was added without nc binaries. Aligned later by comparing with the working tanky SSH policy.

#### Check 4: Git HTTPS endpoints missing git-remote-http (SEVERITY: WARN)

For any endpoint on port 443 with git-related binaries (`/usr/bin/git`), check that `/usr/lib/git-core/git-remote-http` is also in the binaries list.

#### Check 5: Port 80 exposure (SEVERITY: INFO)

For any endpoint on port 443, flag if the same host has no port 80 entry. Some tools (curl without explicit https://) may hit port 80 and get denied.

**What went wrong:** `curl` hit `gitlab.cee.redhat.com:80` (HTTP) and was denied. The policy only allowed port 443.

#### Check 6: OpenShell CA dependency (SEVERITY: INFO)

For any endpoint using `tls: terminate` or no TLS setting (default=terminate), note that the sandbox CA bundle must include the OpenShell proxy CA. Cross-reference with the `create.py` CA bundle logic.

**What went wrong:** `create.py` built the CA bundle from `/etc/openshell-tls/ca-bundle.pem` but didn't append `/etc/openshell-tls/openshell-ca.pem`. Git push to GitHub (which uses `tls: terminate`) failed with certificate verification errors.

### Step 4: Output results

Present findings as a table grouped by policy file:

```
## policy-docs.yaml

| # | Severity | Check | Section | Host | Issue | Fix |
|---|----------|-------|---------|------|-------|-----|
| 1 | ERROR | dup-host | claude_code, google_workspace | oauth2.googleapis.com | Different TLS settings across sections | Move to shared google_auth section |
| 2 | ERROR | tls-skip | npm_registry | registry.npmjs.org | Missing tls:skip | Add tls: skip |
| 3 | WARN | ssh-nc | apac_jump | user-jump.int.apac-tech-lab.net:22 | Missing nc binaries | Add /usr/bin/nc, /usr/bin/nc.openbsd |

No issues: policy.yaml, policy-fw.yaml
```

If no issues found, report the policy as clean.

### Step 5: Suggest fixes

For each ERROR finding, provide the exact YAML edit needed. For duplicate hosts, suggest extracting into a shared section. For missing `tls: skip`, show the corrected endpoint line.

## Important context

- OpenShell hot-reloads policies via `openshell policy set <name> --policy <file> --wait`, but this **adds** new sections — it cannot remove creation-time policies. Duplicate hosts from creation persist even after hot reload.
- Sandbox recreation is expensive: it triggers container image builds/pulls that write gigabytes through the podman VM's virtio-blk device, often exceeding macOS's disk-write watchdog limit and killing the VM.
- Always fix policy files **before** sandbox creation. Hot-reload is a band-aid, not a fix for structural issues.
