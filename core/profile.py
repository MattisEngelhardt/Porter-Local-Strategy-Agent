"""Dimension profiles (Block B): one codebase, switchable per department.

A *profile* selects which Porter dimension is active — which commands a department's Porter
exposes — **without forking the code**. The default profile ``all`` is the all-rounder (every
dimension enabled), so existing behaviour is unchanged when no profile is set.

The active profile is resolved from, in order: the ``PORTER_PROFILE`` environment variable, then
the ``./.porter_profile`` file (one line), else ``all``. This is kept deliberately **independent of
config.yaml** so switching a profile never collides with in-progress config edits, and a fresh
clone defaults to the all-rounder. Switch with ``switch-profile.ps1`` or ``python main.py profile``.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

_PROFILE_FILE = Path("./.porter_profile")

# Utility commands available in every profile (reading/asking is never dimension-specific).
_ALWAYS: frozenset[str] = frozenset({"ask", "analyze-doc", "profile"})

_RESEARCH: frozenset[str] = frozenset({"research", "analyze", "prepare"})
_ANALYST: frozenset[str] = frozenset({"score-cvs"})
_BUILDER: frozenset[str] = frozenset({"build-report"})


class ProfileError(Exception):
    """An unknown profile was requested (fail fast with the valid choices)."""


class Profile(BaseModel):
    """One dimension profile: a name + label + the set of commands it enables."""

    name: str
    label: str
    description: str
    commands: frozenset[str]


PROFILES: dict[str, Profile] = {
    "all": Profile(
        name="all",
        label="Allrounder",
        description="Every dimension: research + analyst + builder.",
        commands=_RESEARCH | _ANALYST | _BUILDER,
    ),
    "research": Profile(
        name="research",
        label="Research / Strategy",
        description="Web research -> PDF / PPTX / Excel.",
        commands=_RESEARCH,
    ),
    "analyst": Profile(
        name="analyst",
        label="Analyst",
        description="Read & evaluate documents (e.g. score & rank CVs; first use: Recruiting).",
        commands=_ANALYST,
    ),
    "builder": Profile(
        name="builder",
        label="Builder",
        description="Build artifacts from documents (e.g. mgmt reporting; first use: Finance).",
        commands=_BUILDER,
    ),
}


def resolve_profile(name: str | None) -> Profile:
    """Resolve a profile name to a :class:`Profile`, falling back to ``all`` for unknown names."""
    key = (name or "all").strip().lower()
    return PROFILES.get(key, PROFILES["all"])


def active_profile_name() -> str:
    """Return the active profile name: PORTER_PROFILE env, else ./.porter_profile, else ``all``."""
    env = os.environ.get("PORTER_PROFILE")
    if env and env.strip():
        return env.strip().lower()
    try:
        text = _PROFILE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    return text.lower() or "all"


def active_profile() -> Profile:
    """Return the currently active :class:`Profile`."""
    return resolve_profile(active_profile_name())


def set_active_profile(name: str) -> Profile:
    """Persist the active profile to ``./.porter_profile`` (validates against known profiles)."""
    key = (name or "").strip().lower()
    if key not in PROFILES:
        raise ProfileError(f"Unknown profile '{name}'. Choose: {', '.join(PROFILES)}.")
    _PROFILE_FILE.write_text(key + "\n", encoding="utf-8")
    return PROFILES[key]


def command_enabled(profile: Profile, command: str) -> bool:
    """True if ``command`` is enabled under ``profile`` (utility commands are always enabled)."""
    return command in _ALWAYS or command in profile.commands
