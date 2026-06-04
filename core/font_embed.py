"""Embed the deck's OFL TTFs into a saved ``.pptx`` so it renders with its fonts anywhere.

python-pptx cannot embed fonts, so this post-processes the saved package at the OOXML level: each
used family's TTF is added as ``ppt/fonts/fontN.fntdata``, wired via a relationship + a
``<p:embeddedFont>`` entry, the presentation is flagged ``embedTrueTypeFonts``, and the ``fntdata``
content-type default is registered. Without this the board would see Calibri when the deck is
forwarded (the fonts are not installed on their machine) — exactly the "one font everywhere"
complaint, in transit.

Pure file I/O + XML via lxml (which preserves the original namespace prefixes, so the round-trip
never mangles ``mc:Ignorable`` and friends). **Fail-open** (returns ``False`` and leaves the
original deck byte-for-byte untouched) so an embedding quirk never loses a render (REQ-5).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

# OOXML namespaces (constants — never hardcoded prefixes, only URIs).
_NS_PRESENTATION = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_FONT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
_FONT_CONTENT_TYPE = "application/x-fontdata"

_CONTENT_TYPES_PART = "[Content_Types].xml"
_PRESENTATION_PART = "ppt/presentation.xml"
_PRESENTATION_RELS_PART = "ppt/_rels/presentation.xml.rels"

# CT_Presentation children that may follow <p:embeddedFontLst>; we insert it just before the first
# of these that exists (schema order), else right after <p:notesSz>/<p:sldSz>.
_AFTER_FONT_LST = ("custShowLst", "photoAlbum", "custDataLst", "kinsoku", "defaultTextStyle")


def font_file_for(family: str, fonts_dir: str | Path) -> Path | None:
    """Resolve a family name to its shipped TTF (``Space Grotesk`` → ``SpaceGrotesk.ttf``)."""
    candidate = Path(fonts_dir) / f"{family.replace(' ', '')}.ttf"
    return candidate if candidate.is_file() else None


def _q(namespace: str, tag: str) -> str:
    """Clark-notation qualified name ``{ns}tag``."""
    return f"{{{namespace}}}{tag}"


def _ensure_fntdata_content_type(raw: bytes) -> bytes:
    """Add the ``fntdata`` default content type if absent (idempotent)."""
    root = etree.fromstring(raw)
    default = _q(_NS_CONTENT_TYPES, "Default")
    for node in root.findall(default):
        if str(node.get("Extension", "")).lower() == "fntdata":
            return raw
    node = etree.SubElement(root, default)
    node.set("Extension", "fntdata")
    node.set("ContentType", _FONT_CONTENT_TYPE)
    return bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))


def _add_font_relationships(raw: bytes, count: int) -> tuple[bytes, list[str]]:
    """Append ``count`` font relationships; return the patched rels XML + the new relation ids."""
    root = etree.fromstring(raw)
    used = {str(rel.get("Id")) for rel in root}
    ids: list[str] = []
    for index in range(1, count + 1):
        rid = f"rIdEmbeddedFont{index}"
        while rid in used:
            rid += "x"
        used.add(rid)
        ids.append(rid)
        rel = etree.SubElement(root, _q(_NS_PKG_REL, "Relationship"))
        rel.set("Id", rid)
        rel.set("Type", _FONT_REL_TYPE)
        rel.set("Target", f"fonts/font{index}.fntdata")
    patched = bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))
    return patched, ids


def _add_embedded_font_list(raw: bytes, families: list[str], rel_ids: list[str]) -> bytes:
    """Flag the presentation for embedding and insert ``<p:embeddedFontLst>`` in schema position."""
    root = etree.fromstring(raw)
    root.set("embedTrueTypeFonts", "1")
    root.set("saveSubsetFonts", "0")

    font_lst = etree.SubElement(root, _q(_NS_PRESENTATION, "embeddedFontLst"))
    for family, rid in zip(families, rel_ids, strict=True):
        embedded = etree.SubElement(font_lst, _q(_NS_PRESENTATION, "embeddedFont"))
        font = etree.SubElement(embedded, _q(_NS_PRESENTATION, "font"))
        font.set("typeface", family)
        regular = etree.SubElement(embedded, _q(_NS_PRESENTATION, "regular"))
        regular.set(_q(_NS_REL, "id"), rid)

    # Move it into the correct child position (SubElement appended it to the end).
    after_tags = {_q(_NS_PRESENTATION, tag) for tag in _AFTER_FONT_LST}
    anchor_next = next((child for child in root if child.tag in after_tags), None)
    if anchor_next is not None:
        anchor_next.addprevious(font_lst)
    else:
        anchor_prev = root.find(_q(_NS_PRESENTATION, "notesSz"))
        if anchor_prev is None:
            anchor_prev = root.find(_q(_NS_PRESENTATION, "sldSz"))
        if anchor_prev is not None:
            anchor_prev.addnext(font_lst)
    return bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))


def embed_fonts(pptx_path: str | Path, families: list[str], fonts_dir: str | Path) -> bool:
    """Embed each resolvable family's TTF into the saved ``.pptx``; return ``True`` on success.

    Deduplicates families, skips any without a shipped TTF, and no-ops (returns ``False``) when none
    resolve. Any failure leaves the original deck untouched (fail-open, REQ-5).
    """
    path = Path(pptx_path)
    resolved: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for family in families:
        if not family or family in seen:
            continue
        ttf = font_file_for(family, fonts_dir)
        if ttf is not None:
            resolved.append((family, ttf))
            seen.add(family)
    if not resolved:
        return False

    tmp = path.with_name(path.name + ".embed.tmp")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        if not {_CONTENT_TYPES_PART, _PRESENTATION_PART, _PRESENTATION_RELS_PART} <= members.keys():
            return False

        members[_CONTENT_TYPES_PART] = _ensure_fntdata_content_type(members[_CONTENT_TYPES_PART])
        members[_PRESENTATION_RELS_PART], rel_ids = _add_font_relationships(
            members[_PRESENTATION_RELS_PART], len(resolved)
        )
        members[_PRESENTATION_PART] = _add_embedded_font_list(
            members[_PRESENTATION_PART], [family for family, _ in resolved], rel_ids
        )
        for index, (_, ttf) in enumerate(resolved, start=1):
            members[f"ppt/fonts/font{index}.fntdata"] = ttf.read_bytes()

        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for name, data in members.items():
                out.writestr(name, data)
        tmp.replace(path)
        return True
    except (OSError, etree.XMLSyntaxError, ValueError):
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False
