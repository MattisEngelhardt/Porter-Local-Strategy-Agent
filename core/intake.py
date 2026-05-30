"""Interactive REPL intake layer (Phase 1: text only).

A minimal, rich-formatted chat loop over :class:`LocalLLMClient`. File-path detection
(routing to pdf/excel readers) is a Phase 2 feature and voice input (Ctrl+Space) is a
Phase 5 feature — both are intentionally left as TODOs here and import no Phase 2+ code.
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from core.config import AppConfig
from llm.local_llm_client import LLMError, LocalLLMClient

EXIT_COMMANDS = {"exit", "quit", ":q", "q"}


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
            "Type your question. Type [bold]exit[/bold] to quit.",
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

        # TODO(Phase 2): detect bare file paths in `text` -> route to pdf_reader/excel_reader.
        # TODO(Phase 5): voice input via Ctrl+Space overlay -> inject transcript here.
        _answer(client, console, text, accent)


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
