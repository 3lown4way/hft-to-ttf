#!/usr/bin/env python3
"""Temporary CI bridge: replace the downloaded smoke-test HWP with the I-GAM HWPX render input."""
from __future__ import annotations

import base64
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parts = sorted((ROOT / "inputs").glob("igam-live-1-4.part*.b64"))
if not parts:
    raise SystemExit("I-GAM HWPX base64 parts not found")
raw = "".join(p.read_text(encoding="utf-8") for p in parts)
clean = re.sub(r"[^A-Za-z0-9+/=]", "", raw)
data = base64.b64decode(clean, validate=False)
if not data.startswith(b"PK"):
    raise SystemExit(f"decoded input is not a ZIP/HWPX: {data[:16]!r}")
out = ROOT / "input.hwp"
out.write_bytes(data)
with zipfile.ZipFile(out) as zf:
    bad = zf.testzip()
    if bad:
        raise SystemExit(f"HWPX ZIP member failed CRC: {bad}")
    names = set(zf.namelist())
    required = {"mimetype", "Contents/header.xml", "Contents/section0.xml"}
    missing = required - names
    if missing:
        raise SystemExit(f"HWPX missing required members: {sorted(missing)}")
print("IGAM_HWPX_BYTES", len(data))
print("IGAM_HWPX_SHA256", hashlib.sha256(data).hexdigest())
print("IGAM_HWPX_ZIP_OK", len(names), "members")
print("input.hwp overwritten with HWPX payload for the existing rhwp smoke renderer")
