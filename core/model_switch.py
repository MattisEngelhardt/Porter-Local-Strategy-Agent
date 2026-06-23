"""In-session AI-model switching for the REPL (``/model``) — one source of truth for the choices.

The picker shows the **real, recognisable model names** (e.g. ``Gemma 4 E4B``); the internal LM
Studio identifiers stay under the hood. Switching **reuses the proven PowerShell boot scripts**
instead of re-implementing the machine-specific cold-start (Norton TLS, the LM Studio runtime, the
8 GB VRAM offload policy). For a local model that means: ``switch-model.ps1 <profile>`` writes the
``llm:`` block of config.yaml, then ``porter.local.ps1`` brings LM Studio up and loads the model —
exactly what typing ``porter`` / ``porter12b`` does today. The caller then rebuilds the live client
from the reloaded config.

Names map 1:1 to the launchers (no invented identifiers): ``Gemma 4 E4B`` → ``Porter-LMStudio``,
``Gemma 4 12B`` → ``Porter-12B``, ``Nemotron 3 Ultra 550B`` → OpenRouter cloud. The cloud switch
mirrors ``porter-nemotron.ps1`` (key from .env + a certifi/Windows-store CA bundle for this
TLS-inspected machine) but stays in-process: it sets the env and rebuilds the client on the
``openrouter`` provider — no relaunch.
"""

from __future__ import annotations

import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from rich.console import Console

from core.config import AppConfig, LLMConfig, load_config

_ROOT = Path(__file__).resolve().parent.parent

# Nemotron 3 Ultra 550B via OpenRouter (cloud, free tier) — mirrors porter-nemotron.ps1.
_NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
_NEMOTRON_BASE_URL = "https://openrouter.ai/api"  # the OpenAI SDK appends /v1
_CA_BUNDLE_PATH = Path(tempfile.gettempdir()) / "porter-nemotron-cacert.pem"
_CA_BUNDLE_MAX_AGE_S = 12 * 3600


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
    ModelChoice(
        value="nemotron",
        title="Nemotron 3 Ultra 550B",
        hint="cloud · OpenRouter (free tier)",
        kind="nemotron",
    ),
]


def find_model(value: str) -> ModelChoice | None:
    """Return the registry entry for ``value`` (case-insensitive), or ``None`` if unknown."""
    key = (value or "").strip().lower()
    for model in MODELS:
        if model.value == key:
            return model
    return None


def active_model_value(llm: LLMConfig) -> str | None:
    """Match the live ``llm`` config to a registry entry, else ``None``.

    Local models match by served identifier; Nemotron matches by its OpenRouter model id.
    """
    for model in MODELS:
        if model.kind == "lmstudio" and llm.model == model.served_id:
            return model.value
        if model.kind == "nemotron" and llm.model == _NEMOTRON_MODEL:
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


_NEMOTRON_KEY_HELP = (
    "No OpenRouter API key found. Create a free key at https://openrouter.ai/keys (it starts with "
    "'sk-or-...'), then add ONE line to the gitignored .env in the project root:\n"
    "    OPENAI_API_KEY=sk-or-...your-key...\n"
    "and run /model again. (Local models need no key.)"
)


def _resolve_openrouter_key() -> str:
    """Find the OpenRouter key: env (OPENROUTER_API_KEY, OPENAI_API_KEY) then the .env file."""
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    env_path = _ROOT / ".env"
    if env_path.is_file():
        values = dotenv_values(env_path)
        for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
            from_file = values.get(name)
            if from_file and from_file.strip():
                return from_file.strip()
    return ""


def _build_ca_bundle() -> str | None:
    """Combine certifi + the Windows Root/CA stores into a temp PEM; return its path (cached 12h).

    Pure-Python mirror of porter-nemotron.ps1's Get-CaBundle so a mid-session cloud switch works on
    this TLS-inspected box (Norton injects a local root the bundled certifi does not trust) without
    launching the PowerShell launcher. Best-effort: returns ``None`` if nothing could be assembled.
    """
    if _CA_BUNDLE_PATH.is_file():
        age = time.time() - _CA_BUNDLE_PATH.stat().st_mtime
        if age < _CA_BUNDLE_MAX_AGE_S:
            return str(_CA_BUNDLE_PATH)
    parts: list[str] = []
    try:
        import certifi

        parts.append(Path(certifi.where()).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - certifi optional; fall through to the OS store
        pass
    if sys.platform == "win32":
        for store in ("ROOT", "CA"):
            try:
                for cert_bytes, encoding, _trust in ssl.enum_certificates(store):
                    if encoding == "x509_asn":
                        parts.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
            except Exception:  # noqa: BLE001 - a missing/locked store must not abort the switch
                continue
    if not parts:
        return None
    try:
        _CA_BUNDLE_PATH.write_text("\n".join(parts), encoding="ascii", errors="ignore")
    except OSError:
        return None
    return str(_CA_BUNDLE_PATH)


def _apply_nemotron(config_path: Path, console: Console) -> AppConfig:
    """Switch to Nemotron (OpenRouter cloud) in-process: set env, return an ``openrouter`` config.

    Reuses the proven prep from porter-nemotron.ps1 (key + CA bundle) but never relaunches: the
    caller rebuilds the client on the returned config, which the OpenAI transport drives via the
    ``OPENAI_API_KEY`` / ``SSL_CERT_FILE`` env set here.
    """
    key = _resolve_openrouter_key()
    if not key:
        raise ModelSwitchError(_NEMOTRON_KEY_HELP)
    os.environ["OPENAI_API_KEY"] = key  # LocalLLMClient reads this for the OpenAI-compatible call
    bundle = _build_ca_bundle()
    if bundle:
        os.environ["SSL_CERT_FILE"] = bundle  # TLS trust bridge for the inspected network
    else:
        console.print(
            "[dim]note: no CA bundle built — cloud TLS may fail on a TLS-inspected network.[/dim]"
        )
    cfg = load_config(config_path)
    cfg.llm.provider = "openrouter"
    cfg.llm.base_url = _NEMOTRON_BASE_URL
    cfg.llm.model = _NEMOTRON_MODEL
    return cfg


def apply_model(value: str, config_path: Path, console: Console) -> AppConfig:
    """Switch Porter to model ``value``, booting whatever it needs, and return the reloaded config.

    Reuses the proven boot scripts / prep (see module docstring). Raises :class:`ModelSwitchError`
    on an unknown choice, a missing script, or a missing cloud key. The caller rebuilds its
    :class:`LocalLLMClient` from the returned config. Never touches ``.porter_profile`` — the active
    role is independent of the model.
    """
    choice = find_model(value)
    if choice is None:
        raise ModelSwitchError(
            f"Unknown model '{value}'. Choose: {', '.join(m.value for m in MODELS)}."
        )
    if choice.kind == "lmstudio":
        _boot_lmstudio(choice, console)
        return load_config(config_path)
    return _apply_nemotron(config_path, console)
