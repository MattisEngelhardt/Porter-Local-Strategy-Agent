# Porter — Commit- & Branch-Architektur (verbindlich)

> Stand 23.06.2026. Zweck: klare, professionelle Ordnung; **alle Beiträge zählen** auf
> „contributions in the last year"; **du musst nie selbst einen Pull Request anklicken.**

---

## In einem Satz (BWL-Klartext)

**`main` ist der „Porter, der alles kann" und die einzige Wahrheit.** Alle Arbeit landet auf
`main` → wird sofort gezählt. **Claude (der Agent) macht das Git komplett selbst** — committen
und pushen — **du machst nichts von Hand.** Die einzelnen Abteilungs-Versionen sind später
**Profile/eigene Repos**, *nicht* dauerhafte Branches.

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

## Die Dimensionen — wie getrennt wird (ohne Branch-Chaos)

| Dimension | Heute | Trennung |
|---|---|---|
| Research / Strategy | auf `main` | Profil `research` (+ Tag als Snapshot) |
| Analyst / Recruiting | auf `main` (`score-cvs`) | Profil `recruiting` |
| Builder / Finance | auf `main` (`build-report`) | Profil `finance` |
| Alleskönner | = `main` | Profil `all` |

- **Dimensionen = Profile (Einstellung), KEINE Dauer-Branches.** Ein Dauer-Branch pro Abteilung
  würde (a) nicht gezählt bis gemerged und (b) ständig „behind" laufen — genau das Chaos, das wir
  vermeiden. Deshalb: ein Code auf `main`, ein Profil wählt die Abteilung.
- **Endziel (Strategie-Zettel):** ein eigenes **Repo pro Abteilung** — jedes Repo hat seine eigene
  `main` und eigene Contribution-Zählung. Wird aus dem Alleskönner gepackt, wenn die Dimensionen
  stabil sind. (Profil-Schalter = Zwischenschritt dorthin.)

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
