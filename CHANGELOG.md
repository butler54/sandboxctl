# CHANGELOG

<!-- version list -->

## v1.8.2 (2026-07-19)

### Bug Fixes

- **15-01**: Write backup/restore tarballs to /sandbox/ instead of /tmp/
  ([`ccfa842`](https://github.com/butler54/sandboxctl/commit/ccfa842c712206f4ef0d44e8d9bb9fb0b900404d))


## v1.8.1 (2026-07-09)

### Bug Fixes

- Recover command container name prefix, podman env, and Linux support
  ([`ce45f36`](https://github.com/butler54/sandboxctl/commit/ce45f36cba73c181e81984d8561cae313fbc244d))


## v1.8.0 (2026-07-08)

### Code Style

- Fix ruff format in context.py
  ([`db607c5`](https://github.com/butler54/sandboxctl/commit/db607c5c06342d6cda4683e4543ff93f41887766))

### Features

- Resolve open issues #46-#50
  ([`e12d1a8`](https://github.com/butler54/sandboxctl/commit/e12d1a87361137d6ec1ee050b44993bf6ed89a73))


## v1.7.1 (2026-07-04)

### Bug Fixes

- Use openshell- prefix for SSH health check and update SSH config on create
  ([`0e28a97`](https://github.com/butler54/sandboxctl/commit/0e28a97879b3545863afc39aed2b38d041f78888))

### Code Style

- Fix line length in test_openshell.py
  ([`ebef1a5`](https://github.com/butler54/sandboxctl/commit/ebef1a5c9e40a6778599a9a6f5bd90bd278ba17e))


## v1.7.0 (2026-07-04)

### Chores

- Bump github/codeql-action/upload-sarif from 4.36.2 to 4.36.3
  ([`8c8226b`](https://github.com/butler54/sandboxctl/commit/8c8226b69f7b2014bb069f5fe81f067fd791b1f4))

### Features

- Add .claude-mem to backup paths and make extra paths configurable
  ([`68a19be`](https://github.com/butler54/sandboxctl/commit/68a19be5be84f71afea76a376c9f1100b52174e9))


## v1.6.0 (2026-07-03)

### Features

- Stage agents, backup rotation, and /opt in default policy
  ([`310e285`](https://github.com/butler54/sandboxctl/commit/310e2858e25386262c6dcd6b61b42718f430d428))


## v1.5.0 (2026-07-02)

### Bug Fixes

- Stage GWS OAuth credentials via live export during sandbox creation
  ([`0a8ba3b`](https://github.com/butler54/sandboxctl/commit/0a8ba3b7712724e87336af4a7d27107d9aab1ecf))

### Features

- Claude context backup and restore across sandbox lifecycle
  ([`0bb87e4`](https://github.com/butler54/sandboxctl/commit/0bb87e42b3e994cf6329d48335e9c35263072d35))


## v1.4.6 (2026-07-02)

### Bug Fixes

- Use $USER for keychain account lookup in post-launch setup
  ([`5db1514`](https://github.com/butler54/sandboxctl/commit/5db151454f109333f1577d45a09119118ee1933a))


## v1.4.5 (2026-07-02)

### Bug Fixes

- GitLab token shell quoting and per-server credential helpers
  ([`6940dc3`](https://github.com/butler54/sandboxctl/commit/6940dc34202fcc45ce5b58e7b174c9e449c70dcf))


## v1.4.4 (2026-07-02)

### Bug Fixes

- Inject Vertex AI env vars, GitLab token, and re-apply TLS policy
  ([`6a49e9f`](https://github.com/butler54/sandboxctl/commit/6a49e9fca7432221486111a11e2c3e16bff35c1f))


## v1.4.3 (2026-07-02)

### Bug Fixes

- Resolve migration blockers — provider YAML, image refs, CA bundle
  ([`e3530ba`](https://github.com/butler54/sandboxctl/commit/e3530bad525ba4e1102f419265ef92643b4cbd7b))


## v1.4.2 (2026-07-01)

### Bug Fixes

- Close remaining feature gaps from external analysis
  ([`e96c000`](https://github.com/butler54/sandboxctl/commit/e96c00065930fad818eb9cd1252e1bea946e75d7))


## v1.4.1 (2026-07-01)

### Bug Fixes

- Close security findings and feature gaps
  ([`fa4fb3e`](https://github.com/butler54/sandboxctl/commit/fa4fb3ea2f92152a285e6c59f30fa74e78723e71))

### Code Style

- Fix ruff format violations
  ([`b1d2c12`](https://github.com/butler54/sandboxctl/commit/b1d2c12d0d6bd2b6f924c7d1b1a4b12ff1468492))


## v1.4.0 (2026-06-30)

### Code Style

- Fix ruff format violation in cli.py
  ([`8d878ce`](https://github.com/butler54/sandboxctl/commit/8d878ce40e0f36a4402d3761f24c34c818c4baad))

### Features

- Security uplift — input validation, SAST, urllib refactor
  ([`6013016`](https://github.com/butler54/sandboxctl/commit/601301687a23de65913a3585929c47fb51ce5dfa))


## v1.3.0 (2026-06-30)

### Bug Fixes

- Strip ANSI codes in doctor help test assertion
  ([`a72aea0`](https://github.com/butler54/sandboxctl/commit/a72aea03a1e6b43b9a968e9fe99b9ce355a0ebf5))

### Features

- Enhanced doctor with credential validation, --fix, and --continue
  ([`9ceffcb`](https://github.com/butler54/sandboxctl/commit/9ceffcbf2b4df73033000f02c8af68fe0bfab572))


## v1.2.0 (2026-06-29)

### Bug Fixes

- Remove click import from test_setup — not a direct dependency
  ([`b82473f`](https://github.com/butler54/sandboxctl/commit/b82473fec2f7c12eb6181d8ace330a54ab1ae1ce))

### Features

- Add setup and restart commands
  ([`43dd535`](https://github.com/butler54/sandboxctl/commit/43dd535d8292df26c20afa219599f2321163d29c))


## v1.1.0 (2026-06-29)

### Bug Fixes

- Remove click import from test_open_cmd
  ([`292de90`](https://github.com/butler54/sandboxctl/commit/292de906c324a249c72802c2e76379e6a482675a))

- Strip ANSI codes in CLI help assertions
  ([`152c91f`](https://github.com/butler54/sandboxctl/commit/152c91f155216a11d841fdbc8e42268a2ea993fb))

### Chores

- Bump actions/setup-python from 6.2.0 to 6.3.0
  ([`6faba94`](https://github.com/butler54/sandboxctl/commit/6faba94b221f715442175f1178bcdefbb8d46bf5))

### Documentation

- Add Phase 8 documentation — README, CONTRIBUTING, MkDocs site
  ([`243dd4e`](https://github.com/butler54/sandboxctl/commit/243dd4e5169d0596e9dbb45f946ae59a7671b038))

- Address PR #18 review comments
  ([`75cca08`](https://github.com/butler54/sandboxctl/commit/75cca0874eca60f65aeb63cd92bc84c04a89e503))

- Address PR #18 review feedback
  ([`e76b5a3`](https://github.com/butler54/sandboxctl/commit/e76b5a3326ecd21178a1ec7a76a0fad356c61aba))

### Features

- Add create and open commands
  ([`af347a8`](https://github.com/butler54/sandboxctl/commit/af347a8b1db4854b70d6e46bcff6b482a30db90e))


## v1.0.2 (2026-06-26)

### Bug Fixes

- Trigger release to verify PyPI trusted publisher
  ([`9bbfec1`](https://github.com/butler54/sandboxctl/commit/9bbfec1156108998d2d2d721b41f089879a3d03e))


## v1.0.1 (2026-06-26)

### Bug Fixes

- Port release to dedicated workflow for PyPI OIDC
  ([`fd7672f`](https://github.com/butler54/sandboxctl/commit/fd7672f8a0a88fba69ee2a42b167bca6526d81e8))


## v1.0.0 (2026-06-26)

- Initial Release
