#!/usr/bin/env python3
from pathlib import Path
import argparse, json

p = argparse.ArgumentParser()
p.add_argument('font_dir')
a = p.parse_args()
root = Path(a.font_dir)

hft = sorted(x for x in root.rglob('*') if x.is_file() and x.suffix.lower() == '.hft')
ttf = sorted(x for x in root.rglob('*') if x.is_file() and x.suffix.lower() == '.ttf')
inf = sorted(x for x in root.rglob('*') if x.is_file() and x.suffix.lower() == '.inf')

info = {
    'hft_count': len(hft),
    'ttf_count': len(ttf),
    'inf_count': len(inf),
    'hft_bytes': sum(x.stat().st_size for x in hft),
    'ttf_bytes': sum(x.stat().st_size for x in ttf),
}
print(json.dumps(info, ensure_ascii=False, indent=2))

expected = (387, 32, 1)
actual = (len(hft), len(ttf), len(inf))
if actual != expected:
    raise SystemExit(f'Unexpected source inventory: HFT/TTF/INF={actual}, expected={expected}')
