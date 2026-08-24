#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import tempfile
import zipfile
from pathlib import Path

from build_composite import build
from hft_core_v34 import read_meta

LANG_TO_LABEL = {
    'hangul': 'HG',
    'latin': 'EN',
    'hanja': 'HJ',
    'other': 'OTHER',
    'symbol': 'SP',
    'user': 'USER',
}
KICE09_OVERRIDES = {'USER.HFT': {0x3C30: '\uF076'}}
KICE09_ALIASES = {'SPSMJ.HFT': {0x341A: ['\uA854'], 0x341B: ['\uA855']}}


def main() -> None:
    ap = argparse.ArgumentParser(description='Build one KICE09 v3.4 fontRef combination for CI matrix execution')
    ap.add_argument('fonts_zip', type=Path)
    ap.add_argument('combinations_csv', type=Path)
    ap.add_argument('--combo', type=int, required=True)
    ap.add_argument('--outdir', type=Path, required=True)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(args.combinations_csv.open(encoding='utf-8-sig')))
    try:
        row = next(r for r in rows if int(r['font_combo_id']) == args.combo)
    except StopIteration:
        raise SystemExit(f'Unknown font_combo_id: {args.combo}')

    with zipfile.ZipFile(args.fonts_zip) as zf, tempfile.TemporaryDirectory() as td:
        lookup = {Path(n).name.upper(): n for n in zf.namelist() if not n.endswith('/')}
        extracted: dict[str, Path] = {}

        def get(filename: str) -> Path:
            key = filename.upper()
            if key not in extracted:
                if key not in lookup:
                    raise FileNotFoundError(filename)
                p = Path(td) / filename
                p.write_bytes(zf.read(lookup[key]))
                extracted[key] = p
            return extracted[key]

        sources = []
        skipped = []
        for lang, label in LANG_TO_LABEL.items():
            value = (row.get(lang) or '').strip()
            if not value or value.startswith('TTF:'):
                if value:
                    skipped.append(f'{lang}:{value}')
                continue
            p = get(value)
            category = read_meta(p).category
            if category not in ('HG', 'EN', 'HJ', 'OTHER', 'SP', 'USER'):
                skipped.append(f'{lang}:{value}:{category}')
                continue
            sources.append((label, p))

        out = args.outdir / f'KICE09_combo_{args.combo:02d}_Regular.ttf'
        cmap_count, log = build(
            sources,
            out,
            f'KICE09 Combo {args.combo:02d} HFT TEMP',
            'Regular',
            False,
            source_code_overrides=KICE09_OVERRIDES,
            source_code_aliases=KICE09_ALIASES,
        )
        manifest = {
            'combo': args.combo,
            'style': 'Regular',
            'cmap': cmap_count,
            'out': out.name,
            'skipped': skipped,
            'log': log,
        }
        (args.outdir / f'combo_{args.combo:02d}_manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
            encoding='utf-8',
        )
        print(out, cmap_count)


if __name__ == '__main__':
    main()
