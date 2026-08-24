#!/usr/bin/env python3
"""Document-specific glyph patches for the 2009-06 KICE Korean exam.

These patches are intentionally *not* universal HFT mappings.  They preserve
legacy document behaviour that was recovered by comparing the original HWPX,
PDF text mapping and Hancom fonts supplied with the source font set.
"""
from __future__ import annotations

from pathlib import Path
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

# The original HWPX scalar U+A2EE is a legacy list-marker binding, not the Yi
# syllable shape implied by modern Unicode.  The recovered KICE09 rendering is
# the Hancom legacy U+F02EE marker.  Its outline below is the exact HBATANG.TTF
# U+F02EE outline supplied in the user's FONTS set, scaled from 1024 UPM to the
# composite's 1000 UPM:
#   HBATANG U+F02EE: advance=1024, lsb=194,
#   points (512,685), (194,367), (512,50), (829,367)
#   -> 1000 UPM: (500,669), (189,358), (500,49), (810,358)
KICE09_A2EE_CP = 0xA2EE
KICE09_A2EE_NAME = 'uniA2EE_KICE09_MARKER'
KICE09_A2EE_ADVANCE = 1000
KICE09_A2EE_LSB = 189
KICE09_A2EE_POINTS = ((500, 669), (189, 358), (500, 49), (810, 358))


def _small_diamond_glyph():
    pen = TTGlyphPen(None)
    p0, p1, p2, p3 = KICE09_A2EE_POINTS
    pen.moveTo(p0)
    pen.lineTo(p1)
    pen.lineTo(p2)
    pen.lineTo(p3)
    pen.closePath()
    return pen.glyph()


def patch_a2ee_marker(ttf_path: Path, source_log: dict | None = None) -> None:
    """Bind U+A2EE to the recovered KICE09 small-diamond marker outline.

    This deliberately replaces any accidental modern Unicode/Yi or generic
    full-em black-diamond mapping for U+A2EE while leaving ordinary U+25C6
    untouched.
    """
    font = TTFont(str(ttf_path), lazy=False)
    order = font.getGlyphOrder()
    if KICE09_A2EE_NAME not in order:
        order.append(KICE09_A2EE_NAME)
        font.setGlyphOrder(order)

    font['glyf'].glyphs[KICE09_A2EE_NAME] = _small_diamond_glyph()
    font['hmtx'].metrics[KICE09_A2EE_NAME] = (
        KICE09_A2EE_ADVANCE,
        KICE09_A2EE_LSB,
    )

    mapped = False
    for table in font['cmap'].tables:
        if table.isUnicode() and table.cmap is not None:
            # U+A2EE is BMP, so every Unicode cmap used by these composites can
            # carry it directly.
            table.cmap[KICE09_A2EE_CP] = KICE09_A2EE_NAME
            mapped = True
    if not mapped:
        font.close()
        raise RuntimeError('No Unicode cmap available for KICE09 U+A2EE patch')

    if 'maxp' in font:
        font['maxp'].numGlyphs = len(order)
    font.save(str(ttf_path))
    font.close()

    if source_log is not None:
        source_log[KICE09_A2EE_CP] = (
            'DOC_PATCH:HBATANG.TTF:U+F02EE:legacy-small-diamond'
        )


def assert_a2ee_marker(ttf_path: Path) -> None:
    """CI guard: U+A2EE must be the recovered small marker, not U+25C6."""
    font = TTFont(str(ttf_path), lazy=False)
    cmap = font.getBestCmap() or {}
    name = cmap.get(KICE09_A2EE_CP)
    if name != KICE09_A2EE_NAME:
        font.close()
        raise RuntimeError(f'U+A2EE mapped to {name!r}, expected {KICE09_A2EE_NAME}')

    g = font['glyf'][name]
    g.recalcBounds(font['glyf'])
    bbox = (g.xMin, g.yMin, g.xMax, g.yMax)
    expected = (189, 49, 810, 669)
    if bbox != expected:
        font.close()
        raise RuntimeError(f'U+A2EE bbox {bbox}, expected {expected}')

    # Ordinary BLACK DIAMOND must remain independent and larger.
    normal = cmap.get(0x25C6)
    if normal:
        ng = font['glyf'][normal]
        ng.recalcBounds(font['glyf'])
        if (ng.xMin, ng.yMin, ng.xMax, ng.yMax) == bbox:
            font.close()
            raise RuntimeError('U+A2EE incorrectly aliases the ordinary U+25C6 outline')
    font.close()
