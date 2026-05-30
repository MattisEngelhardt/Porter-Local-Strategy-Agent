# STRATEGY AGENT — MASTER SPECIFICATION
> Status: LOCKED v0.4 — All open questions resolved. Ready for Opus execution.
> Last updated: 2026-05-30
> Hardware confirmed: ASUS VivoBook Pro 16x, RTX 4060 8GB VRAM, 32GB RAM, Windows 11

---

## 0. HOW TO USE THIS FILE (FOR OPUS INSTANCES)

This is the single source of truth for the Strategy Agent. Before writing a single line of code:
1. Read this file completely — every section.
2. Read `opus_WORKFLOW.md` completely.
3. Read `PROGRESS.md` if it exists.
4. Then and only then: create your phase plan and execute it.

**CRITICAL:** This SPEC was produced in a dedicated pre-development planning session. Every content decision is already made. You (Opus) make NO content decisions. You make only technical implementation decisions when genuine gaps exist, and document each one clearly. Never invent scope or change the role descriptions, templates, or output types.

---

## 1. PROJECT FRAMING

### 1.1 The Problem
Two internship roles at Neura Robotics (Pre-IPO humanoid robotics unicorn, Metzingen Germany, starting September 1, 2026). Both roles share the same core bottleneck: complex analysis and research tasks arrive with short turnaround times, requiring structured professional outputs — briefs, decks, Excel matrices. This work currently takes 2–4 hours manually. The agent collapses it to 20–30 minutes.

**CEO Office Intern**: High-tempo, generalist support for CEO and top management. Daily work spans analytical tasks, meeting and board preparation, cross-functional coordination, market research for ad-hoc questions, and Sonderthemen — special projects that arrive unexpectedly. No day is the same. Speed, structured thinking, and management-ready output quality are what count.

**Strategy Intern**: Analytical depth in Corporate Development. Work centers on strategic initiative analysis, M&A-adjacent projects, competitive and market analyses, business cases, and decision documents for management. Structured frameworks, financial logic, and Excel fluency are explicitly required.

### 1.2 The Solution
A local AI agent that:
- Takes a task via text or voice (bilingual: DE/EN, auto-detected)
- Understands intent through a brief clarification dialog (max 2 questions)
- Executes multi-step research: web search, document analysis, parallel queries
- Reasons locally with thinking mode enabled for complex tasks
- Injects persistent Neura context (brain.md) into every synthesis call
- Produces three classes of professional output: **PDF Brief**, **PowerPoint Deck**, **Excel Workbook**

### 1.3 The Interview Argument
*"I built a local research intelligence agent to automate market and competitive analysis before the internship. Locally because at a company evaluating M&A targets and strategic partnerships, no research input should run through external cloud servers — AI companies would learn which targets are being analyzed. The agent produces a brief, a deck, or an Excel matrix in 20–30 minutes instead of 3 hours manually."*

**Say:** Productivity problem → local solution → measurable time savings → data sovereignty.
**Do NOT say:** "I built a cool AI agent."

---

## 2. NON-NEGOTIABLE REQUIREMENTS

### REQ-1: Completely Local Execution
Every computation runs on the user's machine. No data leaves the machine to any AI company or paid cloud service.
- ❌ No OpenAI API, no Anthropic API, no Gemini API, no Tavily, no Brave Search
- ✅ Local LLM via any OpenAI-compatible local endpoint (Ollama / LM Studio / llama.cpp-server)
- ✅ SearXNG (self-hosted Docker, local)
- ✅ python-pptx (local library, zero network calls)
- ✅ openpyxl + pandas (local libraries, zero network calls)
- ✅ Document reading (pdfplumber, trafilatura) — local, no API

SearXNG nuance: Queries reach Google/Bing but are anonymized. AI companies never learn which targets are researched. Acceptable.

### REQ-2: Zero Cost
- ❌ No paid APIs, subscriptions, or usage-limited services
- ✅ Only open-source libraries, freely installable

### REQ-3: Model-Agnostic + Backend-Agnostic
- The Python client (`LocalLLMClient`) talks to any OpenAI-compatible HTTP endpoint
- All parameters (model name, base_url, num_ctx) come from `config.yaml` — never hardcoded
- Switching model or backend = one line in config.yaml, zero code changes

### REQ-4: Broad Capability
- ✅ Both CEO Office and Strategy Intern workflows fully covered
- ✅ Multi-modal input: text, voice, PDF, images
- ✅ Three output types: PDF Brief, PPTX Deck, Excel Workbook
- ✅ Bilingual: German and English, auto-detected

### REQ-5: Fail Fast, Fail Clearly
- If any dependency is unavailable (Ollama down, SearXNG not reachable, PDF corrupt): print exact fix instructions and exit immediately
- Never silently degrade or spend time debugging internally

---

## 3. TARGET CONTEXT: NEURA ROBOTICS

### 3.1 Company Context
- Pre-IPO humanoid robotics unicorn, Metzingen, Germany
- Founded: March 26, 2019 | CEO: David Reger
- AI-First company with own internal Task Force for AI tools and agent workflows
- High-tempo startup: dynamic, rapidly changing tasks, Rapid Context Switching is normal

### 3.2 CEO Office Intern — Real Task Profile

**From official Neura job description (verbatim):**
> "Du managst Deine täglichen Aufgaben mit einem besonderen Blick für Zahlen und analytische Details"
> "Zusätzlich koordinierst und planst Du kleine Projekte und unterstützt bei der Vorbereitung von Meetings sowie regelmäßigen Board-Meetings"
> "Deine enge Zusammenarbeit mit verschiedenen Fachbereichen und dem Management ermöglicht es Dir, kritische Projektaufgaben auszuführen und Sonderthemen zu betreuen"
> "Du übernimmst gerne die Verantwortung für die Durchführung spezifischer Marktforschung und bereitest Informationen für Slidedecks und Präsentationen professionell auf"

Required skills: MS Office (especially PowerPoint and Excel), German + English, analytical thinking, 6-month commitment.

**From insider intel (Alisa Schweizer, Neura CEO Office):**
- "Im CEO Office ist es besonders wichtig, schnell zwischen sehr unterschiedlichen Themen wechseln zu können und mit viel Spontanität umzugehen"
- "Kein Tag ist wie der andere, und oft geht es darum, parallel mehrere Dinge im Blick zu behalten"
- "Strukturiertes Denken und die Fähigkeit, schnell zu priorisieren, sind dabei wirklich zentral"
- "Weniger tiefe Spezialisierung, sondern ein gutes generelles Verständnis dafür, wie Dinge zusammenhängen"
- "Informationen Management gerecht aufbereiten, dass schnell gute Entscheidungen getroffen werden können"
- "Entrepreneur-Mindset: Dinge aktiv vorantreiben, Verantwortung übernehmen, Themen selbst identifizieren"

**From Ivan Blokhin (former Neura intern in CEO Office area):**
- Tasks included: strategic partnerships with Bluechips, Commercial Due Diligence, large Org-Transformation, Firefighting, short-term Special Projects for Top Management
- "Rapid Context Switching ist normal"
- "Neura ist eine AI-First Company" with own AI Task Force

**Key pattern**: The CEO Office role is about speed, variety, and management-ready output. The agent must handle ANY analytical question that comes up — not one specific domain. Excel and PowerPoint are explicitly required tools.

### 3.3 Strategy Intern — Real Task Profile

**From official Neura job description (verbatim):**
> "Du unterstützt unser Team im Bereich Corporate Development bei der Analyse, Planung und Umsetzung strategischer Initiativen"
> "Du wirkst bei der Vorbereitung und Begleitung von Projekten im Umfeld von M&A, Investments und strategischen Partnerschaften mit"
> "Du führst Markt-, Wettbewerbs- und Unternehmensanalysen durch und bereitest relevante Informationen sowie Daten strukturiert auf"
> "Du unterstützt bei der Erstellung von Präsentationen, Business Cases und Entscheidungsgrundlagen für das Management"

Required skills: Analytical skills, structured and independent working style, MS Excel + PowerPoint (financial models/business cases as explicit plus), interest in Strategie/Corporate Development/M&A/IB, Eigeninitiative, entrepreneurial thinking.

**Key pattern**: Corporate Development is broad — M&A is one component alongside strategic initiatives, investments, and partnerships. Every output is structured, analytically rigorous, and management-ready. Business Cases are a core deliverable. Excel fluency is explicitly required.

### 3.4 Concrete Use Cases — Balanced Across Both Roles

| # | Role | Task | Trigger (Example) | Primary Output |
|---|------|------|--------------------|----------------|
| 1 | CEO Office | Board meeting prep | "Bereite ein Update-Deck zu unserer Competitive Position Q2 2026 vor" | PPTX Deck |
| 2 | CEO Office | Ad-hoc intel for CEO | "CEO trifft morgen Investoren — was muss er zu Figure AI wissen?" | PDF Brief |
| 3 | CEO Office | Sonderthema analysis | "Sollten wir auf der Hannover Messe 2027 ausstellen? Kurze Analyse" | PDF Brief + Decision Matrix (Excel) |
| 4 | CEO Office | Meeting briefing | "Ich treffe [Person] von [Company] — bereite mich vor" | PDF Brief |
| 5 | CEO Office | Org/HR intelligence | "Was sagen die Job Postings von Boston Dynamics über ihre strategische Richtung?" | PDF Brief |
| 6 | CEO Office | Market research for management | "Überblick humanoid robotics Markt 2026 — für Board Präsentation" | PPTX Deck |
| 7 | CEO Office | Option comparison | "Vergleiche diese 3 Event-Sponsoring-Optionen für das CEO Team" | Decision Matrix (Excel) |
| 8 | CEO Office | Document synthesis | PDF + "Fasse diesen Report für das nächste Leadership Meeting zusammen" | PDF Brief |
| 9 | Strategy | Competitor deep-dive | "Vollständige Analyse von 1X Technologies — Funding, Tech, Strategie" | PDF Brief + optional PPTX |
| 10 | Strategy | Target screening | "Screen diese 5 europäischen Robotics Startups als potenzielle Targets" | Decision Matrix (Excel) + Brief |
| 11 | Strategy | Business case | "Business Case für Japan-Expansion: Marktgröße, Investment, ROI" | PPTX Deck + Excel Model |
| 12 | Strategy | Financial benchmark | "Funding und Bewertungsvergleich der Top-5 Humanoid Robotics Companies" | Benchmark Table (Excel) + Brief |
| 13 | Strategy | Partnership evaluation | "Score diese 4 potenziellen strategischen Partner für unsere Healthcare-Expansion" | Partnership Scoring Matrix (Excel) |
| 14 | Strategy | Market analysis | "Marktgröße industrieller Einsatz Humanoid Robots Europa 2026–2030" | PDF Brief + Excel Model |
| 15 | Strategy | Strategic initiative | "Make-vs-Buy Analyse für unsere Greifer-Technologie" | PDF Brief + Decision Matrix |
| 16 | Strategy | Investment memo | PDF + "Analysiere dieses Investment Memo und bewerte die Key Assumptions" | PDF Brief |
| 17 | Both | Industry news synthesis | "Wichtigste Developments in humanoid robotics der letzten 4 Wochen?" | PDF Brief |
| 18 | Both | Pipeline tracking | "Erstelle einen Tracker für unsere aktuelle M&A Pipeline" | Tracker Dashboard (Excel) |

**Important:** For tasks #3, 7, 10, 12, 13, 15, 18 the Excel output is the primary deliverable, not a supplement. For task #11, the agent produces a PPTX AND an Excel simultaneously — this is standard for Business Cases (deck = story, Excel = numbers).

### 3.5 Known Neura Context — Seed for brain.md

**Company Basics:**
- Founded: March 26, 2019 | CEO: David Reger | HQ: Metzingen, Germany
- Pre-IPO unicorn | AI-First company with internal AI Task Force

**Products (know these to avoid redundant explanation):**
- 4NE1 Gen 3.5 — Cognitive Humanoid Robot (flagship)
- 4NE1 Mini — Cognitive Humanoid Robot (compact variant)
- NEURA Quadruped — Four-legged Explorer Robot
- MiPA — Mobile Intelligent Personal Assistant (wheeled)

**Funding History:**
- July 2023: $55M (R&D expansion, Asia + US market entry)
- January 2025: €120M / ~$123M (strategic expansion round)

**Key Strategic Moves:**
- January 2026: Bosch strategic partnership — industrial humanoid robots. Automotive/industrial sector is COVERED — not a partnership white space.
- Nvidia Humanoid Robot Developer Program (Isaac GR00T platform)
- SRCI Working Group (PROFIBUS/PROFINET — robot-PLC standardization)

**Neura's Core Differentiator:**
"Cognitive" robots — autonomous adaptation to environment changes while working alongside humans. Always frame competitor comparisons against this: does the competitor have genuine cognitive capability or scripted behavior?

---

## 4. TECHNICAL ARCHITECTURE

### 4.1 Design Principles
1. **Local-first**: Every component runs on the user's machine
2. **Backend-agnostic**: Any OpenAI-compatible local endpoint
3. **Model-agnostic**: Config-driven, model name never hardcoded
4. **Three equal outputs**: PDF Brief, PPTX Deck, Excel Workbook — all first-class
5. **Stateful**: Agent builds intelligence over time (brain.md + ChromaDB)
6. **Iterative**: Agent converses before working (max 2 questions)
7. **Fail fast**: Dependency checks at startup, exact error messages, no silent degradation

### 4.2 System Overview

```
Input: Text (interactive terminal REPL) OR Voice (faster-whisper, local)
       OR Document (PDF / image / .xlsx — path dropped into terminal)
       File path auto-detection: valid path in input → routes to pdf_reader or excel_reader
  │
  ▼
[INTAKE LAYER]
  Terminal REPL (rich library — formatted, chat-like VS Code terminal experience)
  File path detection: bare paths in input recognized → routed to correct reader
  Multi-modal ingestion: text / voice transcript / PDF text / Excel data / image description
  Intent detection: task type, depth, output format (PDF / PPTX / Excel / combination)
  Language detection: DE or EN — auto-detected, all outputs in same language
  Clarification: max 2 targeted questions before acting
  │
  ▼
[BRAIN LAYER] (always-on context injection)
  Read brain.md → inject into every synthesis LLM call as system context
  brain.md: gitignored, local only, max 300 lines, only content that changes output
  Post-run: agent proposes new high-signal additions → user confirms in REPL
  │
  ▼
[RESEARCH LAYER]
  SearXNG queries (parallel async, self-hosted Docker, localhost:8888)
  Web content fetcher (trafilatura + requests, clean text extraction)
  Document reader: pdf_reader.py (pdfplumber → pytesseract OCR → vision LLM fallback)
  Excel reader: pandas (read user-provided .xlsx as research input)
  Job posting intelligence (strategic signal extraction via SearXNG)
  Result ranking, deduplication, quality filter
  diskcache layer: 24h SQLite cache for search results
  │
  ▼
[MEMORY LAYER] (read/write, Phase 5)
  ChromaDB vector store (local, persistent, file-based, Rust core)
  Embedding: nomic-embed-text via Ollama (CPU, no VRAM competition)
  Retrieval before each run: "Have we researched this entity before?"
  Write after each run: store findings, timestamp, entities, quality rating
  Delta analysis: "Since our last analysis of X [N weeks ago], here is what changed"
  │
  ▼
[REASONING / SYNTHESIS LAYER]
  LocalLLMClient → configured OpenAI-compatible local endpoint
  Default: gemma4:e4b via Ollama (localhost:11434)
  Playbook injection: research_playbook + analysis_playbook + output_playbook (Section 13)
  Thinking mode: enabled for complex tasks (<|think|> token for gemma4)
  Multi-step reasoning chain (Section 5.3)
  │
  ▼
[OUTPUT LAYER — THREE EQUAL OUTPUT TYPES]
  Output A — PDF Brief: Markdown → weasyprint → .pdf
             Naming: ./output/YYYY-MM-DD_topic_brief.pdf
  Output B — PPTX Deck: python-pptx → .pptx (Neura colors, logo bottom-right)
             Naming: ./output/YYYY-MM-DD_topic_deck.pptx
  Output C — Excel Workbook: openpyxl + pandas → .xlsx (4 templates, see Section 12)
             Naming: ./output/YYYY-MM-DD_topic_matrix.xlsx / _benchmark.xlsx / etc.
  Business Case: always produces Output B + Output C simultaneously (deck = story, Excel = model)
```

### 4.3 Model Layer — Backend-Agnostic Design

**User Hardware (confirmed):**
- Machine: ASUS VivoBook Pro 16x | GPU: RTX 4060 (8GB VRAM) | RAM: 32GB | OS: Windows 11

**Default model: gemma4:e4b** (Gemma4 26B MoE, 4B active parameters per token)
- Why: Vision capability (images as input), thinking mode, full commercial license, already on device
- Size: Q4_K_M = 9.6GB. With 32GB RAM, ~1.5–2GB CPU offload is smooth (~20–25 tok/s)
- Context: 128K max. Config default: 32768. With KV cache quantization (q8_0): fits comfortably.
- Thinking mode: prepend `<|think|>` to system prompt
- Q3_K_M alternative (~7.2GB): fits fully in 8GB VRAM, ~30 tok/s, marginally lower quality

**Alternative model (zero code changes to switch): qwen3:8b**
- Q4_K_M: 5.2GB, fits fully in 8GB VRAM, 40+ tok/s, thinking mode built-in, 119 languages
- Switch: one line in config.yaml + `ollama pull qwen3:8b`

**CRITICAL — Ollama 4K Context Default (applies to ALL models, not just gemma4):**
Ollama defaults ALL models to 4096 tokens regardless of model capacity. The `LocalLLMClient` MUST always pass `num_ctx` from config in every API call. Never rely on provider defaults.

**Backend selection (config-driven, zero code changes):**
| Backend | base_url | Best for |
|---------|----------|----------|
| Ollama (default) | http://localhost:11434 | Simplest, best Python integration |
| LM Studio | http://localhost:1234 | GUI VRAM tuning, model management |
| llama.cpp server | http://localhost:8080 | Maximum VRAM efficiency, zero UI overhead |

**LocalLLMClient contract (Phase 1 builds this, all phases use it):**
```python
class LocalLLMClient:
    """Backend-agnostic OpenAI-compatible LLM client. All params from config.yaml."""
    def __init__(self, config: LLMConfig): ...
    def generate(self, prompt: str, system: str = "",
                 use_thinking: bool = None,  # None = config default
                 num_ctx: int = None,         # None = config default — ALWAYS sent to API
                 stream: bool = False) -> str: ...
    def switch_model(self, model_name: str): ...
    @property
    def model_name(self) -> str: ...   # From config, never hardcoded
    @property
    def backend_url(self) -> str: ...  # From config, never hardcoded
```

### 4.4 Research Layer
- SearXNG async client (parallel queries via asyncio, reads all params from config)
- trafilatura + requests for HTML → clean text content fetching
- pdf_reader.py: pdfplumber (text PDFs) → pytesseract OCR (scanned) → gemma4 vision (image PDFs)
- Excel reader: pandas.read_excel() for user-provided .xlsx files as research input
- diskcache SQLite: 24h cache, search results not re-fetched within TTL
- Docker Desktop required: SearXNG runs via docker compose up -d

### 4.5 Memory Layer
**Layer 1 — brain.md (always-on):**
Gitignored markdown file, max 300 lines, injected into every synthesis call. Only content that changes agent output. Sections: Strategic Context / Audience Preferences / Output Style Rules / Current Focus / Active Context / Learnings. Seeded in Phase 5 from Section 3.5.

**Layer 2 — ChromaDB (session memory, Phase 5):**
Local persistent vector DB. Stores research findings per run. Retrieves relevant prior research before each new run. Enables delta analysis after multiple sessions on same entities.

### 4.6 Output Layer — Detailed

**Output A: PDF Brief**
- Pipeline: synthesizer → Jinja2 template → Markdown → weasyprint → .pdf
- Templates: 5 brief types (Section 10), bilingual (DE/EN param)
- When: Quick intel, competitor summaries, meeting prep, document synthesis, industry news

**Output B: PPTX Deck**
- Library: python-pptx (local, zero MCP, zero internet)
- 10 slide types (Section 11), Neura color scheme (from config.yaml), NEURA logo bottom-right every slide
- When: Board meetings, management presentations, market overviews, formal stakeholder outputs

**Output C: Excel Workbook (.xlsx)**
- Library: openpyxl (create/write/format) + pandas (read/process)
- 4 Excel templates (Section 12): Decision Matrix, Benchmark Table, Business Case Model, Tracker
- When: Comparing options, scoring targets/partners, financial models, pipeline tracking
- TWO MODES:
  - **Input mode**: Agent reads user-provided .xlsx (via pandas) as research input
  - **Output mode**: Agent creates professional .xlsx (via openpyxl) as deliverable
- **Business Case rule**: ALWAYS produces Output B (PPTX story) + Output C (Excel model) simultaneously

### 4.7 Voice Input Layer (Phase 5)
- voice_input.py: Tkinter overlay triggered by Ctrl+Space (pynput keyboard hook)
- pyaudio captures audio → faster-whisper transcribes locally (DE+EN auto-detect)
- Transcribed text injected into REPL input as if typed
- Completely free, zero API calls, zero cloud

---

## 5. AGENT BEHAVIOR — ITERATIVE DIALOG

### 5.1 Core Philosophy
Agent converses before working. Max 2 clarifying questions before acting. After delivery: offers one refinement. Does not unsolicited continue or suggest next steps.

### 5.2 Intent Detection and Clarification

**Parse intent from input:**
- Task type: competitor analysis / market research / target screening / business case / board prep / document synthesis / option comparison / pipeline tracking / ad-hoc
- Output format: PDF / PPTX / Excel / combination (auto-suggested based on task, user confirms)
- Audience: CEO/board / strategy team / personal working doc
- Depth: quick (10–15 min) / standard (25–35 min) / deep (45–60 min)
- Language: auto-detected from input

**Ask ONE targeted question (max 2 total):**
- DE: "Für wen ist das — Quick Brief für dich, oder Deck für das Management?"
- EN: "What format do you need — a brief to read, a deck to present, or a matrix to work with?"
- DE (Excel case): "Soll das ein scorierter Vergleich werden, oder eher ein Benchmark Table mit Rohdaten?"

**Confirm plan before executing:**
- DE: "Ich laufe 3 parallele Suchanfragen, lese Top-5 Quellen und erstelle [output type]. ~25 Minuten. Los?"

### 5.3 Multi-Step Reasoning Chain
1. **Decompose**: Break task into 3–5 concrete sub-questions
2. **Inject brain**: Load brain.md → understand Neura context + user preferences before searching
3. **Search**: Parallel SearXNG queries per sub-question
4. **Fetch**: Deep-read top 5 sources or analyze uploaded document/Excel
5. **Extract**: Structured key facts per source (with source tier from research_playbook)
6. **Memory**: Retrieve relevant prior ChromaDB findings — inject delta context if applicable
7. **Synthesize**: Apply analysis_playbook framework for task type → structured output
8. **Quality-check**: Does output answer the original question? Apply output_playbook rules.
9. **Render**: Write to correct output format(s) — one, two, or all three depending on task

### 5.4 Task → Output Mapping

| Task Type | Default Output(s) | Depth | Approx. Time |
|-----------|------------------|-------|--------------|
| Quick intel / news | PDF Brief | Low | 10–15 min |
| Meeting briefing | PDF Brief | Low-Medium | 15–20 min |
| Competitor analysis | PDF Brief + optional PPTX | Medium | 25–35 min |
| Document synthesis | PDF Brief | Medium | 20–30 min |
| Option comparison | Decision Matrix (Excel) | Medium | 25–35 min |
| Target / partner screening | Decision Matrix (Excel) + PDF Brief | Medium | 30–40 min |
| Financial benchmark | Benchmark Table (Excel) + PDF Brief | Medium | 30–40 min |
| Market analysis | PDF Brief + optional PPTX | High | 40–55 min |
| Board meeting prep | PPTX Deck | High | 45–60 min |
| Business case | PPTX Deck + Excel Model (simultaneous) | High | 50–70 min |
| Strategic initiative | PDF Brief + Decision Matrix (Excel) | High | 45–60 min |
| Pipeline tracking | Tracker Dashboard (Excel) | Medium | 20–30 min |
| Ad-hoc Sonderthema | User specifies | Variable | As fast as possible |

---

## 6. FULL TECHNICAL STACK

| Component | Tool | Version | Reason |
|-----------|------|---------|--------|
| LLM Inference | Ollama (default) | 0.22+ | Local, OpenAI-compatible API |
| LLM Alt Backend | LM Studio or llama.cpp-server | Latest | Backend switch = one config line |
| Default Model | gemma4:e4b | Q4_K_M, 9.6GB | Vision, thinking mode, full license |
| Alt Model | qwen3:8b | Q4_K_M, 5.2GB | Full GPU on 8GB VRAM, thinking mode |
| Embedding | nomic-embed-text | via Ollama | Local CPU, ChromaDB RAG |
| Web Search | SearXNG | Self-hosted Docker | Free, unlimited, private |
| Content Fetch | trafilatura + requests | Latest | HTML → clean text, local |
| Document Read | pdfplumber + pytesseract | Latest | PDF text + OCR, local |
| Excel Read | pandas | 2.x | Read user .xlsx files as input |
| Excel Write | openpyxl | 3.x | Create professional .xlsx outputs |
| Excel Format | xlsxwriter | Latest | Advanced chart/format fallback |
| Image Analysis | gemma4:e4b vision | — | Local, no extra model needed |
| Vector DB | ChromaDB | Latest (Rust core) | Local persistent memory |
| LLM Client | LocalLLMClient (custom) | — | Backend-agnostic, no LangChain |
| Data Validation | Pydantic v2 | 2.x | Type safety throughout |
| PPTX Output | python-pptx | Latest | Local, no MCP, no internet |
| PDF Output | weasyprint | Latest | Local Markdown/HTML → PDF |
| Template Engine | Jinja2 | Latest | Bilingual brief templates |
| Cache | diskcache + SQLite | Latest | Search result caching |
| Config | PyYAML | Latest | config.yaml pattern |
| CLI / REPL | typer + rich | Latest | Terminal REPL in VS Code |
| Async | asyncio + aiohttp | Built-in/Latest | Parallel research |
| Voice | faster-whisper + pyaudio | Latest | Local transcription, free |
| Voice UI | pynput + Tkinter | Built-in | Ctrl+Space overlay |

**NOT in the stack:**
- ❌ LangChain (heavy, hard to debug, contradicts model-agnostic design)
- ❌ Any paid search API (Tavily, Brave, Serper)
- ❌ Any external AI API (OpenAI, Anthropic, Gemini)
- ❌ Streamlit or any browser UI (terminal REPL is sufficient)
- ❌ Any MCP connector for Excel (openpyxl is called directly in Python)
- ❌ Any cloud database

---

## 7. PROJECT STRUCTURE

```
strategy-agent/
│
├── config.yaml                         # Single config source — all tunable params
├── .env                                # Secrets (empty — no external keys needed)
├── .gitignore                          # Includes: brain.md, output/, data/, .venv/, logs/
├── docker-compose.yml                  # SearXNG (localhost:8888)
├── requirements.txt                    # All pip dependencies
├── README.md                           # Setup guide (Docker Desktop, Ollama, models)
├── brain.md                            # Agent Brain — GITIGNORED, local only, max 300 lines
│
├── main.py                             # Entry point
│                                       # python main.py          → interactive REPL
│                                       # python main.py ask "…"  → single query
│                                       # Startup: checks Ollama + SearXNG → fail fast
│
├── core/
│   ├── __init__.py
│   ├── intake.py                       # REPL loop, file path detection, voice integration
│   ├── intent_parser.py                # LLM: task type, output format(s), language, depth
│   ├── clarification.py                # Targeted dialog, max 2 questions
│   ├── researcher.py                   # SearXNG async client + content fetcher + cache
│   ├── pdf_reader.py                   # PDF/image reading: pdfplumber → OCR → vision
│   ├── excel_reader.py                 # Read user-provided .xlsx files via pandas
│   ├── synthesizer.py                  # LLM synthesis + playbook injection + Jinja2
│   ├── excel_builder.py                # Create .xlsx outputs via openpyxl (4 templates)
│   ├── memory.py                       # brain.md inject/propose + ChromaDB read/write
│   └── exporter.py                     # python-pptx + weasyprint export orchestration
│
├── llm/
│   ├── __init__.py
│   └── local_llm_client.py             # Backend-agnostic OpenAI-compatible client
│
├── models/
│   ├── __init__.py
│   ├── task.py                         # TaskRequest, Intent, ClarificationRound, OutputFormat
│   ├── research.py                     # SearchQuery, SearchResult, FetchedContent, DocContent
│   ├── synthesis.py                    # SynthesisInput, AnalysisOutput
│   ├── deck.py                         # SlideContent, DeckStructure
│   └── workbook.py                     # ExcelTemplate, WorkbookContent, SheetDefinition
│
├── templates/
│   ├── briefs/
│   │   ├── competitor_brief.md.j2      # T-1
│   │   ├── decision_brief.md.j2        # T-2 (replaces manda_screen — broader scope)
│   │   ├── market_overview.md.j2       # T-3
│   │   ├── board_update.md.j2          # T-4
│   │   ├── document_synthesis.md.j2    # T-5
│   │   └── adhoc_brief.md.j2           # T-6
│   └── decks/
│       ├── competitor_deck.py          # python-pptx builders for each deck type
│       ├── market_deck.py
│       ├── board_deck.py
│       └── business_case_deck.py       # Business Case deck (paired with Excel model)
│
├── playbooks/                          # Quality rules injected into synthesis prompts
│   ├── research_playbook.md            # How to research well (source quality, recency)
│   ├── analysis_playbook.md            # Frameworks for each task type
│   └── output_playbook.md              # Excellence rules for Brief, Deck, Excel
│
├── assets/
│   └── neura_logo.png                  # NEURA logo (black on transparent, provided)
│
├── output/                             # All generated files land here
│   └── .gitkeep
│
├── data/
│   └── chroma_db/
│       └── .gitkeep
│
└── tests/
    ├── test_local_llm_client.py
    ├── test_researcher.py
    ├── test_pdf_reader.py
    ├── test_excel_reader.py
    ├── test_excel_builder.py           # All 4 Excel templates, formula validation
    ├── test_synthesizer.py
    ├── test_exporter.py
    └── test_memory.py
```

---

## 8. CONFIGURATION (config.yaml — Full Schema)

```yaml
llm:
  provider: "ollama"
  base_url: "http://localhost:11434"    # Change to switch backend
  model: "gemma4:e4b"
  num_ctx: 32768                        # CRITICAL: Always passed to API — never rely on default
  temperature: 0.2
  thinking_mode: true
  capabilities:
    vision: true
    context_window: 131072
    practical_context: 32768
  embedding_model: "nomic-embed-text"
  # KV cache optimization — set as SYSTEM environment variable, NOT read from this file:
  # Windows: setx OLLAMA_KV_CACHE_TYPE q8_0
  # Only needed if VRAM is tight with 32K context. Not required for Phase 1.

research:
  searxng_url: "http://localhost:8888"
  max_results_per_query: 8
  max_fetch_per_run: 5
  cache_ttl_hours: 24
  parallel_queries: 3

memory:
  enabled: true
  db_path: "./data/chroma_db"
  collection_name: "strategy_agent_memory"
  top_k_retrieval: 5
  brain_path: "./brain.md"             # Injected into every synthesis call
  max_brain_lines: 300

agent:
  default_language: "auto"             # "auto" | "de" | "en"
  max_clarification_rounds: 2
  show_research_plan: true

output:
  default_format: "brief"              # "brief" | "deck" | "excel" | agent-decides
  output_dir: "./output"
  include_logo: true
  logo_path: "./assets/neura_logo.png"
  colors:
    black: "#000000"
    white: "#FFFFFF"
    accent_cyan: "#4DACC7"
    dark_bg: "#111111"
    charcoal: "#2D2D2D"
    light_surface: "#F5F5F5"
    text_dark: "#111111"
    text_light: "#FFFFFF"
    excel_input_cell: "#FFF2CC"        # Yellow — user-editable input cells
    excel_formula_cell: "#DDEEFF"      # Blue — formula output cells
    excel_positive: "#E2EFDA"          # Green — positive/good values
    excel_negative: "#FFDDC1"          # Red-orange — negative/risk values
    excel_header: "#2D2D2D"            # Dark header rows

voice:
  enabled: false                       # Set true in Phase 5
  model: "base"
  language: "auto"
  hotkey: "ctrl+space"

logging:
  level: "INFO"
  log_file: "./logs/agent.log"
```

---

## 9. CRITICAL TECHNICAL NOTES FOR OPUS

### N-1: Ollama 4K Context Bug — ALL Models
Ollama defaults ALL models to 4096 tokens. Not gemma4-specific — universal Ollama behavior. The `LocalLLMClient` MUST pass `num_ctx` (from config) in every single API call. This is the most common silent failure mode for local agents.

### N-2: Thinking Mode
gemma4: prepend `<|think|>` to system prompt. qwen3: `/think` flag in prompt. The `LocalLLMClient` detects model family from config and handles automatically. Enable for complex analysis tasks, disable for fast/simple queries via `use_thinking` parameter.

### N-3: python-pptx Is Fully Local
`from pptx import Presentation` — zero internet, zero MCP. No connector needed. Creates .pptx files directly to disk.

### N-4: openpyxl Is Fully Local
`from openpyxl import Workbook` — zero internet, zero MCP. No connector needed. The Excel MCP servers that exist in the community are wrappers around openpyxl for external AI clients (Claude Desktop etc.). We call openpyxl directly in Python. Simpler, faster, more control.

### N-5: Excel — Two Distinct Modes
**Input mode** (excel_reader.py): User provides .xlsx → pandas.read_excel() → agent analyzes data
**Output mode** (excel_builder.py): Agent creates .xlsx → openpyxl builds cells/formulas/formatting
These are separate modules. Do not conflate them. Both are in Phase 2 (reader) and Phase 4 (builder).

### N-6: Business Case = Dual Output
When intent parser detects a business case task, the output pipeline must produce TWO files:
1. `.pptx` (deck) — the strategic narrative: problem, rationale, financial summary, recommendation
2. `.xlsx` (Excel model) — the financial engine: assumptions, projections, scenarios
These are generated in one agent run, both saved to ./output/, user gets both file paths at end.

### N-7: SearXNG Docker Prerequisite
Docker Desktop must be installed (not the VS Code extension — the actual Docker Desktop app from docker.com). Startup health check: GET http://localhost:8888/search?q=test&format=json. Failure → print exact instructions and exit.

### N-8: Windows Path Handling
All file paths use `pathlib.Path`. All file I/O specifies `encoding='utf-8'`. No os.path, no string concatenation with separators.

### N-9: brain.md Is Gitignored
brain.md lives only locally. It contains potentially confidential Neura-internal context. It MUST be in .gitignore from Phase 1. Phase 5 seeds the public-knowledge sections from Section 3.5 of this SPEC. The user fills in internal/private sections during the internship.

### N-10: Excel Formula Integrity
Every Excel workbook produced must have working formulas when opened in Microsoft Excel. No hardcoded intermediate values inside formula cells. All user-modifiable inputs go in yellow cells (config.output.colors.excel_input_cell). All formula outputs go in blue cells. This is the difference between a professional deliverable and a static table.

---

## 10. TEMPLATES — BRIEF (PDF OUTPUT)

All templates: Jinja2, bilingual (language param), saved via weasyprint.

### T-1: Competitor Brief
```
# [Company] — Competitive Intelligence Brief
Date: YYYY-MM-DD | Depth: [Standard/Deep] | Language: DE/EN

## Executive Summary (3–5 bullets — bottom line first)

## Company Overview
Founded, HQ, headcount, business model, core product

## Funding & Valuation
Total raised, last round (date + amount + investors), valuation if public, runway signals

## Technology & Product
Key capabilities, differentiation vs. Neura ("cognitive" framing)

## Team & Hiring Signal
Key executives, notable hires/departures, job posting strategic signals

## Strategic Moves (Last 6 Months)
Partnerships, customer wins, geographic expansion, public signals

## Competitive Assessment for Neura
Direct threat / opportunity / positioning implication

## Sources (URL | Date | Tier)
```

### T-2: Decision Brief (formerly M&A Screen — broadened scope)
```
# Decision Analysis: [Topic/Target/Option]
Date: YYYY-MM-DD | Type: [M&A Target / Partnership / Strategic Option] | Language: DE/EN

## Recommendation (top — not bottom)
Go / No-Go / Watch — 2 sentences why

## Quick Facts
Founding, HQ, headcount, stage, funding, core product

## Strategic Fit Assessment
Technology / Market Access / Integration Complexity / Team Quality

## Risk Flags
Key concerns identified from research

## Financial Intelligence
Public revenue/funding signals, investor quality, valuation estimate

## Data Gaps
What could not be verified from public sources

Note: For multiple targets, use Decision Matrix (Excel Template E-1) as primary output.
```

### T-3: Market Overview Brief
```
# [Market/Sector] — Market Intelligence Brief
Date: YYYY-MM-DD | Language: DE/EN

## Market at a Glance
Size, growth rate, key drivers, maturity stage

## Competitive Landscape
Key players — covered in Benchmark Table (Excel E-2) if requested

## Top Trends (3–5)
For each: What is it? Why does it matter for Neura specifically?

## Funding Activity (Last 12 Months)
Notable rounds, investors, directional signals

## Neura's Position
Where does Neura sit in this landscape? Strategic implications.
```

### T-4: Board / Management Brief
```
# [Topic] — Management Brief
Date: YYYY-MM-DD | Audience: Board/C-Suite | Language: EN (default for board)

## Situation (1 paragraph — what's happening)

## Key Developments (max 5 bullets — most impactful only)

## Implications for Neura
Strategic | Operational | Risk

## Recommended Actions (if analysis justifies)

## Sources & Methodology (Appendix)
```

### T-5: Document Synthesis Brief
```
# Document Analysis: [Document Title / Topic]
Date: YYYY-MM-DD | Input: [document name] + [web research if applicable] | Language: DE/EN

## Bottom Line (2–3 sentences)

## Key Facts & Findings
Structured extraction from document + additional context from web research

## Critical Assumptions / Data Quality
What to trust, what to verify, what's missing

## Implications for Neura / Relevant Context
```

### T-6: Ad-Hoc / Sonderthema Brief
```
# Quick Intel: [Topic]
Date: YYYY-MM-DD | Type: Ad-Hoc | Language: DE/EN

## Bottom Line Up Front (2–3 sentences)

## Key Facts
Bullets — most important only, no fluff

## Context (1–2 paragraphs)

## Uncertainty & Gaps

## Sources
```

---

## 11. TEMPLATES — PPTX DECK OUTPUT

### 10 Slide Types (all implemented in Phase 4)
1. **Title**: Topic, date, analysis type, Neura logo
2. **Executive Summary**: 3–5 key bullets, visual hierarchy, "so what" framing
3. **Market/Landscape**: Competitor positioning map or matrix
4. **Company Deep-Dive**: Founded / HQ / Funding / Core Product / Key Metrics
5. **Financial Overview**: Funding timeline, valuation signals, investor quality
6. **Competitive Comparison**: Side-by-side table with key dimensions
7. **Strategic Signals**: Job postings analysis, partnerships, public statements
8. **SWOT / Assessment**: 2x2 grid
9. **Recommendation / Call to Action**: Clean decision slide, Go/No-Go/Watch
10. **Appendix / Sources**: Reference slides

### Neura Color Scheme (from config.yaml output.colors)
- Title slides: Background #111111 (dark_bg), headline white, element in #4DACC7 (accent_cyan)
- Content slides: Background #FFFFFF, text #111111, accents #4DACC7
- Font: Arial (universal python-pptx fallback), 24pt section headers, 14pt body
- Logo: neura_logo.png, bottom-right, every slide, ~2.5cm width
- No gradients. No decorative borders. Maximum white space. Clean minimal aesthetic.
- Rounded rectangles only (no sharp corners on callout boxes)

### Headline Rule (from output_playbook)
Every slide headline = "so what", never a topic label.
- ❌ "Competitive Landscape" → ✅ "Three well-funded competitors closing the gap — Neura must accelerate"
- ❌ "Q3 Revenue" → ✅ "Revenue grew 40% — but burn rate doubled"

---

## 12. TEMPLATES — EXCEL WORKBOOK OUTPUT

Excel is a first-class output type. The user has limited Excel experience — the agent must generate workbooks that are immediately professional and usable, with working formulas, proper formatting, and clear structure. Opus must implement all four templates with high attention to quality.

**Technical stack:** openpyxl (primary), xlsxwriter (charts fallback), pandas (data processing)
**Color coding** (from config.yaml output.colors):
- Yellow (#FFF2CC): User-editable input cells — the only cells the user should change
- Blue (#DDEEFF): Formula output cells — calculated, do not manually edit
- Green (#E2EFDA): Positive/favorable values
- Red-orange (#FFDDC1): Negative/risk values
- Dark (#2D2D2D): Header rows

**Universal rules across all templates:**
- Freeze first row (headers) and first column (entity names) always
- Excel Tables with auto-filter on all main data ranges
- Column widths set programmatically (not default 8.43)
- Every workbook: title in cell A1, last-updated date in A2, instructions in A3
- All formula cells: no hardcoded intermediate values — formulas must recalculate when user changes inputs

---

### Template E-1: Decision / Scoring Matrix

**Purpose:** Compare multiple entities (companies, options, partners) across criteria to support a decision. The most universal Excel output — used for M&A screening, partner evaluation, option comparison, vendor selection, Sonderthema analysis.

**When to generate:**
- "Screen these 5 companies as acquisition targets"
- "Compare these 3 strategic options"
- "Score these 4 potential partners"
- "Which of these 5 options should we recommend to the CEO?"

**Structure:**

Tab 1: `Summary Matrix`
```
Row 1: Headers — "Company/Option" | Criterion 1 | Criterion 2 | ... | Weighted Score | Rank
Row 2: Weights — [blank] | 25% | 20% | ... | (auto-sum to 100%) | [blank]
Rows 3+: Each entity — Name | Score 1-5 | Score 2 | ... | =SUMPRODUCT(scores,weights) | =RANK()
Bottom: Color coding via conditional formatting on Weighted Score column
```

Tab 2: `Criteria & Scoring Guide`
- Each criterion: name, definition, how to score 1 (worst) to 5 (best)
- Example anchor scores for each criterion (so user can calibrate)

Tab 3: `Research Notes`
- For each entity × criterion: the evidence/source behind the score
- Agent fills this from research during generation

**Formatting:**
- Conditional formatting on Weighted Score: <40% red, 40–60% yellow, >60% green
- Top-ranked entity row: bold + light green fill
- Weights row: yellow fill (user can change weights → all scores auto-recalculate)
- Auto-ranking: RANK() formula, updates automatically

**Key capability:** User can change weights in row 2 → all weighted scores and rankings update instantly. This is the difference between a static table and an analytical tool.

---

### Template E-2: Intelligence / Benchmark Table

**Purpose:** Structured comparison of multiple entities on factual metrics — no scoring, just organized intelligence. The standard output for market landscapes, financial benchmarks, and competitive snapshots.

**When to generate:**
- "Show me the financial benchmarks for top-5 humanoid robotics companies"
- "Create a competitive landscape table for the Board"
- "Compare the funding history of these 6 targets"

**Structure:**

Tab 1: `Benchmark Table`
- Column A: Entity/Company names (frozen)
- Columns B+: Key metrics appropriate to task type
- For financial benchmark: Founded | HQ | Total Funding | Last Round Date | Last Round Amount | Lead Investor | Valuation (if known) | Headcount | Core Product | Key Customer
- For competitive landscape: Core Tech | Stage | Funding | Key Differentiator | Geographic Focus | Key Partnerships | Strategic Signals
- Row formatting: alternating light/white fill for readability

Tab 2: `Sources`
- Entity | Metric | Value | Source URL | Date retrieved | Confidence (High/Medium/Estimate)
- Agent fills this from research

**Formatting:**
- Excel Table with auto-filter (user can sort by any column)
- Numeric columns right-aligned, currency formatted
- "Estimate" values in italic + footnote marker
- Column widths: auto-fit to content with minimum sensible widths

---

### Template E-3: Business Case Financial Model

**Purpose:** Financial engine for strategic decisions. Assumptions tab → everything else is formula-driven. User changes one input → entire model updates. Always generated together with a PPTX deck (the deck tells the story; this file holds the numbers).

**When to generate:**
- "Build a business case for Japan expansion"
- "Financial analysis for this strategic partnership"
- "Model the ROI for this initiative"
- "Investment case for this M&A target"

**Structure (5 tabs, all formula-linked):**

Tab 1: `Executive Summary`
- Key output metrics in one view: Total Investment | Payback Period | 3-Year NPV | IRR | Recommendation
- All cells are formula references to other tabs — auto-updates when assumptions change
- Agent fills in a written "Bottom Line" cell (2 sentences)

Tab 2: `Assumptions` (ALL YELLOW — user edits here)
- Revenue section: Market size | Neura's target market share Year 1/2/3 | Price point per unit/contract
- Cost section: One-time setup investment | Year 1/2/3 OpEx | Headcount additions
- Timeline: Month when investment starts | Month when first revenue arrives
- Discount rate (for NPV calculation)
- All cells: yellow fill, labeled clearly, units in adjacent column

Tab 3: `Financial Projections`
- Monthly breakdown for Year 1, annual for Years 2–5
- Revenue | Costs | EBITDA | Cumulative Cash Flow
- All formula-based, all linked to Assumptions tab
- No hardcoded numbers in formula cells — ever
- Cumulative Cash Flow row shows breakeven month visually

Tab 4: `Scenarios`
- Three columns: Base Case | Optimistic (+20% revenue, -10% costs) | Pessimistic (-20% revenue, +15% costs)
- Key outputs per scenario: NPV | IRR | Payback Period | Risk Rating
- Scenario multipliers in yellow cells (user can adjust)
- All values formula-linked back to Assumptions tab

Tab 5: `Sources & Audit Trail`
- Every key assumption: what it is, where the number came from, confidence level
- Allows any reader to trace every number back to a source
- Agent fills this from research during generation

**Color coding throughout:**
- Yellow = user inputs (Assumptions tab)
- Blue = formula outputs (all other tabs)
- Green = positive/favorable values
- Red-orange = negative values, risks

---

### Template E-4: Tracker / Status Dashboard

**Purpose:** Living overview of ongoing items — M&A pipeline, partnership pipeline, initiative status, project tracking. Generated once as a template, then maintained by user.

**When to generate:**
- "Create a tracker for our current M&A pipeline"
- "Build a status dashboard for the strategic initiatives we're tracking"
- "Project tracker for my CEO Office Sonderthemen"

**Structure:**

Tab 1: `Dashboard`
- Summary stats: Total items | Active | On Hold | Completed | High Priority count
- All formula-linked to Tracker tab
- "Last updated" cell in yellow (user fills)

Tab 2: `Tracker` (main working view)
| Entity/Item | Category | Status | Priority | Owner | Next Step | Next Step Date | Last Update | Notes |

- Status: dropdown (Active / On Hold / Completed / Dropped) via Excel Data Validation
- Priority: dropdown (High / Medium / Low) via Excel Data Validation
- Conditional formatting: Status → Active=green, On Hold=yellow, Dropped=grey; Priority → High=orange
- Rows auto-filter-ready
- Agent pre-populates with research findings if context is provided (e.g., "create M&A tracker for these 5 companies I just researched")

Tab 3: `Archive`
- Completed/dropped items moved here by user
- Same structure as Tracker tab

**Key design note:** This is the ONE Excel template that becomes a living document the user maintains. It should be clean enough that they actually use it. No complexity beyond what's needed.

---

## 13. AGENT PLAYBOOKS

Three markdown files in `./playbooks/`. Injected into synthesis system prompts for the relevant task type. These are what make the agent excellent rather than just functional. Opus writes these files in Phase 3.

### research_playbook.md — How to Research Well

```markdown
## Source Recency Rules
- Fast-moving markets (robotics, AI, startups): max 6 months. Older sources must be 
  explicitly flagged: "As of [date], which may have changed."
- Funding data: always cross-reference at least 2 sources. Never cite a funding amount
  from a single source without noting uncertainty.
- Product claims: company press releases and blogs → use for intent signals only,
  not as objective facts. They are marketing.

## Source Hierarchy (Tier 1 = highest trust)
- Tier 1: Bloomberg, TechCrunch, Reuters, Financial Times, official SEC/BaFin filings
- Tier 2: Crunchbase (funding), LinkedIn (team/hiring), official company pages (products)
- Tier 3: Industry blogs, Twitter/X, Substack, forums — signals only, never sole source

## Job Posting Intelligence
Job postings reveal strategic intent 3–6 months before public announcements.
- "Hiring 10 enterprise sales reps in Germany" = product-market fit in DACH is happening
- "Hiring VP of Manufacturing" = scaling physical production is the next priority
- "Hiring Chief Medical Officer" = healthcare vertical is being entered
Always check job boards (LinkedIn, Indeed) when assessing a company's strategic direction.

## Cross-Referencing Rule
If a claim is financially material (valuation, revenue, deal size): verify in ≥ 2 independent
sources before including it. If only one source found: include with explicit uncertainty flag.

## Wikipedia Rule
Wikipedia = baseline and background only. Never cite as primary source for current facts.
Use it to understand a company's history/products, then verify current state with Tier 1/2.
```

### analysis_playbook.md — How to Think Well

```markdown
## Framework Selection by Task Type

### Competitor Analysis
Structure: Technology Moat → Commercial Traction → Team Quality → Strategic Threat/Opportunity
- Technology Moat: What do they have that's hard to replicate? Patents? Data? Integration depth?
- Commercial Traction: Revenue signals, customer wins, pilot contracts, enterprise partnerships
- Team Quality: Founders' track record, key technical hires, board composition
- Strategic Threat: How specifically does this affect Neura? Be concrete, not generic.

### M&A Target / Investment Screening
Criteria always include: Technology Fit | Market Access | Integration Complexity | Valuation Signal | Team Quality
- Technology Fit: Is their tech complementary or redundant to Neura's?
- Market Access: Do they open a geography, vertical, or customer segment Neura can't reach alone?
- Integration Complexity: Cultural, technical, operational — estimate High/Medium/Low with rationale
- Valuation Signal: Based on comparable rounds, what's the likely range? Is it realistic for Neura?

### Partnership Evaluation
Criteria: Strategic Fit | Execution Risk | Exclusivity Risk | Decision Timeline
- Strategic Fit: Does this open a door Neura needs? Be specific about the door.
- Execution Risk: Can this partner actually deliver? Check their operational track record.
- Exclusivity Risk: Does partnering with them close off other options?

### Market Sizing
Always use BOTH approaches and show the range:
- Top-down: Total market size (from industry reports) × Neura's realistic share
- Bottom-up: Number of addressable customers × average contract value × win rate
If the two approaches diverge by more than 2x: explain why and present both.

### Business Case Recommendation
Structure (Situation → Complication → Resolution = SCR):
1. Situation: What is the current state? (facts, no judgment)
2. Complication: What has changed or what is the problem? (why now?)
3. Options Considered: What alternatives were evaluated? (min 3)
4. Recommendation: What should we do? (specific, actionable)
5. Financial Case: What does it cost and what do we get? (from Excel model)
6. Key Risks: Top 3, with mitigation for each
7. Next Steps: Concrete actions with owners and timeline

## The Neura Lens
Every competitive or market analysis must answer: "What does this mean for Neura specifically?"
Generic industry statements are not analysis. Example of generic: "The humanoid robotics market is growing rapidly."
Example of analysis: "Boston Dynamics' move into industrial automotive signals that Neura's Bosch partnership is strategically well-timed — but Neura needs to move faster on factory-floor integration features or this window closes."
```

### output_playbook.md — How to Produce Excellent Outputs

```markdown
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
```

---

## 14. RESOLVED QUESTIONS (All Closed)

| # | Question | Decision |
|---|----------|---------|
| Q1 | Neura brand colors? | #000000 black (official), #FFFFFF white, #4DACC7 accent cyan, #111111 dark bg |
| Q2 | Docker installed? | Docker Desktop needs installation from docker.com (VS Code extension ≠ Docker Desktop) |
| Q3 | Output language? | Auto-detect from input. DE and EN both fully supported. |
| Q4 | Voice input timeline? | Phase 5. Ctrl+Space → Tkinter overlay → faster-whisper → REPL input |
| Q5 | Key competitors? | Boston Dynamics, Figure AI, 1X Technologies, Agility Robotics, Apptronik |
| Q6 | PDF/document input? | Yes, core feature. pdf_reader.py in Phase 2. pdfplumber + OCR + vision. |
| Q7 | File naming? | ./output/YYYY-MM-DD_entityname_type.{pdf,pptx,xlsx} |
| Q8 | LLM provider? | Backend-agnostic LocalLLMClient. Ollama default (localhost:11434). One config line to switch. |
| Q9 | Default model? | gemma4:e4b. Q4_K_M or Q3_K_M. Confirmed by user. |
| Q10 | System RAM? | 32GB confirmed. CPU offload for gemma4:e4b is smooth. |
| Q11 | GPU? | RTX 4060, 8GB VRAM. Confirmed. |
| Q12 | Financial data? | Public web via SearXNG (Crunchbase snippets, TechCrunch, Bloomberg). No paid API. |
| Q13 | Neura Brain tool? | Single brain.md, gitignored, max 300 lines, one file for all context. |
| Q14 | Scope too basic? | No. Multi-modal + thinking + three output types + memory + PDF analysis = sophisticated. |
| Q15 | Obsidian/AnyType? | Not needed. brain.md is plain markdown, edited in VS Code directly. |
| Q16 | UI approach? | Terminal REPL with rich library in VS Code integrated terminal. No browser, no Streamlit. |
| Q17 | Excel integration? | openpyxl + pandas, fully local, no MCP server needed. Two modes: read input + create output. |
| Q18 | Excel as main output? | Yes. PPTX, Excel (.xlsx), PDF Brief are the three equal main output types. |
| Q19 | Business Case format? | Always dual output: PPTX (story) + Excel (financial model). Generated simultaneously. |
| Q20 | Excel templates needed? | 4: Decision Matrix, Benchmark Table, Business Case Model, Tracker Dashboard. |
| Q21 | M&A as primary focus? | No. M&A is one use case within Strategy. CEO Office is broader. Agent serves both equally. |

---

## 15. PHASE BREAKDOWN (FOR OPUS INSTANCES)

### Phase 1: Foundation
**Goal:** Running skeleton that calls the LLM and responds.
**Delivers:**
- Full project structure (Section 7), all directories and .gitkeep files
- config.yaml with complete schema including Excel colors, brain path, output formats
- All Pydantic v2 models including workbook.py (ExcelTemplate, WorkbookContent, SheetDefinition)
- LocalLLMClient: backend-agnostic, OpenAI-compatible, always passes num_ctx
- main.py: `python main.py ask "…"` (single query) + `python main.py` (interactive REPL with rich)
- Startup health checks: Ollama running? Model available? Fail fast with exact instructions.
- docker-compose.yml (SearXNG), requirements.txt (all deps including openpyxl, pandas, xlsxwriter)
- .gitignore: includes brain.md, output/, data/, .venv/, logs/
- README.md: setup guide (Docker Desktop, Ollama, model pull, venv)
- Tests: config loading, LocalLLMClient connectivity, backend URL switching

**Success criteria:** `python main.py ask "Was macht Neura Robotics?"` returns LLM response. Interactive REPL starts. Backend switchable via config only.

---

### Phase 2: Research Engine + Document Reading
**Goal:** Agent can search the web and read documents and Excel files.
**Delivers:**
- SearXNG async Python client (reads all params from config, parallel queries)
- Web content fetcher (trafilatura, clean text extraction)
- pdf_reader.py: pdfplumber → pytesseract OCR → gemma4 vision fallback
- excel_reader.py: pandas.read_excel() → structured content for synthesis
- Parallel research execution (asyncio, aiohttp)
- Result ranking and deduplication
- diskcache layer for 24h result caching
- File path auto-detection in REPL input
- Tests: SearXNG connection, parallel search, content fetch, PDF read (text + scanned), Excel read, cache

**Success criteria:**
- `python main.py research "Figure AI Funding 2026"` → structured ranked results
- `python main.py` → drop PDF path in REPL → agent reads and extracts key facts
- `python main.py` → drop .xlsx path in REPL → agent reads and understands content

---

### Phase 3: Agent Brain (Intent + Dialog + Reasoning)
**Goal:** Agent understands what you want and reasons with playbooks.
**Delivers:**
- intent_parser.py: task type, output format(s) (PDF/PPTX/Excel/combination), language, depth
- clarification.py: max 2 targeted questions, smart gap detection, bilingual
- memory.py (read only in this phase): brain.md injection into synthesis calls
- Research planning: decomposes task into parallel sub-queries
- Playbooks written and validated: research_playbook.md, analysis_playbook.md, output_playbook.md
- Playbook injection into synthesis prompts for correct task type
- Multi-step reasoning chain (Section 5.3) with thinking mode
- Task-to-output routing: single output vs dual output (Business Case) vs user choice
- Full pipeline: input → clarification → research → document analysis → reasoning → structured output

**Success criteria:**
- Agent correctly asks ≤2 questions then produces structured analysis for "Screen diese 5 Companies als M&A Targets"
- Agent correctly identifies Business Case task → routes to dual output (PPTX + Excel)
- Output in German when input is German; output in English when input is English

---

### Phase 4: Output Generation — All Three Types
**Goal:** Professional outputs in all three formats.
**Delivers:**
- Jinja2 template system: all 6 brief types (T-1 to T-6), bilingual
- Markdown → PDF (weasyprint), all templates rendering correctly
- python-pptx deck generator: all 10 slide types, Neura color scheme, NEURA logo bottom-right
- business_case_deck.py: complete Business Case deck structure (SCR framework)
- **excel_builder.py — all 4 templates:**
  - E-1: Decision/Scoring Matrix: weighted scoring, RANK() formulas, conditional formatting, Criteria tab, Research Notes tab
  - E-2: Benchmark Table: Excel Table with auto-filter, multiple metric columns, Sources tab
  - E-3: Business Case Model: 5-tab structure (Summary/Assumptions/Projections/Scenarios/Sources), all formulas linked to Assumptions, yellow input cells, Scenario comparison
  - E-4: Tracker Dashboard: 3-tab structure (Dashboard/Tracker/Archive), Data Validation dropdowns, conditional formatting on Status and Priority
- Business Case dual output: PPTX + Excel generated in single agent run, both saved, both paths shown to user
- Output quality validation: completeness check, formula integrity check for Excel
- Full pipeline test: query → research → synthesis → all three output types

**Success criteria:**
- Single competitor query → professional PDF brief
- Board prep query → Neura-styled .pptx with correct colors and logo bottom-right
- Screening query → Excel Decision Matrix with working weighted scores, changes in weights update rankings
- Business case query → PPTX narrative deck + Excel 5-tab model both generated in one run
- All Excel files: open cleanly in Microsoft Excel, formulas recalculate when inputs change

---

### Phase 5: Memory + Voice + Polish + Production-Ready
**Goal:** Complete, persistent, production-ready agent. Zero errors end-to-end.
**Delivers:**
- ChromaDB setup with nomic-embed-text embeddings (Ollama CPU)
- memory.py write: store research findings after each run
- memory.py read: retrieve relevant prior research before new runs
- Delta analysis: "Since our last analysis of [entity] [N weeks ago], here's what changed"
- brain.md brain.md seeded with Section 3.5 content + correct structure from brain.md template
- Brain update flow: agent proposes additions in REPL → user confirms [y/N]
- voice_input.py: Ctrl+Space hotkey (pynput) → Tkinter overlay → faster-whisper → REPL input
- Full end-to-end pipeline test: voice/text → clarification → research → PDF + PPTX + Excel → correct
- Both German and English inputs produce correct language outputs
- Error handling: every dependency failure produces exact fix instructions
- README finalized with complete usage examples and example output screenshots

**Success criteria:**
- Second run on same company → "Ich habe frühere Recherche von [date] — hier ist was sich geändert hat"
- Voice: Ctrl+Space → speech bubble → transcription → REPL input works on Windows
- Business case query (voice input, German) → German PPTX + Excel model in ./output/
- Zero errors end-to-end on all task types

---

### Phase 3.5: Advanced Agent Loop [user-authorized amendment 2026-05-30]

> **§15.5** — This is a deliberate, user-authorized amendment to the LOCKED SPEC (approved in
> `PHASE_3.5_PLAN.md`, v1.0). It deepens the Phase-3 agent loop between Phase 3 and Phase 4. It
> changes no content decisions (RULE 14): the role, Neura context, templates, output types, and
> playbook *content* are untouched. It is purely an architectural upgrade of *how* the agent
> researches and self-checks. Still out of scope here: file rendering (Phase 4), ChromaDB
> memory/learning-delta (Phase 5).

**Goal:** Turn Phase 3's linear loop (intent → ≤3 questions → one research pass → one synthesis)
into a non-linear, self-correcting, proactive multi-agent loop. The `deep_research_playbook.md`
authored in this phase is new content presented for user review.

**Delivers:**
- **Effort master dial (low / high / ultra)** — one auto-detected, overridable knob (`/effort` in
  the REPL, `--effort` on `analyze`) that absorbs the old depth axis and drives the *whole* loop's
  intensity (workers, rounds, fetch depth, clarifications, mid-research questions, revisions,
  critique, thinking, concurrency) **config-driven per level** (`config.yaml` `effort` block).
  Auto-detect defaults to **high** when unsure — never silently shallow.
- **Multi-agent deep research (orchestrator-workers, by default)** — a `ResearchManager`
  decomposes the task into N sub-topics and runs N parallel research-worker identities, each
  validating sources (recency/authority/cross-reference) and reporting structured `Finding`s;
  the manager aggregates a clean evidence report. Correctly concurrent (async, web I/O parallel,
  LLM steps via `asyncio.to_thread`); degree of concurrency is config-gated
  (`effort.worker_concurrency`) → scales to the planned server + larger model with zero code change.
- **`deep_research_playbook.md`** — authored methodology the workers obey (authoritative + recent +
  cross-referenced sources, depth over breadth, confidence + date on every fact).
- **Interleaved mid-research clarification** — a worker/manager that hits a blocking ambiguity comes
  back to the user mid-research with a precise question (bounded by effort) and feeds the answer
  into that area's search.
- **Output critic + revision loop (evaluator-optimizer)** — a separate agent scores the draft
  against a playbook rubric (incl. source-validation) and forces targeted revisions before delivery.
  Effort-gated.
- All advisory layers (worker/critic/coverage) are **fail-open** (never block delivery); hard deps
  (SearXNG all-fail, LLM unreachable) keep Phase-3 fail-fast with fix instructions.

**Success criteria:**
- `analyze --effort ultra "Vollständige Analyse von 1X Technologies …"` → 5 parallel workers,
  multiple rounds, critique + revision; result panel shows effort, workers, rounds, sources
  evaluated, quality score, revisions.
- Auto-effort: a quick news query → low (1 worker, no critique); a 5-company screen → high/ultra
  (multi-worker). `--effort` / `/effort` override wins over auto.
- Raising `effort.worker_concurrency` + `levels.ultra.research_workers` fans out more workers with
  no code change (the future-hardware knob).
- Full `pytest` green; `ruff` clean; `mypy --strict` clean; fail-open paths covered.

---

*End of strategy_agent_SPEC.md v0.4 — All content decisions resolved. Agent architecture complete.*
*Amended 2026-05-30: §15.5 Phase 3.5 (Advanced Agent Loop) — user-authorized.*
