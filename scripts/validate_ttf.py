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
for path in fonts:
    try:
        f = TTFont(path, lazy=False)
        required = {'head', 'hhea', 'maxp', 'cmap', 'name'}
        missing = required.difference(f.keys())
        if missing:
            raise ValueError('missing tables: ' + ', '.join(sorted(missing)))
        glyphs = len(f.getGlyphOrder())
        if glyphs < 2:
            raise ValueError(f'too few glyphs: {glyphs}')
        best_cmap = f.getBestCmap() or {}
        if not best_cmap:
            raise ValueError('empty Unicode cmap')
        print(f'OK  {path}  glyphs={glyphs}  cmap={len(best_cmap)}')
        f.close()
    except Exception as e:
        failed.append((path, e))
        print(f'FAIL {path}: {e}')

if failed:
    raise SystemExit(f'{len(failed)} invalid TTF file(s).')
print(f'Validated {len(fonts)} TTF file(s).')
