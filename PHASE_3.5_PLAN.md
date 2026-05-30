# Phase 3.5 — Advanced Agent Loop (Effort System · Multi-Agent Deep Research · Self-Correction)

> Status: **APPROVED v1.0** — authoritative, user-approved plan for Phase 3.5.
> Read this file completely before writing any code. Date: 2026-05-30.
> This is a user-authorized amendment to the LOCKED SPEC (record it in SPEC §15.5 + WORKFLOW §2).

## Context

Phase 3 shipped a working but **linear** loop: intent → ≤3 upfront questions → one research pass →
one synthesis → output. The user wants a genuinely sophisticated, **non-linear, self-correcting,
proactive** agent — not "3 Fragen abhaken → research → output". Concretely (locked with the user):

1. **Effort system (low / high / ultra)** — one **master dial** (à la Claude Code `/effort`) that
   absorbs the old depth axis and controls the *whole* loop's intensity. **Auto-detected** from
   task complexity **and overridable** (`/effort …` in the REPL, `--effort` on `analyze`). The
   agent surfaces the chosen effort in the plan step so the user sees/can change it.
2. **Multi-agent deep research (orchestrator-workers, by default — not just a gap fallback)** — a
   **ResearchManager** decomposes the task and runs **N parallel research-worker "identities"**,
   each researching a distinct angle, validating sources, and reporting structured findings back to
   the manager, who aggregates a clean evidence report.
3. **Explicit deep-research methodology** — a new authored `deep_research_playbook.md` telling the
   workers *how to research well*: authoritative + **recent (never stale)** + **validated/cross-
   referenced** sources, depth over breadth, confidence + date on every fact. Injected into workers.
4. **Interleaved, proactive mid-research clarification** — when a worker/manager hits an ambiguity
   that couldn't be seen upfront, it comes **back to the user mid-research** with a precise question
   and feeds the answer into that area's search. Bounded by effort.
5. **Output critic + revision loop (evaluator-optimizer)** — a separate agent objectively scores the
   draft against a playbook rubric (incl. source-validation) and forces targeted revisions before
   delivery. Effort-gated.

**Hardware reality (designed around):** one local model (gemma4:e4b, 8 GB VRAM) **serializes**
concurrent LLM calls in Ollama; real parallelism arrives with the planned server + larger model.
So the orchestrator-worker architecture is built **correctly concurrent** (async worker identities,
web I/O genuinely parallel via aiohttp; LLM steps run via `asyncio.to_thread`), but the degree of
concurrency is **config-gated** (`effort.worker_concurrency`) — modest on the laptop, full fan-out
on the server, **zero code change** to scale.

Phase 3.5 is a **user-authorized amendment** to the LOCKED SPEC (recorded in SPEC §15.5 + WORKFLOW
§2). Still out of scope: file rendering (Phase 4), ChromaDB memory/learning-delta (Phase 5). The
`deep_research_playbook.md` is authored content → the user reviews it.

---

## Master loop (target architecture)

```
intake (parse "/effort <lvl>" prefix)
 → parse_intent  + AUTO-DETECT effort (LLM + keyword booster; default HIGH when unsure)
 → upfront clarify  (one-at-a-time, multi-dimensional, ≤ effort.max_clarifications)
 → research plan + effort shown  → confirm  (decline → brain quick answer, then offer full run)
 → ResearchManager.run(effort):
       decompose task → effort.research_workers sub-topics (angles from analysis_playbook)
       run workers concurrently (bounded by effort.worker_concurrency):
           ResearchWorker: craft queries → SearXNG+fetch (Phase-2 engine) → evaluate sources
               (deep_research_playbook: recency/authority/cross-ref) → extract Findings
               (fact + source + date + confidence) → iterate ≤ effort.max_research_rounds
       MID-RESEARCH proactive questions (≤ effort.max_midresearch_questions) → answer fed back
       aggregate + dedup → ResearchReport (worker findings digest + evidence + telemetry)
 → synthesize  (brain + playbooks + findings digest; thinking by effort)  [reuse Phase-3 synthesizer]
 → if effort.critique:  critique → while !passed and < effort.revisions: revise → re-critique
 → quality_check (deterministic floor, kept)
 → PipelineResult(analysis, effort, critique, revisions, research telemetry, answered, midresearch_qs)
```

Every advisory layer is **fail-open** (a worker/critic/coverage glitch never blocks delivery);
hard deps (SearXNG all-fail, LLM unreachable) keep Phase-3 fail-fast with fix instructions.

---

## Design (config-driven · pathlib · utf-8 · LocalLLMClient everywhere · num_ctx always sent)

### 1. Effort dial + config (the single knob; the future-hardware scaler)
`core/config.py`: `EffortLevelConfig` (per-level params) + `EffortConfig`; `config.yaml`: new `effort`
block. Effort is the master dial — depth-gating is replaced by effort-gating.
```yaml
effort:
  default: "high"              # used when auto-detect is unsure (never silently shallow)
  critique_min_score: 75       # global pass threshold
  worker_concurrency: 2        # how many workers truly run at once (laptop=2; server: raise)
  levels:
    low:   {research_workers: 1, max_research_rounds: 1, max_fetch_per_worker: 3,
            max_clarifications: 1, max_midresearch_questions: 0, revisions: 0, critique: false, thinking: false}
    high:  {research_workers: 3, max_research_rounds: 2, max_fetch_per_worker: 5,
            max_clarifications: 2, max_midresearch_questions: 1, revisions: 1, critique: true, thinking: true}
    ultra: {research_workers: 5, max_research_rounds: 3, max_fetch_per_worker: 8,
            max_clarifications: 3, max_midresearch_questions: 2, revisions: 2, critique: true, thinking: true}
```
`EffortConfig.level_for(effort) -> EffortLevelConfig` + safe defaults. Post-upgrade the user just
edits these numbers + `worker_concurrency`.

### 2. Models (typed contracts)
- `models/task.py`: `EffortLevel(StrEnum)` = LOW/HIGH/ULTRA; add `Intent.effort: EffortLevel`
  (auto-detected). `Depth` is **derived from effort** for the time estimate only (LOW→~12min,
  HIGH→~30, ULTRA→~60+); effort is the gating dial everywhere.
- `models/research.py`: `Confidence(StrEnum)` HIGH/MEDIUM/ESTIMATE; `Finding(claim, source_url,
  date, confidence, recency_flag)`; `WorkerFindings(sub_topic, queries, findings, sources, gaps,
  confidence)`; `CoverageGap`/`CoverageReport`; `ResearchReport(sub_topics, worker_findings,
  evidence: list[FetchedContent], rounds_used, workers_used, sources_evaluated, midresearch:
  list[ClarificationRound])`.
- `models/synthesis.py`: `CriterionResult(name, passed, comment)`, `Critique(passed, score, issues,
  criteria, summary)`; extend `PipelineResult` with `effort: EffortLevel`, `critique: Critique|None`,
  `revisions: int`, `research_report: ResearchReport|None` (defaults keep Phase-3 tests valid).

### 3. Deep-research methodology — `playbooks/deep_research_playbook.md` (authored, user-reviewed)
New playbook the workers/manager obey: source-authority ladder (primary/official > Tier-1 press >
Tier-2 > Tier-3 signals); hard **recency windows** (fast-moving ≤6 months; older → date-flag);
**cross-reference** material/financial claims in ≥2 independent sources (else mark Estimate);
company PR/blogs = intent signals not facts; Wikipedia = background only; **depth over breadth**
(follow the thread); discard SEO spam / undated pages for material facts; entity+metric+timeframe
query craft + refine when results are thin/stale; **every fact carries source + date + confidence**.
`core/playbooks.py`: extend `Playbooks` with `deep_research` + load the 4th file (fail-fast).

### 4. Effort detection + override (`core/intent_parser.py` + intake/main)
- `detect_effort(task, intent, llm_suggestion) -> EffortLevel`: deterministic keyword booster
  ("ultra/vollständig/umfassend/tief/deep" → ULTRA; "quick/kurz/überblick/news" → LOW; multi-entity
  screening / business_case / board_prep → HIGH+) combined with the LLM's suggestion; **default
  HIGH** when unsure (never silently shallow). Added to `parse_intent` output (`Intent.effort`).
- Override parsing: `parse_effort_override(text) -> (EffortLevel|None, stripped_text)` for a leading
  `/effort low|high|ultra` token (REPL); `analyze --effort` option (main.py). Explicit always wins.

### 5. Interaction protocol extension (mid-research questions)
`core/pipeline.py` `Interaction`: add `ask_text(self, question: str) -> str` (free-form precise
question). `ReplInteraction` (intake) → `Prompt.ask`; `AutoInteraction` → returns "" (manager logs
"assumption" and proceeds) or canned answers. Upfront `clarify` budget now comes from
`effort.max_clarifications` (≤3 ceiling preserved).

### 6. Orchestrator-workers research — `core/research_agent.py` (new)
- `ResearchWorker.run(sub_topic, effort_cfg) -> WorkerFindings`: LLM crafts targeted queries (deep-
  research methodology injected) → reuse Phase-2 `SearXNGClient`/`ContentFetcher`/`rank`/`dedup` to
  search+fetch (`max_fetch_per_worker`) → LLM evaluates sources (recency/authority) + extracts
  `Finding`s with source+date+confidence → iterate up to `max_research_rounds` if coverage is thin.
  Worker failure is isolated (returns empty findings; manager continues).
- `ResearchManager.run(client, config, intent, plan, interaction, effort_cfg) -> ResearchReport`:
  LLM decomposes into `research_workers` sub-topics (angles chosen via the analysis_playbook
  framework for the task type, e.g. competitor → moat/traction/team/strategic-moves/financials; or
  one worker per entity for a 5-company screen) → runs workers concurrently
  (`asyncio.Semaphore(worker_concurrency)`, LLM steps via `asyncio.to_thread`) → detects blocking
  ambiguities → **mid-research clarification** (≤ `max_midresearch_questions`, via
  `interaction.ask_text`, answer fed into a targeted re-run) → aggregates + dedups findings/evidence
  into a `ResearchReport` with telemetry. Replaces Phase-3's single `_research` step.

### 7. Output critic + revision — `core/critic.py` (new)
- `critique(client, intent, analysis, playbooks, min_score) -> Critique`: rubric from the playbooks
  **incl. deep-research source validation** (claims sourced? ≥2 sources for financials? recent?
  assumptions/gaps flagged? Neura-Lens per point? bottom-line-first? correct language? framework
  fits?). `use_thinking=True`. **Fail-open** (bad parse/LLM error → passed, "critic unavailable").
- `revise(client, intent, analysis, critique, synthesis_input, playbooks) -> AnalysisOutput`: reuses
  `synthesizer.build_system_prompt` + a revision prompt (draft + concrete issues) and
  `synthesizer.parse_analysis` (refactor: extract the existing JSON→AnalysisOutput logic into a
  public `parse_analysis` so synthesize + revise share one path).

### 8. Pipeline integration + presentation
- `core/pipeline.py` `run_pipeline`: wire the full master loop above; effort drives every budget;
  progress via `interaction.notify` per worker/round/critique. `plan_subqueries` becomes the
  manager's decomposition (or feeds it). Telemetry into `PipelineResult`.
- `core/intake.py` `render_result`: show an **effort + telemetry** panel (effort · N workers ·
  rounds · sources evaluated · quality score · revisions · mid-research Qs) so the self-correction
  is visible. `ReplInteraction.ask_text`; `/effort` parsing in the REPL loop.
- `main.py`: `analyze --effort low|high|ultra`.

### 9. Governance (deliberate amendment, not scope-creep)
SPEC `§15.5 — Phase 3.5 (Advanced Agent Loop) [user-authorized amendment 2026-05-30]`; WORKFLOW §2
phase-table row; README status + knobs; full PROGRESS handoff.

---

## Task sequence (atomic; 1 commit each `phase-3.5: …`; PROGRESS updated per task)

1. **Scope + effort config.** SPEC §15.5 + WORKFLOW row + `EffortConfig`/`EffortLevelConfig`
   (config.py + config.yaml) + test_config + PROGRESS 3.5 plan.
2. **Models.** `EffortLevel` + `Intent.effort`; `Confidence`/`Finding`/`WorkerFindings`/
   `CoverageReport`/`ResearchReport` (research.py); `Critique`/`CriterionResult` + `PipelineResult`
   extension (synthesis.py); refactor `synthesizer.parse_analysis`. Update touched tests.
3. **Deep-research playbook.** Author `playbooks/deep_research_playbook.md` (user reviews) + extend
   `Playbooks` loader + tests.
4. **Effort detection + override.** `detect_effort` in intent_parser + `/effort`/`--effort` parsing
   + tests. Clarification budget from effort.
5. **Interaction `ask_text`** (protocol + ReplInteraction + AutoInteraction) + tests.
6. **ResearchWorker** (deep-research loop, source validation) + tests.
7. **ResearchManager** (decompose, parallel orchestration, aggregation, mid-research clarification
   hook) + tests.
8. **Critic + revision** (`core/critic.py`, effort-gated, source-validation rubric) + tests.
9. **Pipeline + presentation** (full loop wiring; render_result telemetry; `analyze --effort`; REPL
   `/effort`) + test_pipeline/test_intake updates.
10. **Quality gate + live** (ruff + mypy --strict + full pytest green; live runs below; document).
11. **Docs + ship** (README + full Phase-3.5 handoff in PROGRESS + `git push origin main`).

---

## Verification (Phase 3.5 success gate)

- **Ultra multi-agent (live):** `python main.py analyze --effort ultra "Vollständige Analyse von 1X
  Technologies — Funding, Tech, Strategie"` → progress shows **5 parallel research workers**,
  multiple rounds, **critiquing/revising**; result panel shows effort=ultra, workers, rounds,
  sources evaluated, quality score, revisions; output applies the rubric (every fact sourced + dated,
  ≥2 sources for financials, Neura-Lens per point, assumptions flagged).
- **Auto-effort + gating (live):** a quick news query auto-detects **low** → 1 worker, no critique,
  fast; a 5-company screen auto-detects **high/ultra** → multi-worker. `--effort` / `/effort`
  override verified to win over auto.
- **Mid-research clarification (live, REPL):** a deliberately ambiguous task → the agent pauses
  mid-research with a precise question, the answer measurably changes the follow-up search.
- **Config-scalable:** raise `effort.worker_concurrency` and `levels.ultra.research_workers` →
  more parallel workers, no code change (proves the future-hardware knob).
- **Tests/quality:** full `pytest` green (88 Phase-3 + new effort/worker/manager/critic/pipeline
  tests); `ruff` clean; `mypy --strict core llm models main.py` clean. Fail-open paths covered
  (worker/critic/coverage bad JSON → no block); hard-dep fail-fast preserved.
- **Deep-research methodology:** unit-assert workers' prompts carry the recency/validation/cross-
  reference rules; live spot-check that cited sources are recent + non-trivial (no Wikipedia-as-
  primary, no undated content farms for financial claims).

## Guardrails / documented decisions
- No new runtime dependencies (RULE 3). All LLM calls via `LocalLLMClient` with `num_ctx`. All paths
  `pathlib.Path`, all I/O utf-8.
- Effort is the single master dial; everything (workers, rounds, fetch depth, clarifications,
  mid-research questions, revisions, critique, thinking, concurrency) is **config-driven per level**
  → scales to the planned server/larger model with zero code change.
- Advisory layers fail-open; hard deps fail-fast. No file rendering (Phase 4), no ChromaDB (Phase 5).
- Phase 3.5 is a **user-authorized SPEC amendment**; `deep_research_playbook.md` is authored content
  presented for user review.

---
