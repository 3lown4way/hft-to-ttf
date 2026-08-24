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
# KICE09 document-specific aliases. HNC 0x343F is the filled black-diamond
# outline in SPSMJ.HFT (normally U+25C6); the original KICE09 PDF ToUnicode
# exposes that same list-marker glyph as U+A2EE. Keep U+25C6 and add U+A2EE.
KICE09_ALIASES = {
    'SPSMJ.HFT': {
        0x341A: ['\uA854'],
        0x341B: ['\uA855'],
        0x343F: ['\uA2EE'],
    }
}

# Human-readable names reconstructed from the v3.4 font_mapping.json.
# The primary name is the original Hangul face.  A short qualifier is used only
# when multiple KICE09 fontRef combinations share the same Hangul face but use
# materially different Latin/Hanja/Japanese/symbol faces, so Windows can install
# all generated Regular fonts without family/style collisions.
COMBO_NAMES = {
    1: '한양중고딕',
    2: '신명 디나루',
    3: '신명 중고딕',
    4: '신명 중명조 - 한양영문',
    5: '신명 중명조',
    6: '신명 중명조 - 한양문자',
    7: '신명 태고딕',
    8: '한양견명조',
    9: '신명 견명조',
    10: '#태고딕',
    11: '신명 신그래픽',
    12: '신명 궁서',
    13: '신명 중고딕 - 혼합',
}


def filename_for_family(family: str) -> str:
    # Keep the original Korean face name visible while avoiding spaces that are
    # inconvenient in downstream scripts. '#' is retained because it is part of
    # the original Hancom face name (#태고딕).
    return family.replace(' - ', '-').replace(' ', '') + '.ttf'


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

    family = COMBO_NAMES.get(args.combo)
    if not family:
        raise SystemExit(f'No original-font name mapping for combo {args.combo}')

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

        out = args.outdir / filename_for_family(family)
        cmap_count, log = build(
            sources,
            out,
            family,
            'Regular',
            False,
            source_code_overrides=KICE09_OVERRIDES,
            source_code_aliases=KICE09_ALIASES,
        )

        # Every SPSMJ-based combination must carry both the ordinary Unicode
        # diamond and the KICE09 document-specific alias, plus the two previously
        # audited SPSMJ aliases. This turns the U+A2EE binding into a CI invariant.
        if any(p.name.upper() == 'SPSMJ.HFT' for _, p in sources):
            required = (0x25C6, 0xA2EE, 0xA854, 0xA855)
            missing = [f'U+{cp:04X}' for cp in required if cp not in log]
            if missing:
                raise RuntimeError('missing KICE09 SPSMJ cmap entries: ' + ', '.join(missing))

        manifest = {
            'combo': args.combo,
            'family': family,
            'style': 'Regular',
            'cmap': cmap_count,
            'out': out.name,
            'sources': {k: (row.get(k) or '').strip() for k in ('hangul', 'latin', 'hanja', 'japanese', 'other', 'symbol', 'user')},
            'skipped': skipped,
            'log': log,
        }
        (args.outdir / f'combo_{args.combo:02d}_manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
            encoding='utf-8',
        )
        print(f'{family} -> {out} / cmap={cmap_count}')


if __name__ == '__main__':
    main()
