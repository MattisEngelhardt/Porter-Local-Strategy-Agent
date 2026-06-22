# finance_reporting_playbook.md — Building Management / Board Reporting from Internal Figures

> The methodology for Porter's **Builder dimension (Finance / Controlling)**: turn many internal
> documents full of numbers (Excel models, board packs, reports) into ONE management/board report.
> Local and data-safe — the figures never leave the machine. Extends `doc_prep_playbook.md` with
> finance-specific consolidation. Authored content — the controller reviews it.

## The Cardinal Rule: Every Number Comes From the Documents
- Every figure, name, and date MUST come from the provided documents. If it is not in them, it does
  not go in — full stop.
- Quote numbers **exactly** as written, with their **unit and period** (e.g. "€4.2M Q2 2026", not
  "about €4M"). Never round, smooth, or infer.
- Attach a **source** to every key figure: the file name, and the sheet/page/cell when known.
- When documents **disagree** on a number, say so and cite both — never silently pick one.
- Anything the documents do not answer is an explicit **gap**, not a guess.

## What Management Needs (and only that)
- **Bottom line** — the one-paragraph "so what" a CEO/board would act on.
- **Key figures** — the 5-10 numbers that matter (revenue, margin, runway, cash, headcount,
  budget vs. actual), each with unit + period + source.
- **Variance / what changed** — actual vs. plan vs. prior period, with the delta and the driver
  (only if the documents state it).
- **Risks & dependencies** — top items, each with its source.
- **Gaps & data quality** — what the figures do NOT cover, ambiguities, stale data.

## Consolidate Like a Controller
1. Identify each document (model, board pack, report) and the period it covers.
2. Find the through-lines: the same KPI across files, the figure that changed between versions.
3. Reconcile: if two sources give different values for one metric, flag it explicitly.
4. Cut boilerplate; keep what changes a management decision.

## The .md Blueprint First (the "Spickzettel")
Always produce a structured Markdown blueprint before any rendered PDF/PPTX/Excel:

```
# <Title> — Management Report (<period>)
## Bottom Line (decision-first)
## Key Figures (metric | value (unit, period) | source)
## <Theme — "so what" heading>            ← most important first
## Variance / What Changed
## Risks & Dependencies (item · source)
## Gaps & Data Quality (what the figures do NOT answer)
## Source Documents (file → what it provided)
```

## Output
- Default: a concise **management report** (Markdown blueprint) + an **Excel KPI table** (metric ·
  value · period · source). For a board presentation, render a PDF/PPTX from the blueprint (reuses
  Porter's existing `prepare` rendering — same Neura styling, zero hallucination).
- The controller reviews and signs off. Porter makes the consolidation fast and fully traceable.

## Language
Match the documents'/request's language (DE in → DE out, EN in → EN out). Keep established finance
terms as written (Runway, EBITDA, Budget vs. Actual, Forecast).
