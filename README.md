# Strategy Agent

A 100% local AI research/strategy agent turning research-heavy tasks into professional
**PDF briefs**, **PowerPoint decks**, and **Excel workbooks** — running entirely on your
machine with no external AI APIs, ever.

> **Status: Phase 3.5 (Advanced Agent Loop) complete.** The agent is now a non-linear,
> self-correcting, multi-agent loop. A single **effort dial** (`low` / `high` / `ultra`,
> auto-detected and overridable) drives the whole run. A **research manager** decomposes the task
> and runs **N parallel research workers**, each following an explicit deep-research methodology
> (authoritative + recent + cross-referenced sources; a source, date, and confidence on every
> fact). It can pause **mid-research** to ask a precise question, then an **output critic** scores
> the draft against a rubric and forces targeted **revisions** before delivery. File rendering
> (PDF/PPTX/Excel), memory, and voice land in Phases 4–5. See `PROGRESS.md` for the live status
> and `strategy_agent_SPEC.md` (incl. §15.5) for the full specification.

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

## Usage

```powershell
# Full agent run (intent → clarify → multi-agent research → critique/revise → analysis).
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

## Project layout (through Phase 3.5)

```
config.yaml            # single source of all tunable params (incl. the effort dial)
main.py                # entry point: analyze [--effort] / ask / research / analyze-doc / REPL
core/                  # config (+ effort), startup checks, REPL intake (+ pipeline wiring),
                       #   researcher (SearXNG + fetch + cache), pdf_reader, excel_reader,
                       #   intent_parser (+ effort detection), clarification, memory (brain inject),
                       #   playbooks, synthesizer, research_agent (worker + manager),
                       #   critic (critique + revise), pipeline (the master loop), json_utils
llm/                   # backend-agnostic LocalLLMClient (text + Ollama vision)
models/                # Pydantic v2 data contracts (all phases)
playbooks/             # research / analysis / output / deep_research rulebooks
tests/                 # pytest suite (127 tests)
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
