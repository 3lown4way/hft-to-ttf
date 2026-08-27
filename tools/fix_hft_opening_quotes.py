#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont

# HFT smart-quote glyphs are authored as paired marks in the same 1000-unit
# symbol cell.  In the source fonts the opening member sits on the far right
# while the closing member sits on the far left.  rhwp already supplies the
# narrow document advance, so keeping that full-cell opening offset makes the
# opening mark intrude into the following Hangul glyph.
#
# Keep the HFT outline and advance unchanged.  Only translate each opening
# member so that its outline center matches the center of its closing partner.
# The translation is derived from the two HFT-derived outlines themselves;
# no PDF widths, oracle metrics, or per-font constants are used.
QUOTE_PAIRS = (
    (0x2018, 0x2019),  # ‘ ’
    (0x201C, 0x201D),  # “ ”
)


def _glyph_bounds(glyph, glyf_table):
    glyph.recalcBounds(glyf_table)
    return glyph.xMin, glyph.xMax


def fix_font(path: Path) -> list[tuple[str, int, tuple[int, int], tuple[int, int]]]:
    font = TTFont(path)
    if "glyf" not in font or "hmtx" not in font:
        return []

    cmap = font.getBestCmap() or {}
    glyf = font["glyf"]
    hmtx = font["hmtx"].metrics
    changes: list[tuple[str, int, tuple[int, int], tuple[int, int]]] = []

    for opener_cp, closer_cp in QUOTE_PAIRS:
        opener_name = cmap.get(opener_cp)
        closer_name = cmap.get(closer_cp)
        if not opener_name or not closer_name:
            continue

        opener = glyf[opener_name]
        closer = glyf[closer_name]
        if opener.isComposite() or closer.isComposite():
            # The KICE HFT-derived smart quotes are simple glyphs.  Avoid
            # silently changing semantics for an unrelated composite font.
            continue

        opener_before = _glyph_bounds(opener, glyf)
        closer_bounds = _glyph_bounds(closer, glyf)
        opener_center2 = opener_before[0] + opener_before[1]
        closer_center2 = closer_bounds[0] + closer_bounds[1]
        dx = int(round((closer_center2 - opener_center2) / 2.0))

        # Source HFT opening quotes are the right-side member of the pair.
        # A non-negative shift means this font does not have that legacy
        # placement pattern (or has already been fixed), so leave it alone.
        if dx >= 0:
            continue

        opener.coordinates.translate((dx, 0))
        opener_after = _glyph_bounds(opener, glyf)
        advance, lsb = hmtx[opener_name]
        hmtx[opener_name] = (advance, lsb + dx)
        changes.append((chr(opener_cp), dx, opener_before, opener_after))

    if changes:
        font.save(path)
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recenter legacy HFT opening smart quotes against their closing partners."
    )
    ap.add_argument("directory", type=Path, help="Directory containing HFT-derived TTF files")
    args = ap.parse_args()

    paths = sorted(args.directory.glob("*.ttf"))
    changed_fonts = 0
    changed_glyphs = 0
    for path in paths:
        changes = fix_font(path)
        if not changes:
            continue
        changed_fonts += 1
        changed_glyphs += len(changes)
        print(path.name)
        for ch, dx, before, after in changes:
            print(f"  {ch} dx={dx:+d} x={before[0]}..{before[1]} -> {after[0]}..{after[1]}")

    print(
        f"opening-quote fix: fonts={len(paths)} changed_fonts={changed_fonts} "
        f"changed_glyphs={changed_glyphs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
