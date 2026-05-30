"""Strategy Agent — entry point.

Usage:
    python main.py                      # interactive REPL (rich)
    python main.py ask "your question"  # single query
    python main.py --config path.yaml   # use a non-default config

Startup runs LLM backend health checks and fails fast with exact fix instructions
(SPEC REQ-5). All behavior is config-driven (config.yaml); nothing is hardcoded.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from core.config import AppConfig, load_config
from core.intake import run_repl
from core.startup import StartupError, check_llm_backend
from llm.local_llm_client import LLMError, LocalLLMClient


def _force_utf8_io() -> None:
    """Force UTF-8 stdout/stderr so bilingual (German) output renders on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - platform dependent
                pass


_force_utf8_io()

app = typer.Typer(
    add_completion=False,
    help="Local strategy/research agent for Neura Robotics internship workflows.",
    no_args_is_help=False,
)
console = Console()

DEFAULT_CONFIG_PATH = Path("config.yaml")


def _bootstrap(config_path: Path) -> tuple[AppConfig, LocalLLMClient]:
    """Load config, run startup checks, and build the LLM client. Fail fast on error."""
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(Panel(str(exc), title="config error", border_style="red"))
        raise typer.Exit(code=1) from exc

    try:
        check_llm_backend(config)
    except StartupError as exc:
        console.print(Panel(str(exc), title="startup check failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    return config, LocalLLMClient(config.llm)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to config.yaml")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Launch the interactive REPL when no subcommand is given."""
    ctx.obj = {"config_path": config_path}
    if ctx.invoked_subcommand is not None:
        return

    config, client = _bootstrap(config_path)
    try:
        run_repl(client, config, console=console)
    finally:
        client.close()


@app.command()
def ask(
    ctx: typer.Context,
    question: Annotated[str, typer.Argument(help="Your question for the agent")],
) -> None:
    """Answer a single question and exit."""
    obj = ctx.obj or {}
    config_path: Path = obj.get("config_path", DEFAULT_CONFIG_PATH)
    config, client = _bootstrap(config_path)

    try:
        with console.status("[dim]thinking…[/dim]", spinner="dots"):
            answer = client.generate(question)
    except LLMError as exc:
        console.print(Panel(str(exc), title="LLM error", border_style="red"))
        raise typer.Exit(code=1) from exc
    finally:
        client.close()

    body = answer.strip() or "[dim](empty response)[/dim]"
    console.print(
        Panel(
            Markdown(body),
            title=client.model_name,
            border_style=config.output.colors.accent_cyan,
        )
    )


if __name__ == "__main__":
    app()
