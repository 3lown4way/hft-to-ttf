#!/usr/bin/env python3
from pathlib import Path
import argparse, zipfile, shutil

p = argparse.ArgumentParser()
p.add_argument('--archives', default='source_archives')
p.add_argument('--output', default='fonts')
a = p.parse_args()

archives = Path(a.archives)
out = Path(a.output)
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True, exist_ok=True)

zips = sorted(archives.glob('fonts-part-*.zip'))
if not zips:
    raise SystemExit(f'No font archives found under {archives}')

seen = set()
for zp in zips:
    print('Extracting', zp)
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if not name:
                continue
            if name in seen:
                raise SystemExit(f'Duplicate source filename: {name}')
            seen.add(name)
            target = out / name
            with z.open(info) as s, target.open('wb') as d:
                shutil.copyfileobj(s, d)

print(f'Extracted {len(seen)} source files to {out}')
if len(seen) != 420:
    raise SystemExit(f'Expected 420 source files, restored {len(seen)}')
