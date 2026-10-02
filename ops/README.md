# ops

Inference operations (ADR-0028): the two llama-server processes surrealmem talks to over HTTP.

| File | Purpose |
|---|---|
| `inference.env` | Model repos, file names, ports and the llama-server path. Override in `inference.local.env`. |
| `systemd/*.service.tmpl` | User unit templates rendered by `scripts/inference.nu` into `~/.config/systemd/user/`. |

```text
just models      # download the GGUFs into MODELS_DIR (idempotent)
just inference   # render + install + enable the units, then wait for both /health endpoints
just inference-status
```

The compose stack holds only SurrealDB; the GPU is used by host processes, never passed into a container.
