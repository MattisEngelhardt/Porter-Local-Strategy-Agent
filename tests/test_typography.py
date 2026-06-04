"""Tests for the Porter typography library + type-themes (core/typography.py).

Pure tokens — no I/O, no pptx. Locks the >=20-family OFL pool, the curated theme pairings, the
unbreakable system-font fallback stacks, and that every theme family is drawn from the pool.
"""

from __future__ import annotations

from core.typography import (
    FONT_LIBRARY,
    TYPE_THEMES,
    all_families,
    font_stack,
    resolve_theme,
    role_fallback,
    theme_names,
)

_ROLES = {"serif", "display", "grotesk", "body", "mono"}


def test_library_has_at_least_20_unique_families() -> None:
    families = all_families()
    assert len(families) >= 20
    assert len(families) == len(set(families))  # deduped


def test_every_theme_resolves_all_roles_from_the_pool() -> None:
    pool = set(all_families())
    for name in theme_names():
        theme = resolve_theme(name)
        assert set(theme) == _ROLES
        for family in theme.values():
            assert family in pool  # never reference a family we do not ship


def test_resolve_theme_falls_back_to_editorial() -> None:
    assert resolve_theme("editorial") == TYPE_THEMES["editorial"]
    assert resolve_theme(None) == TYPE_THEMES["editorial"]
    assert resolve_theme("does-not-exist") == TYPE_THEMES["editorial"]
    assert resolve_theme("  KINETIC ") == TYPE_THEMES["kinetic"]  # case/space-insensitive


def test_font_stack_keeps_primary_then_fallback() -> None:
    stack = font_stack("serif", "Fraunces")
    assert stack.startswith('"Fraunces"')
    assert role_fallback("serif") in stack
    # an unknown role still yields a usable body fallback (never empty)
    assert font_stack("nope", "X").endswith(role_fallback("body"))


def test_font_library_roles_present() -> None:
    assert _ROLES.issubset(set(FONT_LIBRARY) | {"body"})  # body draws from the grotesk pool
    assert "Fraunces" in FONT_LIBRARY["serif"]
    assert "Anton" in FONT_LIBRARY["display"]
