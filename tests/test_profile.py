"""Tests for dimension profiles (Block B) — core/profile.py.

Dimensions are named by *function* (analyst / builder), not by department (Recruiting / Finance),
since the departments may or may not adopt them. Pure unit tests: resolution, per-profile command
gating, active-profile resolution (env > file > default), and persistence. No CLI, no LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import core.profile as profile_mod
from core.profile import (
    PROFILES,
    ProfileError,
    active_profile_name,
    command_enabled,
    resolve_profile,
    set_active_profile,
)


def test_resolve_known_and_unknown() -> None:
    assert resolve_profile("analyst").name == "analyst"
    assert resolve_profile("BUILDER").name == "builder"
    assert resolve_profile(None).name == "all"
    assert resolve_profile("does-not-exist").name == "all"  # safe fallback


def test_profile_names_are_function_not_department() -> None:
    assert set(PROFILES) == {"all", "research", "analyst", "builder"}
    assert "recruiting" not in PROFILES
    assert "finance" not in PROFILES


def test_all_profile_enables_every_command() -> None:
    allrounder = PROFILES["all"]
    for command in ["research", "analyze", "prepare", "score-cvs", "build-report", "ask"]:
        assert command_enabled(allrounder, command)


def test_analyst_profile_gating() -> None:
    analyst = PROFILES["analyst"]
    assert command_enabled(analyst, "score-cvs")
    assert command_enabled(analyst, "ask")  # utility always on
    assert command_enabled(analyst, "analyze-doc")
    assert not command_enabled(analyst, "build-report")
    assert not command_enabled(analyst, "analyze")


def test_builder_profile_gating() -> None:
    builder = PROFILES["builder"]
    assert command_enabled(builder, "build-report")
    assert not command_enabled(builder, "score-cvs")
    assert not command_enabled(builder, "research")


def test_active_profile_env_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTER_PROFILE", "builder")
    assert active_profile_name() == "builder"


def test_active_profile_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PORTER_PROFILE", raising=False)
    profile_file = tmp_path / ".porter_profile"
    profile_file.write_text("analyst\n", encoding="utf-8")
    monkeypatch.setattr(profile_mod, "_PROFILE_FILE", profile_file)
    assert active_profile_name() == "analyst"


def test_active_profile_defaults_to_all(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PORTER_PROFILE", raising=False)
    monkeypatch.setattr(profile_mod, "_PROFILE_FILE", tmp_path / "missing")
    assert active_profile_name() == "all"


def test_set_active_profile_persists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    profile_file = tmp_path / ".porter_profile"
    monkeypatch.setattr(profile_mod, "_PROFILE_FILE", profile_file)
    monkeypatch.delenv("PORTER_PROFILE", raising=False)
    result = set_active_profile("Analyst")
    assert result.name == "analyst"
    assert profile_file.read_text(encoding="utf-8").strip() == "analyst"
    assert active_profile_name() == "analyst"


def test_set_active_profile_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(profile_mod, "_PROFILE_FILE", tmp_path / ".porter_profile")
    with pytest.raises(ProfileError):
        set_active_profile("bogus")
