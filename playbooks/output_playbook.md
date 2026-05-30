# output_playbook.md — How to Produce Excellent Outputs

## Brief Rules (PDF)
- First sentence = the bottom line. Never build up to the conclusion.
- Executive Summary must stand alone — reading only it should give 80% of the value.
- Max 2 pages for a standard brief. 4 pages absolute maximum for a deep dive.
- Cite sources inline, not just at the end.
- No corporate filler phrases: "In today's rapidly evolving landscape..." → delete.

## Deck Rules (PPTX)
- Every headline = "so what", never a topic label.
  BAD: "Competitive Landscape" | GOOD: "Three well-funded competitors are closing the gap"
- Max 25 words on a content slide. If it doesn't fit: cut content, not font size.
- One message per slide. If two messages exist: make two slides.
- Data visualization > text tables. Always.
- Board deck structure: Situation → Complication → Resolution (SCR).
- Recommendation slide: it must be possible to make a decision based on this slide alone.

## Excel Rules
- ALL input assumptions in yellow cells (config color). Nothing hardcoded in formula cells.
- Every workbook has: title in A1, last-updated in A2, brief instructions in A3.
- Column headers always row 1, frozen. First column frozen.
- Formulas must recalculate correctly when the user changes any yellow input cell.
- Consistent color coding throughout: yellow=input, blue=formula, green=positive, red=risk.
- Test every formula before saving: change one yellow cell, verify everything downstream updates.
- No merged cells in data ranges (breaks Excel Table sorting/filtering).
- Tab names: descriptive, max 20 characters, no spaces (use underscores).

## Language Rules (DE/EN)
- Detect language from the user's input. Output in the same language.
- Technical terms that have no natural translation can stay in English (e.g., "Due Diligence",
  "Term Sheet", "Burn Rate") even in German text — this is standard in German strategy/finance.
- Board and management output: English is the safe default unless user specifies German.
- Internal working documents (Excel trackers, own briefs): German if user input is German.
