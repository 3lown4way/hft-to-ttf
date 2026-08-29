#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from fontTools.ttLib import TTFont

# nameID 6 must be ASCII/PostScript-safe, so use a readable 1:1 ASCII name for
# each Korean family.  The user-visible name IDs remain the exact Korean family.
POSTSCRIPT_BY_FAMILY = {
    '한양중고딕': 'HanyangJungGothic-Regular',
    '신명 디나루': 'ShinMyeongDinaru-Regular',
    '신명 중고딕': 'ShinMyeongJungGothic-Regular',
    '신명 중명조 - 한양영문': 'ShinMyeongJungMyeongjo-HanyangLatin-Regular',
    '신명 중명조': 'ShinMyeongJungMyeongjo-Regular',
    '신명 중명조 - 한양문자': 'ShinMyeongJungMyeongjo-HanyangSymbol-Regular',
    '신명 태고딕': 'ShinMyeongTaeGothic-Regular',
    '한양견명조': 'HanyangGyeonMyeongjo-Regular',
    '신명 견명조': 'ShinMyeongGyeonMyeongjo-Regular',
    '#태고딕': 'HashTaeGothic-Regular',
    '신명 신그래픽': 'ShinMyeongShinGraphic-Regular',
    '신명 궁서': 'ShinMyeongGungseo-Regular',
    '신명 중고딕 - 혼합': 'ShinMyeongJungGothic-Mixed-Regular',
}

NAME_IDS_TO_REBUILD = {1, 2, 3, 4, 6, 16, 17}
WINDOWS_LANGS = (0x0409, 0x0412)  # English (US), Korean


def normalize(path: Path) -> None:
    font = TTFont(path, lazy=False)
    name = font['name']

    family = name.getDebugName(1)
    if not family:
        raise ValueError(f'{path}: missing nameID 1 family')
    if family not in POSTSCRIPT_BY_FAMILY:
        raise ValueError(f'{path}: no PostScript mapping for family {family!r}')

    ps_name = POSTSCRIPT_BY_FAMILY[family]
    style = 'Regular'
    unique = f'{family};{style};KICE09-HFT-v3.4'

    # Remove stale/conflicting records for the identity fields.  In particular,
    # no generated font may retain the old common KICEHFTComposite identity.
    name.names = [n for n in name.names if n.nameID not in NAME_IDS_TO_REBUILD]

    # Use exact family names for the user-visible identity fields.
    # nameID 1  = Font Family
    # nameID 2  = Font Subfamily
    # nameID 3  = Unique Font Identifier
    # nameID 4  = Full Font Name
    # nameID 6  = PostScript Name (ASCII-only by spec)
    # nameID 16 = Typographic Family
    # nameID 17 = Typographic Subfamily
    for lang in WINDOWS_LANGS:
        name.setName(family, 1, 3, 1, lang)
        name.setName(style, 2, 3, 1, lang)
        name.setName(unique, 3, 3, 1, lang)
        name.setName(family, 4, 3, 1, lang)
        name.setName(ps_name, 6, 3, 1, lang)
        name.setName(family, 16, 3, 1, lang)
        name.setName(style, 17, 3, 1, lang)

    font.save(path)
    font.close()
    print(f'NAME {path.name}: 1/4/16={family!r}, 2/17={style!r}, 6={ps_name!r}')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    args = ap.parse_args()
    fonts = sorted(p for p in args.root.rglob('*.ttf') if p.is_file())
    if not fonts:
        raise SystemExit('No TTF files found.')
    for path in fonts:
        normalize(path)
    print(f'Normalized name tables for {len(fonts)} TTF file(s).')


if __name__ == '__main__':
    main()
