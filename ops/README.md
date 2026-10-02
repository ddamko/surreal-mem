# ops

Inference operations (ADR-0028): the two llama-server processes surrealmem talks to over HTTP.

| File | Purpose |
|---|---|
| `inference.env` | Model repos, file names, ports and the llama-server path. Override in `inference.local.env`. |
| `systemd/surrealmem-llm|embed.service.tmpl` | llama-server unit templates rendered by `scripts/inference.nu`. |
| `systemd/surrealmem-api|worker.service.tmpl` | API and worker unit templates rendered by `scripts/services.nu` (`just services`). |

```text
just llama-build # clone llama.cpp and build llama-server with HIP for LLAMA_ARCH (gfx1151)
just models      # download the GGUFs into MODELS_DIR (idempotent)
just inference   # render + install + enable the units, then wait for both /health endpoints
just inference-status
```

The compose stack holds only SurrealDB; the GPU is used by host processes, never passed into a container.

Why a project-owned build: a llama.cpp binary must be compiled for the exact GPU architecture and the
installed ROCm. A build made for `gfx1100` on an older ROCm lists the GPU but aborts in the HIP runtime
(`hip::StatCO::getStatFunc ... hipSuccess`) as soon as a model runs. `just llama-build` pins the
architecture and uses the ROCm toolchain under `/opt/rocm`.
