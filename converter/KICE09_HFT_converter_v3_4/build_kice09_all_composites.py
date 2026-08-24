#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, tempfile, zipfile
from pathlib import Path
from build_composite import build
from hft_core_v34 import read_meta

LANG_TO_LABEL = {
    'hangul':'HG', 'latin':'EN', 'hanja':'HJ', 'other':'OTHER', 'symbol':'SP', 'user':'USER'
}
KICE09_OVERRIDES = {'USER.HFT': {0x3C30: '\uF076'}}
KICE09_ALIASES = {'SPSMJ.HFT': {0x341A: ['\uA854'], 0x341B: ['\uA855']}}


def main():
    ap=argparse.ArgumentParser(description='Build one local composite TTF per actually-used KICE09 script fontRef combination')
    ap.add_argument('fonts_zip', type=Path)
    ap.add_argument('combinations_csv', type=Path, help='analysis_v34/KICE09_fontref_combinations_v34.csv')
    ap.add_argument('--outdir', type=Path, default=Path('KICE09_composites_local'))
    ap.add_argument('--with-provisional-bold', action='store_true', help='Also build Bold variants using metric-only +em/20 correction; outline emboldening is NOT exact')
    a=ap.parse_args(); a.outdir.mkdir(parents=True,exist_ok=True)

    rows=list(csv.DictReader(a.combinations_csv.open(encoding='utf-8-sig')))
    with zipfile.ZipFile(a.fonts_zip) as z, tempfile.TemporaryDirectory() as td:
        lookup={Path(n).name.upper():n for n in z.namelist() if not n.endswith('/')}
        extracted={}
        def get(fn):
            k=fn.upper()
            if k not in extracted:
                if k not in lookup: raise FileNotFoundError(fn)
                p=Path(td)/fn; p.write_bytes(z.read(lookup[k])); extracted[k]=p
            return extracted[k]

        manifest=[]
        for row in rows:
            combo=int(row['font_combo_id'])
            sources=[]
            skipped=[]
            for lang,label in LANG_TO_LABEL.items():
                v=(row.get(lang) or '').strip()
                if not v or v.startswith('TTF:'):
                    if v: skipped.append(f'{lang}:{v}')
                    continue
                p=get(v)
                cat=read_meta(p).category
                if cat not in ('HG','EN','HJ','OTHER','SP','USER'):
                    skipped.append(f'{lang}:{v}:{cat}')
                    continue
                sources.append((label,p))
            # No Japanese Unicode scalar occurs in the source document, so JP HFTs are
            # deliberately omitted until their legacy key tables are mapped.
            for style,badj in [('Regular',False)] + ([('Bold',True)] if a.with_provisional_bold else []):
                out=a.outdir/f'KICE09_combo_{combo:02d}_{style}.ttf'
                n,log=build(sources,out,f'KICE09 Combo {combo:02d} HFT TEMP',style,badj,
                            source_code_overrides=KICE09_OVERRIDES,
                            source_code_aliases=KICE09_ALIASES)
                manifest.append({'combo':combo,'style':style,'cmap':n,'out':out.name,'skipped':skipped})
                print(out, n)
        (a.outdir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print('NOTE: U+A2EE and Hanyang-PUA old Hangul are not yet bound in v3.4; see unit-char audit.')

if __name__=='__main__': main()
