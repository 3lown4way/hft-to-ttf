#!/usr/bin/env python3
"""Audit source-of-truth HFT metrics against generated composite TTFs.

This test intentionally uses only the supplied HFT files and generated TTFs.
It does not consult the official PDF and therefore detects whether later
PDF/document-specific repair steps have hidden a converter or renderer issue.
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "converter" / "KICE09_HFT_converter_v3_4"
sys.path.insert(0, str(CONVERTER))
from hft_core_v34 import iter_unicode_glyphs  # noqa: E402


def source_metrics(path: Path, chars: str) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for item in iter_unicode_glyphs(path):
        if item.char not in chars:
            continue
        try:
            coords, _end_pts, _flags = item.glyph.getCoordinates(None)
            lsb = min((x for x, _y in coords), default=0)
        except Exception:
            lsb = 0
        out[item.char] = (item.advance, int(round(lsb)))
    return out


def find_family(family: str) -> Path:
    for path in sorted((ROOT / "output_ttf").glob("*.ttf")):
        font = TTFont(path, lazy=True)
        names = []
        for rec in font["name"].names:
            if rec.nameID == 1:
                try:
                    names.append(rec.toUnicode())
                except Exception:
                    pass
        font.close()
        if family in names:
            return path
    raise RuntimeError(f"generated family not found: {family}")


def ttf_metrics(path: Path, chars: str) -> dict[str, tuple[int, int]]:
    font = TTFont(path, lazy=False)
    cmap = font.getBestCmap() or {}
    out = {}
    for ch in chars:
        name = cmap.get(ord(ch))
        if name:
            out[ch] = tuple(map(int, font["hmtx"].metrics[name]))
    font.close()
    return out


def assert_equal(label: str, source: dict, generated: dict) -> None:
    missing = sorted(set(source) - set(generated))
    if missing:
        raise SystemExit(f"{label}: generated TTF missing {missing}")
    bad = {ch: (source[ch], generated[ch]) for ch in source if source[ch] != generated[ch]}
    if bad:
        raise SystemExit(f"{label}: metric mismatches: {bad}")
    print(f"OK {label}: {len(source)} glyph metrics match HFT -> TTF exactly")
    for ch in source:
        print(f"  U+{ord(ch):04X} {ch!r}: advance={source[ch][0]} lsb={source[ch][1]}")


def main() -> None:
    zip_path = ROOT / "inputs" / "kice09-required48.zip"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        with zipfile.ZipFile(zip_path) as zf:
            for name in ("ENGMJ.HFT", "SPSMJ.HFT"):
                zf.extract(name, td)

        # charPr 10 question-number Latin face: 한양견명조 / ENGMJ.HFT.
        qchars = "0123456789."
        qsrc = source_metrics(td / "ENGMJ.HFT", qchars)
        qttf = ttf_metrics(find_family("한양견명조"), qchars)
        assert_equal("question-number ENGMJ.HFT", qsrc, qttf)

        # Main Shinmyeong Myeongjo symbol face used by 【】, wave dash and quotes.
        schars = "【】～‘’“”"
        ssrc = source_metrics(td / "SPSMJ.HFT", schars)
        sttf = ttf_metrics(find_family("신명 중명조 - 한양문자"), schars)
        assert_equal("SPSMJ.HFT punctuation/symbols", ssrc, sttf)


if __name__ == "__main__":
    main()
