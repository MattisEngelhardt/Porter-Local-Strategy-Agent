# Strategy Agent

A 100% local AI research/strategy agent turning research-heavy tasks into professional
**PDF briefs**, **PowerPoint decks**, and **Excel workbooks** — running entirely on your
machine with no external AI APIs, ever.

> **Status: Phase 4 (Output Generation) complete.** The agent now turns its analysis into the
> three real deliverables — a **PDF brief** (Jinja2 → WeasyPrint, templates T-1..T-6), a
> **Neura-styled PPTX deck** (python-pptx, all 10 slide types, logo bottom-right), and an **Excel
> workbook** (openpyxl, 4 templates: Decision Matrix · Benchmark · Business-Case model · Tracker).
> Excel workbooks are **formula-driven** — change a yellow input cell and weighted scores, ranks,
> NPV/IRR and projections recalculate in MS Excel (no hardcoded intermediates). A **business case**
> emits a deck **and** a financial model in one run. Rendering is wired into both the research and
> the CEO-office document-prep paths and is **fail-open** (a renderer failure never loses the
> analysis). Built on the Phase-3.5 loop: one **effort dial** (`low` / `high` / `ultra`,
> auto-detected and overridable) drives a multi-agent **research manager** (N parallel workers,
> source + date + confidence on every fact), **mid-research** clarification, and an **output
> critic** + **revision** loop. Memory (ChromaDB) and voice land in Phase 5. See `PROGRESS.md` for
> live status and `strategy_agent_SPEC.md` (incl. §15.5) for the full specification.
>
> **PDF note (Windows):** PPTX + Excel are fully local and work out of the box. PDF briefs use
> WeasyPrint, which needs the **GTK3 runtime** on Windows. Install it once (see
> [PDF rendering](#pdf-rendering-weasyprint-gtk) below) and PDF renders with zero code changes;
> until then the agent fails fast with exact instructions and still ships the other deliverables.

---

## Prerequisites

- **Python 3.11+** (developed on 3.12).
- **[Ollama](https://ollama.com/download)** running locally, with the default model pulled:
  ```bash
  ollama pull gemma4:e4b
  ```
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
which on **Windows** needs the **GTK3 runtime** (Pango/Cairo/GObject). One-time install:

1. Download the GTK3 runtime installer from the
   [GTK-for-Windows releases](https://github.com/tschoonj/GTK-for-Windows-Runtime-Installer/releases/latest)
   (`gtk3-runtime-*-win64.exe`).
2. Run it and **tick "Set up PATH environment variable to include GTK+"**.
3. **Reopen the terminal** and re-run — PDF now renders, no code changes.

The agent automatically puts a detected GTK runtime ahead of any conflicting `libgobject` on
`PATH` (e.g. one shipped by Tesseract). If GTK lives in a non-standard folder, point the agent at
its `bin` directory via `output.gtk_runtime_path` in `config.yaml`. Until GTK is present, PDF
rendering fails fast with these instructions while PPTX/Excel still ship.

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
# path to read a document.
python main.py            # type 'exit' to quit

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

## Project layout (through Phase 4)

```
config.yaml            # single source of all tunable params (effort dial, Neura colors, GTK path)
main.py                # entry point: analyze [--effort] / ask / research / prepare / analyze-doc / REPL
core/                  # config (+ effort), startup checks, REPL intake (+ pipeline wiring),
                       #   researcher (SearXNG + fetch + cache), pdf_reader, excel_reader,
                       #   intent_parser (+ effort detection), clarification, memory (brain inject),
                       #   playbooks, synthesizer, research_agent (worker + manager),
                       #   critic (critique + revise), pipeline (the master loop), json_utils,
                       #   content_shaper (analysis → typed deck/workbook), exporter (PDF + PPTX),
                       #   excel_builder (E-1..E-4, formula-driven), doc_synthesis (CEO-office mode)
llm/                   # backend-agnostic LocalLLMClient (text + Ollama vision)
models/                # Pydantic v2 data contracts (all phases)
templates/briefs/      # Jinja2 brief templates T-1..T-6 (+ shared Neura CSS/macros)
assets/                # neura_logo.png (deck logo, bottom-right)
playbooks/             # research / analysis / output / deep_research / doc_prep rulebooks
tests/                 # pytest suite (177 tests)
docker-compose.yml     # SearXNG
```

`brain.md` (agent context) is **gitignored** and local-only; it is injected (read-only) into
every synthesis call in Phase 3 and seeded with content in Phase 5.

## Development

```powershell
python -m pytest tests/ -v             # run tests (live LLM/SearXNG tests skip if those are down)
ruff format . ; ruff check .           # format + lint
mypy --strict core llm models main.py  # type-check core modules
```
