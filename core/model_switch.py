"""In-session AI-model switching for the REPL (``/model``) — one source of truth for the choices.

The picker shows the **real, recognisable model names** (e.g. ``Gemma 4 E4B``); the internal LM
Studio identifiers stay under the hood. Switching **reuses the proven PowerShell boot scripts**
instead of re-implementing the machine-specific cold-start (Norton TLS, the LM Studio runtime, the
8 GB VRAM offload policy). For a local model that means: ``switch-model.ps1 <profile>`` writes the
``llm:`` block of config.yaml, then ``porter.local.ps1`` brings LM Studio up and loads the model —
exactly what typing ``porter`` / ``porter12b`` does today. The caller then rebuilds the live client
from the reloaded config.

Names map 1:1 to ``switch-model.ps1`` / ``porter.local.ps1`` (no invented identifiers):
``Gemma 4 E4B`` → ``Porter-LMStudio`` (google/gemma-4-e4b), ``Gemma 4 12B`` → ``Porter-12B``
(google/gemma-4-12b). Nemotron (cloud) is added in a later slice.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from core.config import AppConfig, LLMConfig, load_config

_ROOT = Path(__file__).resolve().parent.parent


class ModelSwitchError(Exception):
    """A model switch could not be applied (unknown choice, missing script, or boot failure)."""


@dataclass(frozen=True)
class ModelChoice:
    """One user-facing model: the real name shown, plus how to boot/identify it.

    ``value`` is the stable picker id and ``/model <value>`` shortcut. ``served_id`` is the internal
    ``llm.model`` identifier used to detect the active entry. ``switch_profile`` is the
    ``switch-model.ps1`` profile that writes the right ``llm:`` block for a local (LM Studio) model.
    """

    value: str
    title: str
    hint: str
    kind: str  # "lmstudio" | "nemotron"
    switch_profile: str = ""
    served_id: str = ""


# Order = picker order. Real names first so the user instantly sees what is running.
MODELS: list[ModelChoice] = [
    ModelChoice(
        value="gemma4-e4b",
        title="Gemma 4 E4B",
        hint="fast · local (LM Studio)",
        kind="lmstudio",
        switch_profile="gemma4",
        served_id="Porter-LMStudio",
    ),
    ModelChoice(
        value="gemma4-12b",
        title="Gemma 4 12B",
        hint="smart · local (LM Studio)",
        kind="lmstudio",
        switch_profile="porter12b",
        served_id="Porter-12B",
    ),
    # Nemotron 3 Ultra 550B (cloud) is wired in a later slice.
]


def find_model(value: str) -> ModelChoice | None:
    """Return the registry entry for ``value`` (case-insensitive), or ``None`` if unknown."""
    key = (value or "").strip().lower()
    for model in MODELS:
        if model.value == key:
            return model
    return None


def active_model_value(llm: LLMConfig) -> str | None:
    """Match the live ``llm`` config to a registry entry (by served identifier), else ``None``."""
    for model in MODELS:
        if model.kind == "lmstudio" and llm.model == model.served_id:
            return model.value
    return None


def _powershell() -> str:
    """Resolve a PowerShell executable (Windows ``powershell`` or cross-platform ``pwsh``)."""
    return shutil.which("powershell") or shutil.which("pwsh") or "powershell"


def _run_ps(script: Path, args: list[str], *, quiet: bool) -> int:
    """Run a repo PowerShell script from the project root; return its exit code.

    ``quiet`` discards output (used for the config edit); otherwise output is inherited so the user
    sees the live boot progress — the same messages ``porter`` prints.
    """
    if not script.is_file():
        raise ModelSwitchError(f"Required script not found: {script.name}")
    cmd = [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args]
    if quiet:
        completed = subprocess.run(
            cmd, cwd=str(_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
    else:
        completed = subprocess.run(cmd, cwd=str(_ROOT), check=False)
    return completed.returncode


def _boot_lmstudio(choice: ModelChoice, console: Console) -> None:
    """Apply a local model: write the config (quiet) then cold-start LM Studio (visible)."""
    # 1. Edit the llm: block of config.yaml (quiet — like porter12b.ps1 does with *> $null).
    _run_ps(_ROOT / "switch-model.ps1", [choice.switch_profile], quiet=True)
    # 2. Cold-start the backend + load the model. porter.local.ps1 reads the just-written config and
    #    self-heals the LM Studio runtime; it is absent on a fresh clone (Ollama path) — then skip.
    hook = _ROOT / "porter.local.ps1"
    if hook.is_file():
        _run_ps(hook, [], quiet=False)
    else:
        console.print(
            "[dim]porter.local.ps1 not present — config updated; "
            "the model loads on next launch.[/dim]"
        )


def apply_model(value: str, config_path: Path, console: Console) -> AppConfig:
    """Switch Porter to model ``value``, booting whatever it needs, and return the reloaded config.

    Reuses the proven boot scripts (see module docstring). Raises :class:`ModelSwitchError` on an
    unknown choice or a missing script. The caller rebuilds its :class:`LocalLLMClient` from the
    returned config. This never touches ``.porter_profile`` — the active role is independent.
    """
    choice = find_model(value)
    if choice is None:
        raise ModelSwitchError(
            f"Unknown model '{value}'. Choose: {', '.join(m.value for m in MODELS)}."
        )
    if choice.kind == "lmstudio":
        _boot_lmstudio(choice, console)
    else:  # pragma: no cover - cloud branch lands in a later slice
        raise ModelSwitchError(f"Model '{choice.title}' is not wired yet.")
    return load_config(config_path)
