# Porter Editorial — Design Playbook (v3.0)

> **For your review (RULE 14).** This documents the *style* system Porter applies to every PDF brief
> and PPTX deck. It introduces **no new content decisions** — facts, numbers, sources and structure
> come from the analysis and the artifact framework. This file is the user-authorized record of the
> visual language so you can approve, tune, or veto it. Everything here is config-driven
> (`config.yaml → output.style` / `output.colors`, RULE 4) and implemented in `core/design.py`,
> `core/visuals.py`, `core/visual_selector.py`, `core/exporter.py`, and `templates/briefs/`.

## North Star

*Design-driven & artistic — yet enterprise-grade for the Neura CEO-Office / Board.* Every element is
weighed against **both** character/impact **and** board credibility, readability, brand consistency.
When in doubt, *"would this convince in the CEO office?"* wins — without surrendering the artistic
ambition. The `intensity` toggle fine-doses the drama per occasion.

## The 9-point Design-DNA

Distilled from the reference set; encoded across the engine.

1. **Editorial base** — warm cream canvas, oversized type, generous whitespace, hairline rules.
2. **Three type roles** — serif display + grotesk + mono micro-labels (see Typography).
3. **Everything indexed/tagged** — `01·`, `[02]`, category tags, corner-arrows `↗`.
4. **Color blocks with meaning** — one accent per element, rounded corners.
5. **Painterly luminous depth** — a warm→cool gradient + one soft focal glow on cover/divider moments.
6. **HUD / telemetry motif** — mono metric chips built **only from real research counts** (never invented).
7. **Two-tone headline** — exactly one key token (a number, else a proper noun) in the spot color.
8. **Rounded geometry** — outline pills, corner-arrows, soft cards.
9. **Loud but disciplined** — impact via scale/contrast/whitespace, never clutter.

## Palette (meaning-encoded)

Resolved from `config.output.colors`; the chart palette cycles in this order.

| Token | Default | Meaning / use |
| --- | --- | --- |
| `paper` | `#F4F1EA` | warm cream canvas (content pages & slides) |
| `ink` | `#1A1813` | near-black editorial text |
| `canvas_dark` | `#15140F` | dramatic dark canvas — cover, dividers, the recommendation moment |
| `coral` | `#E4572E` | warm attention / two-tone highlight **on cream** |
| `artifact_gold` | `#C99700` | the focal glow + two-tone highlight **on dark** |
| `artifact_blue` | `#1F4E79` | series 1 / lead-in callouts |
| `artifact_teal` | `#157A6E` | series 2 / decision (recommendation) accent |
| `accent_cyan` | `#4DACC7` | series 3 / default frame accent |
| `artifact_risk` | `#B42318` | evidence-gap / risk notes only |

**Chart series order:** blue → teal → cyan → gold → coral → charcoal.
**Two-tone spot color:** coral on the cream canvas, gold on the dark canvas (legibility-driven).

## Typography (multi-font system)

Four OFL families, used strictly by role. Each CSS stack keeps system-font fallbacks so output is
never broken when the fonts are not installed (REQ-1/2; see `assets/fonts/README.md` +
`scripts/install_fonts.py`).

| Role | Family | Fallback | Where |
| --- | --- | --- | --- |
| Serif display | **Fraunces** | Georgia | PDF headlines (`h1`/`h2`), bottom-line standfirst |
| Grotesk display | **Space Grotesk** | Aptos / Segoe UI | deck headlines, brief stat numerals |
| Body | **Inter** | Aptos / Segoe UI | paragraphs, bullets, tables |
| Mono micro-labels | **Space Mono** | Consolas | meta line, ribbon, telemetry chips, tags, page numbers |

The PDF **embeds** the TTFs (subset) via `@font-face`; PowerPoint references the families **by name**
(it substitutes if not installed system-wide).

## Intensity toggle (`output.style.intensity`)

One knob doses the drama; structure is identical either way.

- **`editorial`** (default) — full expressive depth: the luminous warm→cool gradient + soft focal
  glow on the cover/divider, the cream cover band on the brief, the dark HUD ribbon.
- **`restrained`** — board-safe & flat: same layout, same content, but **no gradient, no glow, no
  cover band**; the dark cover stays a solid strong title moment, the ribbon goes to mist/blue.

Use `restrained` for the most conservative board settings; `editorial` for impact.

## What each artifact uses

**PDF brief** (`templates/briefs/` + `core/exporter.py`)
- Cream canvas, serif headlines, two-tone highlight, mono meta + telemetry chips.
- A slim luminous **cover band** (editorial only). The title stays on cream (coral holds).
- **Stat cards** (Focus/Proof/Sources/Status) + indexed **evidence anchors**, one accent per card.
- Embedded **hand-built inline SVG charts** (no raster, no new dependency) — the locked PDF tech.

**PPTX deck** (`core/exporter.py::_DeckRenderer`)
- Content slides on cream; the **cover and the RECOMMENDATION** slide become the dark canvas with the
  gradient + glow (editorial). Two-tone grotesk headlines.
- **System cards** (one accent spine each, big metric or `01` index, `↗`, `[01]` tag).
- **Native, editable** python-pptx charts (the user can retweak before a board meeting).
- Telemetry chips on the bottom rail; logo bottom-right.

## Data charts — and the anti-hallucination contract

Charts use **only numbers already present in the analysis/evidence**. Nothing is ever invented.

- **Selection (`core/visual_selector.py`)** is deterministic and adds **0 extra LLM calls** on the
  laptop default: a financial/market slide (or funding section) gets a **timeline (LINE)** built from
  the report's dated findings; other data slides/sections get a **column** chart from their own
  numeric lines.
- **Folded LLM visual** (server/ultra, via the effort dial) lets the deck shaper *also* propose a
  chart **in the same call** (no extra round-trip) — see `output.style.dedicated_visual_call`.
- **Grounding gate (`core/visuals.validate_spec`)** runs on **every** candidate — deterministic *or*
  LLM-proposed: ≥2 categories, not flat, and ≥50% of values must be findable in the evidence.
  Ungrounded specs are dropped; the renderer falls back (deck → cards/table, brief → text-only).
- Budgets: `max_charts_per_deck` (4), `max_charts_per_brief` (3). Master switch: `charts_enabled`.
- Chart families: column/bar (comparison), line/area (trend), donut (shares).

## Telemetry chips (DNA 6)

Mono outline pills built **only** from a real `ResearchReport`: `SOURCES n`, `WORKERS n`,
`CONFIDENCE X`, `AS OF YYYY-MM`. No report threaded in → **no chips** (never invented). Bilingual
(DE/EN).

## How to tune (no code change)

`config.yaml → output.style`: `intensity`, the four `*_font` names, `fonts_dir`, `charts_enabled`,
`max_charts_per_deck`/`_per_brief`, `dedicated_visual_call`.
`config.yaml → output.colors`: any palette token above.

## Guardrails (non-negotiable)

- **Anti-hallucination** — charts/telemetry surface only evidence-grounded numbers (`validate_spec`).
- **RULE 14** — style is user-authorized (this file); no new *content* decisions in the renderers.
- **REQ-1/2** — local, free, OFL fonts; missing fonts degrade to system fonts, never break.
- **REQ-5** — renderers fail open (a chart/depth quirk never loses the analysis); hard deps fail fast.
- **RULE 4** — every color/font/budget comes from `config.yaml`, nothing hardcoded.
