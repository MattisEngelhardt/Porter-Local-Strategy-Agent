import sys, zipfile, io
from lxml import etree

path = sys.argv[1]
z = zipfile.ZipFile(path)
NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
root = etree.fromstring(z.read('ppt/presentation.xml'))
print("embedTrueTypeFonts:", root.get("embedTrueTypeFonts"), "| saveSubsetFonts:", root.get("saveSubsetFonts"))
typefaces = [f.get("typeface") for f in root.iter('{%s}font' % NS)]
print("Embedded families (presentation.xml):", typefaces)

try:
    from fontTools.ttLib import TTFont
    import fontTools
    print("fontTools:", fontTools.version)
    ft = True
except Exception as e:
    ft = False
    print("fontTools NOT available ->", repr(e), "  (=> instancing fails open, raw variable font embedded)")

for n in sorted(x for x in z.namelist() if x.startswith('ppt/fonts/')):
    data = z.read(n)
    line = f"  {n} ({len(data)/1024:.1f} KB)"
    if ft:
        try:
            f = TTFont(io.BytesIO(data))
            fam = f['name'].getDebugName(1) if 'name' in f else '?'
            line += f"  family={fam!r}  fvar={'YES=VARIABLE(bad)' if 'fvar' in f else 'no=static(ok)'}  sfnt={f.sfntVersion!r}"
        except Exception as e:
            line += f"  LOAD-ERR {e!r}"
    print(line)

# Also test: can fontTools instance the shipped Fraunces.ttf to static here & now?
print("\n-- live instancing test on assets/fonts/Fraunces.ttf --")
try:
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    f = TTFont("assets/fonts/Fraunces.ttf")
    print("  has fvar:", 'fvar' in f, "| axes:", [a.axisTag for a in f['fvar'].axes] if 'fvar' in f else [])
    limits = {}
    for a in f['fvar'].axes:
        limits[a.axisTag] = 400.0 if (a.axisTag == 'wght' and a.minValue <= 400 <= a.maxValue) else a.defaultValue
    instantiateVariableFont(f, limits, inplace=True)
    print("  after instancing: fvar present?", 'fvar' in f, "| sfnt:", f.sfntVersion)
except Exception as e:
    print("  INSTANCING ERROR:", repr(e))
