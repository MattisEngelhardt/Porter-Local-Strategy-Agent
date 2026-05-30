# STRATEGY AGENT — PROGRESS LOG
> File location: ./PROGRESS.md
> Read this completely before planning the next phase.

---

## PHASE 1 — Foundation
**Executed by**: Opus (claude-opus-4-8)
**Date**: 2026-05-30
**Session status**: IN PROGRESS

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
[ ] 10. Verify success gate; write full Phase 1 handoff (this file)

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

### Implementation Gaps Encountered (from SPEC)
- **num_ctx vs OpenAI-compatibility conflict** (see decision above). Resolved conservatively per RULE 9.
- **assets/neura_logo.png** referenced in SPEC §7 as "provided" but is absent on disk. Not a Phase 1 blocker (used in Phase 4). Directory created; logo must be added before Phase 4.
- **brain.md** already exists on disk (4.9 KB). Per SPEC §9 N-9 it is gitignored and owned by Phase 5; left untouched this session.

### What to do FIRST next session (Phase 2 starting point)
1. Run `python -m pytest tests/ -v` — verify all Phase 1 tests pass.
2. Install Docker Desktop (not on PATH yet) + `docker compose up -d` for SearXNG; verify `curl "http://localhost:8080/search?q=test&format=json"`.
3. Begin Phase 2 (researcher.py / pdf_reader.py / excel_reader.py) per SPEC §15.

### PHASE 1 STATUS: ⏳ IN PROGRESS
---
