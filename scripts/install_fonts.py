"""Install Porter's curated OFL font library into ``assets/fonts`` (REQ-1/2: local, free, OFL).

Porter's type system (``core.typography``) draws from a pool of 25+ SIL Open Font License
families on Google Fonts, grouped by role (serif display / grotesk / expressive display / mono)
and paired into type-themes. This script fetches each family's TTF (and its OFL licence) into
``assets/fonts`` with a clean filename so ``core.exporter._font_face_css`` matches it by name
(``PlayfairDisplay.ttf`` → family "Playfair Display") and auto-embeds it in the PDF. The PPTX deck
references families by name (PowerPoint substitutes if a family is not installed system-wide).

To pick the right file resiliently, the script **lists each family's ``ofl/<dir>`` directory via the
GitHub contents API** and chooses the best TTF (a variable ``[wght]`` face, else ``*-Regular.ttf``),
so it does not break when Google Fonts renames a variable-font file.

**Fully optional:** if the directory is absent the renderers degrade to system-font fallbacks
(Georgia / Aptos / Consolas) — output is never broken, just less branded (REQ-5).

Usage (from the repo root, inside the venv)::

    .venv\\Scripts\\python scripts\\install_fonts.py
    .venv\\Scripts\\python scripts\\install_fonts.py --insecure   # corporate cert-revocation box
    .venv\\Scripts\\python scripts\\install_fonts.py --force      # re-download even if present

Stdlib only (urllib + json) — no new dependency.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# GitHub contents API (directory listing) + raw repo root.
_GH_API = "https://api.github.com/repos/google/fonts/contents/ofl"


@dataclass(frozen=True)
class _Font:
    """One OFL family to install: its ``ofl/<dir>`` folder and a clean local filename."""

    family: str
    gf_dir: str  # subfolder under ofl/ (lowercase, no spaces — Google Fonts convention)
    dest_name: str  # clean local filename so ``_font_face_css`` matches the family


# The curated >=20-family library (kept in step with ``core.typography.FONT_LIBRARY``).
_FONTS: tuple[_Font, ...] = (
    # Serif display
    _Font("Fraunces", "fraunces", "Fraunces.ttf"),
    _Font("Playfair Display", "playfairdisplay", "PlayfairDisplay.ttf"),
    _Font("DM Serif Display", "dmserifdisplay", "DMSerifDisplay.ttf"),
    _Font("Bodoni Moda", "bodonimoda", "BodoniModa.ttf"),
    _Font("Cormorant Garamond", "cormorantgaramond", "CormorantGaramond.ttf"),
    _Font("Spectral", "spectral", "Spectral.ttf"),
    _Font("Newsreader", "newsreader", "Newsreader.ttf"),
    _Font("Instrument Serif", "instrumentserif", "InstrumentSerif.ttf"),
    # Grotesk / sans
    _Font("Space Grotesk", "spacegrotesk", "SpaceGrotesk.ttf"),
    _Font("Inter", "inter", "Inter.ttf"),
    _Font("Archivo", "archivo", "Archivo.ttf"),
    _Font("Manrope", "manrope", "Manrope.ttf"),
    _Font("Sora", "sora", "Sora.ttf"),
    _Font("Schibsted Grotesk", "schibstedgrotesk", "SchibstedGrotesk.ttf"),
    _Font("Hanken Grotesk", "hankengrotesk", "HankenGrotesk.ttf"),
    # Expressive display
    _Font("Archivo Black", "archivoblack", "ArchivoBlack.ttf"),
    _Font("Anton", "anton", "Anton.ttf"),
    _Font("Bebas Neue", "bebasneue", "BebasNeue.ttf"),
    _Font("Syne", "syne", "Syne.ttf"),
    _Font("Unbounded", "unbounded", "Unbounded.ttf"),
    _Font("Big Shoulders Display", "bigshouldersdisplay", "BigShouldersDisplay.ttf"),
    # Mono
    _Font("Space Mono", "spacemono", "SpaceMono.ttf"),
    _Font("JetBrains Mono", "jetbrainsmono", "JetBrainsMono.ttf"),
    _Font("IBM Plex Mono", "ibmplexmono", "IBMPlexMono.ttf"),
    _Font("DM Mono", "dmmono", "DMMono.ttf"),
)

_DEFAULT_DEST = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _get(url: str, *, context: ssl.SSLContext | None) -> bytes:
    """HTTP GET ``url`` and return the body (raises on failure)."""
    request = urllib.request.Request(url, headers={"User-Agent": "porter-install-fonts"})
    with urllib.request.urlopen(request, context=context, timeout=60) as response:  # noqa: S310
        body: bytes = response.read()
    return body


def _pick_ttf(entries: list[dict[str, object]]) -> dict[str, object] | None:
    """Choose the best TTF from a GitHub directory listing (variable ``[wght]`` → ``*-Regular``)."""
    ttfs = [e for e in entries if str(e.get("name", "")).lower().endswith(".ttf")]
    if not ttfs:
        return None

    def score(entry: dict[str, object]) -> tuple[int, int]:
        name = str(entry.get("name", ""))
        lower = name.lower()
        if "[wght" in lower or "wght]" in lower:
            rank = 0  # variable font carrying a weight axis — full range, preferred
        elif "[" in name:
            rank = 1  # other variable font
        elif lower.endswith("-regular.ttf"):
            rank = 2
        else:
            rank = 3
        return (rank, len(name))

    return sorted(ttfs, key=score)[0]


def _fetch(font: _Font, dest_dir: Path, *, context: ssl.SSLContext | None, force: bool) -> bool:
    """Fetch one family's best TTF + its OFL licence into ``dest_dir``. Returns True on success."""
    ttf_path = dest_dir / font.dest_name
    if ttf_path.is_file() and not force:
        print(f"  [ok]   {font.family:<22} already present ({ttf_path.name})")
        return True
    try:
        listing_raw = _get(f"{_GH_API}/{font.gf_dir}", context=context)
        entries: list[dict[str, object]] = json.loads(listing_raw)
        best = _pick_ttf(entries)
        if best is None:
            print(f"  [FAIL] {font.family:<22} no .ttf found in ofl/{font.gf_dir}")
            return False
        ttf_path.write_bytes(_get(str(best["download_url"]), context=context))
        size = ttf_path.stat().st_size
        # Best-effort: vendor the licence alongside the font (never fatal).
        licence = next((e for e in entries if str(e.get("name", "")).upper() == "OFL.TXT"), None)
        if licence is not None:
            try:
                (dest_dir / f"{font.dest_name.removesuffix('.ttf')}-OFL.txt").write_bytes(
                    _get(str(licence["download_url"]), context=context)
                )
            except (urllib.error.URLError, OSError):
                pass
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"  [FAIL] {font.family:<22} {exc}")
        return False
    print(f"  [ok]   {font.family:<22} -> {ttf_path.name} ({size // 1024} KB)")
    return True


def register_windows_fonts(dest_dir: Path) -> int:
    """Install the downloaded TTFs for the current Windows user so PowerPoint actually renders them.

    The TTFs only sitting in ``assets/fonts`` are invisible to PowerPoint — it substitutes Calibri,
    which is the real "one font everywhere" bug. This copies each face into the per-user Fonts
    directory (no admin needed since Win10 1809), registers it under ``HKCU\\…\\Fonts``, loads it
    into the session via ``AddFontResourceW``, and broadcasts ``WM_FONTCHANGE`` so running apps pick
    it up. Idempotent + fail-open; a non-Windows host is a clean no-op. Returns how many registered.
    """
    if sys.platform != "win32":
        print("  --register is Windows-only; skipped (the PDF embeds fonts regardless).")
        return 0
    import ctypes  # local: Windows-only GDI/user32 calls
    import winreg

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        print("  [FAIL] LOCALAPPDATA is unset — cannot locate the per-user Fonts directory.")
        return 0
    user_fonts = Path(local_app_data) / "Microsoft" / "Windows" / "Fonts"
    user_fonts.mkdir(parents=True, exist_ok=True)
    reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"

    registered = 0
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
        for font in _FONTS:
            src = dest_dir / font.dest_name
            if not src.is_file():
                continue
            target = user_fonts / font.dest_name
            try:
                if not target.is_file():
                    shutil.copy2(src, target)
                ctypes.windll.gdi32.AddFontResourceW(str(target))  # type: ignore[attr-defined]
                winreg.SetValueEx(
                    key, f"{font.family} (TrueType)", 0, winreg.REG_SZ, str(target)
                )
                registered += 1
            except OSError as exc:
                print(f"  [warn] {font.family:<22} {exc}")

    # Notify running applications that the font set changed (HWND_BROADCAST, WM_FONTCHANGE).
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0, 1000, None)  # type: ignore[attr-defined]
    print(f"  registered {registered}/{len(_FONTS)} fonts for the current user.")
    return registered


def main(argv: list[str] | None = None) -> int:
    """Install the curated OFL font library; return 0 when all families are present, else 1."""
    parser = argparse.ArgumentParser(description="Install Porter's curated OFL font library.")
    parser.add_argument(
        "--dest", type=Path, default=_DEFAULT_DEST, help="Target dir (default: assets/fonts)."
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if a file exists.")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification (only for corporate cert-revocation boxes).",
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="After download, install the TTFs for the current Windows user so PowerPoint renders "
        "them (the deck always embeds its fonts regardless).",
    )
    args = parser.parse_args(argv)

    dest_dir: Path = args.dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    context = ssl._create_unverified_context() if args.insecure else None  # noqa: SLF001

    print(f"Installing Porter's OFL font library ({len(_FONTS)} families) into {dest_dir} ...")
    results = [_fetch(font, dest_dir, context=context, force=args.force) for font in _FONTS]

    ok = sum(results)
    print(f"\n{ok}/{len(_FONTS)} fonts installed.")
    if args.register:
        print("Registering fonts with the OS ...")
        register_windows_fonts(dest_dir)
    if ok < len(_FONTS):
        print(
            "Some downloads failed (network/proxy/rate-limit?). The renderers fall back to system "
            "fonts, so output still works — re-run later (try --insecure behind a corporate proxy)."
        )
        return 1
    print("Done — the PDF embeds the fonts; the deck embeds + (with --register) installs them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
