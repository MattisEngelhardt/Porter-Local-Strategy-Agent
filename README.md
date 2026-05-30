# Strategy Agent

A 100% local AI research/strategy agent turning research-heavy tasks into professional
**PDF briefs**, **PowerPoint decks**, and **Excel workbooks** — running entirely on your
machine with no external AI APIs, ever.

> **Status: Phase 3 (Agent Brain) complete.** The agent now understands a task, asks up to
> 3 smart clarifying questions (one at a time), decomposes it, runs web research, injects
> persistent Neura context (`brain.md`) + the three playbooks, and reasons into a **structured
> analysis** (bottom line → sections → sources) in the input's language (DE/EN). File rendering
> (PDF/PPTX/Excel), memory, and voice land in Phases 4–5. See `PROGRESS.md` for the live status
> and `strategy_agent_SPEC.md` for the full specification.

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
# Full agent run (intent → clarify → research → structured analysis). Needs SearXNG.
python main.py analyze "Screen these 5 European robotics startups as M&A targets"
python main.py analyze "Business case for Japan expansion: market size, investment, ROI"

# Interactive REPL — the primary experience. Free text runs the full agent pipeline:
# it asks up to 3 one-at-a-time clarifying questions, shows a research plan to confirm,
# then researches and produces a structured analysis. Drop a file path to read a document.
python main.py            # type 'exit' to quit

# Single question — a plain one-shot LLM answer, no research, no clarification
python main.py ask "Was macht Neura Robotics?"

# Web research — ranked, deduplicated, source-tiered results (no synthesis)
python main.py research "Figure AI funding 2026"
python main.py research "humanoid robotics market" --max-fetch 3

# Read a document (PDF / image / .xlsx) and print extracted content
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

## Project layout (through Phase 3)

```
config.yaml            # single source of all tunable params
main.py                # entry point: analyze / ask / research / analyze-doc / REPL
core/                  # config, startup checks, REPL intake (+ pipeline wiring),
                       #   researcher (SearXNG + fetch + cache), pdf_reader, excel_reader,
                       #   intent_parser, clarification, memory (brain.md inject),
                       #   playbooks, synthesizer, pipeline (the reasoning chain), json_utils
llm/                   # backend-agnostic LocalLLMClient (text + Ollama vision)
models/                # Pydantic v2 data contracts (all phases)
playbooks/             # research / analysis / output rulebooks injected into synthesis
tests/                 # pytest suite (88 tests)
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
