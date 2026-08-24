#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit('usage: verify_required48.py <font_dir> <manifest>')

font_dir = Path(sys.argv[1])
manifest = Path(sys.argv[2])
expected = {}
for raw in manifest.read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    parts = line.split()
    if len(parts) < 3:
        raise SystemExit(f'bad manifest line: {raw!r}')
    sha, size, name = parts[0], int(parts[1]), parts[2]
    expected[name.upper()] = (sha.lower(), size)

files = {p.name.upper(): p for p in font_dir.iterdir() if p.is_file() and p.suffix.lower() == '.hft'}
if set(files) != set(expected):
    missing = sorted(set(expected) - set(files))
    extra = sorted(set(files) - set(expected))
    raise SystemExit(f'file set mismatch; missing={missing}, extra={extra}')

for name, (sha, size) in expected.items():
    p = files[name]
    data = p.read_bytes()
    actual_sha = hashlib.sha256(data).hexdigest()
    if len(data) != size or actual_sha != sha:
        raise SystemExit(f'hash/size mismatch: {p.name}')

print(f'Verified {len(files)} HFT files against SHA256 manifest.')
