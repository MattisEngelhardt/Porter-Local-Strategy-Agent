"""Regenerate a saved deck's embedded font parts with the FIXED _embeddable_font_bytes,
so we can verify the Fraunces install fix without re-running the whole pipeline."""
import sys, zipfile
from lxml import etree
from core.font_embed import _embeddable_font_bytes, font_file_for

src, dst = sys.argv[1], sys.argv[2]
fonts_dir = "assets/fonts"
NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
with zipfile.ZipFile(src) as z:
    members = {n: z.read(n) for n in z.namelist()}
root = etree.fromstring(members["ppt/presentation.xml"])
families = [f.get("typeface") for f in root.iter("{%s}font" % NS)]
print("declared families:", families)
for i, fam in enumerate(families, 1):
    part = f"ppt/fonts/font{i}.fntdata"
    ttf = font_file_for(fam, fonts_dir)
    if ttf and part in members:
        members[part] = _embeddable_font_bytes(ttf, fam)
        print(f"  rewrote {part} for {fam!r} -> {len(members[part])/1024:.1f} KB")
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
    for n, d in members.items():
        out.writestr(n, d)
print("wrote", dst)
