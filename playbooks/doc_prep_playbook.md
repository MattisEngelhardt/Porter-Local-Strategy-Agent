# doc_prep_playbook.md — Preparing Internal Documents for the CEO Office

> The methodology for the agent's **internal document-preparation mode**: no web research — the
> material is already in hand. The job is to read a pile of internal documents *extremely
> carefully* and turn them into ONE flawless, management-ready briefing. The bar is a CEO-office
> intern who hands the top management something they can act on in two minutes, with zero errors
> and zero invented facts. Authored content — the user reviews it.

## The Cardinal Rule: Zero Hallucination
- Every fact, number, name, and date in the output MUST come from the provided documents. If it
  is not in the documents, it does not go in — full stop.
- Never "round up", smooth over, or infer a figure. Quote numbers exactly as written, with their
  unit and period (e.g. "€4.2M Q2 2026", not "about €4M").
- When documents **disagree** or a number is ambiguous, say so explicitly and cite both places —
  do not silently pick one.
- Mark anything the documents do not answer as an explicit **gap** ("Not covered in the provided
  material"). An honest gap is infinitely better than a confident guess.
- Attribute on demand: every key claim should be traceable to a source document (file name, and
  page/sheet/section when known).

## Read Like an Analyst, Not a Summarizer
Before writing anything, understand the whole pile:
1. **What is each document?** (board pack, financial model, memo, contract, report, email thread.)
2. **What decision or question does management actually have?** Everything serves that.
3. **What are the through-lines across documents** — the same topic appearing in several files,
   the figure that changed between two versions, the risk mentioned in passing but material.
4. **What is signal vs. noise?** Cut boilerplate, legal filler, and repetition. Keep what changes
   a decision.

## Extract What Management Needs (and only that)
- **The decision / bottom line** — what should the reader conclude or do.
- **The few numbers that matter** — the 3–7 figures a CEO would actually quote (revenue, runway,
  deal size, timeline, headcount, valuation), each with unit + period + source.
- **What changed / what's new** — deltas, decisions taken, open items.
- **Risks & dependencies** — top items, each with its source and (if stated) the mitigation.
- **Owners & next steps / dates** — who, what, by when, exactly as the documents state.
Leave out everything that does not help a busy executive decide or act.

## Clarifying Questions (ask after you have read, not before)
First read everything and identify the themes — *then* ask a few precise, high-value questions so
the briefing comes out exactly right. Good questions are specific to what you actually read:
- **Emphasis:** "The pack covers runway, the M&A pipeline, and hiring — which should lead the
  briefing for this audience?"
- **Audience & format:** "Is this a PDF brief to read, or a board deck to present?" "For the CEO,
  or the full board?"
- **Tone / depth:** "One-page executive summary, or a detailed walk-through?"
- **Ambiguity you spotted:** "Doc A says 9-month runway, Doc B implies 11 — which is current?"
Ask only what genuinely changes the output; never ask what the documents already make clear. If
you get no answer, state your assumption and proceed — never block delivery.

## The .md Blueprint First (the "Spickzettel")
Always produce a structured **Markdown blueprint before any PDF/PPTX**. It is both the working
sketch and the cheat-sheet the final file is built from. It forces the structure to be right
before a single slide or page is rendered. Structure:

```
# <Topic> — Management Briefing
Date · Source documents: <file1>, <file2>, …  · Language

## Bottom Line (2–3 sentences, decision-first)
## Key Figures (table: metric | value (unit, period) | source)
## <Theme 1 — "so what" heading>           ← one theme per section, most important first
## <Theme 2 …>
## Decisions / Risks / Open Items           (if the material has them)
## Next Steps (owner · action · date)       (only if stated in the documents)
## Gaps & Data Quality (what the documents do NOT answer)
## Source Documents (file → what it provided)
```

The blueprint is ordered top-down by importance: the reader gets 80% of the value from the
Bottom Line + Key Figures alone.

## How to Produce a Top-Notch PDF Brief
- **Bottom line first.** First sentence = the conclusion. Never build up to it.
- Max ~2 pages for a standard briefing; one theme per section with a "so what" heading, not a
  topic label ("Cash runway shortens to 9 months" — not "Financials").
- Tight bullets over paragraphs; numbers in a small table, right-aligned, with units.
- Cite the source document inline where a figure appears. No corporate filler.
- The Executive Summary must stand alone — reading only it gives the gist.

## How to Produce a Top-Notch PPTX Deck (when it's for a presentation/board)
- **One message per slide.** Every headline = the "so what", ≤ ~15 words.
- Slide flow follows Situation → Complication → Resolution (SCR) for a decision deck.
- A figure/table per slide beats a wall of text; max ~25 words of body per content slide.
- Title slide (topic · date · "prepared for management"), an exec-summary slide, one slide per
  theme, a decisions/risks slide, a clear recommendation/next-steps slide, a sources appendix.
- Neura styling (colors from config, logo bottom-right) is applied at render time (Phase 4).

## Choosing the Output
- **PDF brief** is the default for a read-and-decide briefing (consolidating reports/memos).
- **PPTX deck** when the task says it is for a meeting/board/presentation, or the audience is the
  board. When in doubt for management consumption, a PDF brief is the safe, fast choice.
- A business case is the exception (deck + Excel together — see the analysis/output playbooks).

## Language
Match the documents'/request's language (DE in → DE out, EN in → EN out). Keep established
finance/strategy terms in English even inside German text (Due Diligence, Runway, Term Sheet).
