"""Interactive REPL intake layer (Phase 2: text + document file paths).

A rich-formatted chat loop over :class:`LocalLLMClient`. If the user drops a bare
path to a supported document (PDF / image / .xlsx), it is routed to the matching
reader and the extracted content is shown (extraction only — synthesis is Phase 3).
Voice input (Ctrl+Space) remains a Phase 5 TODO.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from core.config import AppConfig
from core.excel_reader import ExcelReadError, read_excel
from core.pdf_reader import PdfReadError, read_pdf
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import DocContent

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
            "Type your question, or drop a file path (PDF / image / .xlsx) to read it.\n"
            "Type [bold]exit[/bold] to quit.",
            title="ready",
            border_style=accent,
        )
    )

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

        document = detect_file_path(text)
        if document is not None:
            _handle_document(client, console, document, accent)
            continue

        # TODO(Phase 5): voice input via Ctrl+Space overlay -> inject transcript here.
        _answer(client, console, text, accent)


def _handle_document(client: LocalLLMClient, console: Console, path: Path, accent: str) -> None:
    """Read a dropped document path and render its extracted content (or an error)."""
    try:
        with console.status("[dim]reading document…[/dim]", spinner="dots"):
            doc = read_document(path, llm=client)
    except (PdfReadError, ExcelReadError, FileNotFoundError) as exc:
        console.print(Panel(str(exc), title="document error", border_style="red"))
        return
    render_document(console, doc, accent)


def _answer(client: LocalLLMClient, console: Console, prompt: str, accent: str) -> None:
    """Generate one response and render it in a rich panel."""
    try:
        with console.status("[dim]thinking…[/dim]", spinner="dots"):
            response = client.generate(prompt)
    except LLMError as exc:
        console.print(Panel(str(exc), title="LLM error", border_style="red"))
        return

    body = response.strip() or "[dim](empty response)[/dim]"
    console.print(Panel(Markdown(body), title=client.model_name, border_style=accent))
