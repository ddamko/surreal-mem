# scripts

Operational scripts live in the Python package instead: `uv run surrealmem ops --help`
(llama.cpp build, model downloads, systemd units for inference, API and worker). This keeps the
project runnable on any Linux machine with `uv`; the `justfile` recipes are thin wrappers.
