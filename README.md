# Strategy Agent

A 100% local AI research/strategy agent turning research-heavy tasks into professional
**PDF briefs**, **PowerPoint decks**, and **Excel workbooks** — running entirely on your
machine with no external AI APIs, ever.

> **Status: Phase 2 (Research Engine + Document Reading) complete.** The agent now
> searches the web (SearXNG) and reads PDFs / images / Excel files. Reasoning, output
> generation, memory, and voice land in Phases 3–5. See `PROGRESS.md` for the live status
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
  reading **scanned** PDFs / images. Text PDFs and Excel files need no extra binary.

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
curl "http://localhost:8080/search?q=test&format=json"
```

If SearXNG is down or JSON is disabled, the `research` command fails fast with the exact
fix instructions — the rest of the agent (`ask`, REPL, `analyze-doc`) still works without it.

## Usage

```powershell
# Single question
python main.py ask "Was macht Neura Robotics?"

# Web research — ranked, deduplicated, source-tiered results (needs SearXNG)
python main.py research "Figure AI funding 2026"
python main.py research "humanoid robotics market" --max-fetch 3

# Read a document (PDF / image / .xlsx) and print extracted content
python main.py analyze-doc path\to\report.pdf
python main.py analyze-doc path\to\pipeline.xlsx

# Interactive REPL (type 'exit' to quit) — you can also drop a file path to read it
python main.py

# Use a different config file
python main.py --config path\to\config.yaml ask "..."
```

On startup the agent checks that the LLM backend is reachable and the configured model is
available; `research` additionally checks SearXNG. If a check fails, it prints exact fix
instructions and exits (fail fast).

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

## Project layout (through Phase 2)

```
config.yaml            # single source of all tunable params
main.py                # entry point: ask / research / analyze-doc / REPL
core/                  # config, startup checks, REPL intake,
                       #   researcher (SearXNG + fetch + cache),
                       #   pdf_reader, excel_reader
llm/                   # backend-agnostic LocalLLMClient (text + Ollama vision)
models/                # Pydantic v2 data contracts (all phases)
tests/                 # pytest suite
docker-compose.yml     # SearXNG
```

`brain.md` (agent context) is **gitignored** and local-only; it is seeded in Phase 5.

## Development

```powershell
python -m pytest tests/ -v             # run tests (live LLM/SearXNG tests skip if those are down)
ruff format . ; ruff check .           # format + lint
mypy --strict core llm models main.py  # type-check core modules
```
