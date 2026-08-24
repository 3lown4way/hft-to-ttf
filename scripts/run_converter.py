#!/usr/bin/env python3
"""GitHub Actions adapter for KICE09_HFT_converter_v3_4.

The v3.4 package is a KICE09 document-font environment reconstructor, not a
universal converter for every HFT layout in the supplied archive.  This adapter
uses its validated KICE09 path and preserves TTF files that already exist in the
source collection.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--input', required=True)
p.add_argument('--output', required=True)
p.add_argument('--converter', required=True)
a = p.parse_args()

input_dir = Path(a.input).resolve()
output_dir = Path(a.output).resolve()
converter_dir = Path(a.converter).resolve()
output_dir.mkdir(parents=True, exist_ok=True)

# Keep the TTF files that were already present in the supplied font set.
existing_dir = output_dir / 'existing_ttf'
for src in input_dir.rglob('*'):
    if src.is_file() and src.suffix.lower() == '.ttf':
        rel = src.relative_to(input_dir)
        dst = existing_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def find_v34_root(root: Path) -> Path | None:
    candidates = [root / 'KICE09_HFT_converter_v3_4', root]
    for candidate in candidates:
        if (candidate / 'build_kice09_all_composites.py').is_file():
            return candidate
    for entry in root.rglob('build_kice09_all_composites.py'):
        return entry.parent
    return None


v34_root = find_v34_root(converter_dir)

# Also accept the exact ZIP package supplied in chat if it is committed under
# converter/.  Extraction is done at runtime, so the package can remain intact.
if v34_root is None:
    zip_candidates = [
        converter_dir / 'KICE09_HFT_converter_v3_4.zip',
        converter_dir / 'KICE09_HFT_converter_v3_4(1).zip',
    ]
    package = next((z for z in zip_candidates if z.is_file()), None)
    if package:
        runtime = converter_dir / '.runtime_v34'
        if runtime.exists():
            shutil.rmtree(runtime)
        runtime.mkdir(parents=True)
        with zipfile.ZipFile(package) as zf:
            zf.extractall(runtime)
        v34_root = find_v34_root(runtime)

if v34_root is None:
    raise SystemExit(
        'KICE09_HFT_converter_v3_4 was not found. Commit the supplied '
        'KICE09_HFT_converter_v3_4 package under converter/.'
    )

builder = v34_root / 'build_kice09_all_composites.py'
combinations = v34_root / 'analysis_v34' / 'KICE09_fontref_combinations_v34.csv'
if not combinations.is_file():
    raise SystemExit(f'v3.4 combination inventory is missing: {combinations}')

# v3.4 consumes a FONTS.zip.  Repack the restored source folder without
# modifying the originals.
with tempfile.TemporaryDirectory() as td:
    fonts_zip = Path(td) / 'FONTS.zip'
    with zipfile.ZipFile(fonts_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for src in sorted(input_dir.rglob('*')):
            if src.is_file():
                zf.write(src, src.relative_to(input_dir).as_posix())

    generated = output_dir / 'KICE09_composites_v34'
    cmd = [
        sys.executable,
        str(builder),
        str(fonts_zip),
        str(combinations),
        '--outdir',
        str(generated),
    ]
    print('Using converter:', v34_root)
    print('Running:', ' '.join(cmd))
    cp = subprocess.run(cmd, cwd=v34_root)
    if cp.returncode != 0:
        raise SystemExit(cp.returncode)

print('v3.4 KICE09 composite conversion completed.')
print('NOTE: v3.4 does not yet provide a generic Unicode mapping for every HFT in the 387-file collection (notably JP HFT).')
