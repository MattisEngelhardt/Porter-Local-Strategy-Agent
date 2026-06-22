# Porter Dimensions — Progress (newest on top)

> Rolling handoff for the **Analyst (Recruiting)** + **Builder (Finance)** dimensions.
> Branch: `feat/dimensions` (off `main` @ `59e3d09`). Full plan: [PORTER_DIMENSIONS_PLAN.md](PORTER_DIMENSIONS_PLAN.md).
> Distribution = branches now, **separate repo per department = documented end goal**.
> The Research/Strategy dimension (`main` + tag `porter-research-v1.0`) is **frozen and untouched**.

---

## Block A — Document-reader foundation ✅ (2026-06-23)

**Goal:** give Porter the ability to *read* the document types the new dimensions need (Word, PowerPoint)
and a high-fidelity optional path — additively, without changing the Research engine on `main`.

**Shipped (all new/edited files on `feat/dimensions` only):**
- `core/docx_reader.py` — read `.docx` (paragraphs + tables, verbatim) via **python-docx** (already installed). New.
- `core/pptx_reader.py` — read `.pptx` (slide text + tables + speaker notes) via **python-pptx** (already installed). New.
- `core/docling_reader.py` — optional **Docling** (IBM, MIT, local/offline) high-fidelity adapter.
  **Fails open**: raises `DoclingNotInstalledError` if docling absent so callers fall back to the
  lightweight readers. New.
- `core/intake.py` — `read_document` now dispatches `.docx`/`.pptx` (+ `_SUPPORTED_SUFFIXES` so the REPL
  accepts dropped Word/PPTX paths). Edited (additive).
- `main.py` — `prepare` / `analyze-doc` now catch `DocxReadError` / `PptxReadError`; help text updated. Edited.
- `requirements.txt` — new optional "Dimensions" group: `docling` (+ `markitdown` commented). Edited.
- `pyproject.toml` — `docling` added to mypy `ignore_missing_imports` overrides. Edited.
- Tests (new): `tests/test_docx_reader.py`, `tests/test_pptx_reader.py`, `tests/test_docling_reader.py`,
  `tests/test_intake_doc_dispatch.py`.

**Verification:** 14/14 new tests pass · `ruff check` clean · `ruff format` clean · `mypy --strict` clean
(on the 3 new modules). No new hard dependency: `.docx`/`.pptx` reading works today; Docling is opt-in.

**Try it (once on this branch):**
```powershell
python main.py analyze-doc path\to\cv.docx        # prints extracted Word text + tables
python main.py analyze-doc path\to\board_deck.pptx # prints slide text + tables + notes
```

---

## Next blocks (not started)

- **Block B — Profile mechanic:** `core/profile.py` + optional `profile:` config section (default
  `research`, fully backward-compatible) + `switch-profile.ps1` (mirror of `switch-model.ps1`).
- **Block C — Analyst / Recruiting:** `models/scoring.py`, `recruiting_screening_playbook.md`,
  Excel ranking template, `score-cvs` command, profile `recruiting`.
- **Block D — Builder / Finance:** `finance_reporting_playbook.md`, reporting templates,
  `build-report` command, profile `finance`.
- **Block E — Packaging:** cut thin distribution branches `analyst` / `builder` / `all` from this base;
  per-branch README ("so lädst du genau diese Abteilung"). Prepare the eventual repo-per-department split.
- **Block F — (later, per strategy memo):** auto hardware detection → model choice; simple chat App-UI.

## Follow-ups noted during Block A
- Optional: README section documenting `.docx`/`.pptx` support + the Docling opt-in.
- The analyst/builder pipelines should call `core.docling_reader.read_with_docling` first and fall back to
  `read_document` (the high-fidelity → lightweight cascade) when exact tables matter.
