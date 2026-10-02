from pathlib import Path

from typer.testing import CliRunner

from surrealmem.bootstrap import ops
from surrealmem.bootstrap.cli import app


def test_env_file_parsing_expands_home(tmp_path: Path) -> None:
    env = tmp_path / "x.env"
    env.write_text("# comment\nMODELS_DIR=$HOME/models\nLLM_PORT=8081\n\nBAD LINE\n")
    values = ops.load_env_file(env)
    assert values == {"MODELS_DIR": f"{Path.home()}/models", "LLM_PORT": "8081"}
    assert ops.load_env_file(tmp_path / "missing.env") == {}


def test_render_fills_placeholders(tmp_path: Path) -> None:
    template = tmp_path / "u.tmpl"
    template.write_text("ExecStart={{LLAMA_SERVER}} --port {{LLM_PORT}}\n")
    assert (
        ops.render(template, {"LLAMA_SERVER": "/bin/llama", "LLM_PORT": "8081"})
        == "ExecStart=/bin/llama --port 8081\n"
    )


def test_unit_templates_render_without_leftover_placeholders() -> None:
    cfg = ops.config()
    for unit in (*ops.INFERENCE_UNITS, *ops.SERVICE_UNITS):
        rendered = ops.render(ops.OPS_DIR / "systemd" / f"{unit}.service.tmpl", cfg)
        assert "{{" not in rendered, unit
        assert "[Service]" in rendered


def test_dry_run_prints_units() -> None:
    result = CliRunner().invoke(app, ["ops", "inference", "install", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "surrealmem-llm.service" in result.output and "ExecStart=" in result.output
    result = CliRunner().invoke(app, ["ops", "services", "install", "--dry-run"])
    assert result.exit_code == 0 and "surrealmem-worker.service" in result.output
