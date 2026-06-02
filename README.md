# Porter — local Strategy Agent

**Porter** is a 100% local AI research/strategy agent that turns research-heavy tasks into
professional **PDF briefs**, **PowerPoint decks**, and **Excel workbooks** — running entirely on
your machine with no external AI APIs, ever. Type `porter` in your terminal to start chatting.

> **Status: Phase 5 (Memory + Voice + Polish) complete — the project is finished.** The agent is
> production-ready end-to-end: it understands a task (text **or voice**), asks at most a couple of
> clarifying questions, runs multi-agent web research, reasons with persistent Neura context, and
> renders the three real deliverables. New in Phase 5:
> - **Persistent memory (ChromaDB + `nomic-embed-text`, fully local):** every run's analysis is
>   embedded and stored; before each new run the agent retrieves relevant prior findings and, on a
>   **second run about the same entity, shows a bilingual delta** — *"Since our last analysis of X
>   (date, N weeks ago): …what changed."*
> - **Brain-update flow:** after a run the agent proposes durable, high-signal additions to
>   `brain.md`; you confirm `[y/N]` before anything is written.
> - **Voice input (local):** press **Ctrl+Space** (or type `/voice`) to dictate — pyaudio captures,
>   faster-whisper transcribes locally (DE/EN auto-detect), and the transcript lands in the prompt.
> - **`porter` launcher:** one word in PowerShell starts the agent.
>
> Earlier phases still apply: a **PDF brief** (Jinja2 → WeasyPrint, T-1..T-6), a **Neura-styled
> PPTX deck** (python-pptx, all 10 slide types, logo bottom-right), and a **formula-driven Excel
> workbook** (openpyxl, 4 templates — change a yellow input and scores/ranks/NPV/IRR recalculate).
> A **business case** emits a deck **and** a financial model in one run. One **effort dial**
> (`low`/`high`/`ultra`, auto-detected and overridable) drives a multi-agent **research manager**,
> **mid-research** clarification, and an **output critic + revision** loop. Memory and voice are
> **advisory / fail-open** — if a dependency is missing the agent prints the exact fix and still
> delivers. See `PROGRESS.md` for the full build log.
>
> **PDF note (Windows):** PPTX + Excel are fully local and work out of the box. PDF briefs use
> WeasyPrint, which needs the **GTK/Pango runtime** on Windows — install it once via MSYS2 (see
> [PDF rendering](#pdf-rendering-weasyprint-gtk) below) and PDF renders with zero code changes. The
> agent auto-detects the runtime; until it is present it fails fast with exact instructions and
> still ships the other deliverables.

---

## Prerequisites

- **Python 3.11+** (developed on 3.12).
- **[Ollama](https://ollama.com/download)** running locally, with the default model + the
  embedding model pulled:
  ```bash
  ollama pull gemma4:e4b        # reasoning model
  ollama pull nomic-embed-text  # embeddings for persistent memory (CPU, no VRAM use)
  ```
  Prefer **[LM Studio](https://lmstudio.ai)** (e.g. a more compact ~6.3 GB Q4_K_M of the same Gemma
  model that fits an 8 GB GPU)? It's a first-class alternative — see
  [Switching backend with one command](#switch-llm). One `switch-llm.ps1 lmstudio` and you're on it.
- **[Docker Desktop](https://docker.com)** — needed for the `research` command (SearXNG web
  search). The VS Code Docker extension is **not** enough; install the actual Docker Desktop app.
- **[Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)** — *optional*, only for
  reading **scanned** PDFs / images. Text PDFs and Excel files need no extra binary. On Windows,
  add its install dir (e.g. `C:\Program Files\Tesseract-OCR`) to your PATH and **restart the
  terminal** so `pytesseract` can find `tesseract.exe`.

## Setup

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. Install Phase 1 + Phase 2 dependencies
pip install pydantic pyyaml typer rich python-dotenv openai requests httpx pytest pytest-asyncio ruff mypy
pip install aiohttp trafilatura diskcache pdfplumber pytesseract Pillow pandas openpyxl

# 3. Install Phase 4 output dependencies (PPTX/Excel work immediately; PDF needs GTK — see below)
pip install python-pptx openpyxl xlsxwriter jinja2 weasyprint

# 4. Install Phase 5 dependencies — memory (always-on) + voice (optional)
pip install chromadb                       # persistent memory (local vector store)
pip install faster-whisper pyaudio pynput  # voice input (only needed if you enable voice)
```

`requirements.txt` lists the **full** dependency set for all phases. The heavier
Phase 4–5 libraries (weasyprint, pyaudio, faster-whisper, chromadb, …) often need extra
system libraries on Windows, so they are installed in the phase that first needs them.
To install everything at once:

```powershell
pip install -r requirements.txt
```

### SearXNG (web search, required for `research`)

```powershell
docker compose up -d
```

SearXNG disables its JSON API by default. Enable it once in `searxng-data/settings.yml`
(created on first container start), then restart:

```yaml
search:
  formats:
    - html
    - json
```

```powershell
docker compose restart
# Verify:
curl "http://localhost:8888/search?q=test&format=json"
```

If SearXNG is down or JSON is disabled, the `research` command fails fast with the exact
fix instructions — the rest of the agent (`ask`, REPL, `analyze-doc`) still works without it.

### PDF rendering (WeasyPrint GTK) <a name="pdf-rendering-weasyprint-gtk"></a>

PPTX and Excel outputs are pure Python and work out of the box. **PDF briefs** use WeasyPrint,
which on **Windows** needs the **GTK/Pango runtime** (Pango/Cairo/GLib). See the official
[GTK on Windows guide](https://www.gtk.org/docs/installations/windows/). Two one-time options:

**Recommended — MSYS2** (the agent auto-detects `C:\msys64\mingw64\bin`):

1. Install [MSYS2](https://www.msys2.org/) (keep the default `C:\msys64`).
2. Open the **"MSYS2 MINGW64"** terminal and run: `pacman -S mingw-w64-x86_64-pango`
   (pulls in cairo/glib/harfbuzz — everything WeasyPrint needs).
3. **Reopen** the VS Code terminal and re-run — PDF now renders, no code changes.

**Alternative — GTK3 runtime installer:** open the
[GTK-for-Windows repo](https://github.com/tschoonj/GTK-for-Windows-Runtime-Installer) → **Releases**
→ download `gtk3-runtime-*-win64.exe`, run it and **tick "Set up PATH"**, then reopen the terminal.

The agent automatically puts a detected GTK/Pango runtime **ahead of** any conflicting `libgobject`
on `PATH` (e.g. one shipped by Tesseract). If it lives in a non-standard folder, point the agent at
its `bin` directory via `output.gtk_runtime_path` in `config.yaml`. Until it is present, PDF
rendering fails fast with these instructions while PPTX/Excel still ship.

### The `porter` command (type one word to start)

A `porter.ps1` launcher runs the agent REPL from the project root using the venv Python (any
arguments pass through to `main.py`). To type just `porter` from any terminal, add a function to
your PowerShell `$PROFILE`:

```powershell
# One-time: add a 'porter' function pointing at the launcher
Add-Content $PROFILE "`nfunction porter { & 'C:\path\to\strategy agent\porter.ps1' @args }"
. $PROFILE   # reload (new terminals load it automatically)
```

Then:

```powershell
porter                                  # interactive REPL — chat with Porter
porter ask "Was macht Neura Robotics?"  # one-shot question
porter analyze "..." --effort ultra     # full pipeline, non-interactive
```

### Persistent memory & delta analysis

With `memory.enabled: true` (default) and `nomic-embed-text` pulled, every run's analysis is
embedded (`nomic-embed-text`, CPU) and stored in a local **ChromaDB** at `data/chroma_db/`. Before
each new run the agent retrieves relevant prior findings and injects them; when you analyze the
**same company a second time** it opens with a bilingual delta:

> *Since our last analysis of Figure AI (2026-05-11, 3 weeks ago): the company announced a new
> humanoid model and closed a fresh funding round…*

After a run the agent may propose durable additions to `brain.md` (audience preferences, strategic
facts) — you confirm `[y/N]` before anything is written. Memory is **advisory**: if ChromaDB or the
embedding model is missing, the agent prints the exact fix and still delivers (it never blocks).
The store is local and private — `data/chroma_db/` is gitignored.

### Voice input (Ctrl+Space, fully local)

Set `voice.enabled: true` in `config.yaml` (and install `faster-whisper pyaudio pynput`). In the
REPL, press **Ctrl+Space** to dictate — a small overlay shows while pyaudio records, faster-whisper
transcribes locally (DE/EN auto-detect), and the transcript is typed into the prompt as if you'd
typed it. Or type **`/voice`** to speak a single task. faster-whisper downloads its model once on
first use, then runs entirely offline. Voice is **additive** — disabled by default, it adds no hard
dependency to the text REPL, and any mic/model failure prints an exact fix without breaking the REPL.
Tune `voice.model` (size), `voice.language`, `voice.hotkey`, and `voice.max_record_seconds` in config.

## Usage

```powershell
# Full agent run (intent → clarify → multi-agent research → critique/revise → analysis →
# rendered deliverables in ./output/). The task type picks the format(s): a screen → Excel
# decision matrix + PDF brief; a business case → PPTX deck + Excel model (both, in one run).
python main.py analyze "Screen these 5 European robotics startups as M&A targets"
python main.py analyze "Business case for Japan expansion: market size, investment, ROI"

# Effort master dial — auto-detected from the task, overridable with --effort:
python main.py analyze --effort ultra "Vollständige Analyse von 1X Technologies — Funding, Tech, Strategie"
python main.py analyze --effort low "Latest humanoid robotics funding news"

# Interactive REPL — the primary experience. Free text runs the full agent pipeline:
# it asks one-at-a-time clarifying questions, shows the research plan + effort to confirm,
# then runs the multi-agent research and produces a structured analysis. Prefix with
# '/effort low|high|ultra' to override (alone, it sets the session default). Drop a file
# path to read a document. Press Ctrl+Space (or type '/voice') to dictate if voice is on.
porter                    # or: python main.py   — type 'exit' to quit

# Single question — a plain one-shot LLM answer, no research, no clarification
python main.py ask "Was macht Neura Robotics?"

# Web research — ranked, deduplicated, source-tiered results (no synthesis)
python main.py research "Figure AI funding 2026"
python main.py research "humanoid robotics market" --max-fetch 3

# Prepare internal documents for management — NO web research (CEO-office mode).
# Deep-reads several files, asks a few targeted questions, consolidates them into one
# management briefing with zero hallucination (every figure traced to its source), writes a
# Markdown blueprint (Spickzettel) to ./output/, and RENDERS the deliverable(s):
#   --format deck  → Neura-styled .pptx (works locally)
#   --format brief → .pdf  (needs WeasyPrint's GTK runtime; skipped with instructions if absent)
#   --format both  → both (default)
# If it can't tell whether you want internal prep or web research, it asks you.
python main.py prepare board_pack.pdf q2_financials.xlsx --task "Consolidate for the board" --format deck

# Read a single document (PDF / image / .xlsx) and print extracted content (no synthesis)
python main.py analyze-doc path\to\report.pdf
python main.py analyze-doc path\to\pipeline.xlsx

# Use a different config file
python main.py --config path\to\config.yaml ask "..."
```

**`analyze` vs the REPL vs `ask`:** `analyze` runs the full pipeline non-interactively
(clarifications auto-answered with sensible defaults, research plan auto-confirmed) — ideal for
scripting. The **REPL** (`python main.py`) is the interactive version: it actually asks the
clarifying questions and lets you confirm or decline the research plan (declining gives a quick
`brain.md`-grounded answer instead). `ask` is a simple one-shot with no research.

On startup the agent checks that the LLM backend is reachable and the configured model is
available; `analyze`/`research` additionally check SearXNG. If a check fails, it prints exact
fix instructions and exits (fail fast). Output language follows the input (German in → German
out, English in → English out).

## Configuration

Everything tunable lives in **`config.yaml`** — nothing is hardcoded.

- **Switch model:** change `llm.model` (e.g. `qwen3:8b`) and `ollama pull` it. Zero code changes.
- **Switch backend:** change `llm.provider` + `llm.base_url`:
  | Backend | provider | base_url |
  |---------|----------|----------|
  | Ollama (default) | `ollama` | `http://localhost:11434` |
  | LM Studio | `lmstudio` | `http://localhost:1234` |
  | llama.cpp server | `llamacpp` | `http://localhost:8080` |
- **Context window:** `llm.num_ctx` (default 32768) is sent on **every** LLM call. Ollama
  otherwise silently defaults all models to 4096 tokens — this agent never relies on that default.

### Switching backend with one command — Ollama ↔ LM Studio (`switch-llm.ps1`) <a name="switch-llm"></a>

Prefer **LM Studio**? It often ships a **more compact quant** of the same model than Ollama — e.g.
`google/gemma-4-e4b` (Gemma 4, effective 4B) is **~6.3 GB (Q4_K_M)** in LM Studio vs ~9.6 GB in Ollama,
so it fits fully in an **8 GB GPU** (e.g. RTX 4060) and runs faster with no VRAM overflow. A
`switch-llm.ps1` helper flips the backend cleanly and reversibly — it edits **only** the four `llm.*`
fields in `config.yaml` (`provider`, `base_url`, `model`, `embedding_model`); nothing else is touched,
nothing is deleted, and both backends stay installed.

```powershell
.\switch-llm.ps1            # show the active backend (changes nothing)
.\switch-llm.ps1 lmstudio   # route the agent at LM Studio (:1234)
.\switch-llm.ps1 ollama     # route the agent back at Ollama (:11434)
```

When switching to `lmstudio` the script **auto-detects** the loaded chat + embedding model ids from the
running LM Studio server (`/v1/models`), so you never hand-edit them. After a switch, `porter` and every
command use the new backend automatically.

**Activate LM Studio first (it does not auto-serve like Ollama).** Install [LM Studio](https://lmstudio.ai),
download the model in-app (search `gemma-4-e4b`, Q4_K_M), then start the server + load the model — and the
embedding model for memory:

```powershell
lms server start                                             # OpenAI-compatible API on :1234
lms get text-embedding-nomic-embed-text-v1.5                 # embeddings for persistent memory
lms load google/gemma-4-e4b --context-length 32768 --gpu max -y
.\switch-llm.ps1 lmstudio                                    # point Porter at LM Studio
```

(Or enable **"Run server at login"** + **JIT model loading** in the LM Studio app so it serves
automatically after a reboot.) Notes: embeddings are 768-dim on both backends (same `nomic-embed-text`
model), so the ChromaDB memory store stays compatible — no rebuild. **Vision** (reading scanned/image
PDFs *via the LLM*) is Ollama-only; under LM Studio, text-PDF + Tesseract OCR still work, and PPTX/PDF/Excel
**rendering is pure Python** so output quality is identical on both backends. If the LM Studio server is
down, commands fail fast with instructions — switch back with `.\switch-llm.ps1 ollama` anytime.

### Effort master dial (`effort:` block)

One knob controls the whole loop's intensity. Each level sets the number of research workers,
research rounds, fetch depth per worker, clarification + mid-research budgets, revisions, and
whether the critic and thinking mode run:

| Level | workers | rounds | fetch/worker | clarif. | mid-research Q | revisions | critique | thinking |
|-------|:------:|:------:|:-----------:|:------:|:-------------:|:--------:|:-------:|:-------:|
| `low`   | 1 | 1 | 3 | 1 | 0 | 0 | off | off |
| `high`  | 3 | 2 | 5 | 2 | 1 | 1 | on  | on  |
| `ultra` | 5 | 3 | 8 | 3 | 2 | 2 | on  | on  |

Effort is **auto-detected** from the task (explicit words like "ultra"/"vollständig" → ultra,
"quick"/"kurz" → low; heavy task types floor at high; default high when unsure) and **overridable**
via `--effort` / the REPL `/effort` prefix. `effort.worker_concurrency` caps how many workers truly
run at once — modest on a laptop (one local model serializes LLM calls), raised on a server. After a
hardware upgrade you just edit these numbers — **zero code changes** to scale.

## Project layout

```
config.yaml            # single source of all tunable params (effort dial, memory, voice, colors)
porter.ps1             # 'porter' launcher — starts the REPL from the project root
main.py                # entry point: analyze [--effort] / ask / research / prepare / analyze-doc / REPL
core/                  # config (+ effort/memory/voice), startup checks, REPL intake (+ pipeline,
                       #   memory + voice wiring), researcher (SearXNG + fetch + cache), pdf_reader,
                       #   excel_reader, intent_parser (+ effort detection), clarification,
                       #   memory (brain inject + ChromaDB store + delta + brain-update),
                       #   voice_input (Ctrl+Space → faster-whisper), playbooks, synthesizer,
                       #   research_agent (worker + manager), critic (critique + revise),
                       #   pipeline (the master loop), json_utils, content_shaper, exporter
                       #   (PDF + PPTX), excel_builder (E-1..E-4), doc_synthesis (CEO-office mode)
llm/                   # backend-agnostic LocalLLMClient (text + Ollama vision + embeddings)
models/                # Pydantic v2 data contracts (all phases)
templates/briefs/      # Jinja2 brief templates T-1..T-6 (+ shared Neura CSS/macros)
assets/                # neura_logo.png (deck logo, bottom-right)
playbooks/             # research / analysis / output / deep_research / doc_prep rulebooks
data/chroma_db/        # persistent memory (gitignored, local-only)
tests/                 # pytest suite (221 tests)
docker-compose.yml     # SearXNG
```

`brain.md` (agent context) is **gitignored** and local-only; it is injected (read-only) into
every synthesis call and is seeded with the public Neura context. The persistent memory store
(`data/chroma_db/`) is likewise gitignored and never leaves your machine.

## Development

```powershell
python -m pytest tests/ -v             # run tests (live LLM/SearXNG tests skip if those are down)
ruff format . ; ruff check .           # format + lint
mypy --strict core llm models main.py  # type-check core modules
```
