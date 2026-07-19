---
name: sandbox-network-debug
description: Diagnose and fix OpenShell sandbox networking failures — proxy 403, TLS certs, SSRF denials, DNS, gateway issues
---

# sandbox-network-debug

Systematic diagnosis of OpenShell sandbox networking failures. Uses a decision tree to isolate the failing layer (proxy policy, TLS, SSRF, DNS, gateway, landlock) and provides targeted fixes. All diagnostic commands are non-destructive and read-only until a fix is confirmed.

## When to use

- Sandbox cannot reach a host (403, timeout, connection refused)
- TLS certificate verification failures (`server certificate verification failed`)
- SSH through the sandbox proxy fails
- After a host reboot or podman machine restart
- `sandboxctl doctor` reports infrastructure issues
- Gateway error logs show `podman.sock: No such file or directory`

## Instructions

### Step 1: Identify the sandbox and failure

Get the sandbox name and the exact error message. Key error patterns to look for:

- `403 Forbidden` → proxy policy denial (go to Step 2)
- `server certificate verification failed` → CA bundle issue (go to Step 3)
- `Connection timed out` / `Connection refused` → infrastructure (go to Step 5)
- `Permission denied` on `/opt` paths → landlock (go to Step 6)

### Step 2: Raw CONNECT test

Isolate whether the proxy allows the connection. Run from inside the sandbox:

```bash
openshell sandbox exec --name <SANDBOX> -- bash -c \
  'printf "CONNECT <HOST>:<PORT> HTTP/1.1\r\nHost: <HOST>:<PORT>\r\n\r\n" | nc -w 10 10.200.0.1 3128'
```

Read the response:

| Response | Meaning | Next step |
|----------|---------|-----------|
| `HTTP/1.1 200 Connection Established` | Proxy allows — problem is upstream | Step 3 (TLS) or destination unreachable |
| `HTTP/1.1 403 Forbidden` with JSON body | Proxy denies — read the JSON `detail` field | Step 4 |
| Connection refused to `10.200.0.1:3128` | Supervisor proxy not running | Step 5 |
| Hangs with no response | DNS resolution failure inside supervisor | Step 5 (check DNS) |

### Step 3: CA bundle check

The CA bundle at `/sandbox/.ca-bundle.pem` must contain:
1. The system CA bundle from `/etc/openshell-tls/ca-bundle.pem`
2. The OpenShell proxy CA from `/etc/openshell-tls/openshell-ca.pem`
3. Any custom CAs (e.g. Red Hat internal CAs)

The bundle is lost on every container restart. Diagnose:

```bash
openshell sandbox exec --name <SANDBOX> -- bash -c \
  'grep -c "BEGIN CERTIFICATE" /sandbox/.ca-bundle.pem; grep -c "OpenShell" /sandbox/.ca-bundle.pem'
```

If the OpenShell CA count is 0, rebuild with `sandboxctl doctor --fix <SANDBOX>`. If doctor doesn't fix it (e.g. custom CAs not in config), rebuild manually:

```bash
openshell sandbox exec --name <SANDBOX> -- bash -c \
  'cat /etc/openshell-tls/ca-bundle.pem > /sandbox/.ca-bundle.pem; cat /etc/openshell-tls/openshell-ca.pem >> /sandbox/.ca-bundle.pem'
```

Then upload custom CAs via `openshell sandbox upload` and append them.

### Step 4: Policy analysis

Read the JSON body from the 403 response. The `detail` field tells you exactly what failed:

#### 4a: `declared endpoint check failed`

The host:port is not in any policy section, or the calling binary isn't in the allowed binaries list.

**Diagnose:**
```bash
openshell policy get --full <SANDBOX> | grep -A5 "<HOST>"
```

If the host isn't found, add it to the appropriate policy section. If it is found, check the `binaries` list matches the binary making the connection.

**Fix:** Edit the policy YAML, then hot-reload:
```bash
openshell policy set --policy <POLICY_FILE> --wait <SANDBOX>
```

#### 4b: `allowed_ips check failed`

The host resolves to an IP address not covered by the `allowed_ips` ranges. This commonly happens when:
- A host resolves to a **private IP** (RFC 1918) — SSRF protection blocks private IPs by default
- A host resolves to an **IPv6 address** — and `allowed_ips` only has IPv4 CIDRs

**Diagnose:** Resolve the host from the host machine (not the sandbox):
```bash
host <HOSTNAME>
dig AAAA <HOSTNAME>
```

**Fix:** Add the resolved IP range to `allowed_ips` in the policy endpoint. For IPv6:
```yaml
allowed_ips:
  - "10.0.0.0/8"
  - "2400::/12"    # APAC IPv6 range
```

Hot-reload the policy after editing.

#### 4c: Binary not in allowed list

The proxy identifies the connecting process by its binary path. Symlinks cause issues — the supervisor may see `/usr/bin/nc.openbsd` (the real binary) not `/usr/bin/nc` (the symlink).

**Fix:** Add both the symlink and the real binary path to the policy's binaries list.

### Step 5: Infrastructure check

Check each layer from bottom up:

**Podman machine:**
```bash
CONTAINERS_MACHINE_PROVIDER=applehv podman machine list
```

**Podman socket:**
```bash
ls -la ~/.local/share/containers/podman/machine/podman.sock
# Follow the symlink — verify the target exists
```

**Gateway:**
```bash
cat /opt/homebrew/var/log/openshell/openshell-gateway.err.log
```

Common gateway error: `no compute driver configured` or `podman.sock: No such file or directory` — means `CONTAINERS_MACHINE_PROVIDER=applehv` is missing from `~/.config/openshell/gateway.env`. Add it and restart:
```bash
brew services restart openshell
```

**Container state:**
```bash
CONTAINERS_MACHINE_PROVIDER=applehv podman ps -a --format '{{.Names}} {{.Status}}' | grep openshell
```

If containers show `Exited (143)`, recover with `sandboxctl recover`.

**Supervisor logs:**
```bash
CONTAINERS_MACHINE_PROVIDER=applehv podman logs --tail 30 openshell-sandbox-<NAME>
```

Look for `netns: Failed to delete network namespace` (supervisor version bug — pin to v0.0.72) or `Cannot access container filesystem for symlink resolution` (informational — binary matching falls back to literal).

**DNS (informational):**
```bash
openshell sandbox exec --name <SANDBOX> -- nslookup github.com
```

Container DNS (`10.89.0.1`) is often broken after podman restarts. This does NOT affect proxy-routed traffic (HTTPS, SSH via ProxyCommand) because the OpenShell proxy resolves hostnames itself. Only affects container-to-container DNS.

### Step 6: Landlock / filesystem check

If the error is `Permission denied` on a path under `/opt`, `/var`, or another system directory, the path is not in the policy's `filesystem_policy.read_only` list.

**Diagnose:**
```bash
grep -A10 "read_only" <POLICY_FILE>
```

**Fix:** Add the path to `read_only`. This requires sandbox recreation — landlock policy is set at creation time and cannot be hot-reloaded.

### Step 7: Verify the fix

After applying a fix, re-run the raw CONNECT test from Step 2. For TLS fixes, test with the actual tool:

```bash
openshell sandbox exec --name <SANDBOX> -- bash -c \
  'GIT_SSL_CAINFO=/sandbox/.ca-bundle.pem git ls-remote https://github.com/<REPO>.git HEAD'
```

For SSH:
```bash
openshell sandbox exec --name <SANDBOX> -- bash -c \
  'ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no <HOST> echo "ssh works"'
```

## Important context

- **Hot-reload scope:** `openshell policy set` can add/modify network policy endpoints and binaries. It cannot change `filesystem_policy` (landlock) — that requires sandbox recreation.
- **CA bundle is ephemeral:** Lost on every container restart. `sandboxctl doctor --fix` rebuilds it, or do it manually per Step 3.
- **Proxy handles DNS:** The OpenShell proxy at `10.200.0.1:3128` resolves hostnames for all CONNECT tunnels. Broken container DNS (`10.89.0.1`) does NOT affect HTTPS or SSH-via-proxy. It only affects direct container DNS lookups (rare).
- **IPv6 SSRF:** The supervisor resolves hostnames and checks the result against `allowed_ips`. If a hostname returns an IPv6 address (common for APAC hosts), `allowed_ips` must include IPv6 CIDRs — IPv4 ranges alone will fail the check.
- **Binary symlinks:** The supervisor resolves binary paths by reading `/proc/<pid>/exe`. If it can't access the container filesystem (rootless, no `CAP_SYS_PTRACE`), it falls back to literal path matching. List both the symlink and the real binary in the policy.
- **Gateway env:** The brew-managed gateway reads `~/.config/openshell/gateway.env` on startup. `CONTAINERS_MACHINE_PROVIDER=applehv` must be set there for macOS applehv podman.
