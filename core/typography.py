"""Porter typography library + curated type-themes (Editorial v4.0).

A pool of **25+ free OFL font families** (all on Google Fonts; fetched by
``scripts/install_fonts.py``), grouped by role, plus curated **type-themes** that pair them so a
deck mixes 3–4 contrasting families per composition — never 20 on one slide. Pure tokens: no file
I/O, no python-pptx, no LLM. Each role carries a system-font fallback stack so output is never
broken when the OFL TTFs are not installed (REQ-1/2). Theme selection is config-driven (RULE 4)
via ``output.style.type_theme``.
"""

from __future__ import annotations

# System-font fallback stacks per role (mirror the stacks in ``core.design``).
_SERIF_FALLBACK = '"Georgia", "Times New Roman", serif'
_GROTESK_FALLBACK = '"Aptos", "Segoe UI", Arial, sans-serif'
_BODY_FALLBACK = '"Aptos", "Segoe UI", Arial, sans-serif'
_MONO_FALLBACK = '"Consolas", "Courier New", monospace'
_DISPLAY_FALLBACK = '"Arial Black", "Aptos", Impact, sans-serif'

_ROLE_FALLBACK: dict[str, str] = {
    "serif": _SERIF_FALLBACK,
    "grotesk": _GROTESK_FALLBACK,
    "body": _BODY_FALLBACK,
    "mono": _MONO_FALLBACK,
    "display": _DISPLAY_FALLBACK,
}

# The selection pool, grouped by role. `display` = expressive statement faces; `grotesk` = workhorse
# sans (also used for `body`). Every family is OFL and present under ofl/<dir> on Google Fonts.
FONT_LIBRARY: dict[str, tuple[str, ...]] = {
    "serif": (
        "Fraunces",
        "Playfair Display",
        "DM Serif Display",
        "Bodoni Moda",
        "Cormorant Garamond",
        "Spectral",
        "Newsreader",
        "Instrument Serif",
    ),
    "grotesk": (
        "Space Grotesk",
        "Inter",
        "Archivo",
        "Manrope",
        "Sora",
        "Schibsted Grotesk",
        "Hanken Grotesk",
    ),
    "display": (
        "Archivo Black",
        "Anton",
        "Bebas Neue",
        "Syne",
        "Unbounded",
        "Big Shoulders Display",
    ),
    "mono": (
        "Space Mono",
        "JetBrains Mono",
        "IBM Plex Mono",
        "DM Mono",
    ),
}

DEFAULT_THEME = "editorial"

# Curated pairings: each theme names one family per role (serif display / expressive display /
# grotesk headline / body / mono). The `editorial` theme equals the v3.0 defaults so the default
# deck/brief output is unchanged.
TYPE_THEMES: dict[str, dict[str, str]] = {
    "editorial": {
        "serif": "Fraunces",
        "display": "Archivo Black",
        "grotesk": "Space Grotesk",
        "body": "Inter",
        "mono": "Space Mono",
    },
    "kinetic": {
        "serif": "Instrument Serif",
        "display": "Anton",
        "grotesk": "Space Grotesk",
        "body": "Archivo",
        "mono": "JetBrains Mono",
    },
    "luxury": {
        "serif": "Bodoni Moda",
        "display": "Playfair Display",
        "grotesk": "Sora",
        "body": "Manrope",
        "mono": "IBM Plex Mono",
    },
    "modern": {
        "serif": "Newsreader",
        "display": "Unbounded",
        "grotesk": "Syne",
        "body": "Manrope",
        "mono": "DM Mono",
    },
    "brutalist": {
        "serif": "DM Serif Display",
        "display": "Bebas Neue",
        "grotesk": "Archivo",
        "body": "Hanken Grotesk",
        "mono": "Space Mono",
    },
}


def theme_names() -> list[str]:
    """Names of all available type-themes (stable order)."""
    return list(TYPE_THEMES.keys())


def resolve_theme(name: str | None) -> dict[str, str]:
    """Role→family mapping for a theme name, falling back to the editorial default if unknown."""
    key = (name or DEFAULT_THEME).strip().lower()
    return dict(TYPE_THEMES.get(key, TYPE_THEMES[DEFAULT_THEME]))


def role_fallback(role: str) -> str:
    """System-font fallback stack for a role (used to keep CSS stacks unbreakable)."""
    return _ROLE_FALLBACK.get(role, _BODY_FALLBACK)


def font_stack(role: str, family: str) -> str:
    """A CSS font stack ``"family", <role fallbacks>`` (OFL primary → system fallback)."""
    return f'"{family}", {role_fallback(role)}'


def all_families() -> list[str]:
    """Every family in the library, deduped in a stable order (used by the installer/tests)."""
    seen: list[str] = []
    for families in FONT_LIBRARY.values():
        for family in families:
            if family not in seen:
                seen.append(family)
    return seen
