# Porter — Commit- & Branch-Architektur (verbindlich)

> Stand 23.06.2026. Zweck: klare, professionelle Ordnung; **alle Beiträge zählen** auf
> „contributions in the last year"; **du musst nie selbst einen Pull Request anklicken.**

---

## In einem Satz (BWL-Klartext)

**`main` ist der „Porter, der alles kann" und die einzige Linie, die zählt** (Streak/Contributions).
Alle echte Arbeit wird auf `main` committet → zählt sofort. Die Dimensionen sind **sauber getrennte
Module** im Code, per **Profil** schaltbar (= ein Code, der entweder alles kann *oder* als eine
einzelne Dimension läuft). **Am Ende wird jede Dimension ein eigenes Repo — sauber, *weil* die
Module getrennt sind, nicht wegen Branches.** **Claude macht das Git komplett selbst; du machst
nichts von Hand.**

---

## Die Regeln (so bleibt es sauber & gezählt)

1. **`main` = der Alleskönner.** Research **und** Analyst (Recruiting) **und** Builder (Finance)
   liegen auf `main`. Das ist die eine Codebasis, die gepflegt wird.
2. **GitHub zählt Commits nur auf `main`** (dem Default-Branch). Deshalb: **alles muss auf `main`
   landen**, sonst zählt es nicht und es erscheint „X commits behind".
3. **Standard-Weg = direkt auf `main` committen + normaler `git push`.** Zählt sofort, **kein PR**,
   kein „behind". (Das ist dein gewünschter Sofort-Fluss.)
4. **Wenn doch mal ein Branch nötig ist** (großes, riskantes Experiment): **Claude** merged ihn
   selbst per **regulärem Merge** zurück nach `main` (**nie** Squash, **nie** Rebase/Force) — und
   **du klickst nichts**. Danach wird der Branch aufgeräumt.
5. **Niemals** bereits gepushte Commits rebasen/force-pushen (das bricht die Zählung — der alte
   2026-06-03-Fehler).
6. **Du musst nie selbst einen PR ausführen.** Falls ein PR entsteht, erledigt Claude ihn per
   `gh` automatisch (Token aus `git credential`). Auf GitHub musst du nichts anklicken.

---

## Was fest verankert ist (Snapshots)

- **Tag `porter-research-v1.0`** → friert den reinen Research-Porter ein. Immer ziehbar mit
  `git clone --branch porter-research-v1.0 …`. Bleibt für immer, egal wie `main` wächst.
- Ältere Release-Tags (`v5.0.0` etc.) bleiben unberührt.

---

## Die Dimensionen — was sie sauber UND zählbar UND repo-fähig macht

Drei Dinge zählen — **Branches gehören NICHT dazu**:

1. **`main` = Entwicklung + Zählung.** Jede echte Änderung wird auf `main` committet → zählt sofort
   (Streak sicher). `main` mit allen Dimensionen = der Alleskönner.
2. **Saubere Module pro Dimension** auf dem gemeinsamen Motor: Analyst = `core/recruiting.py` +
   `models/scoring.py` + `playbooks/recruiting_*`; Builder = `core/finance_reporting.py` +
   `models/reporting.py` + `playbooks/finance_*`. **Das** macht den späteren Repo-Split mühelos —
   nicht Branches.
3. **Profile = der Schalter** (`research`/`recruiting`/`finance`/`all`, Block B). Ein Code → läuft
   als Alleskönner *oder* als eine einzelne Dimension. Liefert „einer der alles kann" **und** die
   spezifischen Porter aus *einer* Codebasis.

**Branches:** nur **kurzlebige Feature-Branches**, die Claude selbst nach `main` merged. **Keine
dauerhaften Dimensions-Branches** — sie zählen nicht (bis gemerged), laufen „behind" und bringen
für den Repo-Split keinen Vorteil. (Willst du die Dimensionen trotzdem als Branches *sehen*, legt
Claude reine Spiegel-Branches von `main` an — optional, rein kosmetisch, keine Arbeit darauf.)

**Endziel (Strategie-Zettel):** jede Dimension wird ein **eigenes Repo** (eigene `main`, eigene
Zählung) — per `git subtree split` von {Motor + dieser Dimension}, **kein** History-Rewrite. Erst
wenn die Dimensionen stabil sind. (Optional vorher: Dimension-Module in Unterordner gruppieren,
z. B. `core/dimensions/recruiting/`, macht den Split noch sauberer.)

---

## Aktueller Git-Stand (23.06.2026)

- `main`: Research **+ Block A** (Word/PPTX/Docling-Reader) **+ Block C** (Analyst) **+ Block D**
  (Builder) — alles gezählt.
- Tag `porter-research-v1.0`: reiner Research-Porter, gesichert.
- Branch `feat/dimensions`: war der einmalige Bau-Branch; nach dem Merge = identisch zu `main`
  (kein „behind", kein offener PR). Kann später gelöscht werden.

## Nächster Schritt (optional)

- **Block B — Profil-Schalter** (`switch-profile.ps1` + `profile:` in `config.yaml`), damit eine
  Abteilung mit einem Befehl genau ihre Dimension bekommt. Danach: Repo-Split als Endziel.
