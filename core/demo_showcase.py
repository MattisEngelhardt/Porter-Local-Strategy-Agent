"""Auto-promote the best demo output to the top of the README.

Porter runs are test/demo runs, so the project README showcases one deck at the top under
"🎯 Best demo output". After any run that renders a PPTX deck, :func:`maybe_promote_demo`
compares that run's **output-critic score** (0..100) against the currently published demo's
score. Only on a genuine improvement (strictly higher score, and at least ``demo_min_score``)
does it swap the README link, update the ``.gitignore`` whitelist, record the new baseline, and
commit + push — so GitHub always shows the best demo so far.

Everything here is **fail-open**: any error (no git, no network, parse failure, missing markers)
is swallowed via ``notify`` and never breaks the user's run. Only the PPTX showcase link is
managed; the PDF/XLSX/MD sample links in the README are left untouched.

The baseline lives in ``output/.best_demo.json`` (tracked in git so it persists across clones).
Previously published decks stay tracked in the repo — only the README's top link is swapped — so
the showcase always points at the single best deck without deleting history.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

_MARKER_START = "<!-- BEST_DEMO_PPTX:START -->"
_MARKER_END = "<!-- BEST_DEMO_PPTX:END -->"
_STATE_FILENAME = ".best_demo.json"
_GIT_TIMEOUT = 60  # seconds — never hang a run on a slow remote

# Matches a single `!output/<something>.pptx` whitelist line in .gitignore (the demo deck).
_PPTX_WHITELIST = re.compile(r"^!output/.*\.pptx\s*$", re.MULTILINE)


def maybe_promote_demo(
    *,
    output_files: list[Path],
    critique_score: int | None,
    title: str,
    auto_promote: bool,
    min_score: int,
    repo_root: Path | None = None,
    notify: Callable[[str], None] | None = None,
) -> None:
    """Swap the README "best demo" deck if this run's critic score beats the published one.

    Args:
        output_files: This run's rendered deliverables; the newest ``.pptx`` is the candidate.
        critique_score: The run's output-critic score (0..100), or ``None`` if critique was off
            (then we cannot judge improvement and skip).
        title: Human-readable analysis title, used for the README link text.
        auto_promote: ``config.output.auto_promote_demo`` — master switch.
        min_score: ``config.output.demo_min_score`` — promotion floor.
        repo_root: Repository root (defaults to the current working directory — porter runs from
            the project root).
        notify: Optional sink for a short status line (e.g. ``interaction.notify``).
    """
    say = notify or (lambda _msg: None)
    try:
        if not auto_promote or critique_score is None or critique_score < min_score:
            return

        deck = _latest_pptx(output_files)
        if deck is None:
            return

        root = (repo_root or Path.cwd()).resolve()
        # Only manage decks that physically live inside this repo's working tree. Test runs render
        # to a throwaway tmp dir outside the repo, so this guard keeps the suite (and any ad-hoc
        # run with a custom output dir) from ever touching the tracked README / .gitignore / git.
        try:
            rel = deck.resolve().relative_to(root).as_posix()
        except ValueError:
            return

        state_path = root / "output" / _STATE_FILENAME
        prev_score = _read_prev_score(state_path)
        if prev_score is not None and critique_score <= prev_score:
            return  # not an improvement — leave the published demo in place

        readme = root / "README.md"
        gitignore = root / ".gitignore"
        if not readme.exists() or not gitignore.exists():
            return

        if not _swap_readme_link(readme, rel, title, critique_score):
            return  # markers missing — don't touch a README we can't edit safely
        _swap_gitignore_whitelist(gitignore, rel)
        _write_state(state_path, deck.name, critique_score, title)

        _git_publish(root, rel, deck.name, critique_score, say)
    except Exception as exc:  # fail-open: a showcase update must never break a run
        say(f"Best-demo update skipped: {exc}")


def _latest_pptx(output_files: list[Path]) -> Path | None:
    """Return the most recently modified ``.pptx`` among this run's outputs (None if none)."""
    decks = [p for p in output_files if p.suffix.lower() == ".pptx" and p.exists()]
    if not decks:
        return None
    return max(decks, key=lambda p: p.stat().st_mtime)


def _read_prev_score(state_path: Path) -> int | None:
    """Read the published demo's stored critic score (None if absent/unreadable)."""
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        score = data.get("score")
        return int(score) if score is not None else None
    except (OSError, ValueError, AttributeError, json.JSONDecodeError):
        return None


def _swap_readme_link(readme: Path, rel_path: str, title: str, score: int) -> bool:
    """Replace the content between the BEST_DEMO markers. Returns False if markers are missing."""
    text = readme.read_text(encoding="utf-8")
    start = text.find(_MARKER_START)
    end = text.find(_MARKER_END)
    if start == -1 or end == -1 or end < start:
        return False

    link_text = f"{title.strip()} (PPTX)" if title.strip() else "Latest strategy deck (PPTX)"
    block = (
        f"{_MARKER_START} (auto-updated — do not edit by hand)\n"
        f"> **▶ [{link_text}]({rel_path})**\n"
        f"> — our latest and best end-to-end run (output-critic score {score}/100). "
        f"Click to download/view.\n"
        f"> {_MARKER_END}"
    )
    new_text = text[:start] + block + text[end + len(_MARKER_END) :]
    readme.write_text(new_text, encoding="utf-8")
    return True


def _swap_gitignore_whitelist(gitignore: Path, rel_path: str) -> None:
    """Point the single ``!output/*.pptx`` whitelist line at the new deck (append if absent)."""
    text = gitignore.read_text(encoding="utf-8")
    new_line = f"!{rel_path}"
    if _PPTX_WHITELIST.search(text):
        text = _PPTX_WHITELIST.sub(new_line, text, count=1)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"
    gitignore.write_text(text, encoding="utf-8")


def _write_state(state_path: Path, filename: str, score: int, title: str) -> None:
    """Persist the new baseline (tracked in git so it survives clones)."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"file": filename, "score": score, "title": title}, indent=2) + "\n",
        encoding="utf-8",
    )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
        check=True,
    )


def _git_publish(
    root: Path, deck_rel: str, deck_name: str, score: int, say: Callable[[str], None]
) -> None:
    """Commit exactly the showcase paths and push. Fail-open with a status line."""
    paths = ["README.md", ".gitignore", deck_rel, f"output/{_STATE_FILENAME}"]
    try:
        # Stage and commit only our four paths (pathspec) so no unrelated staged work is swept in.
        _git(root, "add", "--", *paths)
        message = (
            f"chore(demo): showcase best deck (critic {score}/100)\n\n"
            f"Auto-promoted {deck_name} — it beat the previously published demo's critic score. "
            f"Generated by Porter; demo/test data only.\n\n"
            f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
        )
        _git(root, "commit", "-m", message, "--", *paths)
    except subprocess.CalledProcessError as exc:
        say(f"Best-demo commit skipped: {(exc.stderr or exc.stdout or '').strip()[:200]}")
        return
    except (OSError, subprocess.TimeoutExpired) as exc:
        say(f"Best-demo commit skipped: {exc}")
        return

    try:
        _git(root, "push")
        say(f"Published new best demo to GitHub: {deck_name} (critic {score}/100).")
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as exc:
        detail = str(getattr(exc, "stderr", None) or exc).strip()[:200]
        say(f"Best demo committed locally (push failed — push manually): {detail}")
