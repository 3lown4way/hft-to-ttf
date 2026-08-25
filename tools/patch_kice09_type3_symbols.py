#!/usr/bin/env python3
"""KICE09 document-specific Type3 symbol repairs.

The HFT reconstruction preserves the original cell metrics but a few legacy
symbol outlines are not faithful to the 2009 KICE PDF.  Replace only exact
known signatures with vectors recovered from the official PDF Type3 CharProcs.

Repairs:
- U+3010 LEFT BLACK LENTICULAR BRACKET
- U+3011 RIGHT BLACK LENTICULAR BRACKET
- U+FF5E FULLWIDTH TILDE
"""
from pathlib import Path
import sys

from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen

# cp -> (advance, expected reconstructed bbox, Type3 drawing commands)
PATCHES = {
    0x3010: (1000, (661, -94, 937, 765), [
        ("M", (661, 765)), ("L", (937, 765)), ("L", (937, 759)),
        ("C", (855, 698, 793, 527, 793, 350)),
        ("C", (793, 151, 854, -36, 934, -88)),
        ("L", (934, -94)), ("L", (661, -94)), ("Z", ()),
    ]),
    0x3011: (1000, (60, -94, 348, 765), [
        ("M", (348, 765)), ("L", (63, 765)), ("L", (63, 759)),
        ("C", (154, 698, 216, 529, 216, 352)),
        ("C", (216, 137, 153, -36, 60, -88)),
        ("L", (60, -94)), ("L", (348, -94)), ("Z", ()),
    ]),
    0xFF5E: (1000, (272, 646, 722, 784), [
        ("M", (848, 379)), ("L", (828, 396)),
        ("C", (758, 347, 698, 332, 636, 342)),
        ("C", (546, 354, 448, 419, 376, 424)),
        ("C", (301, 434, 212, 407, 169, 349)),
        ("L", (186, 335)),
        ("C", (240, 369, 295, 390, 372, 382)),
        ("C", (462, 367, 527, 312, 633, 302)),
        ("C", (723, 295, 788, 320, 848, 379)),
        ("Z", ()),
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
            print(f"patched symbols: {path.name} ({n})")
            total += n
    print(f"patched symbol glyphs total={total}")
    if total == 0:
        raise SystemExit("no matching KICE09 Type3 symbol signatures found")


if __name__ == "__main__":
    main()
