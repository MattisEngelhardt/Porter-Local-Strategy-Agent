"""Interactive REPL intake layer (Phase 3: full agent pipeline + document file paths).

A rich-formatted chat loop over :class:`LocalLLMClient`. Free-text input runs the full agent
pipeline (intent → clarification → research-plan confirm → research → reasoning → structured
analysis, see :mod:`core.pipeline`). If the user drops a bare path to a supported document
(PDF / image / .xlsx / .docx / .pptx), it is routed to the matching reader and the content shown.
Voice input (Ctrl+Space) remains a Phase 5 TODO.

This module is the REPL's presentation layer: :class:`ReplInteraction` is the rich
implementation of the pipeline's ``Interaction`` protocol, and ``render_result`` displays a
:class:`PipelineResult` including the rendered deliverable paths (PDF / PPTX / Excel).
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from core.config import AppConfig
from core.docling_reader import DoclingReadError, read_with_docling
from core.docx_reader import read_docx
from core.excel_reader import ExcelReadError, read_excel
from core.intent_parser import parse_effort_override
from core.memory import MemoryStore, append_brain_additions
from core.model_switch import (
    MODELS,
    ModelSwitchError,
    active_model_value,
    apply_model,
    find_model,
)
from core.pdf_reader import PdfReadError, read_pdf
from core.picker import Choice
from core.picker import select as select_choice
from core.pipeline import resolve_memory, run_pipeline
from core.pptx_reader import read_pptx
from core.profile import PROFILES, ProfileError, active_profile, set_active_profile
from core.researcher import SearXNGError
from core.startup import StartupError
from core.voice_input import VoiceError, VoiceInput, build_voice_input
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import DocContent
from models.synthesis import PipelineResult
from models.task import EffortLevel, TaskRequest

EXIT_COMMANDS = {"exit", "quit", ":q", "q"}

_EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm"})
_WORD_SUFFIXES = frozenset({".docx"})
_PPTX_SUFFIXES = frozenset({".pptx"})
_PDF_LIKE_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"})
_SUPPORTED_SUFFIXES = _EXCEL_SUFFIXES | _WORD_SUFFIXES | _PPTX_SUFFIXES | _PDF_LIKE_SUFFIXES

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
    """Dispatch a document path to the correct reader (Excel / Word / PowerPoint / PDF / image)."""
    suffix = path.suffix.lower()
    if suffix in _EXCEL_SUFFIXES:
        return read_excel(path)
    if suffix in _WORD_SUFFIXES:
        return read_docx(path)
    if suffix in _PPTX_SUFFIXES:
        return read_pptx(path)
    return read_pdf(path, llm=llm)


def read_document_hifi(path: Path, llm: LocalLLMClient | None = None) -> DocContent:
    """High-fidelity-first read: try Docling, else fall back to the lightweight readers (fail-open).

    Preferred entry point for the Analyst/Builder dimensions where exact tables / multi-column
    layout matter. If the optional ``docling`` package is absent (or conversion fails), Porter
    falls back to :func:`read_document` so it always returns usable text.
    """
    try:
        return read_with_docling(path)
    except DoclingReadError:
        return read_document(path, llm=llm)


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
    if result.delta_note:
        console.print(
            Panel(Markdown(result.delta_note), title="memory · delta", border_style=accent)
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
    if result.output_files:
        plan = f"Generated: [bold]{formats}[/bold]"
    else:
        plan = f"Routed: [bold]{formats}[/bold]  [dim](no files written — see notes above)[/dim]"
    console.print(Panel(plan, title="output plan", border_style=accent))
    if result.artifact_path is not None or result.output_files:
        lines = []
        if result.output_files:
            for file in result.output_files:
                lines.append(f"📄 [bold]{file}[/bold]")
        if result.artifact_path is not None:
            lines.append(f"[dim]blueprint (.md cheat-sheet): {result.artifact_path}[/dim]")
        console.print(Panel("\n".join(lines), title="deliverables written", border_style=accent))
    console.print(Panel(_telemetry_text(result), title="run telemetry", border_style="dim"))


def _telemetry_text(result: PipelineResult) -> str:
    """Build the effort + self-correction telemetry line for the result panel (Phase 3.5)."""
    if result.mode == "document_prep":
        return "mode: [bold]document-prep[/bold]  ·  internal documents consolidated (no research)"
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
    config_path: Path | None = None,
) -> None:
    """Run the interactive REPL until the user exits.

    Args:
        client: The LLM client to answer with.
        config: The loaded application config (used for accent color, etc.).
        console: Optional rich Console (injectable for testing).
        config_path: The config file backing this session — reloaded after a ``/model`` switch.
    """
    console = console or Console()
    accent = config.output.colors.accent_cyan
    cfg_path = config_path or Path("config.yaml")

    # Open persistent memory once for the session (advisory — None if disabled/unavailable).
    memory = resolve_memory(
        config,
        client,
        on_unavailable=lambda msg: console.print(
            Panel(msg, title="memory off (advisory)", border_style="yellow")
        ),
    )

    # Start voice input (Ctrl+Space) if enabled — additive; never blocks the text REPL.
    voice = build_voice_input(config.voice)
    if voice is not None:
        try:
            voice.start()  # hotkey records → transcribes → types the text into the prompt
        except VoiceError as exc:
            console.print(Panel(str(exc), title="voice off (additive)", border_style="yellow"))
            voice = None

    voice_line = (
        "\nVoice: press [bold]Ctrl+Space[/bold] to dictate into the prompt, or type "
        "[bold]/voice[/bold] to speak one task."
        if voice is not None
        else ""
    )
    console.print(
        Panel(
            f"[bold]Porter[/bold] — your local strategy agent\n"
            f"model: [bold]{client.model_name}[/bold]   role: [bold]{active_profile().label}[/bold]"
            f"   backend: {client.backend_url}\n"
            "Type a task — the agent plans, researches (multi-agent), and produces a structured "
            "analysis.\n"
            "Switch: [bold]/model[/bold] (AI model) · [bold]/role[/bold] "
            "(Researcher / Analyst / Builder / Allrounder).\n"
            "Effort: prefix with [bold]/effort low|high|ultra[/bold] (alone = set the session "
            "default; auto-detected otherwise).\n"
            "Or drop a file path (PDF / image / .xlsx) to read it."
            f"{voice_line}\n"
            "Type [bold]exit[/bold] to quit.",
            title="ready",
            border_style=accent,
        )
    )

    session_effort: EffortLevel | None = None

    try:
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

            if text.lower() in {"/voice", "/v"}:
                spoken = _capture_voice(console, voice, accent)
                if not spoken:
                    continue
                text = spoken
                console.print(f"[dim]heard:[/dim] {text}")

            if text.lower() == "/role" or text.lower().startswith("/role "):
                _handle_role_switch(console, accent, text)
                continue

            if text.lower() == "/model" or text.lower().startswith("/model "):
                client = _handle_model_switch(console, accent, text, client, config, cfg_path)
                continue

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

            _handle_task(client, config, console, text, accent, override or session_effort, memory)
    finally:
        if voice is not None:
            voice.stop()


def _handle_role_switch(console: Console, accent: str, raw: str) -> None:
    """Switch Porter's active role (Researcher / Analyst / Builder / Allrounder).

    ``/role`` opens an arrow-key menu; ``/role <name>`` switches directly. The choice persists in
    ``.porter_profile`` via :func:`set_active_profile` and is **independent of the model** — this
    never touches the ``llm:`` config (see core/profile.py for the lock/independence rationale).
    """
    parts = raw.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    current = active_profile()

    if arg:
        chosen: str | None = arg
    else:
        choices = [
            Choice(value=p.name, title=p.label, hint=p.description) for p in PROFILES.values()
        ]
        chosen = select_choice(
            "Pick Porter's role",
            choices,
            active_value=current.name,
            console=console,
        )

    if not chosen:
        console.print("[dim]role unchanged[/dim]")
        return

    try:
        switched = set_active_profile(chosen)
    except ProfileError as exc:
        console.print(Panel(str(exc), title="unknown role", border_style="red"))
        return

    if switched.name == current.name:
        console.print(f"[dim]role stays [bold]{switched.label}[/bold][/dim]")
        return

    console.print(
        Panel(
            f"Porter is now: [bold]{switched.label}[/bold]\n{switched.description}",
            title="role switched",
            border_style=accent,
        )
    )


def _handle_model_switch(
    console: Console,
    accent: str,
    raw: str,
    client: LocalLLMClient,
    config: AppConfig,
    config_path: Path,
) -> LocalLLMClient:
    """Switch Porter's AI model in-session, booting whatever it needs, and hot-swap the client.

    ``/model`` opens an arrow-key menu of the real model names; ``/model <value>`` switches
    directly. Reuses the proven boot scripts (core/model_switch.py) — the same cold-start
    ``porter`` does — then rebuilds the live client from the reloaded config. On failure the
    current client is kept. Never touches the active role (``.porter_profile``): the role stays
    locked across a model switch.

    Returns the client to use going forward (new on success, the original otherwise).
    """
    parts = raw.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    current_value = active_model_value(config.llm)

    if arg:
        chosen: str | None = arg
    else:
        choices = [Choice(value=m.value, title=m.title, hint=m.hint) for m in MODELS]
        chosen = select_choice(
            "Pick Porter's AI model", choices, active_value=current_value, console=console
        )

    if not chosen:
        console.print("[dim]model unchanged[/dim]")
        return client

    target = find_model(chosen)
    if target is None:
        valid = ", ".join(m.value for m in MODELS)
        console.print(
            Panel(
                f"Unknown model '{chosen}'. Choose: {valid}.",
                title="unknown model",
                border_style="red",
            )
        )
        return client

    if target.value == current_value:
        console.print(f"[dim]model stays [bold]{client.model_name}[/bold][/dim]")
        return client

    console.print(
        f"[dim]switching to [bold]{target.title}[/bold] — "
        "booting backend (this can take a moment)…[/dim]"
    )
    try:
        new_cfg = apply_model(target.value, config_path, console)
    except ModelSwitchError as exc:
        console.print(Panel(str(exc), title="model switch failed", border_style="red"))
        return client

    config.llm = new_cfg.llm  # keep in-memory config in sync (prompt budgeting reads num_ctx)
    new_client = LocalLLMClient(new_cfg.llm)
    client.close()  # idempotent; frees the old transport
    console.print(
        Panel(
            f"Porter now runs on: [bold]{new_client.model_name}[/bold]\n"
            f"backend: {new_client.backend_url}",
            title="model switched",
            border_style=accent,
        )
    )
    return new_client


def _capture_voice(console: Console, voice: VoiceInput | None, accent: str) -> str | None:
    """Record one spoken task via the ``/voice`` command; return the transcript or ``None``.

    With voice disabled, prints how to enable it. A capture/transcription failure is shown (with
    its exact fix) and returns ``None`` — the text REPL is never broken.
    """
    if voice is None:
        console.print(
            Panel(
                "Voice is off. Enable it: set [bold]voice.enabled: true[/bold] in config.yaml "
                "and install the voice deps (pyaudio, faster-whisper, pynput).",
                title="voice",
                border_style="yellow",
            )
        )
        return None
    try:
        with console.status("[dim]listening… speak now[/dim]", spinner="dots"):
            text = voice.capture_once().strip()
    except VoiceError as exc:
        console.print(Panel(str(exc), title="voice error", border_style="red"))
        return None
    if not text:
        console.print("[dim](no speech detected)[/dim]")
        return None
    return text


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
    memory: MemoryStore | None = None,
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
            memory=memory,
        )
    except SearXNGError as exc:
        console.print(Panel(str(exc), title="research failed", border_style="red"))
        return
    except StartupError as exc:
        console.print(Panel(str(exc), title="startup check failed", border_style="red"))
        return
    except LLMError as exc:
        console.print(Panel(str(exc), title="LLM error", border_style="red"))
        return
    render_result(console, result, accent)
    _maybe_update_brain(console, config, result, accent)


def _maybe_update_brain(
    console: Console, config: AppConfig, result: PipelineResult, accent: str
) -> None:
    """Show agent-proposed brain.md additions; append the user-confirmed ones ([y/N], default No).

    The brain-update flow (SPEC §4.5/§15): the agent proposes durable, high-signal additions; the
    user confirms before anything is written (brain.md is confidential and local-only, N-9).
    """
    additions = result.proposed_brain_additions
    if not additions:
        return
    body = "\n".join(f"  • {addition}" for addition in additions)
    console.print(
        Panel(
            f"The agent suggests adding these durable notes to brain.md:\n\n{body}",
            title="brain.md update (persistent memory)",
            border_style=accent,
        )
    )
    if Confirm.ask("[bold]Add these to brain.md?[/bold]", default=False):
        written = append_brain_additions(config.memory, additions)
        console.print(f"[dim]added {written} line(s) to {config.memory.brain_path}[/dim]")
    else:
        console.print("[dim]skipped — brain.md unchanged[/dim]")
