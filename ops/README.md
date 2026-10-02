# ops

Host operations for the GPU side of surrealmem (ADR-0028, amended): the two llama-server processes
and, optionally, the API and worker as systemd user units. All commands are Python:
`uv run surrealmem ops --help` (the `just` recipes wrap them).

| File | Purpose |
|---|---|
| `inference.env` | Model repos, file names, ports, llama.cpp source dir and arch. Override in `inference.local.env` (gitignored). |
| `systemd/surrealmem-llm|embed.service.tmpl` | llama-server unit templates. |
| `systemd/surrealmem-api|worker.service.tmpl` | API and worker unit templates (alternative to the container stack). |

```text
just llama-build       # surrealmem ops llama-build   (clone + cmake HIP for LLAMA_ARCH)
just models            # surrealmem ops models        (hf download, idempotent)
just inference         # surrealmem ops inference install  (render, enable --now, wait for /health)
just inference-status  # surrealmem ops inference status
just services          # surrealmem ops services install   (API + worker units)
```

Why a project-owned llama.cpp build: the binary must match the GPU architecture and the installed
ROCm. A build made for `gfx1100` on an older ROCm lists the GPU but aborts in the HIP runtime as
soon as a model runs.

Containers (`just docker-up`) do not include inference; they reach the host endpoints through
`host.docker.internal` (see `SURREALMEM_CONTAINER_*_BASE_URL` in `.env.example`). The units bind to
127.0.0.1 by default, which containers cannot reach: set `LLAMA_BIND_HOST=0.0.0.0` in
`ops/inference.local.env` and run `just inference` again (keep the ports firewalled), or point the
container base URLs at any other OpenAI-compatible endpoint, including a cloud provider.
