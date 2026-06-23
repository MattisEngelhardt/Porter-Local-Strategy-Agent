"""Tests for in-session AI-model switching (core/model_switch.py).

The boot scripts are never actually run: ``_run_ps`` and ``load_config`` are mocked so the tests
assert the registry, active-model detection, and that a local switch invokes the proven scripts
(``switch-model.ps1`` then ``porter.local.ps1``) in the right order.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

import core.model_switch as model_switch
from core.config import AppConfig, LLMConfig
from core.model_switch import ModelSwitchError, active_model_value, apply_model, find_model


def _console() -> Console:
    return Console(file=io.StringIO(), width=100, force_terminal=False)


def test_registry_shows_real_names_and_served_ids() -> None:
    """The picker entries carry the real model names + the internal LM Studio identifiers."""
    e4b = find_model("gemma4-e4b")
    assert e4b is not None
    assert e4b.title == "Gemma 4 E4B" and e4b.served_id == "Porter-LMStudio"
    twelveb = find_model("GEMMA4-12B")  # case-insensitive
    assert twelveb is not None
    assert twelveb.title == "Gemma 4 12B" and twelveb.served_id == "Porter-12B"


def test_find_unknown_returns_none() -> None:
    assert find_model("does-not-exist") is None


def test_active_model_value_matches_served_id() -> None:
    assert active_model_value(LLMConfig(model="Porter-LMStudio")) == "gemma4-e4b"
    assert active_model_value(LLMConfig(model="Porter-12B")) == "gemma4-12b"
    assert active_model_value(LLMConfig(model="some-other-model")) is None


def test_apply_model_unknown_raises() -> None:
    with pytest.raises(ModelSwitchError):
        apply_model("nope", Path("config.yaml"), _console())


def test_apply_model_lmstudio_runs_scripts_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local switch writes config (quiet), cold-starts LM Studio (visible), then reloads."""
    calls: list[tuple[str, list[str], bool]] = []

    def _fake_run_ps(script: Path, args: list[str], *, quiet: bool) -> int:
        calls.append((script.name, args, quiet))
        return 0

    sentinel = AppConfig()
    monkeypatch.setattr(model_switch, "_run_ps", _fake_run_ps)
    monkeypatch.setattr(model_switch, "load_config", lambda _p: sentinel)
    monkeypatch.setattr(model_switch.Path, "is_file", lambda _self: True)  # pretend the hook exists

    result = apply_model("gemma4-12b", Path("config.yaml"), _console())

    assert result is sentinel
    assert [name for name, _args, _quiet in calls] == ["switch-model.ps1", "porter.local.ps1"]
    assert calls[0] == ("switch-model.ps1", ["porter12b"], True)  # config edit is quiet
    assert calls[1][2] is False  # boot progress is visible


def test_apply_model_skips_hook_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no porter.local.ps1 (fresh clone), only the config edit runs — no crash."""
    calls: list[str] = []
    monkeypatch.setattr(
        model_switch,
        "_run_ps",
        lambda script, _args, *, quiet: calls.append(script.name) or 0,
    )
    monkeypatch.setattr(model_switch, "load_config", lambda _p: AppConfig())
    monkeypatch.setattr(model_switch.Path, "is_file", lambda _self: False)

    apply_model("gemma4-e4b", Path("config.yaml"), _console())
    assert calls == ["switch-model.ps1"]  # boot hook skipped
