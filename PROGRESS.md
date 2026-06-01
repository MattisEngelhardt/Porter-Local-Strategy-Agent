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
2. Install Docker Desktop (not on PATH yet) + `docker compose up -d` for SearXNG; verify `curl "http://localhost:8888/search?q=test&format=json"`.
3. Begin Phase 2 (researcher.py / pdf_reader.py / excel_reader.py) per SPEC §15.

### PHASE 1 STATUS: ✅ COMPLETE
---

## PHASE 2 — Research Engine + Document Reading
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-05-30
**Session status**: COMPLETE

### Phase Plan (created at session start)
[x] 1. Install Phase-2 deps into .venv (aiohttp, trafilatura, diskcache, pdfplumber, pytesseract, Pillow, pandas, openpyxl) (done)
[x] 2. Research engine: models (RankedResult, ResearchBundle) + core/researcher.py (SearXNGClient, ContentFetcher, tier/dedup/rank, diskcache, ResearchEngine) + check_searxng startup + `research` CLI + tests (done — 10 pass + 1 live skip)
[x] 3. core/excel_reader.py (pandas) + tests (done — 3 pass)
[x] 4. LocalLLMClient `images` param + core/pdf_reader.py (pdfplumber → OCR → vision) + tests (done — 8 + 2 pass)
[x] 5. REPL file-path detection in intake.py + `analyze-doc` CLI + tests (done — 3 pass)
[x] 6. Quality gate: ruff + mypy --strict + full pytest (done — 44 pass / 1 skip, mypy clean 16 files)
[x] 7. README + PROGRESS handoff + git commits + push (done — this commit)

### Estimated scope: Medium-Large (research engine + 2 document readers + vision)

### Runtime reality at session start (read-only checks)
- Ollama: ✅ HTTP 200. Docker/SearXNG: ❌ not installed (`:8888` down). Tesseract: ❌ not on PATH. Phase-2 pip pkgs: ❌ not installed.
- Decision (confirmed with user): build full Phase 2, unit-test fully offline (mocked), fail-fast with exact setup instructions. Live web/OCR verification deferred until user installs Docker Desktop + Tesseract.

### Key Technical Decisions Made
| Decision | Choice | Reason |
|----------|--------|--------|
| Async transport | **aiohttp** (not httpx.AsyncClient) | SPEC §6 + requirements.txt name aiohttp for parallel research. trafilatura runs in a thread (`asyncio.to_thread`) on aiohttp-fetched HTML so the event loop never blocks. |
| Search cache | diskcache (SQLite) at `./data/cache/`, TTL = `cache_ttl_hours` | SPEC §4.4 names diskcache+SQLite+24h, not a path; `data/` is gitignored. Keyed on normalized (lowercase/trim) query. |
| Source tiers | Domain→tier classifier (Tier-1/2/3 from research_playbook); unknown → Tier 3 | Deterministic + offline-testable. `rank_score = tier_weight + score/10` so tier dominates, SearXNG score breaks ties. |
| Vision fallback | Added `images` param to `LocalLLMClient.generate()` (Ollama native `message.images` base64); non-Ollama + images → `LLMError` | Keeps RULE 6 (all LLM via the client). Default backend is Ollama/gemma4, which is the vision path SPEC §4.3 assumes. |
| `analyze-doc` / REPL doc handling | **Extraction only**, no LLM synthesis | Phase 2 must NOT implement the Phase 3 reasoning chain. Vision uses the LLM only to transcribe image PDFs (extraction, not reasoning). |
| Per-query failure tolerance | `search_many` returns `[]` for a failed query; raises `SearXNGError` only if **all** fail | One dead engine shouldn't kill a run; total failure is a real fail-fast condition. |
| docx reading | **Deferred** | SPEC §7 names only `pdf_reader.py` + `excel_reader.py`; docx is not a Phase-2 success criterion. python-docx left uninstalled. |

### What Was Built (Completed Tasks)
- **models/research.py**: added `RankedResult` (extends `SearchResult` with `tier` + `rank_score`) and `ResearchBundle` (query, sub_queries, ranked results, fetched content, `from_cache`).
- **core/researcher.py** (new): `SearXNGClient` (async JSON search, parallel `search_many` bounded by `parallel_queries`), `ContentFetcher` (aiohttp + trafilatura, parallel, drops failures), pure helpers `classify_tier` / `dedup_results` / `rank_results`, `SearchCache` (diskcache), `ResearchEngine.run()` orchestrator (cache-aware search → dedup → rank → fetch top-N). `SearXNGError` for fail-fast.
- **core/excel_reader.py** (new): `read_excel()` → pandas reads all sheets → structured text summary (sheet name, shape, columns, CSV preview); `ExcelReadError` on parse failure.
- **core/pdf_reader.py** (new): `read_pdf(path, llm=None)` cascade pdfplumber → pytesseract OCR → gemma4 vision; standalone images (.png/.jpg/…) supported; `PdfReadError` / `TesseractNotInstalledError` fail-fast. Backend steps are small seams (`_extract_text_pdfplumber`, `_render_pdf_pages`, `_open_image`, `_ocr_pages`, `_vision_pages`) so tests stub them.
- **llm/local_llm_client.py**: `generate(..., images=...)` attaches base64 images to the Ollama user message; non-Ollama + images raises `LLMError`. `_build_messages` now returns `list[dict[str, Any]]`.
- **core/startup.py**: `check_searxng()` — distinct fail-fast messages for "unreachable" (Docker) vs "not JSON" (enable formats in settings.yml).
- **core/intake.py**: `detect_file_path()` (bare/quoted path to supported doc), `read_document()` dispatcher (xlsx→excel, else pdf), `render_document()` panel; REPL routes dropped paths to the reader. Phase-2 TODO removed; only the Phase-5 voice TODO remains.
- **main.py**: `research "<query>" [--max-fetch N]` (SearXNG check → engine → ranked rich table + summary) and `analyze-doc <path>` (read → render). Factored `_load_config_or_exit`.
- **pyproject.toml**: mypy override `ignore_missing_imports` extended to trafilatura/diskcache/pdfplumber/pytesseract/pandas (no stub packages added — RULE 3).

### Files Created/Modified
| File | Status | Key Contents |
|------|--------|-------------|
| core/researcher.py | Created | SearXNGClient, ContentFetcher, tier/dedup/rank, SearchCache, ResearchEngine |
| core/excel_reader.py | Created | read_excel (pandas input mode) |
| core/pdf_reader.py | Created | pdfplumber → OCR → vision cascade |
| models/research.py | Modified | + RankedResult, ResearchBundle |
| llm/local_llm_client.py | Modified | + images/vision (Ollama) |
| core/startup.py | Modified | + check_searxng |
| core/intake.py | Modified | + file-path detection / read_document / render_document |
| main.py | Modified | + research + analyze-doc commands |
| pyproject.toml | Modified | mypy overrides for new stubless libs |
| tests/test_researcher.py | Created | 11 tests (10 offline + 1 live skip) |
| tests/test_excel_reader.py | Created | 3 tests |
| tests/test_pdf_reader.py | Created | 8 tests |
| tests/test_intake.py | Created | 3 tests |
| tests/test_local_llm_client.py | Modified | + 2 vision tests |
| README.md | Modified | Phase 2 setup (Docker/SearXNG JSON, Tesseract) + new commands |

### Implementation Gaps Encountered (from SPEC)
- **SearXNG JSON format**: the default SearXNG docker image ships JSON output disabled. Documented in README + `check_searxng` fix message (`search.formats: [html, json]`). Not a code issue.
- **pdfplumber page rendering for OCR/vision** (`_render_pdf_pages` via `page.to_image().original`) is implemented but **untested live** (no Tesseract, no scanned PDF this session). Unit tests stub the seam. Verify when Tesseract is installed.
- **docx**: deferred (see decisions).

### Tests Status
- test_config.py: ✅ 6/6 · test_local_llm_client.py: ✅ 14/14 (incl. live LLM) · test_researcher.py: ✅ 10/10 + 1 live skip · test_excel_reader.py: ✅ 3/3 · test_pdf_reader.py: ✅ 8/8 · test_intake.py: ✅ 3/3
- **Total: 44 passed, 1 skipped (live SearXNG).** ruff format/check: clean. mypy --strict (core llm models main.py): clean, 16 files.

### Git Log (this session)
- phase-2: research engine (SearXNG client, fetcher, rank/dedup, 24h cache) + research CLI + SearXNG startup check + tests
- phase-2: excel_reader (pandas input mode) + tests
- phase-2: pdf_reader (pdfplumber -> OCR -> vision cascade) + LLM images/vision support + tests
- phase-2: REPL file-path detection + analyze-doc CLI + tests (ruff/mypy --strict clean, 44 pass)
- phase-2: README + Phase 2 handoff (this commit)

### Known Issues / Technical Debt
- Live `research` and OCR/vision paths are **unverified** (Docker + Tesseract not installed this session). Offline tests + fail-fast cover them; first live run is the next session's first job.
- `analyze-doc` bootstraps the LLM (for the vision fallback), so it needs Ollama up even to read a text-only PDF/xlsx. Acceptable (agent assumes a local LLM); could be made lazy later.
- trafilatura currently extracts text only (no title/metadata) → `FetchedContent.title` stays None. Fine for Phase 2; enrich in Phase 3 if synthesis needs it.
- Cache stores per-query results; whole-run `from_cache` is True only if every sub-query hit. Good enough; no per-query reporting yet.

### What to do FIRST next session (Phase 3 starting point)
1. Run `python -m pytest tests/ -v` — verify 44 pass / 1 skip (or more if SearXNG is now up).
2. **Verify Phase 2 live** (if user has installed Docker + Tesseract): `docker compose up -d`, enable JSON format, then `python main.py research "Figure AI funding 2026"` → ranked results; `python main.py analyze-doc <scanned.pdf>` → OCR/vision text. Document the result.
3. Begin Phase 3 (SPEC §15): `core/intent_parser.py`, `core/clarification.py`, `core/memory.py` (brain.md inject — read only), the three `playbooks/*.md`, and the multi-step reasoning chain (SPEC §5.3) wiring intake → clarification → ResearchEngine → synthesis. `ResearchEngine.run(query, sub_queries=...)` already accepts decomposed sub-queries from the planner.

### PHASE 2 STATUS: ✅ COMPLETE
---

## PHASE 3 — Agent Brain (Intent + Dialog + Reasoning)
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-05-30
**Session status**: IN PROGRESS

### Phase Plan (created at session start)
[x] 1. Env + verify Phase-2 live gates (Tesseract→PATH, research/OCR), set max_clarification_rounds=3 (done 2026-05-30)
[x] 2. Playbooks (3 .md verbatim §13) + core/playbooks.py loader + test_playbooks.py (done — 4 tests)
[x] 3. core/memory.py load_brain (read-only brain.md injection) + test_memory.py (done — 4 tests)
[x] 4. models additions (ResearchPlan, PipelineResult) + core/intent_parser.py + test_intent_parser.py (done — 10 tests + live-verified)
[x] 5. core/clarification.py (budget, multi-dim bilingual, one-at-a-time loop) + test_clarification.py (done — 7 tests)
[x] 6. core/synthesizer.py (brain+playbook injection, thinking-by-depth, robust JSON) + test_synthesizer.py (done — 8 tests)
[x] 7. core/pipeline.py (Interaction, plan_subqueries, full chain, decline path) + test_pipeline.py (done — 6 tests)
[x] 8. Wire-up: REPL → pipeline, main.py analyze command, keep ask (done — REPL routes free-text through pipeline; analyze CLI; 4 render/interaction tests; live success gate passed)
[x] 9. Quality gate: ruff + mypy --strict + full pytest green (done — 88 passed, mypy clean 23 files)
[x] 10. Docs + Phase 3 handoff + git push origin main (done — this commit)

### Runtime reality at session start (read-only checks)
- Ollama ✅ (gemma4:e4b present). SearXNG ✅ HTTP 200 JSON on :8888. venv + Phase-2 deps ✅.
- Tesseract ✅ installed at `C:\Program Files\Tesseract-OCR` and on the persistent **user PATH**
  (the harness shell inherited a frozen env from before the PATH change — so already-open
  terminals need a restart; new terminals resolve `tesseract` automatically).

### Key Technical Decisions Made (Phase 3)
| Decision | Choice | Reason |
|----------|--------|--------|
| max_clarification_rounds | **3** (config.yaml; Pydantic default stays 2) | User-authorized override of SPEC §5.2. Questions scale with complexity (quick 0–1, standard 1–2, complex ≤3), asked one-at-a-time, each multi-dimensional. |
| Tesseract resolution | **PATH only** (no pdf_reader code change) | User instruction ("put it on the PATH"). Already on persistent user PATH; OCR verified live with session PATH set. |
| Language detection | Deterministic heuristic (umlauts + German function words), config override | Robust; never depend on LLM JSON for language (SPEC REQ-5 fail-safe). |

### Task 1 — Live gate verification (2026-05-30)
- `analyze-doc <image.png>` (long text) → **`method: ocr`**, full text transcribed (Tesseract 5.4.0). ✅
- `analyze-doc <image.png>` (short text) → OCR < 50 chars → **vision** fallback (gemma4) transcribed correctly. ✅ (cascade works)
- `research "Figure AI funding 2026" --max-fetch 2` → 8 ranked results (tier classification working), 1 page fetched (~7228 words). ✅
- All 44 prior tests still pass; config.yaml `agent.max_clarification_rounds: 3`.

### What Was Built (Completed Tasks)
- **playbooks/** — `research_playbook.md`, `analysis_playbook.md`, `output_playbook.md` written
  **verbatim** from SPEC §13 (RULE 14). **core/playbooks.py** — cached UTF-8 loader (`Playbooks`
  model), fail-fast on missing/empty.
- **core/memory.py** — `load_brain(MemoryConfig)`: read-only brain.md injection; strips
  single-`#` scaffolding (keeps `##`/`###` + content), caps at `max_brain_lines`, missing/empty → "".
  ChromaDB + propose-additions remain Phase 5 (not stubbed).
- **core/json_utils.py** — tolerant balanced-brace `extract_json_object` / `extract_json_array`
  (handles fenced / prose-wrapped LLM JSON; returns None → callers use conservative defaults).
- **core/intent_parser.py** — `parse_intent` (one fast no-thinking LLM classification → task_type
  / depth / audience / summary; brain-aware); `detect_language` (deterministic DE/EN heuristic,
  never from LLM; config can force); `route_outputs` (deterministic SPEC §5.4 map, incl.
  business_case = [DECK, EXCEL] N-6) + `detect_explicit_formats` override.
- **core/clarification.py** — `clarify` loop: proactive, **one question at a time**, each
  **multi-dimensional** (depth+format+audience triple / excel matrix-vs-benchmark / audience),
  budget scales with complexity (quick 0–1, standard 1–2, complex ≤3), hard-capped by
  `agent.max_clarification_rounds` (3). Pure (injected `ask` callable).
- **core/synthesizer.py** — `build_system_prompt` (brain + all 3 playbooks + Neura-Lens response
  format + language directive), `build_user_prompt` (tiered research evidence + documents),
  `synthesize` (thinking on for standard/deep, off for quick; tolerant JSON → `AnalysisOutput`;
  graceful degrade on LLM/parse failure), `quality_check` (completeness flags, SPEC §5.3 step 8).
- **core/pipeline.py** — `run_pipeline` wires the full SPEC §5.3 chain: decompose → brain inject →
  clarify → research-plan confirm → SearXNG research → synthesis → `PipelineResult`. `Interaction`
  Protocol + headless `AutoInteraction`; `plan_subqueries` (3–5 sub-queries + bilingual "Los?/Go?"
  summary); decline path → brain quick answer then offer full research; live progress via notify.
  **No file rendering (Phase 4), no ChromaDB (Phase 5).**
- **core/intake.py** — REPL free-text now runs the full pipeline; `ReplInteraction` (rich impl of
  the Interaction protocol) + `render_result`; document-drop path unchanged.
- **main.py** — new `analyze "<task>"` command (non-interactive full pipeline via
  `AutoInteraction`); `ask` one-shot kept; fail-fast on SearXNG/LLM/startup errors.
- **models/** — `ResearchPlan` (task.py), `PipelineResult` (synthesis.py).
- **config.yaml** — `agent.max_clarification_rounds: 3` (user-authorized SPEC §5.2 override).

### Files Created/Modified
| File | Status | Key Contents |
|------|--------|-------------|
| playbooks/{research,analysis,output}_playbook.md | Created | Verbatim SPEC §13 rulebooks |
| core/playbooks.py | Created | Cached playbook loader (Playbooks model) |
| core/memory.py | Created | load_brain (read-only brain.md injection) |
| core/json_utils.py | Created | Tolerant JSON object/array extraction |
| core/intent_parser.py | Created | parse_intent + detect_language + route_outputs |
| core/clarification.py | Created | Multi-dim, one-at-a-time clarify loop + budget |
| core/synthesizer.py | Created | Playbook+brain injection, synthesize, quality_check |
| core/pipeline.py | Created | run_pipeline (reasoning chain) + Interaction/AutoInteraction |
| core/intake.py | Modified | REPL→pipeline, ReplInteraction, render_result |
| main.py | Modified | + analyze command, render_result wiring |
| models/task.py | Modified | + ResearchPlan |
| models/synthesis.py | Modified | + PipelineResult |
| config.yaml | Modified | max_clarification_rounds: 3 |
| .gitignore | Modified | ignore data/cache/ |
| tests/test_{playbooks,memory,intent_parser,clarification,synthesizer,pipeline}.py | Created | 39 tests |
| tests/test_intake.py | Modified | +4 render/interaction tests |
| README.md | Modified | Phase 3 usage (analyze, REPL pipeline, clarification) |

### Implementation Gaps Encountered (from SPEC)
- **max_clarification_rounds 2→3**: user-authorized override of SPEC §5.2 (documented above).
- **No orchestrator file in SPEC §7**: `core/pipeline.py` added as a justified module (like
  `core/config.py`/`core/startup.py` in Phase 1).
- **Excel matrix-vs-benchmark choice has no Intent field**: the clarification answer is captured
  in the returned `ClarificationRound` (and feeds synthesis); the actual E-1/E-2 template pick is
  a Phase-4 concern. Documented in clarification.py.
- **SynthesisInput carries no raw task text**: synthesis uses `intent.summary` (the restatement)
  as the task statement; the pipeline passes the real query to the research engine.
- **Tesseract not on the harness PATH**: it IS on the persistent user PATH; already-open
  terminals need a restart (standard Windows env behavior). Verified live with session PATH.

### Tests Status
- test_config.py ✅ · test_local_llm_client.py ✅ · test_researcher.py ✅ · test_excel_reader.py ✅
  · test_pdf_reader.py ✅ · test_intake.py ✅ (7) · test_playbooks.py ✅ (4) · test_memory.py ✅ (4)
  · test_intent_parser.py ✅ (10) · test_clarification.py ✅ (7) · test_synthesizer.py ✅ (8)
  · test_pipeline.py ✅ (6)
- **Total: 88 passed** (live SearXNG/LLM tests run when services are up, else skip).
- `ruff format --check` + `ruff check`: clean (36 files). `mypy --strict core llm models main.py`: clean (23 files).

### Live Verification (this session)
- **Success gate 1 (screening, DE):** `analyze "Screen diese 5 europäischen Robotics Startups als
  M&A Targets"` → structured **German** analysis, routed **Excel + Brief**, real targets (Dexory,
  Sitegeist, Wandercraft, Exotec), Neura-Lens per target, two-stage acquisition recommendation,
  sources cited. ✅
- **Success gate 2 (business case, EN):** `analyze "Business case for ... Japan ... market size,
  investment, ROI"` → **English** analysis, routed **Deck + Excel** (dual output, N-6), SCR
  framework with risks + mitigations, sources (JETRO, trade.gov). ✅
- **Success gate 3 (language):** DE in → DE out, EN in → EN out. ✅
- Phase-2 gates re-confirmed: `research` (8 ranked results) + `analyze-doc` OCR (`method: ocr`).

### Git Log (this session)
- phase-3: env setup + Phase-2 live gate verification + clarify cap=3
- phase-3: playbooks (research/analysis/output, verbatim SPEC §13) + loader + tests
- phase-3: core/memory.py brain.md injection (read-only) + tests
- phase-3: intent parser + deterministic output routing + tolerant JSON util
- phase-3: clarification dialog (proactive, one-at-a-time, multi-dimensional)
- phase-3: synthesizer (brain + 3-playbook injection, thinking-by-depth, robust JSON)
- phase-3: pipeline orchestrator (full SPEC 5.3 reasoning chain) + tests
- phase-3: wire REPL through pipeline + analyze CLI + ReplInteraction/render_result
- phase-3: README + Phase 3 handoff (this commit)

### Known Issues / Technical Debt
- `analyze` and the REPL need SearXNG up (the pipeline always researches unless the plan is
  declined). SearXNG/LLM errors fail fast with fix instructions; the REPL catches them and keeps
  looping rather than crashing.
- Synthesis does extraction + reasoning in one LLM call (no separate extraction pass) — fine for
  Phase 3; revisit if source counts grow. Per-source excerpt is capped at 1800 chars.
- The decline path's "memory" is brain.md only (ChromaDB delta is Phase 5).
- Document attachments aren't auto-read by `analyze`/REPL free-text yet (the doc-drop path reads
  + shows them separately); `run_pipeline` accepts a `documents=` list for when Phase 4/5 wires it.

### What to do FIRST next session (Phase 4 starting point)
1. Run `python -m pytest tests/ -v` — verify 88 pass (live tests need Ollama + SearXNG up).
2. Add `assets/neura_logo.png` (referenced in SPEC §7/§11, still absent) before building decks.
3. Begin Phase 4 (SPEC §15): Jinja2 brief templates T-1..T-6 + weasyprint PDF; `python-pptx`
   deck (10 slide types, Neura colors, logo bottom-right); **excel_builder.py** (E-1..E-4);
   `exporter.py` orchestration. The renderers consume `AnalysisOutput` (synthesis.py) and the
   `DeckStructure`/`WorkbookContent` contracts (models/deck.py, models/workbook.py).
4. Wire rendering into the pipeline: `run_pipeline` already returns `routed_formats`
   (incl. Business Case dual output) — Phase 4 turns those into files in `./output/` and prints
   the paths (replace the "Would generate (Phase 4)" note in `render_result`).

### PHASE 3 STATUS: ✅ COMPLETE
---

## PHASE 3.5 — Advanced Agent Loop (Effort · Multi-Agent Deep Research · Self-Correction)
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-05-30
**Session status**: IN PROGRESS
**Authority**: user-authorized amendment to the LOCKED SPEC — `PHASE_3.5_PLAN.md` v1.0 (APPROVED),
recorded in SPEC §15.5 + WORKFLOW §2.

### Phase Plan (created at session start — 11 atomic tasks, 1 commit each `phase-3.5: …`)
[x] 1. Scope + effort config: SPEC §15.5 + WORKFLOW row + `EffortConfig`/`EffortLevelConfig`
       (config.py + config.yaml) + test_config + this PROGRESS plan (done 2026-05-30)
[x] 2. Models: `EffortLevel` + `Intent.effort`; research.py (`Confidence`/`Finding`/`WorkerFindings`/
       `CoverageGap`/`CoverageReport`/`ResearchReport`); synthesis.py (`Critique`/`CriterionResult`
       + `PipelineResult` extension); refactor `synthesizer.parse_analysis`; tests (done 2026-05-30
       — test_models.py +8, parse_analysis test; 99 tests, mypy/ruff clean)
[x] 3. Deep-research playbook: authored `playbooks/deep_research_playbook.md` (**USER REVIEW
       PENDING** — authored content per RULE 14) + extended `Playbooks` loader (4th file,
       fail-fast) + tests (done 2026-05-30 — Playbooks.deep_research; test_playbooks +2)
[x] 4. Effort detection + override: `detect_effort` (keyword booster + LLM hint + task-type floor,
       default HIGH) + `parse_effort_override` (`/effort` prefix) in intent_parser; classifier emits
       an effort hint; `parse_intent(effort_override=…)`; pipeline clarify budget = min(agent rounds,
       effort.max_clarifications). `analyze --effort` lands in Task 9. (done 2026-05-30 — +7 tests)
[x] 5. Interaction `ask_text` (protocol + ReplInteraction `Prompt.ask` + AutoInteraction canned/""
       with `asked_text` log) + tests (done 2026-05-30 — +2 tests)
[x] 6. ResearchWorker (`core/research_agent.py`): async deep-research loop — craft queries (deep
       playbook injected) → SearXNG+fetch (reused Phase-2) → LLM extracts dated/sourced/confidence
       Findings → iterate ≤ max_research_rounds while thin; LLM via `asyncio.to_thread`; fail-open
       on LLM/parse; SearXNG total-fail propagates (manager decides). +5 tests (done 2026-05-30)
[x] 7. ResearchManager (`core/research_agent.py`): decompose (analysis-playbook-driven, N=research_workers,
       fallback to plan sub-queries) → run workers concurrently (`asyncio.Semaphore(worker_concurrency)`)
       → mid-research clarification (detect blocking ambiguity → `ask_text` → targeted re-run, ≤
       max_midresearch_questions, fail-open) → aggregate ResearchReport + telemetry; SearXNG
       all-worker-fail re-raises SearXNGError (fail-fast). +5 tests (done 2026-05-30)
[x] 8. Critic + revision (`core/critic.py`): `critique` scores a draft 0-100 against a 9-point
       rubric (output + deep-research playbooks injected: sourced / financials≥2 / recency /
       assumptions / Neura-Lens / bottom-line-first / framework / language / no-filler),
       `use_thinking=True`, passed=score≥min_score, fail-open (LLM/parse → passing "unavailable");
       `revise` reuses synthesizer.build_system_prompt + evidence + parse_analysis, fail-open keeps
       draft. +7 tests (done 2026-05-30)
[x] 9. Pipeline + presentation: `run_pipeline` rewired to the full master loop (parse_intent+effort →
       clarify → plan(effort shown) → confirm → ResearchManager → synthesize (findings digest) →
       critique+revise loop (effort-gated) → quality_check → PipelineResult+telemetry). New
       `SynthesisInput.findings_digest` injected into synthesis. `render_result` telemetry panel
       (effort · workers · rounds · sources · quality · revisions · mid-research Qs). REPL `/effort`
       (inline override + session default). `analyze --effort`. test_pipeline rewritten (manager
       stub + critique), +telemetry render test. (done 2026-05-30 — 127 tests, ruff/mypy clean)
[x] 10. Quality gate: ruff format (41 files) + ruff check + `mypy --strict` (25 files) + pytest
        (127 passed, 1 skipped) all green. Live: LOW verified end-to-end; HIGH auto-effort run
        launched live (telemetry appended when it completes). (done 2026-05-30)
[x] 11. Docs (README Phase-3.5 + full PROGRESS handoff) + `git push origin main` (done 2026-05-30)

### Runtime reality at session start (read-only checks, 2026-05-30)
- Ollama ✅ HTTP 200 (gemma4:e4b present). SearXNG ✅ HTTP 200 JSON on :8888. venv + deps ✅.
- All 88 Phase-3 tests pass before any new code (RULE 11). ruff/mypy assumed clean (verified per task).

### Architecture (target master loop)
`intake (parse /effort) → parse_intent + auto-detect effort → upfront clarify (≤ effort) →
research plan + effort shown → confirm → ResearchManager.run(effort) [decompose → N parallel
workers (deep-research playbook: recency/authority/cross-ref → Findings) → mid-research Qs →
aggregate ResearchReport] → synthesize (brain + playbooks + findings) → if effort.critique:
critique → revise loop → quality_check → PipelineResult (effort, critique, revisions, telemetry)`.
Advisory layers fail-open; hard deps fail-fast. Concurrency config-gated (`effort.worker_concurrency`).

### Key Technical Decisions Made (Phase 3.5)
| Decision | Choice | Reason |
|----------|--------|--------|
| Effort as master dial | `EffortConfig.levels[low/high/ultra]` in config.yaml; `level_for()` resolves a level (or `EffortLevel` StrEnum, which equals its value) with safe fallback to `default` | Single knob, everything config-driven per level; scales to server/bigger model with zero code change (SPEC §15.5). Auto-detect defaults to HIGH — never silently shallow (RULE 9). |
| `level_for` accepts `str` | config.py stays decoupled from models (no import of `EffortLevel`) | StrEnum members equal their string value, so passing an `EffortLevel` works seamlessly; avoids a config→models dependency. |

### What Was Built (Completed Tasks)
- **Effort master dial** — `EffortLevelConfig`/`EffortConfig` (`core/config.py`) + `effort` block in
  `config.yaml` (low/high/ultra + `worker_concurrency` + `critique_min_score`). `EffortLevel`
  StrEnum + `Intent.effort` (`models/task.py`). `detect_effort` (explicit keyword > LLM hint +
  task-type floor > HIGH default) + `parse_effort_override` (`/effort` prefix) in
  `core/intent_parser.py`; the classifier emits an effort hint. Every budget reads
  `config.effort.level_for(intent.effort)`.
- **Deep-research playbook** — authored `playbooks/deep_research_playbook.md` (source-authority
  ladder, recency windows, confidence model + ≥2-source rule, query craft, follow-the-thread,
  finding extraction, round/mid-research triggers, manager aggregation). `Playbooks` loader extended
  to 4 files (fail-fast). **Authored content — user review pending.**
- **Multi-agent deep research** — `core/research_agent.py`:
  - `ResearchWorker.run(sub_topic, effort_cfg)` — craft queries (deep playbook injected) → reuse
    Phase-2 `SearXNGClient`/`ContentFetcher`/`rank`/`dedup` → LLM extracts dated/sourced/confidence
    `Finding`s → iterate ≤ `max_research_rounds` while thin. LLM via `asyncio.to_thread`. Fail-open.
  - `ResearchManager.run(...)` — decompose (analysis-playbook-driven, N=`research_workers`, fallback
    to plan sub-queries) → run workers via `asyncio.Semaphore(worker_concurrency)` → mid-research
    clarification (`interaction.ask_text` → targeted follow-up worker) → aggregate `ResearchReport`
    + telemetry. SearXNG all-worker-fail re-raises `SearXNGError` (fail-fast).
- **Output critic + revision** — `core/critic.py`: `critique` (9-point rubric incl. source
  validation, `use_thinking=True`, fail-open) + `revise` (reuses `synthesizer.build_system_prompt`
  + evidence + `parse_analysis`, fail-open).
- **Master loop** — `core/pipeline.py` `run_pipeline` rewired: parse_intent(+effort) → clarify
  (effort budget) → plan (effort surfaced) → confirm → `ResearchManager` → synthesize (validated
  findings digest via new `SynthesisInput.findings_digest`) → critique+revise loop (effort-gated) →
  quality_check → `PipelineResult`(effort, critique, revisions, research_report).
- **Presentation** — `render_result` telemetry panel; REPL `/effort` (inline override + session
  default); `main.py analyze --effort low|high|ultra`. `Interaction.ask_text` (+ ReplInteraction
  `Prompt.ask` + AutoInteraction canned/"" with `asked_text`).

### Files Created/Modified (Phase 3.5)
| File | Status | Key Contents |
|------|--------|-------------|
| core/config.py | Modified | EffortLevelConfig + EffortConfig (level_for) |
| config.yaml | Modified | effort block (low/high/ultra) |
| models/task.py | Modified | EffortLevel + Intent.effort |
| models/research.py | Modified | Confidence/Finding/WorkerFindings/CoverageGap/CoverageReport/ResearchReport |
| models/synthesis.py | Modified | CriterionResult/Critique; PipelineResult ext; SynthesisInput.findings_digest |
| core/synthesizer.py | Modified | public parse_analysis; findings-digest injection |
| core/intent_parser.py | Modified | detect_effort + parse_effort_override + effort hint |
| core/playbooks.py | Modified | 4th playbook (deep_research) |
| playbooks/deep_research_playbook.md | Created | worker/manager methodology (authored) |
| core/research_agent.py | Created | ResearchWorker + ResearchManager |
| core/critic.py | Created | critique + revise (fail-open) |
| core/pipeline.py | Modified | full master loop + effort budgets + critique loop |
| core/intake.py | Modified | telemetry panel + REPL /effort + ask_text |
| main.py | Modified | analyze --effort |
| tests/{test_models,test_research_agent,test_critic}.py | Created | +8 / +10 / +7 |
| tests/test_{config,playbooks,intent_parser,synthesizer,pipeline,intake}.py | Modified | effort/4th-playbook/parse_analysis/manager/telemetry tests |
| strategy_agent_SPEC.md / opus_WORKFLOW.md / README.md | Modified | §15.5 amendment / phase row / Phase-3.5 docs |

### Tests Status
- **127 passed, 1 skipped** (live SearXNG test) — up from 88. ruff format/check clean (41 files);
  `mypy --strict core llm models main.py` clean (25 files). Fail-open paths covered (worker bad
  JSON / no sources, critic LLM-error + bad JSON, decompose fallback); hard-dep fail-fast covered
  (manager all-worker SearXNG failure re-raises).

### Live Verification (this session)
- **Auto-effort LOW (live):** `analyze --effort low "Latest humanoid robotics funding news 2026"`
  → telemetry `effort: low · 1 worker · 1 round · 22 sources evaluated · 2 read`, no critique panel
  (low disables it), structured analysis with Neura-Lens + explicit data-gap flag. ✅
- **Auto-effort HIGH (live):** `analyze "Screen these 5 European robotics startups as M&A targets"`
  → auto-detected **high** (target_screening floors to HIGH). Telemetry:
  `effort: high · 3 workers · 2 rounds · 133 sources evaluated · 20 read · quality 75/100
  (passed) · 0 revisions`. Routed to **Excel + Brief** (dual output). The critic ran and passed at
  the threshold (75) → no revision. Synthesis used **inline source citations** ([16]/[18]/[19]/[20])
  and the Neura Lens per point. ✅ Notably, since the task named no specific 5 startups and the
  headless `AutoInteraction` returns "" for mid-research questions, the agent **proceeded on a
  stated assumption** — it delivered a screening *framework* and flagged the missing target list
  rather than fabricating names (the documented fail-open mid-research behavior; in the REPL it
  would ask `ask_text` instead). Total wall-clock ~12 min on the laptop (single gemma4 serializes).

### Key Technical Decisions (added)
| Decision | Choice | Reason |
|----------|--------|--------|
| Worker/manager in one module | `core/research_agent.py` (both classes) | Plan §6; manager owns SearXNG/fetcher + shares across workers. `_Interaction` Protocol locally avoids a pipeline↔research_agent circular import. |
| Findings digest into synthesis | new `SynthesisInput.findings_digest` (not reusing `prior_findings`) | Keeps `prior_findings` reserved for Phase-5 ChromaDB; injects validated claim·confidence·date·source so synthesis leads with verified facts. |
| Critic injectability seam | `manager`/`effort_override` params on `run_pipeline`; critic via scripted client in tests | Full loop is offline-testable; live path builds real ResearchManager. |

### Known Issues / Technical Debt (Phase 3.5)
- **`deep_research_playbook.md` is authored content awaiting user review** (RULE 14 — only the user
  approves agent content). It is methodology, not Neura facts, but flag it.
- Live **ultra** (5 workers, 3 rounds, 2 revisions) is the same code path as the verified low/high
  runs with the config numbers raised; on the single local gemma4 it serializes to ~45–70 min, so it
  was not babysat to completion this session (proven by the high run + `worker_concurrency`/N being
  pure config, asserted in `test_research_agent`). On the planned server it fans out with no code
  change.
- Each worker opens its own aiohttp session per search/fetch call (Phase-2 behavior); a shared
  session pool is a future optimization, not needed for correctness.
- The research cache (diskcache) is bypassed by the manager's workers (they call SearXNG directly);
  wiring per-worker caching is a possible future optimization.

### What to do FIRST next session (Phase 4 starting point)
1. Run `python -m pytest tests/ -v` — verify 127 pass (live tests need Ollama + SearXNG up).
2. Review `playbooks/deep_research_playbook.md` (authored content) and adjust if desired.
3. Add `assets/neura_logo.png` (still absent) before building decks.
4. Begin Phase 4 (SPEC §15): brief templates T-1..T-6 + weasyprint PDF; python-pptx decks;
   `excel_builder.py` (E-1..E-4); `exporter.py`. Renderers consume `AnalysisOutput`; the
   `PipelineResult` now also carries `research_report` (worker findings + sources + confidence)
   which Phase 4 can use to fill Excel "Sources"/"Audit Trail" tabs and the telemetry into footers.

### Addendum — CEO-Office Document-Preparation Mode (internal docs, no research)
A second use case added on the same loop: when documents are attached and no fresh web data is
needed, the agent **consolidates internal documents into one management briefing** instead of
researching. New pieces:
- **Routing** — `route_mode(task, has_documents, task_type)` (`WorkMode.RESEARCH` |
  `DOCUMENT_PREP`): documents → doc-prep unless the task explicitly asks for web data; wired into
  `run_pipeline` (skips planning/confirm/research entirely).
- **`playbooks/doc_prep_playbook.md`** (authored, user review pending) — zero-hallucination rule
  (every figure traced to its source, gaps flagged), what management needs, **.md-blueprint-first**,
  how to build top-notch PDF/PPTX, and how to ask targeted clarifying questions.
- **`core/doc_synthesis.py`** — `propose_doc_questions` (read → identify themes → ask ≤budget
  precise questions on emphasis/audience/format/style, fail-open), `synthesize_briefing` (deep read,
  thinking on, guidance-injected, zero-hallucination prompt), `to_management_markdown` (the
  Spickzettel/blueprint) + `write_briefing_md` → `./output/…_briefing.md`.
- **Loop optimization** — doc-prep gets the same interleaved clarification idea as mid-research:
  the agent asks theme-specific questions *after reading* (budget = min(agent rounds,
  effort.max_clarifications)); answers feed synthesis as guidance. Empty answers → assume + proceed.
- **Pipeline/presentation** — `PipelineResult.mode` + `artifact_path`; `render_result` shows the
  blueprint path + a doc-prep telemetry line. **`main.py prepare <files…> --task`** CLI.
- **Output:** PDF brief and/or PPTX deck, both rendered from the same `AnalysisOutput`. The `.md`
  blueprint (Spickzettel) is always written first as the cheat-sheet.

### Addendum 2 — Real PPTX/PDF rendering + mode ambiguity ask (CEO-office, user-requested)
The doc-prep skill now **produces the deliverables**, not just the blueprint:
- **`core/exporter.py`** (the SPEC §7 name) — `build_management_deck` (python-pptx: dark title
  slide, Executive Summary, one "so what" slide per theme, Sources; Neura colors from config, logo
  bottom-right if present) and `build_management_pdf` (WeasyPrint HTML→PDF, Neura-styled). PPTX is
  fully local and works now; PDF uses WeasyPrint (SPEC §6) and **fails fast with exact GTK-install
  instructions** if the runtime is absent — renderer is correct, zero code change once GTK is in.
- **Wiring** — `_render_outputs` renders the routed formats (PDF for brief, PPTX for deck),
  **fail-open per renderer** (a render failure never loses the briefing); `PipelineResult.output_files`
  carries the rendered paths; `render_result` lists them and stops saying "Phase 4" when real files
  ship. `main.py prepare … --format brief|deck|both` (default both).
- **Mode ambiguity ask** — `classify_work_mode()` returns `None` when documents are attached but the
  instruction is unclear; `run_pipeline` then **asks the user** ("only prepare for management, or
  also research?") instead of guessing (clear doc-prep / research phrases still decide instantly;
  headless picks prepare). `route_mode` kept as the deterministic resolver.
- **Deps:** `python-pptx` + `weasyprint` installed into the venv (both already in requirements.txt /
  SPEC §6 — no new dependency). mypy overrides add `pptx`/`weasyprint`.
- **Live-verified:** `prepare neura_q2_board.xlsx --format deck` → real 6-slide .pptx (Title · Exec
  Summary · 3 "so what" theme slides · Sources), every figure attributed to the source file (no
  hallucination), blueprint `.md` written. Tests: +13 total (routing incl. ambiguity, questions,
  guidance, briefing, markdown, write, pipeline branch, deck build, PDF fail-fast).

### What to do FIRST next session (Phase 4 starting point)
1. Run `python -m pytest tests/ -v` — verify 141 pass (live tests need Ollama + SearXNG up).
2. **Read `PHASE_4_KICKOFF.md`** (project root) — the full onboarding prompt for Phase 4, incl. the
   carry-over items below.
3. **Carry-over open items (do these as part of Phase 4):**
   - **PDF live**: WeasyPrint is pip-installed but its **GTK runtime is missing on Windows**, so
     `core/exporter.build_management_pdf` fails fast at import (instructions included). Install the
     GTK3 runtime, then live-verify PDF; build the T-1..T-6 brief templates on this path.
   - **Playbook reviews (RULE 14)**: `playbooks/deep_research_playbook.md` and
     `playbooks/doc_prep_playbook.md` are authored content **awaiting user review** — surface them,
     don't silently rewrite.
   - **`core/exporter.py` already exists** (Phase-3.5 slice: `build_management_deck` +
     `build_management_pdf`). Phase 4 **extends/absorbs** it (10 slide types, all brief templates,
     `excel_builder.py` E-1..E-4) — do not duplicate. `assets/neura_logo.png` is still **missing**
     (needed bottom-right on decks) — add it before building decks.
4. Phase 4 = Output Generation (SPEC §15): Jinja2 briefs T-1..T-6 + WeasyPrint PDF; python-pptx 10
   slide types (Neura colors, logo); `excel_builder.py` E-1..E-4 (formula integrity, N-10); wire
   rendering into the **research** path too (turn `PipelineResult.routed_formats` into files like
   doc-prep already does). Business Case = dual output (deck + Excel, N-6).

### PHASE 3.5 STATUS: ✅ COMPLETE
(Code complete, 141 tests green, ruff/mypy --strict clean (27 files), pushed. Web-research loop:
LOW + HIGH live-verified. CEO-office document-preparation mode: routing + ambiguity-ask, deep
read, targeted clarifications, .md blueprint, and **real PPTX + PDF rendering** — live-verified
(6-slide deck from a Q2 xlsx, no hallucination). PDF needs WeasyPrint GTK runtime (fail-fast).)
---

## PHASE 4 — Output Generation (All Three Types)
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-05-31
**Session status**: IN PROGRESS

### Phase Plan (10 atomic tasks; 1 commit each `phase-4: …`; PROGRESS updated per task)
[x] 0. Baseline 141 green (RULE 11); installed jinja2 into venv; logo set up (done 2026-05-31)
[x] 1. `assets/neura_logo.png` in place (user-provided, copied to SPEC §7 name). PDF live blocked
       on GTK (see below) — PDF code built code-complete + fail-fast instead (done 2026-05-31)
[x] 2. Brief templates T-1..T-6 (Jinja2 HTML) + `exporter.render_brief_html`/`build_brief_pdf`
       (task-type→template, logo, bilingual, GTK bootstrap) + 5 tests (done 2026-05-31 — 146 green)
[x] 3. Generalized `exporter.build_deck` — all 10 slide types (Neura colors, logo bottom-right)
       (done 2026-05-31 — 148 green; `_DeckRenderer` + back-compat `build_management_deck`)
[x] 4. `core/content_shaper.py` `shape_deck` (slide selection per task type; SCR business case) +
       deterministic fallback (done 2026-05-31 — 153 green)
[x] 5. `core/excel_builder.py` E-1 Decision Matrix (weights yellow, SUMPRODUCT/RANK, cond-fmt,
       Criteria_Guide + Research_Notes tabs) (done 2026-05-31 — 160 green; N-10 verified: data_only
       re-open returns None → pure formulas)
[x] 6. excel_builder E-2 Benchmark (Excel Table+auto-filter+Sources) + E-4 Tracker (Dashboard
       COUNTIF formulas, Status/Priority data-validation dropdowns, cond-fmt, Archive)
       (done 2026-05-31 — 163 green)
[x] 7. excel_builder E-3 Business Case 5-tab model (Summary NPV/IRR formulas, Assumptions all
       yellow, Projections/Scenarios formula-linked, Sources audit) — N-10 verified (done 2026-05-31
       — 169 green; data_only re-open returns None for NPV → pure formulas)
[x] 8. `content_shaper.shape_workbook` (task-type→template routing E-1..E-4 + per-template
       structured LLM shaping + deterministic fail-open fallbacks) (done 2026-05-31 — 176 green)
[x] 9. Pipeline wiring: `_render_outputs` now renders all 3 formats (BRIEF→build_brief_pdf,
       DECK→shape_deck+build_deck, EXCEL→shape_workbook+build_workbook), **called in the research
       path** + doc-prep path; business-case dual output verified (N-6: .pptx+.xlsx in one run);
       `excel_builder.build_workbook` dispatcher; `render_result` "Phase 4" caveat removed; tests
       route output to tmp_path (no ./output pollution) (done 2026-05-31 — 177 green)
[x] 10. Quality gate (ruff format 49 + ruff check + mypy --strict 29 + 177 pytest, all green) +
        live deliverable renders (board PPTX w/ logo · screening matrix w/ live SUMPRODUCT/RANK ·
        business-case deck+xlsx N-6) + PROGRESS/README/WORKFLOW + push (done 2026-05-31)

### Key Technical Decisions (Phase 4)
| Decision | Choice | Reason |
|----------|--------|--------|
| Excel/deck content shaping | New `core/content_shaper.py`: one structured LLM call per deliverable → typed JSON (entities/criteria/weights/scores; assumptions) | Prose `AnalysisOutput` lacks the numeric per-entity data Excel needs; shaping yields genuinely-populated matrices with **real formulas** (meets gate). Fail-open deterministic fallbacks. User-approved. |
| Briefs render path | Jinja2 **HTML** templates → WeasyPrint (not Markdown→HTML) | SPEC §4.6 says "Markdown→weasyprint" but WeasyPrint consumes HTML and no Markdown lib is in SPEC §6 (RULE 3). HTML templates + shared Neura CSS is the clean local path. |
| Deck renderer | One generalized `build_deck(DeckStructure)` over the 10 slide types (not per-type `templates/decks/*.py`) | User guidance "extend exporter.py, don't duplicate". Avoids 4 near-duplicate builders; content selection lives in the shaper. |
| GTK on Windows | `_ensure_gtk_dll_dir` forces a found GTK `bin` ahead of any incompatible libgobject on PATH (e.g. Tesseract) + `OutputConfig.gtk_runtime_path` | Tesseract ships a broken libgobject earlier on PATH; this makes WeasyPrint load the right libs once a real GTK runtime is installed — zero code change. |
| Logo | User-provided `Neura Robotics Logo.png` copied to `assets/neura_logo.png` (SPEC §7 / config path) | Real brand asset; config-driven; existing `include_logo and is_file()` guard already handles absence. |

### Carry-over from Phase 3.5
- **Playbook reviews (RULE 14):** `deep_research_playbook.md` + `doc_prep_playbook.md` — user
  **approved as-is** this session (kept unchanged).
- **PDF live / GTK:** WeasyPrint still cannot load GTK in the venv — the Tesseract folder ships an
  incompatible `libgobject-2.0-0.dll` earlier on PATH and **no real GTK3 runtime is installed**.
  Auto-install was attempted but the download is blocked from the agent shell (GitHub 404/empty) and
  a GTK install needs admin. **Resolution:** PDF code is complete + unit-tested (HTML render) +
  fail-fast with exact instructions, and `_ensure_gtk_dll_dir` will pick up a GTK runtime the moment
  one is installed. **User action to go live:** install the GTK3 runtime (e.g. tschoonj
  `gtk3-runtime-*-win64.exe`, enable "set up PATH"), reopen the terminal — then PDF renders with no
  code change. PPTX + Excel are fully local (no GTK).

### What Was Built (Phase 4)
- **Brief system (T-1..T-6)** — `templates/briefs/` six bilingual Jinja2 **HTML** templates
  (competitor / decision / market / board / document-synthesis / adhoc) + shared `_styles.md.j2`
  (Neura CSS, all colors from config) + `_macros.md.j2`. `exporter.render_brief_html` (pure,
  testable) + `build_brief_pdf` (task-type→template, base64-embedded logo, bullet/paragraph body
  conversion, HTML-escaped → WeasyPrint). `_ensure_gtk_dll_dir` forces a found GTK `bin` ahead of
  any incompatible `libgobject` on PATH.
- **Deck renderer (all 10 slide types)** — `exporter._DeckRenderer` + `build_deck(DeckStructure)`:
  title / exec-summary / market / company / financial / competitive-comparison (styled table) /
  strategic-signals / SWOT (2×2 grid) / recommendation (decision callout) / appendix. Neura colors,
  Arial, borderless rounded rects, **logo bottom-right on every slide**. `management_deck_structure`
  is the deterministic fallback; `build_management_deck` delegates (back-compat).
- **`core/content_shaper.py`** — `shape_deck` (prose `AnalysisOutput` → typed `DeckStructure` with
  "so what" headlines + SCR ordering for business cases) and `shape_workbook` (task-type→template
  routing + per-template structured extraction → E-1..E-4 data). One LLM call each, **fail-open** to
  deterministic builders.
- **`core/excel_builder.py` (E-1..E-4, all formula-driven, N-10)** — `build_decision_matrix`
  (yellow weights row, `=SUMPRODUCT` weighted scores, `=RANK`, colour-scale + top-rank cond-fmt,
  Criteria_Guide + Research_Notes), `build_benchmark_table` (Excel Table + auto-filter + Sources),
  `build_business_case` (5 tabs: Summary NPV/IRR formulas · Assumptions all-yellow · Projections &
  Scenarios formula-linked · Sources/Audit), `build_tracker` (Dashboard COUNTIF formulas, Status/
  Priority data-validation dropdowns, cond-fmt, Archive). `build_workbook` dispatcher.
- **Pipeline wiring** — `_render_outputs` renders all three formats (shaping decks/Excel first) and
  is now called in the **research path** as well as doc-prep; business case → Deck + Excel in one run
  (N-6). Fail-open per renderer. `render_result` drops the "Phase 4" caveat and lists deliverables.

### Files Created/Modified (Phase 4)
| File | Status | Key Contents |
|------|--------|-------------|
| templates/briefs/*.md.j2 (8) | Created | T-1..T-6 + shared _styles + _macros |
| assets/neura_logo.png | Created | NEURA wordmark (user-provided) |
| core/exporter.py | Modified | brief render + build_deck (10 types) + GTK bootstrap; back-compat shims |
| core/content_shaper.py | Created | shape_deck + shape_workbook (+ routing, fail-open) |
| core/excel_builder.py | Created | E-1..E-4 builders + build_workbook dispatcher |
| core/pipeline.py | Modified | _render_outputs (3 formats) wired into research path |
| core/intake.py | Modified | render_result deliverables panel (no Phase-4 caveat) |
| models/workbook.py | Modified | DecisionMatrix/Benchmark/BusinessCase/Tracker data + items |
| core/config.py / config.yaml | Modified | OutputConfig.gtk_runtime_path |
| pyproject.toml | Modified | mypy overrides + openpyxl |
| tests/test_exporter.py / test_content_shaper.py / test_excel_builder.py | Created/Modified | +9 / +11 / +17 |
| tests/test_pipeline.py / test_intake.py | Modified | tmp_path output, N-6 dual-output, deliverables panel |
| README.md | Modified | Phase 4 status, GTK section, layout |

### Tests Status (final)
- **177 passed, 1 skipped** (live SearXNG) — up from 141. ruff format (49 files) + ruff check clean;
  `mypy --strict core llm models main.py` clean (29 files). N-10 formula integrity verified by
  re-opening each workbook with `data_only=True` and asserting formula cells return `None` (no
  hardcoded intermediates) for E-1 (SUMPRODUCT/RANK), E-3 (NPV/IRR/projections), and E-4 dashboard.

### Live Verification (this session, offline renders)
- **Board deck** → 3-slide Neura `.pptx`, **logo bottom-right on every slide** (shape_type 13 count
  == slide count). ✅
- **Screening** → Excel decision matrix with live `=SUMPRODUCT(B7:D7,$B$6:$D$6)` + `=RANK(...)`;
  changing a weight recalculates (data_only re-open returns None → pure formula). ✅
- **Business case** → **PPTX deck + Excel model in one run** (N-6); Summary NPV =
  `=-Assumptions!$B$4+NPV(Assumptions!$B$9,Projections!E7:E9)`. ✅
- **Bilingual** → DE/EN labels verified in brief HTML + Excel headers. ✅
- **PDF → LIVE ✅ (2026-05-31).** User installed MSYS2 + `mingw-w64-x86_64-pango`; the agent's
  `_ensure_gtk_dll_dir` auto-detects `C:\msys64\mingw64\bin` (via `os.add_dll_directory`, so it does
  not pollute PATH) and forces it ahead of the Tesseract `libgobject`. `build_brief_pdf` rendered a
  real 71 KB T-1 competitor brief to `./output/`. All 177 tests still green with MSYS2 on PATH
  (pandas/numpy unaffected, verified with `mingw64/bin` first on PATH). **All three output types are
  now production-live.**

### Carry-over / Known Issues (Phase 4)
- **PDF — RESOLVED, now live.** Earlier in the session WeasyPrint couldn't load GTK (the agent shell
  blocks external downloads; the Tesseract folder ships an incompatible `libgobject`). The user
  installed **MSYS2 + `mingw-w64-x86_64-pango`**; `_ensure_gtk_dll_dir` auto-detects
  `C:\msys64\mingw64\bin` and registers it via `os.add_dll_directory` (ahead of Tesseract, without
  polluting PATH). PDF rendered live (71 KB T-1 brief). No further action needed.
- **Authored playbooks** (`deep_research_playbook.md`, `doc_prep_playbook.md`) — **user-approved
  as-is** this session (RULE 14); left unchanged.
- Deck/Excel **shaping** adds one LLM call per deliverable; fail-open fallbacks keep delivery robust
  if the local model returns bad JSON. On the single local gemma4 these calls serialize (seconds).

### What to do FIRST next session (Phase 5 starting point)
1. Run `python -m pytest tests/ -v` — verify **177 pass** (live tests need Ollama + SearXNG up).
2. PDF is **already live** (MSYS2/Pango installed). Smoke-check after any environment change:
   `python main.py analyze "Competitor brief on Figure AI"` → a `.pdf` in `./output/`.
3. Phase 5 (SPEC §15): ChromaDB memory (`core/memory.py` write/read via `nomic-embed-text`), delta
   analysis, brain.md seeding from SPEC §3.5 + the propose-additions REPL flow, voice
   (`voice_input.py`, Ctrl+Space → faster-whisper), and end-to-end production polish. The renderers
   (`exporter` / `excel_builder` / `content_shaper`) and the wired pipeline are ready to consume.

### PHASE 4 STATUS: ✅ COMPLETE
(All three output types render production-quality deliverables **live** — PDF briefs T-1..T-6
(WeasyPrint + MSYS2/Pango), Neura PPTX decks (10 slide types, logo), and 4 formula-driven Excel
templates (N-10). Rendering wired into both the research and doc-prep paths; business case = dual
output (N-6). 177 tests green, ruff + mypy --strict clean. PDF + PPTX + Excel all live-verified.)
---

## PHASE 5 — Memory + Voice + Polish (Production-Ready)
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-06-01
**Session status**: IN PROGRESS

### Phase Plan (atomic; 1 commit each `phase-5: …`; PROGRESS updated per task)
[x] 0. Baseline 177 (176 pass + 1 skip) ✓ (RULE 11). Pulled `nomic-embed-text`; installed
       chromadb / faster-whisper / pyaudio / pynput into venv (all import cleanly); added mypy
       overrides for the stub-less libs. (done 2026-06-01)
[x] 1. `LocalLLMClient.embed(texts)` — provider-aware (Ollama `/api/embeddings`; OpenAI
       `/v1/embeddings`), `embedding_model` from config, fail-fast w/ exact pull fix. +5 tests
       incl. a live embed (done 2026-06-01 — 181 green).
[x] 2. `core/memory.py` ChromaDB store — `MemoryStore` (write/retrieve via injected `embed_fn`
       + duck-typed collection), `open_memory()` factory (persistent; fail-open `MemoryLayerError`),
       `MemoryRecord`, `extract_entities`, `make_record`/`build_memory_document` (done 2026-06-01).
[x] 3. Delta analysis — `recall()`: retrieve priors, entity-overlap → bilingual delta note
       (guaranteed header + LLM body, fail-open template) naming the prior date + age
       (done 2026-06-01 — committed with task 2; +21 memory tests, 199 green).
[x] 4. Pipeline wiring — retrieve BEFORE synthesis (delta + `prior_findings` → `SynthesisInput`,
       SPEC §5.3 step 6), write AFTER render; `resolve_memory`; `memory` param; `delta_note` +
       `proposed_brain_additions` on `PipelineResult`; fail-open notify; REPL + `analyze` wired.
       +6 tests (done 2026-06-01).
[x] 5. Brain-update flow — `propose_brain_additions` + `append_brain_additions` (idempotent
       managed heading) + REPL `_maybe_update_brain` [y/N] (default No). Seeded `brain.md` from
       SPEC §3.5 verbatim (Company Basics / Funding / Nvidia + SRCI moves) — gitignored, N-9,
       68 injected lines, all facts verified present (done 2026-06-01).
[x] 6. `core/voice_input.py` — `VoiceInput` (Ctrl+Space pynput → Tkinter overlay → pyaudio →
       faster-whisper DE/EN → inject as typed), lazy imports, fail-fast, `enabled=false` → no
       hotkey thread; REPL `/voice` + hotkey + stop-on-exit; `VoiceConfig` extended. +17 tests
       (done 2026-06-01 — 221 green).
[x] 6b. **Porter launcher** — `porter.ps1` (venv python + main.py from project root) + a `porter`
       function added to the user's PowerShell `$PROFILE`; REPL banner rebranded to **Porter**.
       Verified: `porter --help` runs; `$PROFILE` function resolves (done 2026-06-01).
[x] 7. Production polish — README finalized (Porter / memory / delta / voice / setup), config.yaml
       voice fields, dependency-failure messages audited. Quality gate: ruff + `mypy --strict`
       (30 files) + 221 pytest — all green (done 2026-06-01).
[x] 8. Live end-to-end verification — EN competitor brief (PDF + memory write), memory/delta live
       (real nomic + ChromaDB + gemma; hardened so a flaky extraction never loses the delta),
       German business case → German PPTX + 5-tab Excel (N-10 holds), voice fail-fast verified.
       PROGRESS handoff + `git push` (done 2026-06-01).

### Estimated scope: Large (the final phase — memory layer + voice layer + production polish)
### Critical dependencies: Ollama (✓ gemma4:e4b) · SearXNG (✓ JSON) · nomic-embed-text (✓ pulled)
· chromadb 1.5.9 + faster-whisper + pyaudio 0.2.14 + pynput (✓ installed). Renderers + wired
pipeline (Phase 4) consumed as-is.

### What Was Built (Phase 5)
- **`LocalLLMClient.embed(texts)`** — provider-aware embeddings: Ollama native `/api/embeddings`
  (one request per text) and OpenAI-compatible `/v1/embeddings`; uses `llm.embedding_model`
  (`nomic-embed-text`, CPU — no VRAM competition). Fail-fast `LLMError` with the exact
  `ollama pull nomic-embed-text` fix on a missing model/empty vector (RULE 6/10).
- **`core/memory.py` (Layer 2 — ChromaDB)** — `MemoryStore` writes each run's analysis digest
  (title + bottom line + sections) as an embedded document with metadata (entities, ISO timestamp,
  task type, language, quality score) and retrieves the nearest priors. `open_memory()` builds a
  persistent client at `data/chroma_db` with `embedding_function=None` (vectors always come from
  our local embedder — **nothing is ever downloaded by ChromaDB**). `extract_entities()` (fast LLM,
  fail-open) tags runs. `recall()` retrieves priors, builds the injected `prior_findings`, and — on
  an **entity overlap** — produces a **bilingual delta note**: a deterministically-built header
  (`Since our last analysis of X (date, N weeks ago):` / German) guaranteeing the SPEC §15 phrase,
  plus an LLM "what changed" body that **fails open** to a template.
- **Brain-update flow (Layer 1)** — `propose_brain_additions()` (durable, high-signal only;
  fail-open) + `append_brain_additions()` (idempotent `## AGENT-PROPOSED ADDITIONS` heading, dated
  bullets, kept by `load_brain`). The REPL's `_maybe_update_brain` shows them and writes only on an
  explicit `[y/N]` **default-No** confirm (brain.md is confidential — N-9). `brain.md` seeded from
  SPEC §3.5 (Company Basics / Funding History / Nvidia + SRCI moves) verbatim.
- **Pipeline wiring** — `run_pipeline` gained a `memory` param (advisory). Research path:
  retrieve+delta **before** synthesis (delta + priors injected into `SynthesisInput.prior_findings`,
  SPEC §5.3 step 6) → write the run **after** delivery → propose brain additions (effort-gated, not
  on LOW). Every memory op is wrapped fail-open (`MemoryLayerError` → `notify`, deliver anyway).
  `resolve_memory()` opens the store once (caller-side); the REPL and `analyze` pass it in.
  `PipelineResult` gained `delta_note` + `proposed_brain_additions` (defaults → back-compat).
- **`core/voice_input.py` (Layer — voice)** — `VoiceInput`: Ctrl+Space (pynput `GlobalHotKeys`) →
  Tkinter overlay → pyaudio capture (16 kHz mono, `max_record_seconds`) → faster-whisper transcribe
  (DE/EN auto) → inject as typed (pynput `Controller`). All heavy libs **lazy-imported** via
  `_require` (exact pip fix on ImportError); `voice.enabled=false` → `build_voice_input` returns
  None (no hotkey thread, no hard dep). Record/transcribe/inject/overlay are overridable seams →
  fully unit-tested without a mic/model. REPL: `/voice` synchronous command + the hotkey path +
  stop-on-exit.
- **`porter` launcher** — `porter.ps1` runs the REPL from the project root via the venv Python
  (args pass through to `main.py`); a `porter` function added to the user's PowerShell `$PROFILE`.
  REPL banner rebranded **Porter** (display only — RULE 14, no content/output change).

### Key Technical Decisions (Phase 5)
| Decision | Choice | Reason |
|----------|--------|--------|
| Memory = advisory/fail-open vs fail-fast | Fail-**open** everywhere (notify the exact fix, deliver anyway); embeddings/ChromaDB never block | SPEC REQ-5 + kickoff: memory is additive. "No silent degrade" satisfied by always surfacing the precise fix. Hard deps (Ollama/SearXNG) keep their fail-fast. |
| ChromaDB embeddings | We pass vectors directly (`embedding_function=None`); embed via `LocalLLMClient.embed` | Keeps everything local — ChromaDB never downloads its default ONNX model; honors RULE 6 (all embed calls via the client). |
| Entity matching for delta | LLM `extract_entities` + forgiving case-insensitive substring overlap | Precise "same company" detection that still fires on `Figure` vs `Figure AI`; semantic retrieval finds candidates, entity overlap gates the delta. |
| Delta note construction | Deterministic header (guarantees the §15 phrase + date + age) + LLM body, fail-open to a template | The success-gate phrase always appears even if the model hiccups. |
| `run_pipeline` opens memory? | **No** — caller opens via `resolve_memory`, passes it in (`None` = off) | Keeps the 177 prior tests untouched (they pass no store → memory off) and avoids surprise ChromaDB/embedding calls in tests. |
| Brain append target | EOF under one idempotent `## AGENT-PROPOSED ADDITIONS` heading | No mid-file surgery; survives repeated confirms without duplicate headers; `load_brain` keeps the bullets, strips the `#` comment. |
| Voice recording | Fixed `max_record_seconds` window per press (config-driven) | Robust + dependency-light (no deprecated `audioop` silence detection); good enough for a local push-to-talk tool. |
| Voice deps | Lazy `_require()` indirection (not top-level imports) | Importing `core.voice_input` needs none of pyaudio/whisper/pynput; tests force the ImportError branch by monkeypatching `importlib.import_module`. |
| Porter launcher encoding | ASCII-only `porter.ps1` | PowerShell 5.1 reads BOM-less UTF-8 `.ps1` as ANSI — em dashes broke the parse; ASCII is portable. |

### Files Created/Modified (Phase 5)
| File | Status | Key Contents |
|------|--------|-------------|
| llm/local_llm_client.py | Modified | `embed()` + `_embed_ollama`/`_embed_openai` + `embedding_model` property |
| core/memory.py | Modified | ChromaDB `MemoryStore`/`open_memory`/`MemoryRecord`, `extract_entities`, `recall`+`build_delta_note`, brain-update helpers (kept `load_brain`) |
| core/pipeline.py | Modified | `resolve_memory`, memory retrieve/write wiring, `_quality_score`, `memory` param |
| core/intake.py | Modified | session memory + voice wiring, `/voice`, `_maybe_update_brain`, delta panel, Porter banner |
| core/voice_input.py | Created | `VoiceInput` + `build_voice_input` (lazy, fail-fast, seam-testable) |
| core/config.py / config.yaml | Modified | `VoiceConfig` (sample_rate/max_record_seconds/compute_type/device_index) |
| models/synthesis.py | Modified | `PipelineResult.delta_note` + `proposed_brain_additions` |
| main.py | Modified | `analyze` resolves + passes `memory` |
| porter.ps1 | Created | one-word launcher (venv python + main.py) |
| brain.md | Modified (gitignored) | seeded with SPEC §3.5 public facts |
| pyproject.toml | Modified | mypy overrides: chromadb/faster_whisper/pyaudio/pynput |
| tests/test_local_llm_client / test_memory / test_pipeline / test_intake / test_voice_input | Created/Modified | +5 / +21 / +6 / +7 / +14 tests |

### Tests Status (Phase 5)
- **221 passed, 1 skipped** (up from 177), in ~40s. `ruff format` + `ruff check` clean;
  `mypy --strict core llm models main.py` clean (**30** source files). New coverage: embed
  payload/parse/fail-fast + live embed; memory write/retrieve (fake + real `EphemeralClient`),
  entity extraction, recall delta (same/diff/empty entity), delta fail-open template, brain
  propose/append + `load_brain` keep; pipeline memory delta-inject+write + fail-open; REPL
  brain-update [y/N] + delta panel; voice capture/handle-hotkey/inject seams + lazy-import fail-fast
  + hotkey parsing + `start()` listener.

### Git Log (this session)
- phase-5: LocalLLMClient.embed (provider-aware nomic-embed-text) + Phase 5 plan
- phase-5: porter launcher + REPL display name 'Porter'
- phase-5: ChromaDB memory store + delta analysis + brain-update helpers
- phase-5: wire ChromaDB memory into pipeline + REPL brain-update flow
- phase-5: local voice input (Ctrl+Space -> faster-whisper -> REPL)
- phase-5: finalize README (Porter launcher, memory/delta, voice, setup)
- phase-5: harden delta detection (match prior entity named in the request)
- phase-5: Phase 5 complete — live verification + handoff (this commit)

### Live Verification (this session — real Ollama/gemma4:e4b + SearXNG + ChromaDB)
- **Memory + embeddings + delta (mechanism):** real `nomic-embed-text` embeddings + real ChromaDB
  PersistentClient write→query + real gemma delta → *"Since our last analysis of Figure AI
  (2026-05-11, 3 weeks ago): …new humanoid model… fresh funding round in 2026."* ✅
- **Delta robustness:** the headline gate could be missed when the per-run entity-extraction call
  flakes (observed live on run #2). Hardened `recall` to also match a **prior's entity named in the
  current request**; re-verified live with **empty extraction** → delta still fires
  ("…$1B → $39B valuation…"). ✅
- **End-to-end EN run (`analyze --effort low` "competitor brief on Figure AI"):** 24 sources
  evaluated / 3 read → Neura-Lens analysis (brain.md context visible) → **PDF written** to
  `./output/`, run **stored in ChromaDB** (entity `Figure AI`, quality 100), exit 0. ✅
- **German business case (`analyze --effort low`, DE):** one run → **German 9-slide PPTX deck**
  (markers: für/und/Markt/Investition/Geschäft/Analyse) **+ 5-tab Excel** business-case model
  (Summary/Assumptions/Projections/Scenarios/Sources); `Summary!B5 = =Assumptions!$B$4` re-opens as
  `None` under `data_only` → **pure formula, N-10 holds**. Dual output in one run (N-6). ✅
- **Voice:** pynput/pyaudio/faster-whisper/numpy installed + import clean; `VoiceInput` logic +
  seams unit-tested; model-load **fail-fast verified** (the agent shell blocks the one-time
  HuggingFace download — `LocalEntryNotFoundError`/SSL — exactly like the Phase-4 GTK case; the
  error carries the exact fix). **Manual user step (needs network for the one-time model download +
  a real mic + interactive desktop):** set `voice.enabled: true`, press **Ctrl+Space** to dictate.
- **Zero errors end-to-end** across all three live runs (EN + DE), exit 0 each. `pytest` 223 passed
  / 1 skipped; `ruff` clean; `mypy --strict` 30 files clean.

### PROJECT COMPLETE — what Porter does end-to-end
Porter is a **100% local** research/strategy agent for the Neura Robotics CEO-Office + Strategy
internships. One command — **`porter`** — opens the REPL (or `python main.py`). You give it a task
by **text or voice (Ctrl+Space)**, in German or English; it parses intent + auto-detects effort
(`low`/`high`/`ultra`), asks ≤2 clarifying questions, confirms a research plan, then runs
**multi-agent web research** (SearXNG + parallel workers, source+date+confidence on every fact),
**consults persistent memory** (ChromaDB) to inject prior findings and a **bilingual delta** on
repeat entities, reasons with **brain.md** Neura context + playbooks, **self-critiques and revises**,
and renders the routed deliverables: a **PDF brief** (T-1..T-6), a **Neura PPTX deck** (10 slide
types, logo), and/or a **formula-driven Excel workbook** (E-1..E-4); a **business case** emits a deck
**and** an Excel model in one run. After delivery it stores the run and may propose durable
**brain.md** additions for `[y/N]` confirm. CEO-office **document-prep** mode consolidates internal
files (zero-hallucination) without web research. Everything is local (Ollama `gemma4:e4b` +
`nomic-embed-text`, SearXNG, python-pptx/openpyxl/WeasyPrint) — no external AI API, ever. Memory and
voice are **advisory/fail-open**; hard deps fail fast with exact fixes.

**Run it:** `porter` (REPL) · `porter analyze "…" --effort ultra` · `porter prepare file.pdf` ·
`porter ask "…"`. Prereqs: Ollama (`gemma4:e4b` + `nomic-embed-text`), Docker/SearXNG, `pip install
-r requirements.txt`; PDF needs the GTK/Pango runtime (MSYS2) and voice needs the one-time
faster-whisper model download. Next step (post-Phase-5, recorded above): **fix the thin
bibliography** so every source the workers used lands in the brief.

### Post-Phase-5 Backlog (next steps — DO NOT LOSE)
1. **Bibliography too thin (must-fix, user-flagged 2026-06-01).** Rendered briefs usually list
   **fewer than 5 sources** — clearly insufficient for strategy work. Today the bibliography is
   whatever the LLM emits in its JSON `sources` (`core/synthesizer.py` `_coerce_sources`); the
   deterministic `_sources_from_research` fallback only fires when the LLM cites **none**, and gemma
   lists very few. **Fix:** the research workers already carry the real sources
   (`WorkerFindings.sources` + every `Finding.source_url` with date/confidence, aggregated in
   `ResearchReport.worker_findings`/`.evidence`); deterministically compile the bibliography from the
   **union of all worker sources + finding URLs** (dedup by URL, keep date + tier via
   `classify_tier` + confidence) and **always merge** it into `AnalysisOutput.sources` (not only when
   the LLM emits zero). Mostly a synthesizer change + passing the full `ResearchReport` sources into
   synthesis; the PDF/PPTX sources sections already consume `AnalysisOutput.sources`. Watch `num_ctx`
   (more sources = bigger prompt). The agent's directive: *workers send all their best/used sources →
   the orchestrating agent writes them all into the bibliography.*

### PHASE 5 STATUS: ✅ COMPLETE
(ChromaDB session memory with `nomic-embed-text` embeddings + bilingual delta analysis
(hardened, live-verified) + brain.md seed/propose-flow + local voice input (Ctrl+Space →
faster-whisper) + the `porter` launcher + production polish. Memory/voice are advisory/fail-open.
223 tests + ruff + `mypy --strict` (30 files) green. Live-verified: EN end-to-end (PDF + memory),
delta on repeat entity, German business case → German PPTX + Excel (N-6/N-10). **The Strategy Agent
("Porter") is complete end-to-end.** One known post-phase next step recorded: thicken the
bibliography.)
---
