# OPUS WORKFLOW INSTRUCTIONS
# Strategy Agent — Session Execution Protocol
> This file tells every Opus instance exactly how to work.
> Read it fully before touching a single file.
> Version: 0.3 | Last updated: 2026-05-30

---

## 0. CRITICAL RULES — NEVER VIOLATE

```
RULE 1:  Read strategy_agent_SPEC.md + this file completely before writing ANY code.
RULE 2:  Read PROGRESS.md completely (if it exists) before planning.
RULE 3:  Never add dependencies not listed in SPEC.md Section 6.
RULE 4:  Never hardcode model names, API keys, file paths, color values, or URLs.
RULE 5:  Every file path uses pathlib.Path. No string concatenation. No os.path.
RULE 6:  Every LLM call uses LocalLLMClient (never raw requests to Ollama in business logic).
RULE 7:  After EVERY session, write a complete handoff to PROGRESS.md.
RULE 8:  The Phase 5 agent must be production-ready. Not a prototype. Not "basics."
RULE 9:  If a genuine implementation gap exists (not covered by SPEC), make the most
         conservative choice and document it clearly in PROGRESS.md.
RULE 10: num_ctx MUST be passed in every LLM API call. Never rely on any provider's default.
RULE 11: Run all existing tests BEFORE writing new code. A broken foundation must not
         be built upon. If previous tests fail, fix them first.
RULE 12: Git commit after every completed task (not after every line — after each task
         from your plan is done and verified). Commit message: "phase-N: [task description]"
RULE 13: Update PROGRESS.md after every completed task (not just at session end).
         A session that crashes mid-way leaves a recoverable state this way.
RULE 14: You make NO content decisions about the agent. The SPEC is authoritative.
         You make only technical/implementation decisions and document them.
         Never ask "should the agent know about Neura?" — that is answered in the SPEC.
```

---

## 1. SESSION START PROTOCOL (EVERY SESSION, NO EXCEPTIONS)

Execute this sequence before doing anything else. Do not skip steps.

```
1. READ strategy_agent_SPEC.md — complete, every section
2. READ opus_WORKFLOW.md (this file) — complete
3. READ PROGRESS.md — if it exists
   - If PROGRESS.md doesn't exist: you are Phase 1 Opus. Create it after planning.
   - If it exists: understand exactly what is done, what state the code is in,
     what decisions were made, and what phase you are executing.
4. IDENTIFY your phase from PROGRESS.md "Current Phase" field.
5. CHECK DEPENDENCIES:
   - Is Ollama running? Run: curl http://localhost:11434/api/tags
   - Is the configured model available? Run: ollama list
   - For Phase 2+: Is SearXNG reachable? Run: curl http://localhost:8888/search?q=test&format=json
   - If any dependency is missing: document in PROGRESS.md and write code that fails fast
     with clear setup instructions. Do NOT silently skip.
6. RUN EXISTING TESTS (if any exist):
   - cd into project root
   - Run: python -m pytest tests/ -v
   - All tests must pass before you write any new code. Fix failures first.
7. CREATE your session plan (see Section 3).
8. Write plan to PROGRESS.md before executing (see Section 7).
9. GIT INIT (if Phase 1 and no .git yet): git init && git add . && git commit -m "phase-1: project scaffold"
10. Execute the plan — commit after each completed task.
11. Write end-of-session handoff to PROGRESS.md.
```

---

## 2. THE FIVE PHASES — SUMMARY TABLE

| Phase | Name | Core Deliverable | Success Gate |
|-------|------|-----------------|--------------|
| 1 | Foundation | LocalLLMClient + Pydantic models + CLI + Docker compose + startup checks | `python main.py ask "test"` returns LLM response. Backend switchable via config only. |
| 2 | Research Engine | SearXNG client + pdf_reader + content fetcher + cache + parallel async | `python main.py research "query"` returns real web results. `python main.py analyze-doc file.pdf` returns extracted facts. |
| 3 | Agent Brain | Intent parser + bilingual clarification + multi-step reasoning + Neura Brain injection | Agent asks ≤2 questions then produces structured analysis for complex M&A query in correct language. |
| 3.5 | Advanced Agent Loop | Effort master dial (low/high/ultra) + multi-agent deep research (orchestrator-workers) + deep_research_playbook + mid-research clarification + output critic/revision (user-authorized amendment, SPEC §15.5) | `analyze --effort ultra` → N parallel workers, rounds, critique+revision; auto-effort + `/effort` override; config-scalable; tests/ruff/mypy green. |
| 4 | Output Generation ✅ | Jinja2 briefs (T-1..T-6, DE+EN) + PDF + PPTX (all 10 slide types, Neura colors, logo) + excel_builder (E-1..E-4, formula-driven N-10) + content_shaper; rendering wired into research + doc-prep paths | One query → professional PDF brief + Neura .pptx (logo bottom-right) + recalculating Excel; business case = deck + Excel (N-6). 177 tests/ruff/mypy green. (PDF needs the user's one-time Windows GTK install.) |
| 5 | Memory + Voice + Polish | ChromaDB RAG + Voice Ctrl+Space + Delta analysis + End-to-end production quality | Second run on same entity shows delta. Voice works. Zero errors end-to-end. Both DE and EN. |

---

## 3. SESSION PLANNING PROCESS

At the start of each session, before coding:

### Step 1: Read and understand the phase
From SPEC.md Section 15, read the full description of your phase:
- What are the exact deliverables?
- What are the success criteria?
- What does this phase depend on from previous phases?

### Step 2: Assess current state
From PROGRESS.md:
- What files exist and what's in them?
- What was the last completed task?
- What tests are passing?
- Are there any open issues from the previous phase?
- **If a previous phase is marked INCOMPLETE:** Continue that phase from the last completed task. Do not skip to the next phase.

### Step 3: Create your session plan
Write a detailed, ordered task list. Every task must be:
- **Concrete**: not "implement research" but "create `core/researcher.py` with `SearXNGClient` class containing `search_async(query: str, max_results: int) -> list[SearchResult]` method"
- **Independently testable**: a test can verify it in isolation
- **Atomic**: if the session crashes after this task, the next Opus can continue from here

Format for PROGRESS.md:
```
## Phase [N] Session Plan
Created: [timestamp]
Status: IN PROGRESS

### Tasks:
[ ] 1. Create SearXNG Docker Compose config with health check endpoint
[ ] 2. Implement SearXNGClient in core/researcher.py (async, reads config)
[ ] 3. Implement ContentFetcher (trafilatura) in core/researcher.py
[ ] 4. Implement pdf_reader.py: pdfplumber + pytesseract + vision fallback
[ ] 5. Add diskcache layer for search result caching
[ ] 6. Write tests/test_researcher.py (SearXNG + content fetch + PDF read)
[ ] 7. Integration test: full research pipeline from query to structured output

### Estimated scope: Medium (5–6 hours of focused work)
### Critical dependencies: LocalLLMClient from Phase 1 (✓ available), Docker Desktop (user must have installed)
```

### Step 4: Execute sequentially
- Check off `[x]` as tasks complete
- After each task: run its tests, then `git commit -m "phase-N: [task name]"`
- If a task takes significantly longer than expected: note it, continue — never skip
- Update PROGRESS.md after EACH task (not just at end)

---

## 4. CODING STANDARDS

### Architecture Rules
- **No LangChain**. Thin, focused Python classes. LangChain adds 50+ dependencies, makes debugging a nightmare, and contradicts the model-agnostic design.
- **Config-driven everything**. Model name, backend URL, paths, colors, timeouts — all from config.yaml. Nothing hardcoded. Color hex values go in config.yaml, referenced in code as `config.output.colors.accent_cyan`.
- **Pydantic v2 everywhere**. All data flowing between modules has a Pydantic type. No untyped dicts.
- **Single responsibility**. `researcher.py` only researches. `pdf_reader.py` only reads documents. `synthesizer.py` only synthesizes. No cross-module logic creep.
- **Async for I/O**. All web requests, SearXNG calls, and content fetching use asyncio. Sync for LLM calls.
- **Fail fast**. If a dependency check fails at startup, print exact fix instructions and exit. Never silently degrade.

### The LocalLLMClient (Phase 1 critical, all subsequent phases use it)
```python
# Contract — Phase 1 builds it. Phases 2–5 call it.
# Backend-agnostic: talks to Ollama, LM Studio, or llama.cpp-server identically.
class LocalLLMClient:
    def __init__(self, config: LLMConfig): ...

    def generate(self,
                 prompt: str,
                 system: str = "",
                 use_thinking: bool = None,   # None = use config default
                 num_ctx: int = None,          # None = use config default — ALWAYS passed to API
                 stream: bool = False) -> str: ...

    def switch_model(self, model_name: str): ...

    @property
    def model_name(self) -> str: ...
    @property
    def backend_url(self) -> str: ...
```

**Critical implementation detail:** `num_ctx` must ALWAYS be included in every API payload sent to the provider. Ollama (and all compatible local providers) default to 4096 tokens for ALL models. The config value (default: 32768) must override this in every single call. This is the most common silent failure mode for local agents.

**Thinking mode for gemma4:** Prepend `<|think|>` to system prompt when `use_thinking=True` AND model is gemma4-family. For qwen3-family: use `/think` flag in prompt (different mechanism, same config interface — detect from `config.llm.model`).

### File Structure Rules
- Follow SPEC.md Section 7 exactly. New top-level files require justification in PROGRESS.md.
- All generated outputs: `./output/` — never to project root.
- Test files mirror module: `core/researcher.py` → `tests/test_researcher.py`
- `config.yaml` is the only place for configuration values.
- `brain.md` is in project root — read by agent at runtime, editable by user in VS Code. Gitignored — never committed.

### Python Standards
- Python 3.11+
- Type hints on ALL function signatures — no exceptions
- Docstrings on all public classes and functions (one-liner is fine)
- `pathlib.Path` for ALL file paths
- All file I/O: specify `encoding='utf-8'` explicitly
- Error handling with specific exceptions — no bare `except:`
- All LLM API calls: wrapped in try/except with informative error messages

### Code Quality
- Format with `ruff format` (or `black` if ruff unavailable)
- Lint with `ruff check --fix`
- Type-check critical modules with `mypy --strict core/` (especially LocalLLMClient and Pydantic models)
- No commented-out dead code left in final commits

---

## 5. WHAT EACH PHASE MUST NOT DO

### Phase 1 must NOT:
- Implement SearXNG, ChromaDB, pdf_reader, or output generation
- Import Phase 2+ modules (they don't exist yet)
- Try to make the full pipeline work end-to-end

### Phase 2 must NOT:
- Implement the LLM reasoning chain (Phase 3)
- Implement output formatting (Phase 4)
- Build memory system (Phase 5)
- Perfect research quality — working and tested is sufficient

### Phase 3 must NOT:
- Implement final PDF/PPTX output (Phase 4)
- Implement ChromaDB memory (Phase 5)
- Polish output format — structured and correct is the bar

### Phase 4 must NOT:
- Implement memory retrieval in synthesis (Phase 5)
- Perfect every edge case — correct and clean is the bar
- Voice input (Phase 5)

### Phase 5 MUST:
- Complete all remaining items
- Make the agent production-ready, not prototype-quality
- Handle errors gracefully with exact fix instructions
- Verify complete pipeline works end-to-end (both DE and EN inputs)
- Write comprehensive documentation and usage examples
- Seed `brain.md` with initial Neura facts from SPEC Section 3.5

---

## 6. DEPENDENCY INSTALLATION — COMMANDS

```bash
# Ollama model (if not already pulled)
ollama pull gemma4:e4b
ollama pull nomic-embed-text     # For Phase 5 ChromaDB embeddings

# Python environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

pip install -r requirements.txt
```

requirements.txt (Phase 1 creates it, later phases append):
```
# Core
pydantic>=2.0.0
pyyaml>=6.0
typer>=0.9.0
python-dotenv>=1.0.0

# LLM (OpenAI-compatible client — works with Ollama, LM Studio, llama.cpp)
openai>=1.0.0                    # OpenAI SDK for OpenAI-compatible local endpoints
requests>=2.31.0
httpx>=0.25.0

# Research (Phase 2+)
aiohttp>=3.9.0
trafilatura>=1.6.0
diskcache>=5.6.0

# Document Reading (Phase 2+)
pdfplumber>=0.10.0               # Text-based PDFs
pytesseract>=0.3.10              # OCR for scanned PDFs
Pillow>=10.0.0                   # Image handling
python-docx>=1.1.0               # Word document reading

# Output (Phase 4+)
python-pptx>=0.6.23
weasyprint>=60.0
jinja2>=3.1.0
openpyxl>=3.1.0                  # Create/write/format .xlsx files
pandas>=2.0.0                    # Read user-provided .xlsx files
xlsxwriter>=3.1.0                # Advanced chart/format fallback for Excel

# Memory (Phase 5+)
chromadb>=0.5.0

# Voice (Phase 5+)
faster-whisper>=0.10.0
pyaudio>=0.2.14
pynput>=1.7.0                    # Keyboard hotkey detection

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0

# Code Quality
ruff>=0.4.0
mypy>=1.8.0
```

**SearXNG** via Docker (Phase 2+):
```yaml
# docker-compose.yml (Phase 1 creates this file)
version: '3.8'
services:
  searxng:
    image: searxng/searxng:latest
    ports:
      - "8888:8080"
    volumes:
      - ./searxng-data:/etc/searxng
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8080/"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Start: `docker compose up -d`
Verify: `curl "http://localhost:8888/search?q=test&format=json"`

---

## 7. PROGRESS.md FORMAT — MANDATORY

Every Opus instance reads and writes PROGRESS.md. This is the handoff protocol.

**Location**: `PROGRESS.md` in project root.
**Update rule**: Append to existing content after each phase. Never delete previous phase documentation. Update task checkboxes DURING execution (not just at end).

### Template for Phase N Session:

```markdown
# STRATEGY AGENT — PROGRESS LOG
> File location: ./PROGRESS.md
> Read this completely before planning Phase N.

---

## PHASE [N] — [Phase Name]
**Executed by**: Opus [model version if known]
**Date**: YYYY-MM-DD
**Session status**: IN PROGRESS → COMPLETE

### Phase Plan (created at session start)
[Ordered task list — update checkboxes as you go]
[x] 1. Task one (completed YYYY-MM-DD HH:MM)
[x] 2. Task two (completed YYYY-MM-DD HH:MM)
[ ] 3. Task three — IN PROGRESS if session ended mid-task

### What Was Built (Completed Tasks)
[For each completed task: what was built, key implementation notes]

### Key Technical Decisions Made
| Decision | Choice | Reason |
|----------|--------|--------|
| [e.g., caching strategy] | [diskcache SQLite] | [simple, local, no server] |
| [e.g., PDF OCR fallback] | [pytesseract] | [only if pdfplumber returns <50 chars] |

### Files Created/Modified
| File | Status | Key Contents |
|------|--------|-------------|
| core/researcher.py | Created | SearXNGClient + ContentFetcher |
| tests/test_researcher.py | Created | 8 tests, all passing |
| requirements.txt | Updated | Added trafilatura, aiohttp, diskcache |

### Implementation Gaps Encountered (from SPEC)
[Any genuine spec gap: what conservative choice was made and why]

### Tests Status
- tests/test_local_llm_client.py: ✅ 5/5 passing
- tests/test_researcher.py: ✅ 8/8 passing
- [List all test files and pass status]

### Git Log (this session)
- phase-2: searxng client with parallel queries
- phase-2: content fetcher with trafilatura
- phase-2: pdf_reader pdfplumber + pytesseract
- phase-2: diskcache layer
- phase-2: all tests passing

### Known Issues / Technical Debt
[Shortcuts taken, known limitations, things the next phase should know about]

### What to do FIRST next session (Phase [N+1] starting point)
1. Run `python -m pytest tests/ -v` — verify all [X] tests pass
2. [Specific first task for next Opus to do after tests pass]
3. [Any context the next Opus needs that isn't obvious from the code]

### PHASE [N] STATUS: ✅ COMPLETE | ⏳ IN PROGRESS
---
```

---

## 8. IMPORTANT CONTEXT FOR EVERY OPUS INSTANCE

### The Origin of This Project
This SPEC and WORKFLOW were developed in a dedicated pre-development planning session between the user and Claude. Every content decision about the agent is already made and captured in `strategy_agent_SPEC.md`. The user is applying to two internship roles at Neura Robotics (CEO Office Intern, Strategy Intern) starting September 1, 2026. The agent is their competitive advantage: it collapses 3-hour research tasks to 20–30 minutes.

**What this means for you:**
You (Opus) do NOT decide what the agent should do, what it should know, what models to use by default, what language to output, what Neura is, or what templates to build. All of that is in the SPEC. Your job is to:
1. Read the SPEC completely
2. Plan your phase's implementation
3. Execute the plan with high quality
4. Document everything for the next Opus
5. Make only genuine technical implementation decisions (e.g., "which retry strategy for a 429?") and document them

### Non-Negotiable Constraints (memorize these)
1. **Fully local** — no external AI API calls ever
2. **Completely free** — no paid services, subscriptions, or usage limits
3. **Backend-agnostic** — LocalLLMClient talks to any OpenAI-compatible endpoint
4. **Model-agnostic** — switching model = one config.yaml line change
5. **Bilingual** — German and English inputs/outputs both work perfectly
6. **Fail fast** — dependency problems cause immediate clear error messages, never silent degradation

### Hardware Context
- User: Windows 11, ASUS VivoBook Pro 16x
- GPU: RTX 4060, 8GB VRAM
- RAM: 32GB system RAM
- Default model: gemma4:e4b (9.6GB Q4_K_M — partial CPU offload, fine with 32GB RAM)
- IDE: VS Code — agent CLI runs from integrated terminal

### The 4K Context Bug
Ollama defaults ALL models to 4096 tokens. Always pass `num_ctx` from config in every API call. This is not model-specific — it applies to Ollama globally.

### python-pptx Has No External Dependencies
`from pptx import Presentation` — zero internet, zero MCP, zero server. It writes .pptx files to disk.

### The brain.md File
`brain.md` in project root. Gitignored — never committed. Max 300 lines. Only content that changes the agent's output. Sections: Strategic Context / Audience Preferences / Output Style Rules / Current Focus / Active Context / Learnings. The agent reads it at the start of every synthesis call. Phase 5 seeds it. Phases 1–4 create the file path structure but leave it to Phase 5 to populate.

---

## 9. CHECKLIST BEFORE CLOSING ANY SESSION

Before writing your PROGRESS.md handoff, verify every item:

```
[ ] All planned tasks completed (or explicitly documented why not, with IN PROGRESS state)
[ ] All tests passing: python -m pytest tests/ -v → 0 failures
[ ] No hardcoded values (model names, URLs, paths, colors — all from config.yaml)
[ ] LocalLLMClient used for all LLM calls (no raw requests to Ollama in business logic)
[ ] num_ctx passed in all LLM API calls (never relying on provider defaults)
[ ] pathlib.Path used for all file paths; no string concatenation
[ ] encoding='utf-8' specified in all file I/O operations
[ ] All new functions have type hints and docstrings
[ ] ruff format + ruff check run; no lint errors remaining
[ ] requirements.txt updated with all new dependencies
[ ] Git committed after each completed task (check: git log --oneline -20)
[ ] PROGRESS.md updated with: completed tasks, technical decisions, test status, Git log
[ ] README.md updated with any new setup steps or commands
[ ] Phase success criteria verified (from SPEC Section 15)
[ ] "What to do FIRST next session" section written clearly in PROGRESS.md
```

---

## 10. IF SOMETHING IS UNCLEAR OR CONTRADICTORY

Priority order for resolving conflicts:
1. **SPEC Section 2 (Non-Negotiable Requirements)** — always wins
2. **SPEC Technical Architecture (Section 4)** — follow unless genuinely impossible
3. **This WORKFLOW.md** — follow precisely
4. **Your own technical judgment** — only for genuine implementation gaps, always documented

If something seems wrong, impossible, or contradictory:
- Do NOT silently work around it
- Make the best technical choice available
- Document it clearly in PROGRESS.md under "Implementation Gaps Encountered"
- Note what SPEC constraint it touches (if any)
- Move forward — do not stall

---

## 11. ERROR RECOVERY PROTOCOL

If you are starting a session and PROGRESS.md shows a phase as `IN PROGRESS`:

```
1. Read the last completed task (the last [x] in the task list)
2. Run tests: python -m pytest tests/ -v
3. If tests pass: continue from the first unchecked [ ] task
4. If tests FAIL:
   a. Identify which module is broken
   b. Fix the broken tests FIRST before adding any new code
   c. Document the fix in PROGRESS.md under "Implementation Gaps"
   d. Commit: git commit -m "phase-N-recovery: fix [description]"
   e. Then continue from the next unchecked task
5. NEVER start a new phase if the current phase has unchecked tasks — finish what was started
6. NEVER assume previous code is correct without running tests first
```

If git history is missing (no .git or corrupted):
- Start from scratch with what exists on disk
- Treat existing code as "unknown state" — run tests to verify
- Document the situation in PROGRESS.md and commit the current state immediately

---

## 12. GIT PROTOCOL

```
# Project root — initialize once in Phase 1:
git init
echo ".venv/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "output/" >> .gitignore
echo "data/chroma_db/" >> .gitignore
echo "logs/" >> .gitignore
echo "brain.md" >> .gitignore       # Agent brain — local only, never commit
echo ".env" >> .gitignore
git add .
git commit -m "phase-1: project scaffold"

# After each completed task:
git add -A
git commit -m "phase-[N]: [concrete task description]"

# Good commit message examples:
# "phase-1: LocalLLMClient with config-driven backend URL"
# "phase-2: SearXNG client with parallel async queries"
# "phase-2: pdf_reader pdfplumber + pytesseract fallback"
# "phase-3: intent parser DE/EN language detection"
# "phase-4: all 10 PPTX slide types with Neura color scheme"
# "phase-5: ChromaDB memory write + delta analysis"

# NEVER commit:
# - .env files
# - output/ directory (generated files)
# - data/chroma_db/ (user's personal memory)
# - .venv/ (Python virtual environment)
# - *.pyc or __pycache__
```

---

*End of opus_WORKFLOW.md v0.3*
