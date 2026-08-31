# sandboxctl mlflow

Manage the MLflow tracking server used for Claude Code / opencode session
observability.

## Usage

```
sandboxctl mlflow start
sandboxctl mlflow stop
sandboxctl mlflow status
```

## Subcommands

| Command | Description |
|---|---|
| `start` | Start the managed MLflow tracking server (Podman container with bind-mounted storage). No-op in external mode. |
| `stop` | Stop the managed MLflow container. No-op in external mode. |
| `status` | Show server state, tracking URI, and data-directory size (managed), or a reachability probe (external). |

## Configuration

The server is configured via the `[mlflow]` section of `config.toml`:

```toml
[mlflow]
tracking_uri = "http://localhost:5050"   # http/https only
managed = true                            # sandboxctl manages a Podman container
data_dir = "~/.config/sandboxctl/mlflow-data"
port = 5050
```

- **Managed mode** (`managed = true`): sandboxctl runs and lifecycles the MLflow
  container locally, persisting data to `data_dir` (survives Podman VM restarts
  via a bind mount).
- **External mode** (`managed = false`): you provide a reachable `tracking_uri`;
  sandboxctl only validates and injects it — it never starts or stops a
  container.

At `sandboxctl create`, when a profile has `mlflow = true`, sandboxctl validates
the server is healthy (starting the managed container and polling with backoff
if needed), then injects `MLFLOW_TRACKING_URI` and Claude Code tracing env vars
into the sandbox. If the server can't be made healthy, create fails closed with
a clear error.

See [Profiles](../configuration/profiles.md) for the per-profile `mlflow` toggle.

## Status

Implemented.
