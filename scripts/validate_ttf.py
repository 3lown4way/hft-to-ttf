#!/usr/bin/env python3
from pathlib import Path
import argparse
from fontTools.ttLib import TTFont

p = argparse.ArgumentParser()
p.add_argument('output_dir')
a = p.parse_args()
root = Path(a.output_dir)
fonts = sorted(x for x in root.rglob('*') if x.is_file() and x.suffix.lower() == '.ttf')
if not fonts:
    raise SystemExit('No TTF files were generated.')

failed = []
postscript_names = {}
for path in fonts:
    try:
        f = TTFont(path, lazy=False)
        required = {'head', 'hhea', 'maxp', 'cmap', 'name', 'OS/2'}
        missing = required.difference(f.keys())
        if missing:
            raise ValueError('missing tables: ' + ', '.join(sorted(missing)))
        glyphs = len(f.getGlyphOrder())
        if glyphs < 2:
            raise ValueError(f'too few glyphs: {glyphs}')
        best_cmap = f.getBestCmap() or {}
        if not best_cmap:
            raise ValueError('empty Unicode cmap')
        fs_type = int(f['OS/2'].fsType)
        if fs_type != 0:
            raise ValueError(f'unexpected OS/2.fsType=0x{fs_type:04X}; expected 0x0000')

        ps_values = sorted({n.toUnicode() for n in f['name'].names if n.nameID == 6})
        if len(ps_values) != 1:
            raise ValueError(f'expected one PostScript name, found {ps_values!r}')
        ps_name = ps_values[0]
        try:
            ps_bytes = ps_name.encode('ascii')
        except UnicodeEncodeError:
            raise ValueError(f'PostScript name is not ASCII: {ps_name!r}')
        if len(ps_bytes) > 63:
            raise ValueError(f'PostScript name exceeds 63 bytes: {ps_name!r}')
        postscript_names.setdefault(ps_name, []).append(path)

        print(f'OK  {path}  glyphs={glyphs}  cmap={len(best_cmap)}  fsType=0x{fs_type:04X}  psName={ps_name}')
        f.close()
    except Exception as e:
        failed.append((path, e))
        print(f'FAIL {path}: {e}')

for ps_name, paths in sorted(postscript_names.items()):
    if len(paths) > 1:
        msg = f'duplicate PostScript name {ps_name!r}: ' + ', '.join(str(x) for x in paths)
        failed.append((paths[0], ValueError(msg)))
        print('FAIL ' + msg)

if failed:
    raise SystemExit(f'{len(failed)} invalid TTF issue(s).')
print(f'Validated {len(fonts)} TTF file(s); PostScript names are unique.')
