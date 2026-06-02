# PORTER — EDITORIAL DESIGN-SYSTEM + VISUAL-ENGINE — PROGRESS / HANDOFF LOG

> **Convention (read first):** This file is the rolling handoff for the multi-session "Peak PDF/PPTX"
> revamp. **Newest session sits at the TOP.** Each Opus session implements ONE block, then prepends a
> full handoff here (what was built · decisions · gate status · *detailed* next steps) so the next Opus
> can continue cold. When you finish your block, write your handoff at the top — the Opus after you
> depends on it, exactly as you depended on the one below.
>
> **Master plan:** `C:\Users\engel\.claude\plans\analysier-dieses-projekt-extrem-linked-rivest.md`
> (also summarized in §"North Star & locked decisions" below).
> **Project log:** `PROGRESS.md` (the original Phase 1–5 build). **Spec:** `strategy_agent_SPEC.md`.

---

## NORTH STAR & LOCKED DECISIONS (apply to every block)

**North Star:** *Design-driven & artistic — yet enterprise-grade for the Neura CEO-Office/Board.* Every
component is weighed against BOTH: character/depth/impact AND board credibility, readability, brand
consistency. When in doubt, "would this convince in the CEO office?" wins — without giving up the artistic
ambition (the `intensity` toggle fine-doses per occasion).

**Locked (from user Q&A):**
- **Render tech:** native python-pptx charts (editable) + hand-built **SVG** in PDF (WeasyPrint). **Zero new
  code dependencies.** (matplotlib deliberately avoided — not in SPEC §6.)
- **Canvas:** **cream-editorial base** + dark luminous gradient cover/dividers for depth. Consistent + pro.
- **Type:** **Serif in PDF, Grotesk in Deck** + Sans body + Mono micro-labels (multi-font).
- **Color:** curated editorial palette, meaning-encoded; feeds cards + charts.
- **Depth/cover:** expressive — locally-generated gradient/duotone + full-bleed dividers.
- **Chart set (this revamp):** core data charts — column/bar, line/timeline, donut.
- **Perf (RTX 4060 8GB, gemma ~28 tok/s):** config-switchable; **laptop default = 0 extra LLM calls**
  (fold visual selection into the existing `shape_deck` call + deterministic extraction). Dedicated
  visual-planner call only on server/ultra via the effort dial.
- **LLM backend:** an **elegant one-line switch** (Ollama ↔ LM Studio, `switch-llm.ps1`) keeps **both
  backends first-class** — now and for future hardware/RAM. **LM Studio is currently active**
  (`config.yaml` `provider: lmstudio`, model `Porter-LMStudio`); Ollama (`gemma4:e4b`) stays fully
  supported. **Do NOT rip out Ollama tests/logs** — keep them switch-aware. Renderers never call the LLM.

**9-point Design-DNA (from the 8 user reference screenshots — encode all of it over the blocks):**
1 Editorial base (cream, oversized type, whitespace, hairlines) · 2 three type roles (serif display +
grotesk + mono labels) · 3 everything indexed/tagged (`01·`, `[02]`, category tags, corner-arrows ↗) ·
4 color blocks with meaning (one accent per element, rounded corners) · 5 painterly luminous depth
(warm→cool gradient + one glow) · 6 HUD/telemetry motif (mono metric chips from REAL data) · 7 two-tone
headline (one key token in spot color) · 8 rounded geometry + outline pills + corner-arrows · 9 loud but
disciplined (impact via scale/contrast/whitespace, never clutter).

**4-block plan:** Block 1 = Foundation & Engine ✅ · Block 2 = PPTX Editorial renderer · Block 3 = PDF
Editorial renderer · Block 4 = Integration/Intelligence (guard, shaper, pipeline wiring, schema-guided
decoding, fonts installer, design_playbook.md, live verification).

**Non-negotiables (all blocks):** anti-hallucination (charts/telemetry use ONLY numbers present in the
analysis/evidence — `validate_spec` enforces grounding) · RULE 14 (no new *content* decisions; style is
user-authorized; `design_playbook.md` goes to user review) · REQ-1/2 (local, free, OFL fonts) · N-8
(pathlib + utf-8) · RULE 4 (colors/fonts from config) · REQ-5 (renderers fail-open; hard deps fail-fast).

---

## SESSION 1 — BLOCK 1: Foundation & Visual Engine ✅ COMPLETE
**By:** Opus (claude-opus-4-8) · **Date:** 2026-06-02 · **Status:** done, all gates green.

### What was built (pure, fully unit-tested, NOT yet wired into the live render path → zero risk)
- **`core/config.py` + `config.yaml`** — `ColorsConfig` gained `paper #F4F1EA`, `ink #1A1813`,
  `canvas_dark #15140F`, `coral #E4572E`. New **`StyleConfig`** on `OutputConfig.style`:
  `intensity` (`editorial`|`restrained`), `serif_font`/`grotesk_font`/`body_font`/`mono_font`,
  `fonts_dir`, `charts_enabled`, `max_charts_per_deck`(4), `max_charts_per_brief`(3),
  `dedicated_visual_call`(False). All have defaults → existing configs keep working.
- **`models/visuals.py`** (new) — `ChartType{COLUMN,BAR,LINE,AREA,DONUT}`, `ChartSeries(name,values)`,
  `ChartSpec(chart_type,categories,series,caption,unit,source,note)`. A `@model_validator` enforces
  **structural** renderability (≥1 category, ≥1 series, every series length == #categories, finite values)
  → any constructed `ChartSpec` is renderable; **semantic** gating lives in `validate_spec`.
- **`models/deck.py` / `models/synthesis.py`** — additive `visual: ChartSpec | None = None` on
  `SlideContent` and `Section` (default None → back-compat). This is how charts attach to a slide/section.
- **`core/design.py`** (new) — the deterministic "art-director skill". Pure, medium-agnostic tokens:
  - palette/color: `chart_series_colors(colors)` (deep_blue→teal→cyan→gold→coral→charcoal),
    `hex_to_rgb`, `luminance`, `contrast_text(bg,colors)`.
  - fonts (CSS stacks for PDF, with system fallbacks): `serif_stack`/`grotesk_stack`/`body_stack`/
    `mono_stack(style)`; `deck_fonts(style) -> {"display","body","mono"}` (single names for PPTX).
    Fallback constants `SERIF_FALLBACK=Georgia`, `GROTESK_FALLBACK=Aptos`, `BODY_FALLBACK=Aptos`,
    `MONO_FALLBACK=Consolas`.
  - `split_for_highlight(text) -> (before, token, after)` — two-tone headline (number token, else proper
    noun, else `(text,"","")`).
  - `telemetry_chips(report|None, language) -> list[str]` — source-grounded HUD chips
    (`SOURCES n`, `WORKERS n`, `CONFIDENCE X`, `AS OF YYYY-MM`) from a `ResearchReport`; `None`→`[]`.
  - depth/SVG: `depth_gradient_stops(colors)` (warm→cool), `glow_color(colors)` (gold),
    `svg_escape`, `linear_gradient_svg(gid, stops, x1,y1,x2,y2)`. Plus `design_marker()`, `is_editorial(style)`.
- **`core/visuals.py`** (new) — the chart engine:
  - `validate_spec(spec|None, evidence_text="", *, min_points=2, ground_ratio=0.5) -> ChartSpec|None` —
    anti-hallucination gate: ≥2 categories, not all-equal, and (if evidence given) ≥50% of values must be
    findable in the evidence. Deterministic extractors pass by construction.
  - `timeline_from_findings(report|None, language) -> ChartSpec|None` — LINE from dated numeric findings;
    refuses mixed scales (won't mix `$55M` with `$1.2B`); prefers currency amounts (so "1X" in a name isn't
    read as the number).
  - `numbers_from_text(text) -> list[(label,value)]` + `chart_from_pairs(pairs, chart_type, ...)` ;
    `numbers_in_text(text) -> set[str]`.
  - `render_chart_svg(spec, colors, style, *, width=560, height=300, on_dark=False) -> str` — pure, returns a
    full themed `<svg>` (column/bar grouped, line/area with markers, donut with legend; value labels;
    caption). **This is what the PDF embeds.**
  - `add_native_chart(slide, spec, colors, *, left_in, top_in, width_in, height_in) -> bool` — native,
    **editable** python-pptx chart (COLUMN/BAR/LINE/AREA/DOUGHNUT), palette-colored, data labels on,
    title/gridlines off. **Fail-open: returns False on any error → caller must fall back.**
- **Tests:** `tests/test_design.py` (17) + `tests/test_visuals.py` (16) = **33 new**, all green.
- **Fix (honoring the elegant switch):** `tests/test_config.py` — the old live-config assertion hard-pinned
  `provider == "ollama"` and so broke whenever the user switched to LM Studio. It is now **switch-aware**:
  (a) `test_llm_schema_defaults_match_spec` keeps the **Ollama** schema defaults (LLMConfig() = ollama /
  gemma4:e4b per SPEC §8) — never removed; (b) `test_live_config_llm_matches_active_backend` validates the
  active backend's contract (Ollama specifics when on Ollama, LM Studio when on LM Studio) + invariants
  (num_ctx 32768, thinking). Both backends pass; **no Ollama test/log was removed or weakened.**

### Gate status (end of Block 1)
- **pytest: 274 passed, 1 skipped** (the live SearXNG test). 33 new, 0 failures.
- **mypy --strict core llm models main.py: clean (35 files).**
- **ruff: clean on all Block-1 files.**
- python-pptx native charts + ChartSpec validation verified live in tests (real `Presentation`, `has_chart`).

### ⚠️ Pre-existing issues NOT introduced by Block 1 (decide before any commit)
- **`ruff format --check .` flags 4 files I did NOT author/touch:** `core/synthesizer.py`,
  `tests/test_synthesizer.py`, `tests/test_clarification.py` (all git-**modified** = the in-progress
  *bibliography* work, with E501 long lines), and `core/artifact_framework.py` (git-**clean** = committed
  format drift). I left them untouched to avoid clobbering the uncommitted bibliography work. **Recommend:**
  run `ruff format` on them when that work is committed (don't fold into this revamp's commits).
- **Working tree already had uncommitted changes at session start** (config.yaml, clarification.py,
  pipeline.py, synthesizer.py, models/synthesis.py, test_clarification/pipeline/synthesizer) — the
  bibliography fix (per auto-memory, "RESOLVED 2026-06-02"). My Block-1 edits to `config.yaml` and
  `models/synthesis.py` stack on top of those — keep that in mind when committing (group logically).
- **Known limitation:** `timeline_from_findings` / `numbers_from_text` are best-effort heuristics; they
  prefer currency amounts but prose without `$/€` and a number can still be noisy. The folded-LLM visual
  (Block 4) + `validate_spec` grounding are the real quality levers.

### Run/verify commands
```
& .venv\Scripts\python -m pytest tests\test_visuals.py tests\test_design.py -q
& .venv\Scripts\python -m mypy --strict core llm models main.py
& .venv\Scripts\python -m ruff check core\design.py core\visuals.py models\visuals.py
```

---

## NEXT: BLOCK 2 — PPTX Editorial Renderer (detailed brief for the next Opus)

**Goal:** Rework `core/exporter.py::_DeckRenderer` (and `build_deck`) so every slide renders in the Editorial
system and slides with a `.visual` show a native chart. Pure rendering only — do NOT change deck *structure*
(that's `artifact_framework.prepare_deck_for_render`, Block 4) and do NOT add LLM calls.

**Do this:**
1. **Read first:** `core/exporter.py` (esp. `_DeckRenderer`: `_frame`, `_headline`, `_text`, `_signal_cards`,
   `_body_callout`, `_title_slide`, `render`, per-type renderers), `core/design.py`, `core/visuals.py`,
   and `tests/test_exporter.py` (keep these green / update expectations intentionally).
2. **Canvas:** content slides → `colors.paper` (cream) instead of white; cover + a dark "divider" treatment
   for `TITLE`/`RECOMMENDATION` (and optional act-dividers) → `colors.canvas_dark` with a **luminous
   gradient + one glow** when `is_editorial(style)`. python-pptx gradient API is limited — prefer
   **layered semi-transparent rounded rects** (or test `shape.fill.gradient()`+`gradient_stops`); **fail-open
   to a solid `canvas_dark`** if the gradient misbehaves. Use `depth_gradient_stops` + `glow_color`.
3. **Fonts:** replace hardcoded `"Aptos"/"Aptos Display"/"Arial"` (note `_bullets` hardcodes Arial) with
   `deck_fonts(style)` → display=grotesk on headlines, body on body, mono on rails/labels/telemetry.
4. **Two-tone headline:** in `_headline`, use `design.split_for_highlight(headline)` and render the token in
   an accent color — needs a small multi-run text helper (current `_text` is single-run; add `_headline_two_tone`).
5. **System cards:** upgrade `_signal_cards` to the DNA-4 "system card" (big metric/number top-left via the
   existing metric-token idea + `visuals`/`design`, bold headline, micro body, category tag bottom-left,
   corner-arrow ↗, rounded, one accent per card).
6. **Telemetry footer (DNA 6):** render `design.telemetry_chips(research_report, language)` as mono chips on
   the bottom rail. **Add `research_report: ResearchReport | None = None` to `build_deck` (and thread it to
   the renderer)** now; the pipeline passes it in Block 4. Chips only show when data exists.
7. **Charts:** in the content/table/exec renderers, if `sc.visual` is not None → call
   `visuals.add_native_chart(slide, sc.visual, colors, left_in=…, top_in=…, width_in=…, height_in=…)` in the
   body area; **if it returns False, fall back** to the current cards/table. Respect `style.max_charts_per_deck`.
8. **Intensity:** `restrained` → flat fills, no gradient/glow, same structure (board-safe).
9. **Tests:** extend `tests/test_exporter.py` — a slide with `visual=` yields `has_chart`; cover uses
   canvas_dark; telemetry chips text present when a report is passed; two-tone splits a numeric headline;
   `restrained` skips gradient shapes; fonts set to grotesk/mono. Keep the existing structural assertions
   (artifact framework still inserts title/exec/evidence/recommendation/sources).
10. **Gate:** `ruff` + `mypy --strict` + full `pytest` green; do a live `porter analyze` and open the .pptx.

**Then:** prepend a SESSION 2 handoff above this section (newest on top) with what changed, any `build_deck`
signature changes (Block 4 depends on them), and detailed Block-3 (PDF) next steps.
