# CHANGELOG

<!-- version list -->

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
