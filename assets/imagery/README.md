# Neura cover imagery (drop-in)

Porter's deck **cover** can sit on a full-bleed Neura brand image (robot shots, hero photography)
under a dark scrim, with the title knocked out over it — the warm, photographic "Cofounder" feel.

## How to use

Drop professional Neura images into this folder (`assets/imagery/`):

- Supported formats: `.jpg` / `.jpeg` / `.png` / `.webp`
- Recommended size: **16:9, ≥ 1920×1080** (it is laid full-bleed, so use a high-res image).
- Name a preferred cover `cover.jpg` / `hero.jpg` / `title.jpg` — it wins automatically. Otherwise
  Porter picks one deterministically from whatever is here (stable per deck title).

The directory is configured by `config.yaml → output.imagery_dir` (default `./assets/imagery`).

## Fail-open

If this folder is empty or missing, the cover degrades to the luminous warm→cool **gradient** cover
(today's behavior). Nothing breaks, no network, no image generation, no invented content (REQ-5).

## Light logo on dark slides

The dark cover/divider needs a **light** logo variant so the mark does not vanish. Add one and point
`config.yaml → output.logo_path_light` at it (e.g. `./assets/neura_logo_light.png`). Without it,
Porter keeps the standard logo and simply avoids the page-number collision.

> Binary images are git-ignored by default — commit only if you intend to ship them with the repo.
