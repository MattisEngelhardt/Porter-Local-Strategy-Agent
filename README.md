# Strategy Agent

A 100% local AI research/strategy agent for two Neura Robotics internship roles
(CEO Office Intern, Strategy Intern). It turns research-heavy tasks into professional
**PDF briefs**, **PowerPoint decks**, and **Excel workbooks** — running entirely on your
machine with no external AI APIs, ever.

> **Status: Phase 1 (Foundation) complete.** The skeleton runs and talks to a local LLM.
> Research, document reading, reasoning, output generation, memory, and voice land in
> Phases 2–5. See `PROGRESS.md` for the live status and `strategy_agent_SPEC.md` for the
> full specification.

---

## Prerequisites

- **Python 3.11+** (developed on 3.12).
- **[Ollama](https://ollama.com/download)** running locally, with the default model pulled:
  ```bash
  ollama pull gemma4:e4b
  ```
- **Docker Desktop** — only needed from Phase 2 (for SearXNG web search). Not required for Phase 1.

## Setup

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. Install Phase 1 dependencies (core subset)
pip install pydantic pyyaml typer rich python-dotenv openai requests httpx pytest pytest-asyncio ruff mypy
```

`requirements.txt` lists the **full** dependency set for all phases. The heavier
Phase 2–5 libraries (weasyprint, pyaudio, faster-whisper, chromadb, …) often need extra
system libraries on Windows, so they are installed in the phase that first needs them.
To install everything at once:

```powershell
pip install -r requirements.txt
```

## Usage

```powershell
# Single question
python main.py ask "Was macht Neura Robotics?"

# Interactive REPL (type 'exit' to quit)
python main.py

# Use a different config file
python main.py --config path\to\config.yaml ask "..."
```

On startup the agent checks that the LLM backend is reachable and the configured model is
available. If not, it prints exact fix instructions and exits (fail fast).

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

## Project layout (Phase 1)

```
config.yaml            # single source of all tunable params
main.py                # entry point: `ask` + REPL
core/                  # config loader, startup checks, REPL intake
llm/                   # backend-agnostic LocalLLMClient
models/                # Pydantic v2 data contracts (all phases)
tests/                 # pytest suite
docker-compose.yml     # SearXNG (Phase 2)
```

`brain.md` (agent context) is **gitignored** and local-only; it is seeded in Phase 5.

## Development

```powershell
python -m pytest tests/ -v      # run tests (a live LLM test skips if Ollama is down)
ruff format . ; ruff check .    # format + lint
mypy --strict core llm models   # type-check core modules
```
