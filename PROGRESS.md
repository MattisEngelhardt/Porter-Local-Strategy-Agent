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
[ ] 7. ResearchManager (decompose, parallel orchestration, aggregation, mid-research clarification) + tests
[ ] 8. Critic + revision (`core/critic.py`, effort-gated, source-validation rubric, fail-open) + tests
[ ] 9. Pipeline + presentation (full master loop wiring; render_result telemetry; `analyze --effort`;
       REPL `/effort`) + test_pipeline/test_intake updates
[ ] 10. Quality gate (ruff + mypy --strict + full pytest green) + live runs (ultra multi-agent,
        auto-effort, mid-research, config-scalable) + document
[ ] 11. Docs (README + full Phase-3.5 handoff) + `git push origin main`

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

### PHASE 3.5 STATUS: ⏳ IN PROGRESS
---
