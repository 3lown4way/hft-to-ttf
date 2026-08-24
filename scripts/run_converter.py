#!/usr/bin/env python3
"""Stable CI adapter for the previously-built KICE09 HFT -> TTF converter."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--input', required=True)
p.add_argument('--output', required=True)
p.add_argument('--converter', required=True)
a = p.parse_args()

input_dir = Path(a.input).resolve()
output_dir = Path(a.output).resolve()
conv = Path(a.converter).resolve()
output_dir.mkdir(parents=True, exist_ok=True)

# Preserve TTFs that are already present in the supplied source set.
for src in input_dir.rglob('*'):
    if src.is_file() and src.suffix.lower() == '.ttf':
        rel = src.relative_to(input_dir)
        dst = output_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

# Explicit command override for a recovered converter using another entrypoint.
override = os.environ.get('HFT_CONVERTER_COMMAND', '').strip()
if override:
    env = os.environ.copy()
    env['HFT_INPUT_DIR'] = str(input_dir)
    env['TTF_OUTPUT_DIR'] = str(output_dir)
    print('Running HFT_CONVERTER_COMMAND:', override)
    cp = subprocess.run(override, shell=True, cwd=Path.cwd(), env=env)
    raise SystemExit(cp.returncode)

# Windows batch entrypoints used by earlier converter-package iterations.
bat_candidates = [
    conv / 'build_all_fonts.bat',
    conv / 'build_needed_fonts.bat',
    conv / 'build_47_fonts.bat',
]
for entry in bat_candidates:
    if entry.exists():
        env = os.environ.copy()
        env['HFT_INPUT_DIR'] = str(input_dir)
        env['TTF_OUTPUT_DIR'] = str(output_dir)
        print('Running:', entry)
        cp = subprocess.run(['cmd', '/d', '/c', str(entry)], cwd=entry.parent, env=env)
        raise SystemExit(cp.returncode)

py_candidates = [
    conv / 'convert_all.py',
    conv / 'hft_to_ttf.py',
    conv / 'converter.py',
    conv / 'main.py',
]
for entry in py_candidates:
    if entry.exists():
        env = os.environ.copy()
        env['HFT_INPUT_DIR'] = str(input_dir)
        env['TTF_OUTPUT_DIR'] = str(output_dir)
        attempts = [
            [sys.executable, str(entry), '--input', str(input_dir), '--output', str(output_dir)],
            [sys.executable, str(entry), str(input_dir), str(output_dir)],
        ]
        last = 1
        for cmd in attempts:
            print('Trying:', ' '.join(cmd))
            cp = subprocess.run(cmd, cwd=entry.parent, env=env)
            last = cp.returncode
            if last == 0:
                raise SystemExit(0)
        raise SystemExit(last)

found = [str(x.relative_to(conv)) for x in conv.rglob('*') if x.is_file()]
print('Converter files found:', found[:100])
raise SystemExit(
    'KICE09 HFT converter core is missing or its entrypoint name is unknown. '
    'Place the recovered v3.3 converter source under converter/ or set '
    'HFT_CONVERTER_COMMAND in the workflow.'
)
