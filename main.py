"""Strategy Agent — entry point.

Usage:
    python main.py                      # interactive REPL (rich)
    python main.py ask "your question"  # single query
    python main.py --config path.yaml   # use a non-default config

Startup runs LLM backend health checks and fails fast with exact fix instructions
(SPEC REQ-5). All behavior is config-driven (config.yaml); nothing is hardcoded.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from core.config import AppConfig, load_config
from core.docx_reader import DocxReadError
from core.excel_reader import ExcelReadError
from core.intake import read_document, render_document, render_result, run_repl
from core.pdf_reader import PdfReadError
from core.pipeline import AutoInteraction, resolve_memory, run_pipeline
from core.pptx_reader import PptxReadError
from core.researcher import ResearchEngine, SearchCache, SearXNGError
from core.startup import StartupError, check_llm_backend, check_searxng
from llm.local_llm_client import LLMError, LocalLLMClient
from models.task import EffortLevel, OutputFormat, TaskRequest


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


def _load_config_or_exit(config_path: Path) -> AppConfig:
    """Load and validate config, or print the error and exit non-zero (fail fast)."""
    try:
        return load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(Panel(str(exc), title="config error", border_style="red"))
        raise typer.Exit(code=1) from exc


def _bootstrap(config_path: Path) -> tuple[AppConfig, LocalLLMClient]:
    """Load config, run LLM startup check, and build the client. Fail fast on error."""
    config = _load_config_or_exit(config_path)

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


@app.command()
def research(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="What to research on the web")],
    max_fetch: Annotated[
        int | None,
        typer.Option("--max-fetch", help="How many top pages to deep-read"),
    ] = None,
) -> None:
    """Search the web via SearXNG and return ranked, deduplicated results."""
    obj = ctx.obj or {}
    config_path: Path = obj.get("config_path", DEFAULT_CONFIG_PATH)
    config = _load_config_or_exit(config_path)

    try:
        check_searxng(config)
    except StartupError as exc:
        console.print(Panel(str(exc), title="startup check failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    cache = SearchCache(config.research)
    engine = ResearchEngine(config.research, cache=cache)
    try:
        bundle = asyncio.run(engine.run(query, max_fetch=max_fetch))
    except SearXNGError as exc:
        console.print(Panel(str(exc), title="research failed", border_style="red"))
        raise typer.Exit(code=1) from exc
    finally:
        cache.close()

    accent = config.output.colors.accent_cyan
    table = Table(title=f"Research: {query}", border_style=accent, show_lines=False)
    table.add_column("#", justify="right", style="dim", no_wrap=True)
    table.add_column("Tier", no_wrap=True)
    table.add_column("Title")
    table.add_column("URL", style="dim")
    for idx, result in enumerate(bundle.results, start=1):
        table.add_row(str(idx), result.tier.value, result.title or "(untitled)", result.url)

    if bundle.results:
        console.print(table)
    else:
        console.print(Panel("No results found.", border_style="red"))

    fetched_words = sum(item.word_count for item in bundle.fetched)
    summary = (
        f"{len(bundle.results)} ranked result(s), "
        f"{len(bundle.fetched)} page(s) fetched (~{fetched_words} words)."
    )
    if bundle.from_cache:
        summary += "  [dim](served from 24h cache)[/dim]"
    console.print(Panel(summary, title="summary", border_style=accent))


@app.command()
def analyze(
    ctx: typer.Context,
    task_text: Annotated[str, typer.Argument(help="The task to research and analyze")],
    effort: Annotated[
        EffortLevel | None,
        typer.Option("--effort", help="Override the effort master dial: low | high | ultra"),
    ] = None,
) -> None:
    """Run the full agent pipeline non-interactively (intent → research → structured analysis).

    Clarifications are auto-answered (sensible defaults) and the research plan is auto-confirmed,
    so this is the scriptable counterpart to the interactive REPL (``python main.py``). ``--effort``
    overrides the auto-detected effort level (otherwise it is inferred from the task).
    """
    obj = ctx.obj or {}
    config_path: Path = obj.get("config_path", DEFAULT_CONFIG_PATH)
    config, client = _bootstrap(config_path)

    try:
        check_searxng(config)
        memory = resolve_memory(
            config,
            client,
            on_unavailable=lambda msg: console.print(
                Panel(msg, title="memory off (advisory)", border_style="yellow")
            ),
        )
        with console.status("[dim]analyzing…[/dim]", spinner="dots"):
            result = run_pipeline(
                client,
                config,
                TaskRequest(raw_input=task_text),
                AutoInteraction(),
                effort_override=effort,
                memory=memory,
            )
    except StartupError as exc:
        console.print(Panel(str(exc), title="startup check failed", border_style="red"))
        raise typer.Exit(code=1) from exc
    except SearXNGError as exc:
        console.print(Panel(str(exc), title="research failed", border_style="red"))
        raise typer.Exit(code=1) from exc
    except LLMError as exc:
        console.print(Panel(str(exc), title="LLM error", border_style="red"))
        raise typer.Exit(code=1) from exc
    finally:
        client.close()

    render_result(console, result, config.output.colors.accent_cyan)


_FORMAT_CHOICES: dict[str, list[OutputFormat]] = {
    "brief": [OutputFormat.BRIEF],  # PDF
    "deck": [OutputFormat.DECK],  # PPTX
    "both": [OutputFormat.BRIEF, OutputFormat.DECK],
}


@app.command()
def prepare(
    ctx: typer.Context,
    files: Annotated[
        list[Path],
        typer.Argument(help="Internal document paths (PDF / image / .xlsx / .docx / .pptx)"),
    ],
    task_text: Annotated[
        str,
        typer.Option("--task", "-t", help="What to prepare (e.g. 'consolidate for the board')"),
    ] = "Consolidate these documents into one management briefing",
    output_format: Annotated[
        str,
        typer.Option(
            "--format", "-f", help="Output deliverable(s): brief (PDF) | deck (PPTX) | both"
        ),
    ] = "both",
) -> None:
    """Consolidate internal documents into ONE management deliverable (no web research).

    The CEO-office mode: reads several documents (PDF / image / .xlsx) deeply, applies the doc-prep
    playbook (zero hallucination, management structure), writes a Markdown blueprint to ``output/``,
    and renders the chosen deliverable(s): a Neura-styled **PPTX** deck (works locally) and/or a
    **PDF** brief (needs WeasyPrint's GTK runtime; skipped with instructions if absent).
    """
    formats = _FORMAT_CHOICES.get(output_format.lower())
    if formats is None:
        console.print(
            Panel(
                f"Unknown --format '{output_format}'. Choose: brief | deck | both.",
                title="bad option",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    obj = ctx.obj or {}
    config_path: Path = obj.get("config_path", DEFAULT_CONFIG_PATH)
    config, client = _bootstrap(config_path)  # LLM client enables the vision fallback for scans

    try:
        with console.status("[dim]reading documents…[/dim]", spinner="dots"):
            documents = [read_document(path, llm=client) for path in files]
        with console.status(
            "[dim]reading deeply + rendering management briefing…[/dim]", spinner="dots"
        ):
            result = run_pipeline(
                client,
                config,
                TaskRequest(raw_input=task_text),
                AutoInteraction(),
                documents=documents,
                doc_formats=formats,
            )
    except (PdfReadError, ExcelReadError, DocxReadError, PptxReadError, FileNotFoundError) as exc:
        console.print(Panel(str(exc), title="document error", border_style="red"))
        raise typer.Exit(code=1) from exc
    except StartupError as exc:
        console.print(Panel(str(exc), title="startup check failed", border_style="red"))
        raise typer.Exit(code=1) from exc
    except LLMError as exc:
        console.print(Panel(str(exc), title="LLM error", border_style="red"))
        raise typer.Exit(code=1) from exc
    finally:
        client.close()

    render_result(console, result, config.output.colors.accent_cyan)


@app.command(name="analyze-doc")
def analyze_doc(
    ctx: typer.Context,
    doc_path: Annotated[
        Path, typer.Argument(help="Path to a PDF / image / .xlsx / .docx / .pptx file")
    ],
) -> None:
    """Read a document and print its extracted content (no synthesis — Phase 2)."""
    obj = ctx.obj or {}
    config_path: Path = obj.get("config_path", DEFAULT_CONFIG_PATH)
    config, client = _bootstrap(config_path)  # LLM client enables the vision fallback

    try:
        with console.status("[dim]reading document…[/dim]", spinner="dots"):
            doc = read_document(doc_path, llm=client)
    except (PdfReadError, ExcelReadError, DocxReadError, PptxReadError, FileNotFoundError) as exc:
        console.print(Panel(str(exc), title="document error", border_style="red"))
        raise typer.Exit(code=1) from exc
    finally:
        client.close()

    render_document(console, doc, config.output.colors.accent_cyan)


if __name__ == "__main__":
    app()
