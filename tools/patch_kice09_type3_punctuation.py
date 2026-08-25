#!/usr/bin/env python3
"""KICE09 document-specific punctuation outline patch.

The recovered 2009-06 KICE PDF renders the Hanyang ShinMyeongjo symbol
quotes as compact Type3 glyphs (widths 230/441 in a 1000-unit em).  The
raw SPSMJ.HFT reconstruction keeps the shell's 1000-unit side-bearing
layout, so U+2018/U+2019/U+201C/U+201D appear displaced / dash-like when
used as ordinary Unicode punctuation.  Replace only the exact SPSMJ
reconstruction signatures with the vectors recovered from the official
PDF Type3 CharProcs.  Other symbol families are intentionally untouched.
"""
from pathlib import Path
import sys

from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen

# cp -> (advance, expected reconstructed bbox, Type3 drawing commands)
PATCHES = {
    0x2018: (230, (773, 573, 899, 826), [
        ("M", (154, 784)), ("L", (164, 769)),
        ("C", (139, 743, 103, 685, 103, 651)),
        ("C", (103, 639, 106, 633, 115, 633)),
        ("C", (120, 633, 127, 633, 137, 633)),
        ("C", (154, 633, 171, 613, 171, 583)),
        ("C", (171, 550, 146, 528, 116, 528)),
        ("C", (75, 528, 55, 563, 55, 603)),
        ("C", (55, 691, 109, 743, 154, 784)), ("Z", ()),
    ]),
    0x2019: (230, (99, 566, 232, 824), [
        ("M", (74, 538)), ("L", (64, 553)),
        ("C", (89, 579, 125, 637, 125, 671)),
        ("C", (125, 683, 122, 689, 113, 689)),
        ("C", (108, 689, 101, 689, 91, 689)),
        ("C", (74, 689, 57, 709, 57, 739)),
        ("C", (57, 772, 82, 794, 112, 794)),
        ("C", (153, 794, 173, 759, 173, 719)),
        ("C", (173, 631, 119, 579, 74, 538)), ("Z", ()),
    ]),
    0x201C: (441, (558, 572, 905, 826), [
        ("M", (348, 784)), ("L", (358, 769)),
        ("C", (333, 743, 297, 685, 297, 651)),
        ("C", (297, 639, 300, 633, 309, 633)),
        ("C", (314, 633, 321, 633, 331, 633)),
        ("C", (348, 633, 365, 613, 365, 583)),
        ("C", (365, 550, 340, 528, 310, 528)),
        ("C", (269, 528, 249, 563, 249, 603)),
        ("C", (249, 691, 303, 743, 348, 784)), ("Z", ()),
        ("M", (173, 784)), ("L", (183, 769)),
        ("C", (158, 743, 122, 685, 122, 651)),
        ("C", (122, 639, 125, 633, 134, 633)),
        ("C", (139, 633, 146, 633, 156, 633)),
        ("C", (173, 633, 190, 613, 190, 583)),
        ("C", (190, 550, 165, 528, 135, 528)),
        ("C", (94, 528, 74, 563, 74, 603)),
        ("C", (74, 691, 128, 743, 173, 784)), ("Z", ()),
    ]),
    0x201D: (441, (97, 566, 436, 826), [
        ("M", (92, 537)), ("L", (82, 552)),
        ("C", (107, 578, 143, 636, 143, 670)),
        ("C", (143, 682, 140, 688, 131, 688)),
        ("C", (126, 688, 119, 688, 109, 688)),
        ("C", (92, 688, 75, 708, 75, 738)),
        ("C", (75, 771, 100, 793, 130, 793)),
        ("C", (171, 793, 191, 758, 191, 718)),
        ("C", (191, 630, 137, 578, 92, 537)), ("Z", ()),
        ("M", (267, 537)), ("L", (257, 552)),
        ("C", (282, 578, 318, 636, 318, 670)),
        ("C", (318, 682, 315, 688, 306, 688)),
        ("C", (301, 688, 294, 688, 284, 688)),
        ("C", (267, 688, 250, 708, 250, 738)),
        ("C", (250, 771, 275, 793, 305, 793)),
        ("C", (346, 793, 366, 758, 366, 718)),
        ("C", (366, 630, 312, 578, 267, 537)), ("Z", ()),
    ]),
}


def make_glyph(commands):
    out = TTGlyphPen(None)
    pen = Cu2QuPen(out, max_err=0.7, reverse_direction=False)
    for op, v in commands:
        if op == "M":
            pen.moveTo(v)
        elif op == "L":
            pen.lineTo(v)
        elif op == "C":
            pen.curveTo(v[0:2], v[2:4], v[4:6])
        elif op == "Z":
            pen.closePath()
    return out.glyph()


def patch_font(path: Path) -> int:
    font = TTFont(path)
    cmap = font.getBestCmap() or {}
    patched = 0
    for cp, (advance, expected_bbox, commands) in PATCHES.items():
        glyph_name = cmap.get(cp)
        if not glyph_name:
            continue
        old = font["glyf"][glyph_name]
        old.recalcBounds(font["glyf"])
        bbox = (old.xMin, old.yMin, old.xMax, old.yMax)
        if bbox != expected_bbox:
            continue
        glyph = make_glyph(commands)
        glyph.recalcBounds(font["glyf"])
        font["glyf"][glyph_name] = glyph
        font["hmtx"][glyph_name] = (advance, glyph.xMin)
        patched += 1
    if patched:
        font.save(path)
    return patched


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "runtime_fonts")
    total = 0
    for path in sorted(root.glob("*.ttf")):
        n = patch_font(path)
        if n:
            print(f"patched quotes: {path.name} ({n})")
            total += n
    print(f"patched quote glyphs total={total}")
    if total == 0:
        raise SystemExit("no SPSMJ quote signatures found")


if __name__ == "__main__":
    main()
