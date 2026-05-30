# STRATEGY AGENT — PROGRESS LOG
> File location: ./PROGRESS.md
> Read this completely before planning the next phase.

---

## PHASE 1 — Foundation
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-05-30
**Session status**: COMPLETE

### Phase Plan (created at session start)
[x] 1. Scaffold dirs + .gitkeep + .gitignore + .env; git init; first commit "phase-1: project scaffold" (done)
[x] 2. config.yaml (SPEC §8) + core/config.py loader + tests/test_config.py (done — 6/6 pass)
[x] 3. requirements.txt (full, per WORKFLOW §6) + .venv + install Phase 1 core subset (done)
[x] 4. All models/*.py Pydantic v2 types (task, research, synthesis, deck, workbook) (done)
[x] 5. llm/local_llm_client.py (provider-aware) + tests/test_local_llm_client.py (done — 12 unit + 1 live, all pass)
[x] 6. core/startup.py health checks + core/intake.py REPL (done)
[x] 7. main.py (typer: `ask` + REPL), wiring config → startup checks → client (done — gate verified)
[x] 8. docker-compose.yml + README.md (done)
[x] 9. ruff format + ruff check --fix; mypy --strict on llm/ + models/ + core/ + main.py (done — clean; enums → StrEnum)
[x] 10. Verify success gate; write full Phase 1 handoff (this file) (done)

### Estimated scope: Medium (foundation skeleton)
### Critical dependencies: Ollama 0.24.0 (✓ running, gemma4:e4b present), Python 3.12.10 (✓)

---

### Key Technical Decisions Made
| Decision | Choice | Reason |
|----------|--------|--------|
| LLM transport | **Provider-aware** `LocalLLMClient` (config.llm.provider) | SPEC requires both "OpenAI-compatible" (REQ-3) AND "num_ctx always honored" (N-1/RULE 10). Ollama's `/v1` endpoint silently drops `num_ctx` (verified empirically). For `provider:ollama` → native `/api/chat` with `options.num_ctx` (guaranteed); for lmstudio/llamacpp/openai → OpenAI SDK `/v1` + `extra_body` options. Backend switch stays a one-line config change. |
| New file core/config.py | Pydantic config models + loader | Config loading is essential; not named in SPEC §7 tree → justified addition. |
| New file core/startup.py | Health checks (Ollama up? model present?) | SPEC §15 lists startup checks as a Phase-1 deliverable without naming a file → justified. |
| New file pyproject.toml | ruff + mypy + pytest config | Self-contains this repo (pytest was picking up the legacy parent monorepo's pyproject.toml as rootdir); centralizes tooling. Runtime deps stay in requirements.txt. |
| Dependency install | Full requirements.txt written; only Phase 1 core subset installed into .venv | Heavy Phase 2–5 libs (weasyprint, pyaudio, faster-whisper, chromadb) need extra Windows system libs; defer to their phases. Confirmed with user. |
| Git | New independent repo inside the "strategy agent" folder | Matches sibling amadeus_repo / study_agent_repo split; parent monorepo is legacy. Confirmed with user. |

### What Was Built (Completed Tasks)
- **Scaffold + git**: full SPEC §7 directory tree, `.gitkeep`s, `.gitignore` (brain.md/.env/output/data ignored, .gitkeep kept), empty `.env`. New independent git repo.
- **config.yaml** (verbatim SPEC §8) + **core/config.py**: Pydantic v2 `AppConfig` with nested `LLMConfig`/`ResearchConfig`/`MemoryConfig`/`AgentConfig`/`OutputConfig`+`ColorsConfig`/`VoiceConfig`/`LoggingConfig` and `load_config()` (fail-fast on missing/invalid).
- **models/**: all Pydantic contracts — `task.py` (TaskRequest, Intent, ClarificationRound, OutputFormat, Language, TaskType, Depth, Audience), `research.py` (SearchQuery, SearchResult, FetchedContent, DocContent, SourceTier), `synthesis.py` (SynthesisInput, AnalysisOutput, Section, SourceRef), `deck.py` (SlideContent, DeckStructure, SlideType), `workbook.py` (ExcelTemplate, WorkbookContent, SheetDefinition, CellValue). Enums use `StrEnum`.
- **llm/local_llm_client.py**: provider-aware `LocalLLMClient`. `generate()`, `stream_generate()`, `switch_model()`, `model_name`/`backend_url`/`provider` props, `close()`. Ollama→native `/api/chat`; others→OpenAI SDK `/v1`. **num_ctx always in payload.** gemma `<|think|>` / qwen `/think`+`/no_think` thinking-mode injection. Typed error hierarchy (`LLMError`, `LLMConnectionError`).
- **core/startup.py**: `check_llm_backend()` / `list_ollama_models()` — verify backend reachable + model present, raise `StartupError` with exact fix instructions.
- **core/intake.py**: rich REPL (`run_repl`) with welcome panel, spinner, Markdown answer panels, config-driven accent color. File-path/voice routing left as Phase 2/5 TODOs.
- **main.py**: typer CLI — `ask "<q>"` + no-arg REPL, `--config`, fail-fast bootstrap, forced UTF-8 stdout for bilingual output.
- **docker-compose.yml** (SearXNG, Phase 2), **README.md**, **pyproject.toml** (ruff/mypy/pytest), **requirements.txt** (full, phase-grouped).

### Files Created/Modified
| File | Status | Key Contents |
|------|--------|-------------|
| config.yaml | Created | Full SPEC §8 schema |
| core/config.py | Created | AppConfig + nested models + load_config |
| core/startup.py | Created | LLM backend health checks (fail fast) |
| core/intake.py | Created | rich REPL loop |
| llm/local_llm_client.py | Created | Provider-aware client; always sends num_ctx |
| models/*.py (5 + __init__) | Created | All Pydantic v2 data contracts |
| main.py | Created | typer CLI: ask + REPL |
| tests/test_config.py | Created | 6 tests |
| tests/test_local_llm_client.py | Created | 11 unit + 1 live test |
| requirements.txt / pyproject.toml | Created | deps (full) + tooling config |
| docker-compose.yml / README.md | Created | SearXNG (Phase 2) + setup guide |
| .gitignore / .env | Created | brain.md/.env/output/data ignored |

### Implementation Gaps Encountered (from SPEC)
- **num_ctx vs OpenAI-compatibility conflict** (see decision above). Resolved conservatively per RULE 9.
- **assets/neura_logo.png** referenced in SPEC §7 as "provided" but is absent on disk. Not a Phase 1 blocker (used in Phase 4). Directory created; logo must be added before Phase 4.
- **brain.md** already exists on disk (4.9 KB). Per SPEC §9 N-9 it is gitignored and owned by Phase 5; left untouched this session.

### Tests Status
- tests/test_config.py: ✅ 6/6 passing
- tests/test_local_llm_client.py: ✅ 12/12 passing (11 offline unit + 1 live against gemma4:e4b)
- **Total: 18/18 passing.** `ruff format`/`ruff check`: clean. `mypy --strict core llm models main.py`: clean (13 files).

### Success Gate — Verified
- `python main.py ask "Was macht Neura Robotics?"` → real German response from gemma4:e4b ✅
- `python main.py` → rich REPL starts, answers, exits cleanly ✅
- Config-only model switch: ran `ask` against `amadeus:latest` via `--config` (zero code changes) ✅
- num_ctx=32768 confirmed in every outgoing payload ✅
- Fail-fast verified: unreachable backend AND missing model → exact fix instructions + exit code 1 ✅

### Git Log (this session)
- phase-1: project scaffold
- phase-1: config.yaml + Pydantic config loader + pyproject + core deps
- phase-1: all Pydantic v2 data models (task/research/synthesis/deck/workbook)
- phase-1: provider-aware LocalLLMClient (always sends num_ctx) + tests
- phase-1: startup health checks (fail fast) + rich REPL intake
- phase-1: main.py CLI (ask + REPL) with UTF-8 bilingual output
- phase-1: ruff + mypy --strict clean (StrEnum, OpenAI return casts)
- phase-1: Phase 1 complete — handoff (this commit)

### Known Issues / Technical Debt
- Only the **Phase 1 core subset** of dependencies is installed in `.venv`. Phase 2+ must `pip install` the libs it needs (aiohttp, trafilatura, diskcache, pdfplumber, pytesseract, etc.) — all already listed in requirements.txt.
- `stream_generate()` exists and is unit-covered for Ollama indirectly, but the REPL currently uses non-streaming `generate()` with a spinner. Streaming display can be wired into the REPL later if desired (not required by spec).
- Thinking-mode family detection is **name-based** per SPEC §9 N-2 (`gemma*`/`qwen*`). The local `amadeus:*` models are gemma4-derived but won't get `<|think|>` (name doesn't match) — acceptable; switch `llm.model` to `gemma4:e4b` for thinking mode.
- Non-Ollama backends pass `num_ctx` via `extra_body.options` (best-effort); LM Studio/llama.cpp set context at load time. Only the default Ollama path is guaranteed/tested for num_ctx.

### What to do FIRST next session (Phase 2 starting point)
1. Run `python -m pytest tests/ -v` — verify all Phase 1 tests pass.
2. Install Docker Desktop (not on PATH yet) + `docker compose up -d` for SearXNG; verify `curl "http://localhost:8080/search?q=test&format=json"`.
3. Begin Phase 2 (researcher.py / pdf_reader.py / excel_reader.py) per SPEC §15.

### PHASE 1 STATUS: ✅ COMPLETE
---

## PHASE 2 — Research Engine + Document Reading
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-05-30
**Session status**: IN PROGRESS

### Phase Plan (created at session start)
[ ] 1. Install Phase-2 deps into .venv (aiohttp, trafilatura, diskcache, pdfplumber, pytesseract, Pillow, pandas, openpyxl)
[ ] 2. Research engine: models (RankedResult, ResearchBundle) + core/researcher.py (SearXNGClient, ContentFetcher, tier/dedup/rank, diskcache, ResearchEngine) + check_searxng startup + `research` CLI + tests
[ ] 3. core/excel_reader.py (pandas) + tests (real tiny .xlsx)
[ ] 4. LocalLLMClient `images` param + core/pdf_reader.py (pdfplumber → OCR → vision) + tests (mocked)
[ ] 5. REPL file-path detection in intake.py + `analyze-doc` CLI + tests
[ ] 6. Quality gate: ruff + mypy --strict + full pytest
[ ] 7. README + PROGRESS handoff + git commits + push

### Estimated scope: Medium-Large (research engine + 2 document readers + vision)
### Runtime reality at session start (read-only checks)
- Ollama: ✅ HTTP 200. Docker/SearXNG: ❌ not installed (`:8080` down). Tesseract: ❌ not on PATH. Phase-2 pip pkgs: ❌ not installed.
- Decision (confirmed with user): build full Phase 2, unit-test fully offline (mocked), fail-fast with exact setup instructions. Live web/OCR verification deferred until user installs Docker Desktop + Tesseract.

### PHASE 2 STATUS: ⏳ IN PROGRESS
---
