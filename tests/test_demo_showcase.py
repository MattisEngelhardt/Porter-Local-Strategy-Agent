"""Tests for the best-demo showcase auto-promotion (``core.demo_showcase``).

Git operations are exercised against a non-git temp dir, so ``_git_publish`` always fails and is
swallowed fail-open — these tests assert the README / .gitignore / state-file swap behaviour and
the improvement gate, never the network.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.demo_showcase import _MARKER_END, _MARKER_START, maybe_promote_demo


def _seed_repo(
    root: Path, *, whitelist: str = "!output/old_deck.pptx", score: int | None = 70
) -> None:
    (root / "output").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        f"# Porter\n\n{_MARKER_START}\n> **old link**\n> {_MARKER_END}\n\nrest\n", encoding="utf-8"
    )
    (root / ".gitignore").write_text(f"output/*\n!output/.gitkeep\n{whitelist}\n", encoding="utf-8")
    if score is not None:
        (root / "output" / ".best_demo.json").write_text(
            json.dumps({"file": "old_deck.pptx", "score": score}), encoding="utf-8"
        )


def _deck(root: Path, name: str = "2026-06-10_new_deck.pptx") -> Path:
    path = root / "output" / name
    path.write_bytes(b"PK fake pptx")
    return path


def _promote(root: Path, deck: Path, score: int | None, **kw: object) -> list[str]:
    msgs: list[str] = []
    maybe_promote_demo(
        output_files=[deck],
        critique_score=score,
        title=kw.get("title", "New Deck"),  # type: ignore[arg-type]
        auto_promote=kw.get("auto_promote", True),  # type: ignore[arg-type]
        min_score=kw.get("min_score", 0),  # type: ignore[arg-type]
        repo_root=root,
        notify=msgs.append,
    )
    return msgs


def test_promotes_on_higher_score(tmp_path: Path) -> None:
    _seed_repo(tmp_path, score=70)
    deck = _deck(tmp_path)
    _promote(tmp_path, deck, 88)

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    state = json.loads((tmp_path / "output" / ".best_demo.json").read_text(encoding="utf-8"))

    assert "output/2026-06-10_new_deck.pptx" in readme
    assert "88/100" in readme
    assert "!output/2026-06-10_new_deck.pptx" in gitignore
    assert "!output/old_deck.pptx" not in gitignore  # the single pptx whitelist line is replaced
    assert state == {"file": "2026-06-10_new_deck.pptx", "score": 88, "title": "New Deck"}


def test_skips_when_not_an_improvement(tmp_path: Path) -> None:
    _seed_repo(tmp_path, score=70)
    deck = _deck(tmp_path)
    _promote(tmp_path, deck, 70)  # equal score is not an improvement

    assert "old link" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_skips_without_critique_score(tmp_path: Path) -> None:
    _seed_repo(tmp_path, score=70)
    deck = _deck(tmp_path)
    _promote(tmp_path, deck, None)

    assert "old link" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_respects_disabled_switch(tmp_path: Path) -> None:
    _seed_repo(tmp_path, score=10)
    deck = _deck(tmp_path)
    _promote(tmp_path, deck, 99, auto_promote=False)

    assert "old link" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_respects_min_score_floor(tmp_path: Path) -> None:
    _seed_repo(tmp_path, score=None)  # no prior baseline
    deck = _deck(tmp_path)
    _promote(tmp_path, deck, 50, min_score=80)  # below the floor

    assert "old link" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_ignores_deck_outside_repo(tmp_path: Path) -> None:
    """A deck rendered outside the repo (e.g. the test suite's tmp output) is left alone."""
    repo = tmp_path / "repo"
    _seed_repo(repo, score=10)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    deck = outside / "stray_deck.pptx"
    deck.write_bytes(b"PK")

    _promote(repo, deck, 95)

    assert "old link" in (repo / "README.md").read_text(encoding="utf-8")
    state = (repo / "output" / ".best_demo.json").read_text(encoding="utf-8")
    assert "stray" not in state


def test_first_promotion_without_baseline(tmp_path: Path) -> None:
    """With score=null baseline, the first qualifying run takes over."""
    _seed_repo(tmp_path, score=None)
    deck = _deck(tmp_path)
    _promote(tmp_path, deck, 60)

    assert "output/2026-06-10_new_deck.pptx" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_missing_markers_leaves_readme_untouched(tmp_path: Path) -> None:
    _seed_repo(tmp_path, score=10)
    (tmp_path / "README.md").write_text("# Porter\n\nno markers here\n", encoding="utf-8")
    deck = _deck(tmp_path)
    _promote(tmp_path, deck, 95)

    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# Porter\n\nno markers here\n"
