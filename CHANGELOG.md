# CHANGELOG

<!-- version list -->

## v1.13.0 (2026-08-10)

### Bug Fixes

- **21**: Fix all remaining ruff lint and format violations
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Add noqa suppressions for S104 and S310 in mlflow_cmd.py
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Anchor URL assertion to 'Tracking URI:' prefix to fix CodeQL S104
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Fix ruff B007, B904, ANN001, S104 in mlflow_cmd and test
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Move mlflow_app import to top of cli.py to fix ruff E402
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-03**: Add mlflow=False to gitlab profile tests to avoid health-check errors
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

### Features

- **21**: MLflow observability — container lifecycle, CLI, and sandbox integration
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Implement status, directory size, external mode
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Implement stop, is_running, health check
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-03**: Add optional prompted MLflow setup step (MLFLOW-04)
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-03**: Implement MLflow validate-then-start + fail-closed URI injection (GREEN)
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

### Testing

- **21-02**: Add failing tests for mlflow start
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Add tests for status, directory size, external mode
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-02**: Add tests for stop, is_running, health check
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))

- **21-03**: Add failing test for MLflow URI injection (RED)
  ([#93](https://github.com/butler54/sandboxctl/pull/93),
  [`1c0498e`](https://github.com/butler54/sandboxctl/commit/1c0498e001f2c01d550912d932a02bc6b987f8e9))


## v1.12.0 (2026-08-08)

### Features

- **21-01**: Add MlflowConfig section with validation
  ([`fc724b1`](https://github.com/butler54/sandboxctl/commit/fc724b130529da7d40d02883daa3c2e10fc06d36))

- **21-01**: Add Profile.mlflow opt-out boolean (default-on)
  ([`032a717`](https://github.com/butler54/sandboxctl/commit/032a717e859490177053f0a69c44e415849db8ce))

### Testing

- **21-01**: Add Wave 0 test scaffolds for mlflow_cmd, setup, create
  ([`0a8065c`](https://github.com/butler54/sandboxctl/commit/0a8065c540fd7ae2293ff85a7715fc0793cac7d3))


## v1.11.0 (2026-08-07)

### Chores

- Bump actions/checkout from 7.0.0 to 7.0.1 ([#77](https://github.com/butler54/sandboxctl/pull/77),
  [`330571b`](https://github.com/butler54/sandboxctl/commit/330571be6fec9e4450c13720af9e084b094c3ed9))

- Bump actions/setup-python from 6.3.0 to 7.0.0
  ([#79](https://github.com/butler54/sandboxctl/pull/79),
  [`f8c9543`](https://github.com/butler54/sandboxctl/commit/f8c9543f56c9953f0144f8e39ad8faa4d423b3c2))

- Bump pypa/gh-action-pypi-publish from 1.14.0 to 1.14.1
  ([#78](https://github.com/butler54/sandboxctl/pull/78),
  [`219787f`](https://github.com/butler54/sandboxctl/commit/219787fcd9a15861628a67e4490d735fc5197923))

### Code Style

- **20-01**: Satisfy ruff (add -> None on test fns, minor fix)
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

### Documentation

- **20-03**: Add [extensions] examples to bundled profiles
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

### Features

- **20**: Extension management ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-01**: Extensions model + profile wiring end-to-end
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-01**: Implement denylist, ID validation, and full classifier
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-01**: Implement idempotent install helper
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-02**: Implement extension install hook in open_sandbox
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-02**: Populate workspace recommendations with full declared list
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-03**: Implement extensions install CLI command
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

### Testing

- **20-01**: Add failing tests for denylist and ID validation
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-01**: Add failing tests for install helper
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-02**: Add failing tests for extension install hook
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-02**: Add failing tests for workspace recommendations
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))

- **20-03**: Add failing tests for extensions install command
  ([#84](https://github.com/butler54/sandboxctl/pull/84),
  [`dc35a3e`](https://github.com/butler54/sandboxctl/commit/dc35a3e7cc276272acd4ccd9ed9bf850c6d8f5cf))


## v1.10.0 (2026-08-06)

### Code Style

- **19**: Satisfy ruff lint on phase 19 test files
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

### Features

- **19**: VS Code integration — decoupled launch, SSH auto-reconnect, workspace settings
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-01**: Implement spawn_terminal_with_claude and refactor open_sandbox for decoupled launch
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-01**: Implement terminal app detection and WorkspaceConfig.terminal_app
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-02**: Implement ensure_ssh_keepalive for SSH resilience
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-02**: Wire SSH keepalive into open_sandbox
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-03**: Extend generate_workspace with Remote-SSH settings + extension recommendations
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

### Testing

- **19-01**: Add failing tests for spawn_terminal_with_claude and open_sandbox refactor
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-01**: Add failing tests for terminal detection and WorkspaceConfig.terminal_app
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-02**: Add failing tests for ensure_ssh_keepalive idempotency
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-02**: Add failing tests for keepalive wiring in open_sandbox
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))

- **19-03**: Add failing tests for Remote-SSH settings + extensions.recommendations
  ([#83](https://github.com/butler54/sandboxctl/pull/83),
  [`8f6a4b5`](https://github.com/butler54/sandboxctl/commit/8f6a4b50abb1451f9f0e9e2f414d9caae13d4d05))


## v1.9.2 (2026-07-31)

### Bug Fixes

- Work around CodeQL false positive on hostname string assertions
  ([`5841327`](https://github.com/butler54/sandboxctl/commit/5841327eb9332788d9da1765a535704266e5a1ac))

- **17-02**: Add tls:skip to Vertex provider YAML for OAuth endpoints
  ([#69](https://github.com/butler54/sandboxctl/pull/69),
  [`dc29771`](https://github.com/butler54/sandboxctl/commit/dc29771eca8170f3882f55547249c301944d8304))

### Chores

- Align codeql-action/init to v4.37.3 to match analyze
  ([`4244879`](https://github.com/butler54/sandboxctl/commit/4244879302f98ff616d388f7ea8b5ebfdb472aff))


## v1.9.1 (2026-07-31)

### Bug Fixes

- Add GH_SSL_CAINFO to CA bundle env vars ([#68](https://github.com/butler54/sandboxctl/pull/68),
  [`f9fa2b7`](https://github.com/butler54/sandboxctl/commit/f9fa2b72ee9fb0e104f80424474c58ec5825631d))

### Chores

- Bump astral-sh/setup-uv from 8.3.2 to 9.0.0
  ([`d731bcb`](https://github.com/butler54/sandboxctl/commit/d731bcb1584e128ff3af75ce979f9b78de0cdf2b))

- Bump github/codeql-action/analyze from 4.37.0 to 4.37.3
  ([`8619f22`](https://github.com/butler54/sandboxctl/commit/8619f22f834b65a41ceebcec4754af958194ba82))

- Bump github/codeql-action/upload-sarif from 4.37.0 to 4.37.3
  ([`998c201`](https://github.com/butler54/sandboxctl/commit/998c20128a01b7b9476f6830f3cd8a2faf1833f7))

- Bump ossf/scorecard-action from 2.4.3 to 2.4.4
  ([`17fa6c5`](https://github.com/butler54/sandboxctl/commit/17fa6c53b94f39059c749037bcbbacd3bf19581f))

- Bump python-semantic-release/python-semantic-release
  ([`cbc2f29`](https://github.com/butler54/sandboxctl/commit/cbc2f29e0abba8dfda049e4d13a02efd973f481c))

### Documentation

- Update README for v1.9, add shell completion to setup
  ([`722365b`](https://github.com/butler54/sandboxctl/commit/722365b9e7720c478647f30ec542c04294729e0c))


## v1.9.0 (2026-07-19)

### Bug Fixes

- Quote YAML values with embedded double-quotes in failure-catalog
  ([`684a93b`](https://github.com/butler54/sandboxctl/commit/684a93bc68910d0c84f642db351fec84425a4bf2))

### Chores

- Bump astral-sh/setup-uv from 8.2.0 to 8.3.2
  ([`7a0ede2`](https://github.com/butler54/sandboxctl/commit/7a0ede254f19ad2359432415c7191ed32af669a4))

- Bump github/codeql-action/analyze from 4.36.2 to 4.37.0
  ([`68beafd`](https://github.com/butler54/sandboxctl/commit/68beafd8b1b4966bf9ab75fbbe2bb7c0cfd6eb13))

- Bump github/codeql-action/init from 4.36.2 to 4.37.0
  ([`8ae0737`](https://github.com/butler54/sandboxctl/commit/8ae073726e3d2e4b3bf2d23a9851a58eb69fd187))

- Bump github/codeql-action/upload-sarif from 4.36.3 to 4.37.0
  ([`5fdc776`](https://github.com/butler54/sandboxctl/commit/5fdc77615eff1f2b20d9d8fda538f6bec4ceb514))

- Bump step-security/harden-runner from 2.19.4 to 2.20.0
  ([`4664872`](https://github.com/butler54/sandboxctl/commit/466487283345f18fba5c33dcd93e83934fe90c3a))

### Features

- Bundle sandboxctl skills and auto-install during setup
  ([`c36d618`](https://github.com/butler54/sandboxctl/commit/c36d6184ca41c58b151a617c83047bf03e72209c))


## v1.8.4 (2026-07-19)

### Bug Fixes

- Bootstrap GWS token_cache.json in doctor --fix
  ([#60](https://github.com/butler54/sandboxctl/pull/60),
  [`554fe2f`](https://github.com/butler54/sandboxctl/commit/554fe2fd7062e6c0747a8cc166a53b797390c588))


## v1.8.3 (2026-07-19)

### Bug Fixes

- **15-02**: Rewrite upgrade command with installation detection
  ([`b5d28b9`](https://github.com/butler54/sandboxctl/commit/b5d28b9f81446caf76949fcde9f204adb2e50163))

### Code Style

- Add missing type annotations for ruff ANN compliance
  ([`933de05`](https://github.com/butler54/sandboxctl/commit/933de05f34d6de1a1b961ebd84bfb2bed0ffa083))


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
