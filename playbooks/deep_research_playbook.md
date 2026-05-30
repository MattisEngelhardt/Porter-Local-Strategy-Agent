# deep_research_playbook.md — How to Run Deep Research (Worker + Manager Methodology)

> This is the operating manual for a single **research worker** and the **research manager** in
> the multi-agent loop. It extends `research_playbook.md` (which still holds): that file says
> *which sources to trust*; this file says *how to actually research a sub-topic to depth*.
> Every worker obeys this. The standard is high: authoritative, recent, cross-referenced — never
> a shallow first-page skim.

## Mission
You are one specialist assigned ONE sub-topic. Your job is not to collect links — it is to
produce a small set of **verified facts** about your sub-topic, each with a source, a date, and a
confidence level, plus an honest list of what you could NOT verify. Depth over breadth: three
facts you have triangulated beat fifteen you skimmed.

## Source Authority Ladder (use the highest available; never stop at the bottom)
1. **Primary / official** — the entity's SEC/BaFin/companies-house filings, audited financials,
   official funding announcements, patents, the actual product spec. Highest trust for facts.
2. **Tier-1 independent press** — Bloomberg, Reuters, Financial Times, TechCrunch, WSJ. Trusted
   for events, deals, numbers (still cross-reference money).
3. **Tier-2 structured data** — Crunchbase / PitchBook (funding), LinkedIn (team/headcount/hiring),
   official company pages (products, leadership). Good for structure, weaker for "current".
4. **Tier-3 signals only** — blogs, X/Twitter, Substack, forums, vendor marketing. Never the sole
   source for a material fact. Use to find a lead, then climb the ladder to confirm it.

## Recency Windows (hard rules — the market moves monthly)
- **Fast-moving facts** (funding, valuation, headcount, partnerships, product status, leadership):
  prefer sources **≤ 6 months old**. If the best source is older, you MUST set `recency_flag`
  (e.g. "as of 2025-09, may have changed") and drop confidence by one level.
- **Undated pages** count as stale for any material/financial fact. Do not present an undated
  number as current.
- Always capture each source's **publication / as-of date**. A fact with no date is an Estimate.

## Cross-Referencing & the Confidence Model
Map every fact to exactly one confidence level — this is non-negotiable:
- **HIGH** — corroborated by **≥ 2 independent** authoritative sources (independent = not
  republishing the same press release), recent, dated.
- **MEDIUM** — one authoritative + recent source, or two weaker/older ones that agree.
- **ESTIMATE** — single weak source, undated, inferred, or sources disagree. Say so plainly.
- **Financially material claims** (valuation, revenue, deal size, funding total): require ≥ 2
  independent sources for HIGH. One source → MEDIUM at best, flagged. Conflicting numbers → present
  the range as an ESTIMATE, never silently pick one.

## Query Craft (and how to refine)
- Build queries as **entity + metric + timeframe**: `"1X Technologies" funding round 2026`,
  not `1X news`. Add the year/quarter for anything time-sensitive.
- Run a small spread of angles per sub-topic, not one query repeated.
- **Refine when results are thin or stale**: if the first pass returns only old or low-tier hits,
  reformulate — add the year, swap synonyms, name the specific metric, or target a filing/official
  page directly. Thin results are a signal to dig, not to give up.
- Company PR/blog is fine to *find* an event; then confirm the fact one rung up the ladder.

## Follow the Thread (depth)
When a source names a concrete lead — an investor, a customer, a date, a number, a hire — and it
matters to the sub-topic, **pull that thread**: one targeted follow-up query to verify or expand
it. This is the difference between "they raised a round" and "they raised €120M in Jan 2025 led by
[investor], confirmed by Reuters + the company filing."

## What to Discard
- SEO content farms, listicles, AI-spun summaries with no author/date → discard for facts.
- Press releases / company blogs presented as objective fact → demote to *intent signal* only.
- Wikipedia → **background only**, never a primary source for a current fact (per research_playbook).
- Anything you cannot date, for any material claim.

## Extracting Findings (the worker's output)
For each fact you keep, record a Finding with: the **claim** (one precise sentence), the
**source_url**, the **date** of that source, a **confidence** (HIGH/MEDIUM/ESTIMATE), and a
**recency_flag** if the source is older than the window. Then list the **gaps** — what the
sub-topic still needs that you could not verify. An honest gap is more useful than a fabricated
number.

## When to Run Another Round
Do another research round (within the effort budget) when: a material fact rests on a single
source, the best evidence is stale, the sub-topic's core question is still unanswered, or a
promising thread is unfollowed. Stop when the sub-topic's key facts are dated and corroborated, or
the budget is exhausted — and report the residual gaps.

## When to Come Back With a Mid-Research Question
Only interrupt the user for an ambiguity that **could not be seen upfront and materially changes
the search** — e.g. two real companies share the name, or the right scope (which geography /
segment / which "expansion") only became ambiguous once the evidence came in. Ask ONE precise
question, offer the concrete options you found, and feed the answer straight into a targeted
re-search. Never ask what you can reasonably assume; if you must assume, state the assumption.

## Manager Aggregation
The manager decomposes the task into distinct, non-overlapping sub-topics (driven by the
analysis_playbook framework for the task type), runs the workers, then aggregates: dedup facts,
keep the highest-confidence version of each, surface conflicts as ranges, and compile the union of
gaps. The aggregated evidence — not raw links — is what synthesis reasons over.
