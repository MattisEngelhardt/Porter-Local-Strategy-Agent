# PHASE 4 KICKOFF — Onboarding-Prompt für den nächsten Opus

> Diesen Prompt 1:1 an den nächsten Opus senden. Er ist die Übergabe für **Phase 4 (Output
> Generation)** plus die offenen Restpunkte aus Phase 3.5, die mit zu erledigen sind.

---

Du bist Opus und baust den **Strategy Agent** weiter — einen **100% lokalen** Research-/Strategie-
Agenten für zwei Neura-Robotics-Praktika (CEO Office + Strategy/Corporate Development). Phasen
**1, 2, 3 und 3.5 sind fertig, getestet (141 Tests grün, ruff + `mypy --strict` clean über 27
Dateien) und auf `main` gepusht.** Du übernimmst **PHASE 4 — OUTPUT GENERATION** und erledigst dabei
zusätzlich die unten genannten Restpunkte aus 3.5. Höchste Qualität — der User will produktionsreife,
management-taugliche Outputs, keine Prototypen.

## LIES ZUERST, IN DIESER REIHENFOLGE (keine Tokens mit Raten verbrennen)
1. `strategy_agent_SPEC.md` — **komplett**. Autoritativ. Besonders: §15 Phase 4 (dein Auftrag), §10
   (Brief-Templates T-1..T-6), §11 (10 PPTX-Slide-Typen + Neura-Farben + Logo), §12 (Excel E-1..E-4),
   §9 N-3/N-4/N-6/N-10 (python-pptx/openpyxl lokal, Business-Case-Dual-Output, Excel-Formel-Integrität),
   §15.5 (Phase-3.5-Amendment).
2. `opus_WORKFLOW.md` — **komplett**. Arbeitsprotokoll + die 14 RULES (Pflicht). Insb. RULE 3 (keine
   neuen Deps außerhalb SPEC §6), 5/8/10 (pathlib, utf-8, num_ctx), 11–13 (Tests vor Code, Commit +
   PROGRESS pro Task), 14 (keine Content-Entscheidungen — SPEC ist autoritativ).
3. `PROGRESS.md` — **komplett**, vor allem die Phase-3.5-Sektion samt **„What to do FIRST next
   session (Phase 4 starting point)"** und beide Addenda (Doc-Prep-Mode + Rendering).
4. `PHASE_3.5_PLAN.md` — Kontext zum Advanced Agent Loop, auf dem du aufbaust.
5. Code, den du erweiterst/konsumierst:
   - `core/exporter.py` (existiert bereits — Phase-3.5-Slice, s.u.), `core/synthesizer.py`
     (`AnalysisOutput`, `parse_analysis`), `core/pipeline.py` (`run_pipeline`, `PipelineResult`,
     `_run_document_prep`, `_render_outputs`), `core/intake.py` (`render_result`), `main.py`.
   - Verträge: `models/synthesis.py` (`AnalysisOutput`, `Section`, `SourceRef`, `Critique`,
     `PipelineResult` mit `routed_formats`/`output_files`/`artifact_path`/`mode`/`research_report`),
     `models/research.py` (`ResearchReport`, `WorkerFindings`, `Finding`, `Confidence`),
     `models/deck.py`, `models/workbook.py` (in Phase 1 angelegt — für Phase 4 ausbauen).
   - `playbooks/output_playbook.md` (Brief/Deck/Excel-Exzellenzregeln), `playbooks/analysis_playbook.md`
     (SCR fürs Business-Case-Deck), `config.yaml` (`output.colors` = Neura-Palette + Excel-Farbcodes,
     `output.logo_path`, `output.output_dir`).

## WO DU STEHST (Stand bei Phase-4-Start)
- **Phase 1–3**: LocalLLMClient (provider-aware, num_ctx immer gesetzt), Research-Engine (SearXNG +
  Fetch + Cache), pdf/excel-Reader, Intent/Clarification/Synthese, Reasoning-Chain. ✅
- **Phase 3.5**: Effort-Master-Dial (low/high/ultra), Multi-Agent Deep Research (Orchestrator-Workers
  + `deep_research_playbook`), Mid-Research-Rückfragen, Output-Kritiker + Revision-Loop. ✅ Live
  verifiziert (LOW + HIGH).
- **CEO-Office-Dokumenten-Modus** (Teil von 3.5): `WorkMode` + `route_mode`/`classify_work_mode`
  (Research vs. interne Aufbereitung; bei Unklarheit fragt der Agent den User), `core/doc_synthesis.py`
  (tiefes Lesen, Zero-Hallucination, gezielte Themen-Rückfragen, `.md`-Blueprint/Spickzettel), und
  **echtes PPTX-Rendering live** + **PDF-Rendering (Code fertig, GTK fehlt — s.u.)**.
- Umgebung (Windows 11, PowerShell): venv `.\.venv\Scripts\python.exe`. Ollama läuft (gemma4:e4b).
  SearXNG läuft (Docker :8888, JSON aktiv). `python-pptx` **installiert**; `weasyprint` pip-installiert,
  aber **GTK-Runtime fehlt**. Repo: `main`, Remote vorhanden, alles gepusht.

## DEINE PHASE 4 — OUTPUT GENERATION (SPEC §15)
Drei gleichwertige Output-Typen, produktionsreif, bilingual (DE/EN), alles in `./output/`:
- **PDF-Briefs**: Jinja2-Templates T-1..T-6 (§10) → HTML → **WeasyPrint** → `.pdf`. Bottom-line-first,
  Quellen inline, max 2 Seiten Standard.
- **PPTX-Decks**: **python-pptx**, **alle 10 Slide-Typen** (§11), Neura-Farben aus `config.output.colors`,
  **Logo unten rechts auf jeder Slide**, „so what"-Headlines (nie Themen-Label), eine Message pro Slide.
  Business-Case-Deck nach SCR (§13).
- **Excel-Workbooks**: neues `core/excel_builder.py`, **openpyxl**, **E-1..E-4** (§12): Decision/Scoring
  Matrix (gewichtete `SUMPRODUCT`/`RANK`, Conditional Formatting), Benchmark Table (Auto-Filter,
  Sources-Tab), Business-Case-Modell (5 Tabs, alles formelgekoppelt an Assumptions, gelbe Input-Zellen),
  Tracker (Data-Validation-Dropdowns). **N-10: echte Formeln, keine hartkodierten Zwischenwerte** —
  Änderung einer gelben Zelle rechnet alles neu.
- **Orchestrierung**: `core/exporter.py` ausbauen; **Rendering auch in den Research-Pfad einhängen** —
  `run_pipeline` liefert `PipelineResult.routed_formats` (inkl. Business-Case-Dual-Output, N-6); mach
  daraus Dateien (wie es der Doc-Prep-Pfad via `_render_outputs` schon tut) und ersetze in
  `render_result` den „file rendering is Phase 4"-Hinweis. `assets/neura_logo.png` **fehlt noch** →
  vor dem Deck-Bau hinzufügen.

## ZUSÄTZLICH: OFFENE RESTPUNKTE AUS PHASE 3.5 (mit erledigen)
1. **PDF live bekommen (Teil deines PDF-Auftrags).** `core/exporter.build_management_pdf` ist fertig
   und korrekt (WeasyPrint, Neura-styled HTML→PDF) und **fällt aktuell fail-fast mit exakter
   GTK-Anleitung** aus, weil das **GTK3-Runtime auf Windows fehlt** (`libgobject`/`pango`/`cairo`).
   To-do: GTK3-Runtime installieren (Link in der Fehlermeldung + WeasyPrint-Doc), Terminal neu starten,
   PDF **live verifizieren** (`python main.py prepare <xlsx> --format brief`), und darauf die T-1..T-6
   Brief-Templates aufsetzen. **Null Code-Änderung nötig, damit der bestehende PDF-Pfad läuft.**
2. **Zwei authored Playbooks zur User-Review vorlegen (RULE 14).** `playbooks/deep_research_playbook.md`
   und `playbooks/doc_prep_playbook.md` sind von Opus verfasste Methodik (kein Neura-Fakteninhalt) und
   **warten auf das Review des Users**. Nicht still umschreiben — dem User explizit zur Freigabe/Anpassung
   vorlegen, dann ggf. einarbeiten.
3. **`core/exporter.py` erweitern, nicht duplizieren.** Es existiert bereits ein Phase-3.5-Slice:
   `build_management_deck` (python-pptx: dunkle Title-Slide, Executive Summary, 1 „so what"-Slide pro
   Thema, Sources) und `build_management_pdf` (WeasyPrint). Phase 4 baut die **vollen** 10 Slide-Typen,
   alle Brief-Templates und `excel_builder` darauf auf und absorbiert/verallgemeinert diesen Slice —
   keine Parallelimplementierung.

## ARBEITSWEISE
- **Plan-Mode**: Lies erst alles, dann erstelle einen atomaren Task-Plan in PROGRESS, dann los.
- **1 Commit pro Task** (`phase-4: …`); **PROGRESS nach JEDEM Task** updaten (RULE 12/13).
- **Tests vor Code** (RULE 11): `python -m pytest tests/ -v` muss vor neuem Code grün sein (141).
- **Config-driven everything**; `pathlib.Path`; `encoding='utf-8'`; alle LLM-Calls via `LocalLLMClient`
  mit `num_ctx`. Keine neuen Deps außerhalb SPEC §6 (python-pptx/weasyprint/jinja2/openpyxl/pandas/
  xlsxwriter sind erlaubt + in requirements.txt).
- **Quality-Gate pro Task, spätestens am Schluss**: `ruff format` + `ruff check` + `mypy --strict core
  llm models main.py` + `python -m pytest tests/ -v` (alles grün). Hinweis: `python-pptx` liefert eigene
  Typen → mypy prüft echt (ggf. gezielte `# type: ignore[...]`); `weasyprint` ist in den mypy-Overrides.
- **Commit-Messages**: auf dieser PowerShell **`git commit -F <tempfile>`** (Set-Content -Encoding utf8)
  in `$env:TEMP` schreiben — **nicht** `-m` Here-Strings (zerschießen mehrzeilige Messages); Tempfile
  außerhalb des Repos halten, sonst landet er im Commit.
- **Fail-fast** für harte Deps (fehlende Libs/Tools → exakte Fix-Anleitung); Rendering-Fehler im
  Doc-Prep-Pfad sind **fail-open** (Briefing geht trotzdem raus) — Muster aus `_render_outputs` beibehalten.
- Verträge nicht brechen: bestehende `AnalysisOutput`/`ResearchReport`/`PipelineResult`-Felder bleiben
  abwärtskompatibel (Defaults), damit alle 141 Tests grün bleiben.

## ERFOLGS-GATE (SPEC §15 Phase 4)
- Competitor-Query → professionelles PDF-Brief. Board-Query → Neura-styled `.pptx` (korrekte Farben,
  Logo unten rechts). Screening → Excel Decision-Matrix mit funktionierenden Gewichten/Rankings (Änderung
  der Gewichte rechnet neu). Business-Case → **PPTX + Excel** in einem Lauf. Alle Excel-Dateien öffnen
  sauber in MS Excel, Formeln rechnen neu (N-10). Beide Sprachen. **Tests + ruff + mypy grün.**

## ABSCHLUSS
Voller Phase-4-Handoff in `PROGRESS.md` (Tasks, Entscheidungen, Tests, „What to do FIRST" für Phase 5)
+ README-Update + `git push origin main`. Phase 5 (ChromaDB-Memory + Voice + Polish) bleibt außen vor.

Lies SPEC + WORKFLOW + PROGRESS vollständig, dann leg los mit dem Phase-4-Plan.
