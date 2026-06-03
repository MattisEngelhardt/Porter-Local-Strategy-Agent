# Porter Editorial fonts (OFL)

Porter's PDF brief **embeds** and the PPTX deck **names** a four-family editorial type system
(`core/design.py`). All four are free [SIL Open Font License](https://openfontlicense.org) fonts:

| Role            | Family         | Source (Google Fonts) |
| --------------- | -------------- | --------------------- |
| Serif display   | **Fraunces**   | `ofl/fraunces`        |
| Grotesk display | **Space Grotesk** | `ofl/spacegrotesk` |
| Body            | **Inter**      | `ofl/inter`           |
| Mono micro-labels | **Space Mono** | `ofl/spacemono`     |

## Install

The TTFs are **not committed** (kept out of git as binaries). Fetch them once into this directory:

```powershell
.venv\Scripts\python scripts\install_fonts.py
# behind a corporate proxy with cert-revocation issues:
.venv\Scripts\python scripts\install_fonts.py --insecure
```

The installer downloads each family's variable TTF (Space Mono: regular) plus its `OFL.txt`, with a
clean filename (`Fraunces.ttf`, `SpaceGrotesk.ttf`, `Inter.ttf`, `SpaceMono.ttf`) that
`core/exporter.py::_font_face_css` matches by the family's normalised name.

## Degradation (REQ-5)

If this directory is empty/absent, the renderers fall back to the system fonts kept in every CSS
stack — **Georgia** (serif), **Aptos / Segoe UI** (grotesk/body), **Consolas** (mono) — so output is
never broken, just less branded. Once the TTFs are present they auto-embed in the next PDF; PowerPoint
substitutes the named families if they are not installed system-wide.
