"""Interactive REPL intake layer (Phase 3: full agent pipeline + document file paths).

A rich-formatted chat loop over :class:`LocalLLMClient`. Free-text input runs the full agent
pipeline (intent → clarification → research-plan confirm → research → reasoning → structured
analysis, see :mod:`core.pipeline`). If the user drops a bare path to a supported document
(PDF / image / .xlsx), it is routed to the matching reader and the extracted content is shown.
Voice input (Ctrl+Space) remains a Phase 5 TODO.

This module is the REPL's presentation layer: :class:`ReplInteraction` is the rich
implementation of the pipeline's ``Interaction`` protocol, and ``render_result`` displays a
:class:`PipelineResult` (no file rendering — that is Phase 4).
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from core.config import AppConfig
from core.excel_reader import ExcelReadError, read_excel
from core.intent_parser import parse_effort_override
from core.pdf_reader import PdfReadError, read_pdf
from core.pipeline import run_pipeline
from core.researcher import SearXNGError
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import DocContent
from models.synthesis import PipelineResult
from models.task import EffortLevel, TaskRequest

EXIT_COMMANDS = {"exit", "quit", ":q", "q"}

_EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm"})
_PDF_LIKE_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"})
_SUPPORTED_SUFFIXES = _EXCEL_SUFFIXES | _PDF_LIKE_SUFFIXES

# How much extracted text to show in the REPL before truncating.
_DOC_PREVIEW_CHARS = 2000


def detect_file_path(text: str) -> Path | None:
    """Return a supported document path if the whole input is a bare path to one.

    Handles surrounding single/double quotes (common when paths contain spaces on
    Windows). Returns ``None`` for ordinary questions.
    """
    candidate = text.strip().strip('"').strip("'").strip()
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES:
        return path
    return None


def read_document(path: Path, llm: LocalLLMClient | None = None) -> DocContent:
    """Dispatch a document path to the correct reader (Excel vs PDF/image)."""
    if path.suffix.lower() in _EXCEL_SUFFIXES:
        return read_excel(path)
    return read_pdf(path, llm=llm)


def render_document(console: Console, doc: DocContent, accent: str) -> None:
    """Render extracted :class:`DocContent` in a rich panel (text truncated)."""
    preview = doc.text[:_DOC_PREVIEW_CHARS]
    if len(doc.text) > _DOC_PREVIEW_CHARS:
        preview += "\n\n[dim]… (truncated)[/dim]"
    meta = f"type: {doc.doc_type} · method: {doc.extraction_method}"
    if doc.page_count is not None:
        meta += f" · pages/sheets: {doc.page_count}"
    console.print(
        Panel(
            preview or "[dim](no text extracted)[/dim]",
            title=f"{doc.source_path.name}  ({meta})",
            border_style=accent,
        )
    )


class ReplInteraction:
    """Rich implementation of the pipeline's ``Interaction`` protocol (interactive REPL)."""

    def __init__(self, console: Console, accent: str) -> None:
        """Bind the console and accent colour used for prompts and progress."""
        self._console = console
        self._accent = accent

    def ask_choice(self, question: str, options: list[str]) -> str:
        """Show a numbered multiple-choice question and return the user's one-word answer."""
        self._console.print(f"\n[bold]{question}[/bold]")
        for index, option in enumerate(options, start=1):
            self._console.print(f"  [{self._accent}]{index}[/].  {option}")
        return Prompt.ask("[bold]›[/bold]").strip()

    def ask_text(self, question: str) -> str:
        """Ask a free-form mid-research question and return the user's typed answer.

        The agent paused research with a precise question; an empty answer lets it proceed on a
        stated assumption.
        """
        self._console.print(f"\n[bold {self._accent}]↯ mid-research question[/]")
        self._console.print(f"[bold]{question}[/bold]")
        return Prompt.ask("[bold]›[/bold]").strip()

    def confirm(self, prompt: str) -> bool:
        """Ask a yes/no question (defaults to yes)."""
        return Confirm.ask(f"[bold]{prompt}[/bold]", default=True)

    def notify(self, message: str) -> None:
        """Print a dim progress/status line."""
        self._console.print(f"[dim]{message}[/dim]")


def render_result(console: Console, result: PipelineResult, accent: str) -> None:
    """Render a :class:`PipelineResult` (structured analysis or declined quick answer)."""
    if result.declined:
        body = result.quick_answer or "[dim](no answer)[/dim]"
        console.print(
            Panel(Markdown(body), title="quick answer (no research)", border_style=accent)
        )
        return

    analysis = result.analysis
    if analysis is None:
        console.print(Panel("[dim](no analysis produced)[/dim]", border_style="red"))
        return

    console.print(
        Panel(
            Markdown(f"**{analysis.title}**\n\n{analysis.bottom_line}"),
            title=f"bottom line · {analysis.language.value}",
            border_style=accent,
        )
    )
    for section in analysis.sections:
        console.print(
            Panel(Markdown(section.body or "—"), title=section.heading, border_style=accent)
        )
    if analysis.sources:
        lines = []
        for source in analysis.sources:
            tier = f"  [{source.tier.value}]" if source.tier else ""
            lines.append(f"- {source.url}{tier}")
        console.print(Panel("\n".join(lines), title="sources", border_style="dim"))

    formats = ", ".join(fmt.value for fmt in result.routed_formats) or "brief"
    console.print(
        Panel(
            f"Would generate: [bold]{formats}[/bold]  [dim](file rendering is Phase 4)[/dim]",
            title="output plan",
            border_style=accent,
        )
    )
    console.print(Panel(_telemetry_text(result), title="run telemetry", border_style="dim"))


def _telemetry_text(result: PipelineResult) -> str:
    """Build the effort + self-correction telemetry line for the result panel (Phase 3.5)."""
    parts = [f"effort: [bold]{result.effort.value}[/bold]"]
    report = result.research_report
    if report is not None:
        parts.append(f"{report.workers_used} workers")
        parts.append(f"{report.rounds_used} rounds")
        parts.append(f"{report.sources_evaluated} sources evaluated")
        parts.append(f"{len(report.evidence)} read")
        if report.midresearch:
            parts.append(f"{len(report.midresearch)} mid-research Q")
    if result.critique is not None:
        verdict = "passed" if result.critique.passed else "failed"
        parts.append(f"quality {result.critique.score}/100 ({verdict})")
        parts.append(f"{result.revisions} revision(s)")
    return "  ·  ".join(parts)


def run_repl(
    client: LocalLLMClient,
    config: AppConfig,
    console: Console | None = None,
) -> None:
    """Run the interactive REPL until the user exits.

    Args:
        client: The LLM client to answer with.
        config: The loaded application config (used for accent color, etc.).
        console: Optional rich Console (injectable for testing).
    """
    console = console or Console()
    accent = config.output.colors.accent_cyan

    console.print(
        Panel(
            f"[bold]Strategy Agent[/bold]\n"
            f"model: [bold]{client.model_name}[/bold]   backend: {client.backend_url}\n"
            "Type a task — the agent plans, researches (multi-agent), and produces a structured "
            "analysis.\n"
            "Effort: prefix with [bold]/effort low|high|ultra[/bold] (alone = set the session "
            "default; auto-detected otherwise).\n"
            "Or drop a file path (PDF / image / .xlsx) to read it.\n"
            "Type [bold]exit[/bold] to quit.",
            title="ready",
            border_style=accent,
        )
    )

    session_effort: EffortLevel | None = None

    while True:
        try:
            user_input = Prompt.ask("[bold]you[/bold]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            return

        text = user_input.strip()
        if not text:
            continue
        if text.lower() in EXIT_COMMANDS:
            console.print("[dim]bye[/dim]")
            return

        override, stripped = parse_effort_override(text)
        if override is not None and not stripped:
            # "/effort ultra" with no task → set the session default effort.
            session_effort = override
            console.print(
                f"[dim]effort set to [bold]{override.value}[/bold] for this session[/dim]"
            )
            continue
        if override is not None:
            text = stripped

        document = detect_file_path(text)
        if document is not None:
            _handle_document(client, console, document, accent)
            continue

        # TODO(Phase 5): voice input via Ctrl+Space overlay -> inject transcript here.
        _handle_task(client, config, console, text, accent, override or session_effort)


def _handle_document(client: LocalLLMClient, console: Console, path: Path, accent: str) -> None:
    """Read a dropped document path and render its extracted content (or an error)."""
    try:
        with console.status("[dim]reading document…[/dim]", spinner="dots"):
            doc = read_document(path, llm=client)
    except (PdfReadError, ExcelReadError, FileNotFoundError) as exc:
        console.print(Panel(str(exc), title="document error", border_style="red"))
        return
    render_document(console, doc, accent)


def _handle_task(
    client: LocalLLMClient,
    config: AppConfig,
    console: Console,
    text: str,
    accent: str,
    effort_override: EffortLevel | None = None,
) -> None:
    """Run the full agent pipeline for a free-text task and render the result."""
    interaction = ReplInteraction(console, accent)
    try:
        result = run_pipeline(
            client,
            config,
            TaskRequest(raw_input=text),
            interaction,
            effort_override=effort_override,
        )
    except SearXNGError as exc:
        console.print(Panel(str(exc), title="research failed", border_style="red"))
        return
    except LLMError as exc:
        console.print(Panel(str(exc), title="LLM error", border_style="red"))
        return
    render_result(console, result, accent)
