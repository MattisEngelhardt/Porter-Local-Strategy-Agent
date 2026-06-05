import sys, zipfile, io
from fontTools.ttLib import TTFont

path = sys.argv[1]
z = zipfile.ZipFile(path)
for n in sorted(x for x in z.namelist() if x.startswith('ppt/fonts/')):
    f = TTFont(io.BytesIO(z.read(n)))
    fam = f['name'].getDebugName(1) if 'name' in f else '?'
    fstype = f['OS/2'].fsType if 'OS/2' in f else 'NO OS/2'
    psname = f['name'].getDebugName(6) if 'name' in f else '?'
    full = f['name'].getDebugName(4) if 'name' in f else '?'
    tables = ",".join(sorted(f.reader.tables.keys()))
    macStyle = f['head'].macStyle if 'head' in f else '?'
    fsSel = f['OS/2'].fsSelection if 'OS/2' in f else '?'
    print(f"{n}")
    print(f"   family={fam!r} full={full!r} psname={psname!r}")
    print(f"   fsType={fstype} (0=installable) | macStyle={macStyle} | fsSelection={fsSel}")
    print(f"   tables: {tables}")
