"""Host operations in plain Python (ADR-0028): llama.cpp build, model downloads, systemd user units
for inference, API and worker. Everything here shells out to standard tools (git, cmake, hf,
systemctl, curl) so it runs on any Linux developer machine with ``uv``.

Configuration comes from ``ops/inference.env`` with optional overrides in
``ops/inference.local.env`` (both ``KEY=VALUE`` lines; ``$HOME`` is expanded).
"""

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

REPO_ROOT = Path(__file__).resolve().parents[4]
OPS_DIR = REPO_ROOT / "ops"
UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
INFERENCE_UNITS = ("surrealmem-llm", "surrealmem-embed")
SERVICE_UNITS = ("surrealmem-api", "surrealmem-worker")

ops_app = typer.Typer(no_args_is_help=True, help="Host operations: build, models, units")
inference_app = typer.Typer(
    no_args_is_help=True, help="llama-server units for the instruct and embedding models"
)
services_app = typer.Typer(no_args_is_help=True, help="API and worker units")
ops_app.add_typer(inference_app, name="inference")
ops_app.add_typer(services_app, name="services")


# ----------------------------------------------------------------------------- configuration


def load_env_file(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines, ignoring blanks and comments; ``$HOME`` is expanded."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    home = str(Path.home())
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().replace("$HOME", home).replace("${HOME}", home)
    return values


def config() -> dict[str, str]:
    values = load_env_file(OPS_DIR / "inference.env")
    values.update(load_env_file(OPS_DIR / "inference.local.env"))
    values.setdefault("LLAMA_SRC", str(Path.home() / ".local/share/surrealmem/llama.cpp"))
    values.setdefault("LLAMA_ARCH", "gfx1151")
    values.setdefault("LLAMA_SERVER", str(Path(values["LLAMA_SRC"]) / "build-hip/bin/llama-server"))
    values.setdefault("MODELS_DIR", str(Path.home() / ".local/share/surrealmem/models"))
    values.setdefault("LLAMA_BIND_HOST", "127.0.0.1")
    values["REPO"] = str(REPO_ROOT)
    values["UV"] = shutil.which("uv") or "uv"
    values["API_PORT"] = api_port()
    return values


def api_port() -> str:
    env = load_env_file(REPO_ROOT / ".env")
    return env.get("SURREALMEM_API_PORT") or os.environ.get("SURREALMEM_API_PORT") or "8790"


def render(template: Path, values: dict[str, str]) -> str:
    text = template.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


# ----------------------------------------------------------------------------- helpers


def run(cmd: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> int:
    typer.echo("$ " + " ".join(cmd), err=True)
    merged = {**os.environ, **(env or {})}
    return subprocess.run(cmd, check=check, env=merged).returncode


def capture(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, check=False, capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        return ""


def http_ok(url: str, *, timeout: float = 3.0) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read(200).decode("utf-8", "replace").strip()
    except urllib.error.URLError, TimeoutError, OSError:
        return None


def wait_for(url: str, *, attempts: int = 120, delay: float = 2.0) -> bool:
    for _ in range(attempts):
        if http_ok(url) is not None:
            return True
        time.sleep(delay)
    return False


@dataclass(frozen=True, slots=True)
class UnitStatus:
    unit: str
    active: str
    health: str


def unit_status(unit: str, health_url: str | None) -> UnitStatus:
    active = capture(["systemctl", "--user", "is-active", f"{unit}.service"]) or "unknown"
    health = "-"
    if health_url:
        body = http_ok(health_url)
        health = body if body is not None else "unreachable"
    return UnitStatus(unit=unit, active=active, health=health)


def print_status(rows: list[UnitStatus]) -> None:
    width = max(len(r.unit) for r in rows)
    for r in rows:
        typer.echo(f"{r.unit:<{width}}  {r.active:<10}  {r.health}")


def install_units(units: tuple[str, ...], values: dict[str, str], *, dry_run: bool) -> None:
    for unit in units:
        rendered = render(OPS_DIR / "systemd" / f"{unit}.service.tmpl", values)
        if dry_run:
            typer.echo(f"# ---- {unit}.service\n{rendered}")
            continue
        UNIT_DIR.mkdir(parents=True, exist_ok=True)
        (UNIT_DIR / f"{unit}.service").write_text(rendered, encoding="utf-8")
    if dry_run:
        return
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", "--now", *(f"{u}.service" for u in units)])


# ----------------------------------------------------------------------------- build + models


@ops_app.command("llama-build")
def llama_build(
    force: Annotated[bool, typer.Option(help="Rebuild even if the binary exists")] = False,
) -> None:
    """Clone llama.cpp and build llama-server with HIP for LLAMA_ARCH (default gfx1151)."""
    cfg = config()
    src = Path(cfg["LLAMA_SRC"])
    binary = src / "build-hip" / "bin" / "llama-server"
    if binary.exists() and not force:
        typer.echo(f"present  {binary} (use --force to rebuild)")
        return
    if not (src / ".git").exists():
        run(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(src)])
    hipconfig = "/opt/rocm/bin/hipconfig"
    env = {
        "HIPCXX": f"{capture([hipconfig, '-l'])}/clang",
        "HIP_PATH": capture([hipconfig, "-R"]) or "/opt/rocm",
    }
    arch = cfg["LLAMA_ARCH"]
    run(
        [
            "cmake",
            "-S",
            str(src),
            "-B",
            str(src / "build-hip"),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DGGML_HIP=ON",
            f"-DAMDGPU_TARGETS={arch}",
            f"-DCMAKE_HIP_ARCHITECTURES={arch}",
            "-DLLAMA_BUILD_TESTS=OFF",
            "-DLLAMA_BUILD_EXAMPLES=OFF",
            "-DLLAMA_BUILD_TOOLS=ON",
            "-DLLAMA_BUILD_SERVER=ON",
        ],
        env=env,
    )
    run(
        [
            "cmake",
            "--build",
            str(src / "build-hip"),
            "--target",
            "llama-server",
            "-j",
            str(os.cpu_count() or 4),
        ],
        env=env,
    )
    typer.echo(f"built    {binary}")


@ops_app.command("models")
def models() -> None:
    """Download the instruct and embedding GGUFs into MODELS_DIR (idempotent)."""
    cfg = config()
    target_dir = Path(cfg["MODELS_DIR"])
    target_dir.mkdir(parents=True, exist_ok=True)
    for repo, file in ((cfg["EMBED_REPO"], cfg["EMBED_FILE"]), (cfg["LLM_REPO"], cfg["LLM_FILE"])):
        target = target_dir / file
        if target.exists():
            typer.echo(f"present  {file} ({target.stat().st_size / 1e9:.1f} GB)")
            continue
        typer.echo(f"download {repo} {file}")
        run(["hf", "download", repo, file, "--local-dir", str(target_dir)])


# ----------------------------------------------------------------------------- inference units


@inference_app.command("install")
def inference_install(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the rendered units only")
    ] = False,
) -> None:
    """Render, install and start the llama-server units, then wait for both health endpoints."""
    cfg = config()
    if not dry_run:
        if not Path(cfg["LLAMA_SERVER"]).exists():
            raise typer.BadParameter(
                f"llama-server not found at {cfg['LLAMA_SERVER']}; "
                "run `surrealmem ops llama-build` or set LLAMA_SERVER in ops/inference.local.env"
            )
        for file in (cfg["LLM_FILE"], cfg["EMBED_FILE"]):
            if not (Path(cfg["MODELS_DIR"]) / file).exists():
                raise typer.BadParameter(
                    f"model missing: {file}; run `surrealmem ops models` first"
                )
    install_units(INFERENCE_UNITS, cfg, dry_run=dry_run)
    if dry_run:
        return
    for unit, port in (
        ("surrealmem-llm", cfg["LLM_PORT"]),
        ("surrealmem-embed", cfg["EMBED_PORT"]),
    ):
        url = f"http://127.0.0.1:{port}/health"
        typer.echo(f"waiting for {unit} at {url}")
        if not wait_for(url):
            raise typer.Exit(code=1)
        typer.echo(f"ready    {unit}")


@inference_app.command("status")
def inference_status() -> None:
    """Unit state and health of the inference endpoints."""
    cfg = config()
    print_status(
        [
            unit_status("surrealmem-llm", f"http://127.0.0.1:{cfg['LLM_PORT']}/health"),
            unit_status("surrealmem-embed", f"http://127.0.0.1:{cfg['EMBED_PORT']}/health"),
        ]
    )


@inference_app.command("stop")
def inference_stop() -> None:
    """Stop and disable the inference units."""
    run(
        ["systemctl", "--user", "disable", "--now", *(f"{u}.service" for u in INFERENCE_UNITS)],
        check=False,
    )


# ----------------------------------------------------------------------------- api + worker units


@services_app.command("install")
def services_install(dry_run: Annotated[bool, typer.Option("--dry-run")] = False) -> None:
    """Render, install and start the API and worker units."""
    cfg = config()
    install_units(SERVICE_UNITS, cfg, dry_run=dry_run)
    if dry_run:
        return
    url = f"http://127.0.0.1:{cfg['API_PORT']}/health/ready"
    if not wait_for(url, attempts=60):
        raise typer.Exit(code=1)
    typer.echo("ready    surrealmem-api\nstarted  surrealmem-worker")


@services_app.command("status")
def services_status() -> None:
    """Unit state of the API and worker, and API health."""
    cfg = config()
    print_status(
        [
            unit_status("surrealmem-api", f"http://127.0.0.1:{cfg['API_PORT']}/health/ready"),
            unit_status("surrealmem-worker", None),
        ]
    )


@services_app.command("stop")
def services_stop() -> None:
    """Stop and disable the API and worker units."""
    run(
        ["systemctl", "--user", "disable", "--now", *(f"{u}.service" for u in SERVICE_UNITS)],
        check=False,
    )


@services_app.command("logs")
def services_logs(
    which: Annotated[str, typer.Argument(help="api | worker")] = "worker",
    lines: Annotated[int, typer.Option("-n", "--lines")] = 50,
) -> None:
    """Show the journal of a unit."""
    run(
        [
            "journalctl",
            "--user",
            "-u",
            f"surrealmem-{which}.service",
            "-n",
            str(lines),
            "--no-pager",
        ],
        check=False,
    )
