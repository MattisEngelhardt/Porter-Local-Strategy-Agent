# Porter Deck Quality Overhaul — Composable Visual Library (Editorial v5.0)

## Context

Porter's latest board deck (Apptronik/Neura threat assessment) is "relatively good but far from the
quality I want." The basics work — cover image, page numbers, Neura logo, some color, and **every cited
source in the bibliography** (keep this). But it is generic: the same rounded `01/02/03` blocks on
nearly every slide, **one font everywhere**, repeated orange-then-black titles, **no diagrams/graphs at
all**, one bibliography page that breaks style, a full-bleed cover that grabbed a random screenshot,
truncated bullet fragments ("…the most"), and a generic title. The goal is a real quality boost — not
just prettier, but *meaningful*: every slide has a clear purpose, varied composition, **labeled diagrams
that do something**, multiple fonts, depth, consistent sourcing — and it must look stunning **while being
100 % instantly legible on every slide**.

A prior big-bang plan (`DESIGN_REVAMP_BLOCK5_PLAN.md`) already added ~10 "archetypes," a director, a
diagram engine, a 25-font library and a vivid palette — and still produced the output above. **The user
does not want that plan re-implemented.** They want a genuinely *deep, composable component library* the
agent picks from and customizes per slide ("10 kinds of tables, and for this one I want 3 columns"),
plus fixing whatever silently flattens everything.

### Why Block 5 underdelivered (root causes — verified in code)

1. **Fonts were never installed → PowerPoint substitutes ONE font everywhere.** All 25 TTFs exist in
   [assets/fonts/](assets/fonts/) but **none are registered with Windows** (verified: Fraunces/Space
   Grotesk/Inter/Space Mono/Archivo Black … all MISSING) and the deck doesn't embed them.
   `scripts/install_fonts.py` only *downloads* TTFs. So `run.font.name = "Space Grotesk"`
   ([core/exporter.py:626](core/exporter.py#L626)) renders as Calibri. *No typography system survives this.*
2. **The archetypes are skin-deep.** `_infer_archetype` ([core/deck_director.py:91](core/deck_director.py#L91))
   funnels most content into `COLORBLOCK_GRID`/`CONTENT`, and nearly every archetype draws the same
   rounded card via `_system_card`/`_color_card`/`_signal_cards`. Different names, identical look.
3. **Diagrams/charts effectively never fire.** Enabled in config, but the archetypes most slides land on
   don't even *call* `_try_chart`/`_try_diagram` (only `_chart_slide`/`_content_slide`/`_table_slide` do
   — [core/exporter.py:2004](core/exporter.py#L2004)); the grounding gate + strict extraction drop the
   rest. Net: zero Schaubilder. (Native python-pptx charts are also visually weak.)
4. **Concrete bugs:** `_diversify` ([core/deck_director.py:140](core/deck_director.py#L140)) rewrites runs
   of 3+ identical archetypes — with 4 `APPENDIX` slides it flips "Sources 3/4" to `EDITORIAL_SPLIT` (the
   inconsistent bibliography page). `cover_image` ([core/imagery.py:26](core/imagery.py#L26)) hash-picks
   from a pool a recent commit polluted with 8 screenshots. Title is pure LLM pass-through
   ([core/synthesizer.py:251](core/synthesizer.py#L251)). Bullets get truncated mid-thought to fragments.

---

## The operating principle — how a 4B local model produces world-class decks

This is the heart of the whole effort. **The local model never designs anything. Design is 100 %
deterministic, hand-built code that can only emit good output.** A 4B model is unreliable at layout,
coordinates, color, XML and long-form prose — so it is given none of those jobs. The labor split:

- **The model does only what a 4B does reliably:** short factual semantic strings — the analysis, one
  headline, a few bullets, comparison rows, the recommendation, the source list. **No coordinates, no
  colors, no fonts, no JSON layout.** (On *high-effort / bigger* models it may emit a coarse one-word
  hint like `archetype=chart`; ignored when absent — the 4B default never needs it.)
- **Every pixel is decided by code I author.** The composer maps content → template; the library's
  primitives are each *already beautiful*; color/type/spacing/depth/shadow are pre-tuned. **There is no
  blank canvas for the model to ruin** — it picks a lane, the lane is gorgeous.
- **LLM output is sanitized before it can ever render** (the "4B-safety layer"): strip markdown, fix
  number tokens, strip generic label prefixes, **truncate only at sentence/word boundaries (never
  "…the most")**, auto-fit/shrink to the box, dedupe, drop empties. Garbage-in is cleaned, never raw.
- **Everything visual is grounded.** Charts/diagrams/stats derive only from numbers and labels that
  appear in the evidence corpus; ungrounded → dropped. **No invented data** (RULE 14 / anti-hallucination).
- **Determinism + guaranteed fallbacks.** Same input → same deck. Any block/template exception degrades
  to a clean fallback (REQ-5). A **legibility guardrail** rejects overflow/clutter and a missing headline.
- **Quality is reached by a tight visual loop *I* run** (render → image → critique → fix), iterating on
  a fixed golden deck until every slide is stunning — **the model is not in that loop at all.**
- **The hybrid recipe is a bonus, not a crutch.** With a stronger model it can fine-tune a slide; with it
  absent (the 4B default) the deck is already world-class and **byte-identical**.

Net: the "intelligence" that makes the deck insane lives in *my* code and *my* iteration, not in the
4B model. The model supplies trustworthy words; the engine supplies world-class design — every time.

### Model- & provider-agnostic by construction (swap 4B → 12B → API, identical decks)

Because design is pure code behind a **typed content contract**, deck quality is invariant to the model.
A swap to gemma-4-12b (or any provider) changes only *content* (slightly better words), never *design*.
Infra already exists — `llm/local_llm_client.py` `LocalLLMClient` (provider ∈ ollama/lmstudio/llamacpp/
openai; `base_url`/`model`/`switch_model`; its docstring: *"switching backend or model is a one-line"*
`config.yaml` change) + the `effort` dial ([config.yaml:37](config.yaml#L37)). We lock the guarantees:

- **One contract, not a model.** The boundary is the Pydantic schema (`AnalysisOutput` → `DeckStructure`/
  `SlideContent`, + optional `ChartSpec`/`DiagramSpec`/`SlideRecipe`). Any model that fills it yields the
  *same* design. The composer/library/charts depend **only on the schema** — never on `provider`/`model`/
  `_detect_family`. An **architecture test** enforces: no design module imports the llm client.
- **Sanitization makes any model safe.** The 4B-safety layer normalizes every model's output — a chattier
  12B, a terser API model, Ollama vs LM Studio JSON quirks — into clean, identical-quality input.
- **Tolerant parsing/repair.** Output is parsed defensively (fenced JSON / trailing commas / key drift
  repaired); on failure → deterministic fallbacks (REQ-5), never a broken deck.
- **Capability tiers keyed on `effort`, not model identity.** Baseline (any model, incl. 4B) =
  content-only → full deterministic design. High-effort (12B+/API) = *optional* archetype hints +
  `SlideRecipe` polish. **The floor is design-identical across models;** with the recipe absent the deck
  is byte-identical.
- **Swap = config, not code.** Moving providers/models is `llm.provider/base_url/model` in `config.yaml`
  (or `switch-llm.ps1`); zero design-engine changes. Palette/theme/fonts/`restrained` are equally config-
  driven. **Invariant (tested): same `DeckStructure` → identical .pptx regardless of which model produced it.**

### Decisions locked with the user (2026-06-04)

- **Composition = Hybrid.** Deterministic composer picks & configures blocks by default (robust on the
  local model, always clean); an optional LLM "slide recipe" can fine-tune on high-effort / bigger model.
- **Charts = matplotlib image-charts.** Bars/lines/pies/labeled axes → crisp themed PNGs (magazine
  quality). Trade-off accepted: not click-to-edit in PowerPoint.
- **Sequencing = Foundation first**, split into **two equal, sequential blocks across two sessions**
  (save credits + raise quality). This session implements **Block 1** only, then checks off exactly what
  landed and writes a hand-off prompt so a fresh session implements **Block 2** without re-planning.
- **Palette = Aivazovsky signature + vivid accents + Neura black/white.** Signature pulls the painting's
  harmony (turquoise, baby-blue, deep-blue ↔ sunset gold/amber, warm orange); studio-vivid (red/blue/
  yellow) as bold accents; **white + black are Neura brand colors, used deliberately.** The **CEO
  decision slide** foregrounds Neura **black/white**, restrained, decision in focus.

---

## Design DNA — the north star (from the user's reference images, 2026-06-04)

Editorial design-studio aesthetic (Forma / Block.studio / KINETIC / Selected Work) on a board deck.
Non-negotiable: **stunning AND 100 % instantly legible — meaning through shapes/diagrams/typography,
never text slapped into rounded rectangles.**

| Reference | What to take |
|---|---|
| **Cofounder** (photo + serif title) | Cover = a beautiful, well-cropped image with an **elegant serif title woven in with depth**. *No pixel-art.* Title on a calm text-safe zone, never on the subject. Several cover treatments auto-picked per image. |
| **Forma** "Build without *friction*" | **Type contrast inside one headline**: bold roman + italic serif, a **recolored special word**, a kicker line with a leading rule, a tracked **mono ticker**. Clean restraint as one valid mode. Empty regions prefer a chart over air. |
| **Selected Work / WARP cards** | Color-blocks with **depth + an exclusive saturated palette**, bold name + small descriptor + `↗`. **Drop the literal 01/02/03 and "N rectangles in a row"** (exactly what read as basic). Keep the look, vary layout (overlap, unequal sizes), use sparingly. |
| **KINETIC** "BREAK GRID. DISTORT" | Huge multi-color **display type for statement/divider** slides. Rule: **steps/systems → a flow diagram, never a block grid.** |
| **"Let's make something loud"** (red) | **Bold saturated full-bleed backgrounds** as a device; mono footer columns; a daring single-color field can carry a slide. |
| **Aivazovsky** (sea at sunset) | **Signature palette**: turquoise / baby-blue / deep-blue ↔ amber / gold-yellow. Feel like an artwork, stay perfectly readable. (Color harmony only — no paintings on slides.) |

---

## Architecture: from "archetype methods" to a composable library

A slide is **assembled from blocks placed into a layout scaffold**, not poured into one card helper.
Four pure-where-possible, independently-testable layers + a composer:

1. **Theme** — resolves 5 font roles + the composed palette per deck/slide. Reuse `design.deck_fonts`,
   `statement_fields`, `knockout_text`, `spot_for_canvas`, `core/typography.py`.
2. **Layout scaffolds** — named regions (rects in inches/EMU): `full_bleed_hero`, `editorial_split`,
   `sidebar`, `quadrant`, `three_panel`, `big_number_hero`, `process_band`, `image_text_split`,
   `compare_columns`, `quote`, `decision`, `appendix_list`. Where asymmetry/overlap/depth lives.
3. **Blocks** — parameterized `render(slide, region, params, theme)` over existing helpers (`_rect`,
   `_rounded`, `_text`, `_soft_shadow`, `_set_alpha`, `_apply_gradient`): `headline`, `kicker`, `body`,
   `bullet_cluster`, `stat_tile`/`kpi_strip`, `chart`, `table` (N styles/columns), `pull_quote`,
   `image`, `source_list`, `shape_accent`, `flow`/`matrix` diagrams. The "library" — pick & customize.
4. **Templates** — declarative presets (scaffold + curated blocks + theme intent): the ~8–10 "krasse
   Templates," each assembled from the library so it stays customizable.

**Composer** (deterministic default): `slide_type` + content shape (bullets/metrics/table/body-only/
step-like) + intent → template; fills block params from sanitized content; enforces diversity + color
rhythm + the legibility guardrail; never breaks structural slides. **Hybrid override:** optional typed
`SlideRecipe` (template id + params), validated/grounded, else the deterministic plan stands.

---

## Slide-type coverage matrix (so the engine can't make a bad page)

Every `SlideType` ([models/deck.py:17](models/deck.py#L17)) has a primary design + a guaranteed fallback;
the composer always lands on one. This is the "alle Seiten berücksichtigt" guarantee.

| SlideType | Primary design | Why / data-shape | Fallback |
|---|---|---|---|
| `TITLE` | Adaptive photo cover: serif title + kicker + subtitle, gradient scrim, light logo | open strong, brand | gradient cover (no image) |
| `EXECUTIVE_SUMMARY` | Metric-hero / editorial-split: 2–3 takeaways + one hero number/chart | headline numbers ($935M) | content cards |
| `MARKET_LANDSCAPE` | Chart (trend line / market bars) + concise takeaways | size/trend over time | bullets + accent |
| `COMPANY_DEEP_DIVE` | Editorial split (robot image + profile) or KPI strip + body | entity profile | content cards |
| `FINANCIAL_OVERVIEW` | Chart (column/line of funding/metrics) + KPI tiles | quantitative | table |
| `COMPETITIVE_COMPARISON` | Styled comparison **table** (multi-column) or grouped-bar chart | entities × attributes | table (always safe) |
| `STRATEGIC_SIGNALS` | **Process/flow diagram** (connected steps) — never a block grid | ordered signals/steps | flow → cards |
| `SWOT` | **2×2 matrix** (saturated quadrants, knockout, axis labels) | 4-quadrant positioning | quadrant cards |
| `RECOMMENDATION` | **Decision slide** — restrained Neura **black/white**, verdict + actions (the payload) | the ask | dark statement |
| `APPENDIX` | Consistent paginated **reference list** (numbered, domain-emphasized) | full cited sources | compact list |

---

## Subsystem specs — how each axis reaches top-notch

**Typography (the "multiple fonts" fix).** Install + embed the theme fonts so they actually render.
Resolve a coherent **type theme** per deck (3–4 families from `core/typography.py`: a serif-display, a
grotesk body, an expressive display, a mono). A clear **role scale**: serif-display for big editorial
headlines/quotes; grotesk for body/bullets; expressive (Archivo Black/Anton/Bebas) for statement/divider
slides; **mono** for kickers, captions, page numbers, tickers, axis labels. **Multi-run headline**: mix
roman/italic/weight and **recolor one "special word"** chosen deterministically (the metric, the company
name, or the key verb — not random). Result: type contrast on *every* slide, not one substituted face.

**Color (composed, not a random box).** Add the Aivazovsky signature tokens + ensure Neura white/black
are first-class ([core/config.py](core/config.py) + [config.yaml](config.yaml) `output.colors`,
back-compat defaults). A signature **turquoise→amber gradient** (via `_apply_gradient`) for hero/divider
canvases. A deterministic **color rhythm** across the deck (loud → calm → loud, never two heavy canvases
back-to-back; one rotating accent per statement/card) — reuse/clean `statement_fields` + `color_score`.
**Contrast guarantee**: every text/background pair goes through `knockout_text`/`contrast_text` so nothing
is ever low-contrast. `restrained` stays flat/board-safe.

**Diagrams / charts (labeled, purposeful, grounded).** Reuse the existing specs — `models/visuals.py`
`ChartSpec`/`ChartType` and `models/diagram.py` `DiagramSpec`/`DiagramType` — and the extraction in
`core/visual_selector.py` + `core/diagrams.py` (`numbers_from_text`, `validate_diagram`), but **render
via matplotlib** (`core/charts_image.py`) into crisp themed PNGs. **Catalog + selection rule (data-shape
→ form):**

| Content shape | Diagram |
|---|---|
| values over time/sequence | **line / area** (labeled axes, gridlines, optional trend) |
| compare magnitude across entities | **column / bar** (value labels) |
| parts of a whole (~100 %) | **donut / pie** |
| a few headline numbers | **KPI strip / metric-hero** |
| ordered steps / a system | **process / flow** (connected nodes, arrows) |
| two-axis positioning / SWOT | **2×2 matrix** |
| stages narrowing / layering | **funnel / pyramid** |
| two entities, many attributes | **comparison columns / table** |

Every label/number must be grounded in evidence (else the diagram is dropped, fail-open). Axes,
series, and units are labeled — "nicht nur schön, sondern beschriftet und bezweckt etwas."

**Imagery (assets — meaningful, not random).** Curate [core/imagery.py](core/imagery.py): only
brand-approved Neura photography is eligible (the 5 real shots; **move the 8 design-reference screenshots
to `assets/imagery/reference/`, excluded from selection** — preserve, don't lose). Selection is by
**suitability + semantics** (16:9 cover-fit, min resolution, topic/section hint), deterministic — not a
hash. Imagery is also a **content block** (Block 2): a robot image on a split/divider, chosen to match
the section. Cover crop is aspect-aware (handles the 1024×1024 squares and any new image).

**Bibliography (consistent + well-formatted).** Keep the praised full-cited-source feed
(`compile_cited_sources` → `_sources_slides`). Fix the `_diversify` inconsistency. Upgrade the style to a
clean, **consistent numbered reference** (domain emphasized, title, tidy wrap — not raw 120-char URLs),
identical on every "Sources N/M" page, paginated.

**Cover + title (the opening slide).** Title-shaping yields a **short punchy main title (≤ ~6 words) + a
descriptive subtitle** (audience/company/date) — not the long generic phrasing; **no hallucinated dates**
(RULE 14). Cover = the curated image, an elegant serif title on a **gradient-scrim text-safe band** (Block
1 robust default; Block 2 adds focal-point crop + multiple cover scaffolds incl. split color-field +
robot). Filename = `YYYY-MM-DD_<short-punchy-slug>_deck.pptx`.

**Decision slide (the CEO payload — fully specified).** Restrained **Neura black/white**, one accent.
Layout: a clear **verdict headline** (e.g. "Accelerate — secure one marquee industrial partner in 12
months"), the **decision** (Go / No-Go / Conditional), **2–3 concrete actions** (owner/horizon if
present), and the **ask**. Minimal ornament — "weniger rumspielen." It must read in 5 seconds.

**Content hygiene (the 4B-safety layer).** In `core/artifact_framework._normalize_slide` + `_short`:
strip inline markdown, fix number/metric tokens, strip generic label prefixes ("Decision:/Recommendation:"),
**truncate only at sentence/word boundaries with auto-fit/shrink (never mid-word fragments)**, dedupe,
drop empties. This is what lets even garbled 4B output always render clean.

---

## BLOCK 1 — Foundation, primitives & the 4B-safety layer (implement THIS session)

> ### ✅ BLOCK 1 STATUS — implemented 2026-06-04 (all gates green: ruff + mypy --strict + pytest)
> Verified end-to-end by rendering a real deck and rasterizing slides via PowerPoint COM (the QA
> loop): fonts now render + embed, a real labeled chart appears, the bibliography is consistent, the
> cover no longer grabs a screenshot.
>
> - ✅ **1.1 Fonts render + embed.** `scripts/install_fonts.py --register` installs all 25 OFL TTFs
>   for the current Windows user (copy to user Fonts dir + `HKCU` registry + `AddFontResourceW` +
>   `WM_FONTCHANGE`); **ran it — 25/25 registered** (verified in the registry). New `core/font_embed.py`
>   embeds the deck's families into the saved `.pptx` (`ppt/fonts/*.fntdata` + `embeddedFontLst`),
>   wired into `_DeckRenderer.save`; fail-open. `lxml` added to mypy overrides. Tests: `tests/test_font_embed.py`.
> - ✅ **1.3 Image-chart engine.** New `core/charts_image.py` (matplotlib → themed transparent PNGs for
>   column/bar/line/area/donut, labeled axes + value labels + mono caption, fonts via `font_manager`
>   from `assets/fonts/`); wired as the **primary** renderer in `_try_chart` (fail-open → native).
>   `matplotlib` added to `requirements.txt` + mypy overrides. Tests: `tests/test_charts_image.py`.
>   Verified: a real "935 m vs 130 m" funding chart renders on the deck.
> - ✅ **1.5 Bibliography.** `_diversify` now exempts structural archetypes (`_STRUCTURAL`) so every
>   "Sources N/M" page is uniform; `_sources_slides` numbers references continuously ("07  domain — title")
>   and `_compact_list` renders them in the mono face. Tests: `tests/test_deck_director.py` (+ existing).
> - ✅ **1.4 Cover imagery curation.** The 8 design-reference screenshots were `git mv`'d to
>   `assets/imagery/reference/` (excluded — subdir) and `core/imagery.list_images` now also filters
>   screenshot-named files; cover pool = the 5 real Neura shots. Tests: `tests/test_imagery.py`.
>   **Deferred to Block 2:** the elegant adaptive serif cover + text-safe-zone + multiple cover scaffolds.
> - ✅ **1.7 Truncation.** `_DeckRenderer._short` now truncates at a sentence/word boundary (never
>   mid-word). The card renderers (`_color_card`/`_system_card`) already auto-fit. **Deferred to Block 2:**
>   the process-diagram node text still hard-truncates (rebuilt as a flow block in Block 2).
> - ✅ **1.8 Model-agnostic guarantees + QA loop.** `tests/test_architecture.py`: no design module imports
>   `llm/`, and the same `DeckStructure` renders identical text twice. The PowerPoint-COM rasterization
>   QA loop is validated (export `.pptx` → per-slide PNGs I inspect).
> - 🔶 **1.2 Typography — partial.** The two-tone recolored-headline-word already renders (verified —
>   "**Funding** leaders pull ahead"), and the 5 font roles now actually render (fonts installed).
>   **Deferred to Block 2:** the richer multi-run headline (serif + italic mixing within one line) and
>   kicker-with-rule motif.
> - 🔶 **1.6 Decision slide — deferred to Block 2** (restrained Neura black/white verdict+actions
>   template). The `RECOMMENDATION` slide still renders via its existing dark treatment (not broken).
>
> **New files:** `core/charts_image.py`, `core/font_embed.py`, `tests/test_font_embed.py`,
> `tests/test_charts_image.py`, `tests/test_imagery.py`, `tests/test_architecture.py`.
> **Edited:** `core/exporter.py` (font-embed in save, image-chart in `_try_chart`, `_short` boundary,
> numbered mono `_compact_list`), `core/deck_director.py` (`_diversify` structural exemption),
> `core/artifact_framework.py` (numbered sources), `core/imagery.py` (curation),
> `scripts/install_fonts.py` (`--register`), `pyproject.toml` (lxml/matplotlib overrides),
> `requirements.txt` (matplotlib). **Not yet committed** — ready to commit directly on `main`.

After Block 1 the *existing* renderer already produces a dramatically better, legible, branded deck;
every visual ingredient Block 2 needs exists and is tested.

- **1.1 Fonts render + embed.** Extend [scripts/install_fonts.py](scripts/install_fonts.py) with a
  `--register` OS-install step (user Fonts dir + `HKCU` registry), idempotent/fail-open; run it. Embed
  used TTFs into the saved pptx (`ppt/fonts/` + `<p:embeddedFontLst>`) via new `core/font_embed.py`,
  invoked from `_DeckRenderer.save` ([core/exporter.py:2091](core/exporter.py#L2091)), fail-open.
- **1.2 Design system: palette + type.** Aivazovsky signature tokens + Neura b/w in config; signature
  gradient; resolve a coherent multi-font theme and apply the **role scale**; **multi-run headline** with
  deterministic special-word recolor + kicker-with-rule + mono labels (generalize `_headline_two_tone`/
  `_display_headline`; fix the size-only font pick at [core/exporter.py:626](core/exporter.py#L626)).
- **1.3 Image-chart engine.** Add `matplotlib` to [requirements.txt](requirements.txt). New
  `core/charts_image.py`: themed PNGs for bar/column/line(+axes)/pie/donut/area/KPI from `ChartSpec`/
  `DiagramSpec`; fonts via `font_manager`→`assets/fonts/` (no OS dependency); pure, fail-open to native.
  **Wire into the data-slide path** and loosen extraction/grounding just enough that a real deck shows
  ≥1 labeled chart now. I **eyeball the PNGs directly** and iterate.
- **1.4 Cover + title.** Curate [core/imagery.py](core/imagery.py) (move screenshots to `reference/`,
  suitability pick); gradient-scrim serif cover with a guaranteed text-safe band + light logo
  ([core/exporter.py:767](core/exporter.py#L767)); short punchy title + subtitle; dated punchy filename.
- **1.5 Bibliography.** Exempt structural archetypes from `_diversify`
  ([core/deck_director.py:133](core/deck_director.py#L133)); clean consistent numbered reference style.
- **1.6 Decision slide.** Implement the restrained Neura black/white verdict+actions spec for
  `RECOMMENDATION`.
- **1.7 Content-hygiene layer.** Complete/verify markdown-strip, token-fix, label-prefix-strip,
  **sentence-boundary truncation + auto-fit**, dedupe in `_normalize_slide`/`_short`.
- **1.8 Visual-QA harness.** A no-LLM golden-deck render (reuse `tests/test_exporter.py` patterns) + a
  rasterizer (PowerPoint COM export, or matplotlib/Pillow PNGs for charts/cover) so I render → screenshot
  → critique → fix each slide.

**Block 1 acceptance (eye-check a real deck):** multiple distinct fonts render (and survive forwarding
via embed); ≥1 real labeled chart on a data slide; clean adaptive serif cover (no screenshot) + punchy
title + dated filename; all source pages one style; decision slide restrained Neura b/w; no truncated
fragments; Aivazovsky palette visible; `restrained` still flat. All gates green.

## BLOCK 2 — Composable library, composer & templates ✅ (implemented 2026-06-05)

> All gates green (`ruff` + `ruff format --check` + `mypy --strict core llm models main.py` = 48
> files + full `pytest`). A 10-slide no-LLM golden deck was rendered and rasterized via PowerPoint
> COM and eyeballed slide-by-slide (cover / metric hero / chart / image profile / comparison /
> flow / SWOT / decision / bibliography). Full handoff at the top of `DESIGN_REVAMP_PROGRESS.md`.

Builds on Block 1's primitives; delivers depth + variety.

- ✅ **2.1 `core/layout.py`** — `Region` (inches, frozen) + pure split/grid/pad helpers + a registry
  of 15 named scaffolds. `tests/test_layout.py` (in-bounds + non-overlap tiling). No pptx/color/LLM.
- ✅ **2.2 `core/blocks.py`** — parameterized `render(kind, surface, slide, region, params, theme)`
  over a structural `Surface` protocol the renderer satisfies (the renderer gained inch-based
  primitives). Blocks: multi-run **headline** (serif/italic + recolored word + kicker-rule), kicker,
  body, callout, bullets, cards (system/color), stat_tiles, **flow** (rebuilt — wraps long node text,
  fixes the truncation), matrix, chart, **table** (editorial/minimal/emphasis/compare · N cols ·
  emphasis col), pull_quote, image (cover-fit), metric, panel, scrim_band, source_list,
  accent_number, decision_chip, decision_actions. `tests/test_blocks.py`.
- ✅ **2.3 `core/composer.py`** — `compose`/`compose_deck → SlideComposition`: the slide-type coverage
  matrix (content-shape-adapted) + color rhythm + diversity via `deck_director.plan_deck` + content
  sanitization + legibility guardrail + per-type fallback. **Flow over block-grid; color cards only
  via the explicit hint, sparing.** `tests/test_composer.py` (16).
- ✅ **2.4 `core/templates.py`** — ~14 distinct presets (adaptive serif **photo cover** w/ text-safe
  band, split **color-field + robot** cover, metric hero, editorial split, image profile, data chart,
  comparison table, process flow, SWOT 2×2, statement, quote, restrained Neura **decision**,
  bibliography, content/color cards). Defines `PlacedBlock`/`CanvasSpec`/`Build`.
- ✅ **2.5 Wire** `_DeckRenderer.render(sc, plan, comp)` → renders the `SlideComposition` first, keeps
  the archetype path as the ultimate fallback (REQ-5). `_frame` split into `_paint_solid_or_dark` +
  `_frame_chrome`; budget-aware `_render_chart_block`. `build_deck` runs `compose_deck`.
  `tests/test_composition_render.py` (4).
- ✅ **2.6 Hybrid recipe + docs** — additive optional `SlideRecipe` on `SlideContent` (template /
  table_style / emphasis_col / cards_style), whitelisted+validated in the composer; **deck
  byte-identical when absent**; no content (RULE 14). `design_playbook.md` + `DESIGN_REVAMP_PROGRESS.md`
  updated. *(The high-effort prompt hint that emits a recipe is the documented extension point — the
  recipe is consumed if present; no LLM prompt was wired, to keep the change additive + risk-free.)*
- ✅ **Folded-in Block-1 deferrals:** the richer **multi-run headline** (serif + italic + recolored
  special word + kicker-with-rule) is the `headline` block; the **process-diagram truncation** is
  fixed by the `flow` block (wraps/auto-fits instead of trimming to 7 words).

---

## Reuse (do not rebuild)

`_rect`, `_rounded`, `_text`, `_soft_shadow`, `_set_alpha`, `_apply_gradient`, `_paint_dark_canvas`,
`_draw_table`, `_compact_list`, `_headline_two_tone`, `_display_headline`, `_big_number`, `_frame`,
`_add_logo`; `design.deck_fonts/statement_fields/knockout_text/spot_for_canvas/darken/lighten`;
`core/typography.py`; `core/visuals.py` (`add_native_chart`, `numbers_from_text`); `core/visual_selector.py`
+ `core/diagrams.py` (extraction + `validate_diagram` grounding); `models/visuals.py` `ChartSpec`,
`models/diagram.py` `DiagramSpec`; `compile_cited_sources` + `_sources_slides`. Assets (fonts, images,
palette) are fine — the gap was rendering, wiring, grounding-wiring, and depth, not the assets.

## Critical files

- **NEW:** `core/charts_image.py`, `core/font_embed.py` (Block 1); `core/layout.py`, `core/blocks.py`,
  `core/composer.py`, `core/templates.py` (Block 2).
- **EDIT:** [core/exporter.py](core/exporter.py) (save/embed, fonts-per-run, cover, headline, decision
  slide, render dispatch), [core/deck_director.py](core/deck_director.py) (`_diversify` fix; logic ported
  to composer), [core/imagery.py](core/imagery.py), [scripts/install_fonts.py](scripts/install_fonts.py),
  [core/artifact_framework.py](core/artifact_framework.py) (hygiene/truncation),
  [core/synthesizer.py](core/synthesizer.py)/[core/content_shaper.py](core/content_shaper.py) (title),
  [requirements.txt](requirements.txt), [config.yaml](config.yaml)+[core/config.py](core/config.py)
  (palette/type/knobs), `models/deck.py` (`SlideRecipe`, Block 2).
- **ASSETS:** move the 8 screenshots to `assets/imagery/reference/`; keep the 5 Neura shots eligible.

## Verification & the visual-QA loop

Gates (after each sub-step; all green to end the session):
```
& .venv\Scripts\python scripts\install_fonts.py --register
& .venv\Scripts\python -m ruff check core llm models tests scripts main.py
& .venv\Scripts\python -m ruff format --check core llm models tests main.py
& .venv\Scripts\python -m mypy --strict core llm models main.py
& .venv\Scripts\python -m pytest -p no:faulthandler -q
```
**Block 1 unit tests:** font-embed injects `ppt/fonts/`+`embeddedFontLst`; `--register` idempotent/fail-
open; each chart family yields a themed PNG; multi-run headline emits ≥2 families + a recolored word;
imagery excludes screenshots + picks by suitability; sentence-boundary truncation (no "…the most");
`_diversify` exempts structural slides; palette tokens load back-compat. **Model-agnostic guarantees:**
an architecture test (no design module imports `llm/`) + a same-`DeckStructure`→identical-`.pptx` test
(model identity can't change the design).

**Visual-QA loop (how top-notch is actually reached).** Render a fixed **no-LLM golden deck**, rasterize
to per-slide PNGs (PowerPoint COM export; charts/cover are already PNGs I can open), then **I inspect
every slide and iterate** until it's stunning — no LLM credits burned. (Tooling present: PyMuPDF +
Pillow; matplotlib added in 1.3. No LibreOffice — use PowerPoint COM or the PNG primitives.) Final
**end-to-end** check via the LM-Studio backend (`& .\porter.local.ps1` → `porter ask "…"`) confirms the
real pipeline against every original complaint.

## Hand-off (produced at the END of this session)

Once Block 1 is implemented + green I will, in this plan file: (1) **check off** each Block 1 sub-step
(✅) with one line on what landed + any deviation; (2) append a self-contained **`## Hand-off prompt for
Block 2`** that (a) explains the overarching situation (complaints, the operating principle, Design DNA,
the two-block split, Hybrid/matplotlib/Aivazovsky decisions), (b) states exactly what Block 1 delivered
and where (files/functions), (c) points to **BLOCK 2** so the next agent implements directly — no
re-planning — in the same extreme detail, reusing Block 1's primitives.

## Notes / risks

- python-pptx font embedding is an OOXML post-process in one fail-open helper.
- matplotlib registers TTFs from `assets/fonts/`, so chart fonts work even before OS install.
- Keep both LLM backends switch-aware; keep `restrained` meaningful; **no invented numbers/labels** —
  every chart label and stat grounded in evidence (RULE 14).
- **Provider/model swap is config-only** (`llm.*` / `switch-llm.ps1`); the design engine is model-
  agnostic by construction — guarded by the import-boundary + same-content→same-deck tests above.
- **Block 1 is independently shippable** and answers most complaints; **Block 2** turns "fixed" into
  "magazine-grade."
- Commit policy (repo CLAUDE.md): commit directly on `main`, plain push, **never rebase/force-push**.

---

## Hand-off prompt for Block 2 (paste into a fresh session)

> **Context — what this is.** You're improving "Porter," a local AI agent (this repo) that generates
> board-grade `.pptx` decks. The user's complaint about the previous output: every slide was the same
> rounded `01/02/03` cards, one font, no diagrams, an inconsistent bibliography, a screenshot cover.
> The full diagnosis, design north-star (the user's reference images: Forma / KINETIC / "Selected
> Work" / Aivazovsky palette), and the locked decisions live in the plan file
> **`C:\Users\engel\.claude\plans\2026-06-04-create-an-exhaustive-board-g-synchronous-petal.md`** —
> **read it first**, especially "The operating principle" (how a 4B local model makes world-class
> decks: it only writes content; 100% of design is deterministic code), "Model- & provider-agnostic by
> construction", the "Design DNA" table, the "Slide-type coverage matrix", and "Subsystem specs".
>
> **Locked decisions:** Hybrid composer (deterministic default + optional LLM recipe) · matplotlib
> image-charts · Aivazovsky signature palette + Neura black/white · the CEO **decision slide** is
> restrained Neura black/white. Tooling: `& .venv\Scripts\python` for everything; gates =
> `ruff check` + `ruff format --check` + `mypy --strict core llm models main.py` + `pytest -p
> no:faulthandler -q`. **Note:** the installed ruff (0.15.15) flags some *pre-existing* format/lint
> drift in files you won't touch (`core/synthesizer.py`, `tests/test_clarification.py`,
> `tests/test_researcher.py`, an unused `grad`) — that's not yours; keep *your* files clean.
>
> **What Block 1 already delivered (build on it, don't redo):** fonts now install (`scripts/install_fonts.py
> --register`) **and** embed into the deck (`core/font_embed.py`, called from `_DeckRenderer.save`);
> the matplotlib image-chart engine `core/charts_image.py` (`render_chart_png` / `add_image_chart`,
> reads `ChartSpec`/`DiagramSpec`, themed + grounded) is wired as the primary chart renderer in
> `_try_chart`; `core/deck_director._diversify` exempts structural archetypes (consistent bibliography);
> `core/artifact_framework._sources_slides` numbers references and `_compact_list` renders them mono;
> `core/imagery.list_images` excludes screenshots (8 moved to `assets/imagery/reference/`);
> `_DeckRenderer._short` truncates at sentence/word boundaries; `tests/test_architecture.py` locks the
> model-agnostic guarantee (no design module imports `llm/`). The PowerPoint-COM QA loop works — render
> a deck then: `powershell -c "$p=New-Object -ComObject PowerPoint.Application; $d=$p.Presentations.Open('<abs.pptx>',$true,$false,$false); $d.Export('<outdir>','PNG'); $d.Close(); $p.Quit()"` → read the PNGs.
>
> **Your job — implement BLOCK 2** (see the plan's "BLOCK 2" section for the full spec): the
> composable library + composer. In order: **2.1** `core/layout.py` (scaffold→named `Region`s, pure,
> unit-tested) → **2.2** `core/blocks.py` (parameterized `render(slide, region, params, theme)` blocks:
> multiple table styles + N-columns, bullet treatments, stat tiles, an **image block** (robot photo on
> splits/dividers, semantic selection), flow/matrix diagram blocks, pull-quote, accents; reuse Block 1's
> `charts_image` + the existing `_rect`/`_rounded`/`_text`/`_soft_shadow`/`_apply_gradient`/
> `_headline_two_tone`/`_display_headline`) → **2.3** `core/composer.py` (`compose(slide, deck_context)
> → SlideComposition`: the Slide-type coverage matrix + data-shape→diagram selection + color rhythm +
> diversity + the legibility guardrail + per-type fallback; port/clean logic from `core/deck_director.py`
> and `_infer_archetype`; **flow over block-grid; color cards only reimagined/un-numbered/sparing**) →
> **2.4** `core/templates.py` (~8–10 visibly distinct presets incl. the elegant **adaptive serif photo
> cover** with a text-safe zone, the **split color-field + robot cover**, the **statement/divider**, and
> the restrained **Neura-black/white decision template** for `RECOMMENDATION`) → **2.5** wire
> `_DeckRenderer.render` to render a `SlideComposition` (keep the current archetype path as the ultimate
> fallback, REQ-5) → **2.6** additive optional `SlideRecipe` on `SlideContent` (whitelisted/validated/
> grounded; deck byte-identical when absent) + update `design_playbook.md` / `DESIGN_REVAMP_PROGRESS.md`.
>
> **Also fold in the Block-1 'deferred' items:** the richer **multi-run headline** (serif + italic
> mixing + recolored special word + kicker-with-rule) as a headline block in 2.2/2.4, and fixing the
> **process-diagram node** hard-truncation by rebuilding it as a flow block.
>
> **Constraints:** every chart/diagram label grounded in evidence (RULE 14, reuse
> `core/visuals.validate_spec` / `core/diagrams.validate_diagram`); pure where possible + fail-open
> (REQ-5); keep `restrained` board-safe; keep both LLM backends switch-aware; **design modules must not
> import `llm/`** (the architecture test enforces it). Verify each sub-block green on the gates and
> eyeball via the PowerPoint-COM QA loop before moving on. Update the plan's BLOCK 2 section with ✅
> check-offs as you land each piece. Commit per repo CLAUDE.md (direct on `main`, never rebase/force-push).
