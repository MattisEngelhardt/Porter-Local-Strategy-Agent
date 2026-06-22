# Porter — Dimensionen-Plan (Research · Analyst · Builder)

> **Status:** Entscheidung + Recherche fertig (Stand 23.06.2026). Aktueller Research-Porter
> gesichert als Tag `porter-research-v1.0` (zeigt auf `59e3d09`). **Am bestehenden Code wurde
> nichts geändert.** Dieses Dokument ist der Bauplan; die Umsetzung läuft auf eigenen Branches.
> Newest-on-top Handoff-Doc im Stil von `DESIGN_REVAMP_PROGRESS.md`.

---

## 0. Für dich in einem Satz (BWL-Klartext)

Porter bleibt **ein Motor**. Was sich pro Abteilung ändert, sind nur die **drei austauschbaren
Teile** aus deinem Strategie-Zettel: **Regelwerk** (wie gearbeitet wird), **Abteilungs-Wissen**
(was Porter über die Abteilung weiß) und **Vorlagen** (wie das Ergebnis aussieht). Wir bauen
**keine** drei getrennten Programme — das müsste man dreimal warten. Stattdessen: ein Code, und
pro Abteilung ein "Profil" + ein eigener GitHub-Branch, den man mit **einem Befehl** lädt. So
bekommst du **beides** zugleich: einen "Porter, der alles kann" (Profil `all`) **und** schlanke,
spezialisierte Porter pro Abteilung (Profil `research` / `recruiting` / `finance`).

**Warum nicht einfach drei Kopien?** Weil jede Verbesserung am Motor (und da passiert gerade viel
— siehe die ganzen Design-Revamp-Dokumente) sonst drei-, vier-, fünfmal nachgezogen werden müsste.
Das ist genau das "viel zu umständlich", das du befürchtet hast. Ein Motor + Profile = einmal
verbessern, alle profitieren.

> **🎯 Endziel (dokumentiert, dein Strategie-Zettel): ein eigenes Repo pro Abteilung**, jedes mit
> *einem* Befehl ladbar. **Weg dahin = jetzt sauber mit mehreren Branches arbeiten** (ein Motor,
> ein Branch je Dimension). Ein fertiger Branch wird später 1:1 zu einem eigenen Repo. So bleibt
> der Motor bis zuletzt *eine* Quelle der Wahrheit, und der Repo-Split ist am Ende ein kleiner,
> mechanischer Schritt — kein paralleles Pflegen von drei Codebasen.

> **Klarstellung Mattis (23.06.2026):** „Keinen bestehenden Code ändern" = die **Strategy-Dimension
> (der gesamte heutige Porter) bleibt unverändert**. Für die **neuen** Dimensionen *wird* Code
> geschrieben — er baut bewusst auf dem heutigen Porter auf, passiert aber ausschließlich auf
> Dimensions-Branches, nie auf `main`.

---

## 1. Die Entscheidung (Empfehlung)

**Gewählt: „Ein Motor, austauschbare Dimensionen" — ein Code, Verteilung über Branches.**

| Frage | Antwort |
|---|---|
| Ein Porter der alles kann, oder mehrere? | **Beides** — aus *einem* Code. „Alles" = Profil `all`. „Spezialisiert" = je ein Profil/Branch. |
| Mehrere Branches auf GitHub? | **Ja, aber dünn.** `main` = Research (gesichert). `analyst`, `builder`, evtl. `all` = derselbe Motor + nur die Dimensions-Teile. Kein Motor-Fork. |
| Mehrere Repos (ein Repo pro Abteilung, wie im Zettel)? | **Das ist das erklärte ENDZIEL** (so steht es im Strategie-Zettel). Wir bereiten es jetzt sauber über Branches vor; ein fertiger Branch lässt sich jederzeit 1:1 zu einem eigenen Repo „befördern" (`git subtree`/Repo-Split). Jetzt sofort drei Repos wäre verfrüht — würde Wartung verdreifachen, bevor die Dimensionen überhaupt stehen. |
| Wird der jetzige Code angefasst? | **Nein.** `main` bleibt unverändert. Tag `porter-research-v1.0` friert den Stand ein. Neues nur additiv auf neuen Branches. |

**Verworfen — „3 separate Repos mit Voll-Kopie des Motors":** verdreifacht jede Bugfix-/Design-Arbeit,
Brain/Wissen vermischt sich, Versionen driften auseinander. Widerspricht dem eigenen Prinzip
„ein Motor, drei Teile".

**Verworfen — „ein Mono-Porter, alles immer an":** Recruiting-Code läge auf dem Finance-Laptop,
das Abteilungs-Wissen (CVs ↔ Zahlen) würde sich vermischen, und „ein Befehl pro Abteilung" würde
zu „alles installieren + konfigurieren". Das `all`-Profil deckt den „kann alles"-Wunsch trotzdem ab.

---

## 2. Porters Architektur heute — und wo die „drei Teile" im Code sitzen

Der Motor (unverändert, wird geteilt):

- `core/pipeline.py` — die Master-Schleife (Intent → Klärfragen → [Research|Docs] → Synthese → Kritik → Render)
- `llm/local_llm_client.py` — backend-agnostischer LLM-Client (Ollama / LM Studio / OpenRouter)
- **Lesen:** `core/pdf_reader.py`, `core/excel_reader.py`, `core/intake.py` (`read_document`-Dispatch)
- **Synthese/Bewertung:** `core/synthesizer.py`, `core/doc_synthesis.py`, `core/critic.py`
- **Render/Bauen:** `core/exporter.py` (PDF+PPTX), `core/excel_builder.py`, `core/composer.py` + Design-System
- `core/config.py` — getypte Config (Pydantic), sauber in Sektionen → **Profile rein additiv möglich**

Die **drei austauschbaren Teile** (das, was pro Abteilung wechselt):

| Teil (Zettel) | Im Code | Heute (Research) |
|---|---|---|
| **Regelwerk** | `playbooks/*.md` (geladen via `core/playbooks.py`) | research / analysis / output / deep_research / doc_prep |
| **Abteilungs-Wissen** | `brain.md` + Memory (`core/memory.py`, ChromaDB) | Neura-/Strategie-Kontext |
| **Vorlagen** | `templates/briefs/*.j2`, `templates/decks/`, Excel-Templates `E-1..E-4` | Board-/Decision-/Competitor-Briefs |

**Befehle heute** (`main.py`): `ask`, `research`, `analyze`, `prepare` (CEO-Office: interne Docs →
Briefing, **ohne** Web), `analyze-doc` (ein Dokument lesen), REPL.

➡️ **Wichtigste Erkenntnis:** Dein „ein Motor, drei Teile" ist im Code **bereits sauber getrennt**.
Die richtige Variations-Einheit ist deshalb das **Profil** (welche Playbooks + welches Brain +
welche Vorlagen + welche Befehle), **nicht** ein kopierter Motor.

### Lücken für die neuen Dimensionen (heute fehlt)

- **Word (.docx) lesen:** `python-docx` ist als Dependency da, aber in `read_document` **nicht
  verdrahtet** (nur `.xlsx`/PDF/Bild). → CVs sind oft Word.
- **PPTX lesen:** `python-pptx` kann nur **schreiben**; Lesen interner Decks fehlt.
- **Bewerten/Ranken (Analyst):** keine Scoring-Pipeline (CV ↔ Stellenprofil → Score → Rang).
- **Finance-Reporting (Builder):** `prepare`/`doc_synthesis` ist der Keim; es fehlen Finance-Playbook
  + Reporting-Vorlagen + „jede Zahl zur Quelle"-Härtung über viele Zahlenquellen.
- **Profil-/Dimensions-Umschalter:** fehlt (analog zum vorhandenen `switch-model.ps1`).

---

## 3. Tool-Recherche (Stand 23.06.2026) — was lokal & kostenlos genutzt wird

Leitplanken: **kostenlos, MIT/permissiv (gefahrlos verteilbar), 100 % lokal/offline** (DSGVO).
**AGPL gemieden** (PyMuPDF) wegen Verteilung an Abteilungen.

### Lesen / Extrahieren (Wort für Wort + Tabellen) — Kern der neuen Use Cases

| Tool | Lizenz | Rolle | Warum |
|---|---|---|---|
| **Docling** (IBM, Linux Foundation) | **MIT** | **Neuer Kern** für hochwertiges Lesen von PDF/DOCX/PPTX/XLSX/Bild → strukturiertes Markdown/JSON/DataFrame | Bestes Open-Source für Tabellen (TableFormer), Mehrspalten, Formeln; **läuft offline auf CPU**; OCR eingebaut; air-gapped tauglich. ~88 % F1. |
| **MarkItDown** (Microsoft) | **MIT** | Optionaler **Schnell-Pfad** für saubere digitale Dateien (15+ Formate → Markdown) | 50–100× schneller als Docling auf einfachen PDFs; leichtgewichtig; gut als Fallback. |
| **pdfplumber** | MIT | **Bleibt** — gut für Finanz-Tabellen | Schon im Einsatz, MIT, präzise Tabellen auf kleinen Mengen. |
| **python-docx** | MIT | Word-Lese-Pfad (leichtgewichtig) | Schon Dependency; nur noch in `read_document` verdrahten. |
| **python-pptx** | MIT | PPTX **lesen** (Text/Tabellen/Notizen) | Schon da (zum Schreiben); fürs Lesen wiederverwenden — **keine neue Dependency**. |
| ~~PyMuPDF~~ | ~~AGPL-3.0~~ | **gemieden** | Schnell, aber AGPL = Quelloffenlegungs-Pflicht bei Verteilung. Nicht nötig. |

**Strategie:** Docling als Standard-Leser für die Analyst/Builder-Dimensionen (Qualität + Tabellen),
MarkItDown als schneller Fallback, pdfplumber/python-docx/python-pptx als leichte Pfade. Alles MIT, alles offline.

### Rendern / Konvertieren (Office-Dateien sichtbar/umwandeln) — „rendern"

| Tool | Lizenz | Rolle |
|---|---|---|
| **LibreOffice headless** (`soffice --headless --convert-to pdf/png`) | MPL/LGPL (frei) | docx/pptx/xlsx ↔ pdf/png lokal konvertieren & rendern (z. B. internes Word als PDF-Vorschau, oder Output prüfen). Optionale System-Abhängigkeit wie GTK für WeasyPrint. |
| **pypdfium2** (schon im venv) | Apache/BSD | PDF-Seite → PNG rastern (Vorschau / Vision-Eingabe) |

### Bewerten (Analyst-Scoring) — **keine neue Lib nötig**

Das ist LLM-Arbeit, kein Tool: Reader (Docling) extrahiert strukturiert → lokales LLM bewertet
gegen eine **Rubrik** (Pydantic-Modell) nach einem **Scoring-Playbook** → gerankte Tabelle über
die vorhandenen Excel-/PPTX-Renderer. Nutzt das bestehende `synthesizer`/`critic`-Muster.

➡️ **Neue Dependencies insgesamt:** nur `docling` (+ optional `markitdown`). Beide MIT, beide
lokal. LibreOffice ist optional und nur für „rendern/konvertieren von Office".

---

## 4. Die drei Dimensionen (Spec)

Jede Dimension = **Motor + Profil** (Befehle + Playbook + Brain-Pack + Vorlagen). Schema:

```
profiles/
  research/   profile.yaml  brain.research.md   (playbooks/templates: bestehende)
  recruiting/ profile.yaml  brain.recruiting.md  playbooks/recruiting_*.md  templates/...
  finance/    profile.yaml  brain.finance.md     playbooks/finance_*.md     templates/...
  all/        profile.yaml  (aktiviert alle Befehle/Playbooks)
```

`profile.yaml` (additiver Config-Layer, optional — Default = `research`, alles bleibt abwärtskompatibel):

```yaml
profile:
  name: recruiting
  commands: [ask, analyze-doc, prepare, score-cvs]   # welche Befehle sichtbar sind
  playbooks: [recruiting_screening, doc_prep]          # Regelwerk
  brain: ./profiles/recruiting/brain.recruiting.md     # Abteilungs-Wissen
  templates_dir: ./profiles/recruiting/templates        # Vorlagen
  default_format: excel                                  # Default-Deliverable
```

### 4.1 Research → Strategy / CEO Office *(existiert, bleibt `main`)*
M&A-Screening, Kapitaleinsatz, 5-Jahres-Strategie, Wettbewerb, Board-Unterlagen. → unverändert.

### 4.2 Analyst → Recruiting *(neu, Branch `analyst`)*
**Job:** Lebensläufe (PDF/Word) einlesen → gegen Stellenprofil **bewerten & ranken**. Lokal =
DSGVO-sicher, **Mensch entscheidet**.
- **Lesen:** docx/pdf via Docling (+ python-docx leicht). CVs Wort für Wort.
- **Neuer Befehl:** `score-cvs <cv1> <cv2> … --profile-spec job.md` → gerankte Tabelle + Begründung je Kandidat, jede Aussage zur CV-Stelle belegt (kein Erfinden).
- **Regelwerk:** `recruiting_screening_playbook.md` (Rubrik, Bias-Vermeidung, „nur was im CV steht", Mensch-entscheidet-Hinweis).
- **Vorlage:** Excel-Ranking (Kandidat × Kriterium, Score, Gesamt, Rang) + optional PDF-Shortlist.
- **Modelle:** `models/scoring.py` (Rubrik, Kriterium, KandidatenScore).

### 4.3 Builder/Ersteller → Finance / Controlling *(neu, Branch `builder`)*
**Job:** aus vielen internen Zahlen automatisch **Management-/Board-Reporting**. **Jede Zahl kommt
aus den Dokumenten** (Zero Hallucination, schon im `doc_prep_playbook` verankert).
- **Lesen:** xlsx (pdfplumber/openpyxl/Docling), interne Decks (pptx-Reader), PDF-Berichte.
- **Neuer Befehl:** `build-report <zahlen.xlsx> <bericht.pdf> … --period "Q2 2026"` → Management-Report (PDF/PPTX) + optional Excel-Modell, jede Kennzahl mit Quelle (Datei/Blatt/Zelle).
- **Regelwerk:** `finance_reporting_playbook.md` (KPI-Konsolidierung, Perioden-Vergleich, Quellen-Trace, Abweichungslogik) — erweitert `doc_prep`.
- **Vorlage:** Board-Reporting-Brief/Deck + KPI-Tabellen.

---

## 5. Verteilung / GitHub — „mit einem Befehl laden"

```
main      ──●  Research-Porter (unverändert)         Tag: porter-research-v1.0
            │
            ├─► analyst   = main + Recruiting-Profil + docx/pptx-Reader + score-cvs
            ├─► builder   = main + Finance-Profil + build-report
            └─► all       = main + alle Profile aktivierbar (der „kann alles"-Porter)
```

- **Ein Befehl pro Abteilung:** `git clone -b analyst <repo>` (bzw. `-b builder` / `-b all`).
- **Motor-Verbesserungen fließen mit `git merge` von `main` in die Branches** — **niemals rebase/force-push** (deine Contribution-Regel bleibt gewahrt; jeder echte Commit zählt).
- **Shared Reader (docx/pptx) + Profil-Mechanik** sind **additiv**; sie könnten später sauber auch
  nach `main` mergen, ohne Research zu verändern (alles ist opt-in über das Profil).
- **Repo-pro-Abteilung** (wie im Zettel) = späteres `git subtree`/Repo-Split aus dem fertigen Branch.

---

## 6. Bauplan in Blöcken (additiv; Engine-Code nur auf Branches)

> Konvention dieses Repos: kohärente Slices, je ein echter Commit, **direkt auf den Branch, plain push**,
> kein squash/rebase. Tests pro Slice (`pytest`, `ruff`, `mypy --strict`).

- **Block A — Fundament (Branch `dimensions` o. `analyst`):**
  `core/docx_reader.py` (python-docx) + `core/pptx_reader.py` (python-pptx) als **neue** Module;
  `read_document`-Dispatch um `.docx/.pptx` erweitern (auf dem Branch, nicht auf `main`).
  Optionaler Docling-Adapter `core/docling_reader.py` (fail-open: fehlt docling → Fallback auf
  pdfplumber/python-docx, exakte Fix-Anweisung). Tests + requirements (`docling`, optional `markitdown`).
- **Block B — Profil-Mechanik:** `core/profile.py` + `profile`-Sektion in `config.py` (Default
  `research`, abwärtskompatibel) + `switch-profile.ps1` (Spiegel von `switch-model.ps1`).
- **Block C — Analyst/Recruiting:** `models/scoring.py`, `recruiting_screening_playbook.md`,
  Excel-Ranking-Vorlage, `score-cvs`-Befehl, Profil `recruiting`. Tests.
- **Block D — Builder/Finance:** `finance_reporting_playbook.md`, Reporting-Vorlagen,
  `build-report`-Befehl, Profil `finance`. Tests.
- **Block E — `all`-Profil + Branches + README je Branch** („so lädst du genau diese Abteilung").
- **Block F — (Zettel-Vision, später):** Hardware-Erkennung wählt Modell automatisch; einfache
  App-UI (Chat statt Terminal).

---

## 7. Garantien (das hast du verlangt)

1. **Nichts am jetzigen Code geändert.** `main` unangetastet; alle uncommitteten Design-Änderungen
   in deinem Arbeitsbereich blieben unberührt.
2. **Jetziger Porter gesichert & ziehbar:** Tag `porter-research-v1.0` (auf `59e3d09`).
   `git checkout porter-research-v1.0` bzw. `git clone --branch porter-research-v1.0 …` holt **exakt**
   den heutigen Research-Porter.
3. **Alles Neue additiv & opt-in** über das Profil (Default bleibt Research) — Research-Porter
   funktioniert unverändert weiter, egal was auf den Dimensions-Branches passiert.

---

## 8. Offen / nächster Schritt (Entscheidung Mattis)

**Verteilungs-Modell bestätigen** (Branches jetzt vs. Repos später) und ob ich Tag + Struktur
**zu GitHub pushen** soll. Danach: Block A starten (docx/pptx-Reader + Docling-Adapter) auf dem Branch.
