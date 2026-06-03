"""Install the four Porter Editorial OFL fonts into ``assets/fonts`` (REQ-1/2: local, free, OFL).

Porter's PDF brief embeds and the PPTX deck names a four-family type system (``core.design``):

* **Fraunces**       — serif display headlines (PDF)
* **Space Grotesk**  — grotesk display (deck headlines / brief accents)
* **Inter**          — body text
* **Space Mono**     — tracked micro-labels / telemetry

All four are SIL Open Font License fonts from Google Fonts. This script fetches each TTF (and its
OFL licence) into ``assets/fonts`` with a clean filename so ``core.exporter._font_face_css`` matches
it by the family's normalised name (``Fraunces*.ttf`` → family "Fraunces", etc.) and auto-embeds it
in the PDF. **Fully optional:** if the directory is absent the renderers degrade to the system-font
fallbacks (Georgia / Aptos / Consolas) — output is never broken, just less branded (REQ-5).

Usage (from the repo root, inside the venv)::

    .venv\\Scripts\\python scripts\\install_fonts.py
    .venv\\Scripts\\python scripts\\install_fonts.py --insecure   # corporate cert-revocation box
    .venv\\Scripts\\python scripts\\install_fonts.py --force      # re-download even if present

Stdlib only (urllib) — no new dependency, in keeping with the locked "zero new code deps" decision.
"""

from __future__ import annotations

import argparse
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Google Fonts raw repo root (the canonical OFL source for all four families).
_GF_RAW = "https://raw.githubusercontent.com/google/fonts/main/ofl"


@dataclass(frozen=True)
class _Font:
    """One OFL family to install: its Google Fonts dir, the source TTF, and a clean dest name."""

    family: str
    gf_dir: str  # subfolder under ofl/
    src_file: str  # the file in the repo (URL-encoded for [ ] , in variable-font names)
    dest_name: str  # clean local filename so ``_font_face_css`` matches the family


# Variable fonts cover the full weight range Porter uses (font-weight: 100 900 in the @font-face).
_FONTS: tuple[_Font, ...] = (
    _Font("Fraunces", "fraunces", "Fraunces%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf", "Fraunces.ttf"),
    _Font("Space Grotesk", "spacegrotesk", "SpaceGrotesk%5Bwght%5D.ttf", "SpaceGrotesk.ttf"),
    _Font("Inter", "inter", "Inter%5Bopsz%2Cwght%5D.ttf", "Inter.ttf"),
    _Font("Space Mono", "spacemono", "SpaceMono-Regular.ttf", "SpaceMono.ttf"),
)

_DEFAULT_DEST = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _download(url: str, dest: Path, *, context: ssl.SSLContext | None) -> int:
    """Download ``url`` to ``dest`` and return the byte count (raises on failure)."""
    request = urllib.request.Request(url, headers={"User-Agent": "porter-install-fonts"})
    with urllib.request.urlopen(request, context=context, timeout=60) as response:  # noqa: S310
        data: bytes = response.read()
    dest.write_bytes(data)
    return len(data)


def _fetch(font: _Font, dest_dir: Path, *, context: ssl.SSLContext | None, force: bool) -> bool:
    """Fetch one font TTF + its OFL licence into ``dest_dir``. Returns True on success."""
    ttf_path = dest_dir / font.dest_name
    if ttf_path.is_file() and not force:
        print(f"  [ok]   {font.family:<14} already present ({ttf_path.name})")
        return True
    ttf_url = f"{_GF_RAW}/{font.gf_dir}/{font.src_file}"
    try:
        size = _download(ttf_url, ttf_path, context=context)
    except (urllib.error.URLError, OSError) as exc:
        print(f"  [FAIL] {font.family:<14} {exc}")
        return False
    # Best-effort: vendor the licence alongside the font (OFL distribution courtesy; never fatal).
    try:
        _download(
            f"{_GF_RAW}/{font.gf_dir}/OFL.txt",
            dest_dir / f"{font.dest_name.removesuffix('.ttf')}-OFL.txt",
            context=context,
        )
    except (urllib.error.URLError, OSError):
        pass
    print(f"  [ok]   {font.family:<14} -> {ttf_path.name} ({size // 1024} KB)")
    return True


def main(argv: list[str] | None = None) -> int:
    """Install the four Editorial OFL fonts; return 0 when all four are present, else 1."""
    parser = argparse.ArgumentParser(description="Install Porter Editorial OFL fonts.")
    parser.add_argument(
        "--dest", type=Path, default=_DEFAULT_DEST, help="Target dir (default: assets/fonts)."
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if a file exists.")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification (only for corporate cert-revocation boxes).",
    )
    args = parser.parse_args(argv)

    dest_dir: Path = args.dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    context = ssl._create_unverified_context() if args.insecure else None  # noqa: SLF001

    print(f"Installing Porter Editorial OFL fonts into {dest_dir} ...")
    results = [_fetch(font, dest_dir, context=context, force=args.force) for font in _FONTS]

    ok = sum(results)
    print(f"\n{ok}/{len(_FONTS)} fonts installed.")
    if ok < len(_FONTS):
        print(
            "Some downloads failed (network/proxy?). The renderers fall back to system fonts, so "
            "output still works — re-run later (try --insecure behind a corporate proxy)."
        )
        return 1
    print("Done - the PDF brief will now embed the branded fonts; PowerPoint uses them by name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
