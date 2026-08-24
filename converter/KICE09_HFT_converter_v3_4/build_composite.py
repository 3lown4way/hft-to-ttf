#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Optional

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from hft_core_v34 import TARGET_UPEM, iter_unicode_glyphs


def build(
    sources,
    out: Path,
    family: str,
    style: str = "Regular",
    bold_metric_adjust: bool = False,
    source_code_overrides: Optional[dict[str, dict[int, str]]] = None,
    source_code_aliases: Optional[dict[str, dict[int, list[str]]]] = None,
):
    """Build a local composite TTF from script-specific HFT sources.

    `source_code_overrides` and `source_code_aliases` are keyed by source
    basename (case-insensitive). They are intended for document-specific
    legacy-code bindings, not universal HNC mappings.
    """
    source_code_overrides = {k.upper(): v for k, v in (source_code_overrides or {}).items()}
    source_code_aliases = {k.upper(): v for k, v in (source_code_aliases or {}).items()}

    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    metrics = {".notdef": (TARGET_UPEM, 0)}
    cmap = {}
    order = [".notdef"]
    source_log = {}

    for label, path in sources:
        key = path.name.upper()
        overrides = source_code_overrides.get(key, {})
        aliases = source_code_aliases.get(key, {})
        for item in iter_unicode_glyphs(
            path,
            TARGET_UPEM,
            code_overrides=overrides,
            code_aliases=aliases,
        ):
            cp = ord(item.char)
            if cp in cmap:
                continue
            name = f"uni{cp:04X}" if cp <= 0xFFFF else f"u{cp:06X}"
            glyph = item.glyph

            # Preserve Hancom's actual HFT output baseline. The v3.4 core
            # subtracts the shell header baseline (200 source units), but direct
            # comparison with the embedded CIDFontType0C outlines in the official
            # 2026 KICE Korean exam shows the rendered baseline is 0.15em.
            # All 48 validated KICE09 HFTs use header baseline=200; therefore the
            # correction from the old geometry is +50 units for 1000 UPEM faces
            # and +16.7 units for 1200 UPEM faces.
            baseline_fix = int(round((200 - 0.15 * item.source_upem) * TARGET_UPEM / item.source_upem))
            try:
                coords, _end_pts, _flags = glyph.getCoordinates(None)
                if baseline_fix:
                    for i, (x, y) in enumerate(coords):
                        coords[i] = (x, y + baseline_fix)
                    glyph.coordinates = coords
                lsb = min((pt[0] for pt in coords), default=0)
            except Exception:
                lsb = 0

            glyphs[name] = glyph
            adv = item.advance
            # Provisional metric-only correction for bold. This switch does NOT
            # reproduce the historical Hancom outline emboldening algorithm.
            if bold_metric_adjust:
                adv += TARGET_UPEM // 20

            # TrueType hmtx leftSideBearing must match the recovered raw xMin.
            # Writing zero here (the old v3.4 behavior) makes TT renderers shift
            # each outline left by its original bearing.
            metrics[name] = (adv, int(round(lsb)))
            cmap[cp] = name
            order.append(name)
            source_log[cp] = f"{label}:{path.name}:HNC0x{item.internal_code:04X}:{item.encryption}"

    fb = FontBuilder(TARGET_UPEM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-220, lineGap=0)
    weight = 700 if style.lower().startswith("bold") else 400
    fb.setupOS2(
        sTypoAscender=800, sTypoDescender=-220, sTypoLineGap=0,
        usWinAscent=820, usWinDescent=220,
        sxHeight=500, sCapHeight=700,
        usWeightClass=weight, usWidthClass=5,
    )
    ps = "".join(c for c in family if c.isascii() and c.isalnum()) or "KICEHFTComposite"
    fb.setupNameTable({
        "familyName": family,
        "styleName": style,
        "uniqueFontIdentifier": f"{family} {style} HFT v3.4 local reconstruction",
        "fullName": f"{family} {style}",
        "psName": f"{ps}-{style.replace(' ', '')}",
        "version": "Version 0.3.4 local HFT reconstruction",
    })
    fb.setupPost()
    fb.setupMaxp()
    out.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out))
    return len(cmap), source_log


def _parse_code_char(spec: str):
    # Syntax: 3C30=F076 or 3C30=U+F076
    left, right = spec.split("=", 1)
    code = int(left.replace("0x", ""), 16)
    rhs = right.strip().upper().replace("U+", "")
    return code, chr(int(rhs, 16))


def main():
    ap = argparse.ArgumentParser(description="Build one local composite TTF from script-specific HFT sources")
    ap.add_argument("--hg", type=Path)
    ap.add_argument("--en", type=Path)
    ap.add_argument("--hj", type=Path)
    ap.add_argument("--other", type=Path)
    ap.add_argument("--sp", type=Path)
    ap.add_argument("--user", type=Path, help="Optional USER.HFT; generic user slots map to U+E000 onward unless overridden")
    ap.add_argument("--user-override", action="append", default=[], metavar="HNC=UNICODE",
                    help="Document-specific USER mapping, e.g. 3C30=F076")
    ap.add_argument("--sp-alias", action="append", default=[], metavar="HNC=UNICODE",
                    help="Additional Unicode alias for a symbol outline, e.g. 341A=A854")
    ap.add_argument("--name", required=True)
    ap.add_argument("--style", default="Regular")
    ap.add_argument("--bold-metric-adjust", action="store_true")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    sources = [(k.upper(), p) for k, p in (
        ("hg", a.hg), ("en", a.en), ("hj", a.hj), ("other", a.other), ("sp", a.sp), ("user", a.user)
    ) if p]

    overrides = {}
    if a.user and a.user_override:
        overrides[a.user.name.upper()] = dict(_parse_code_char(s) for s in a.user_override)
    aliases = {}
    if a.sp and a.sp_alias:
        d = {}
        for s in a.sp_alias:
            code, ch = _parse_code_char(s)
            d.setdefault(code, []).append(ch)
        aliases[a.sp.name.upper()] = d

    n, _ = build(
        sources, a.out, a.name, a.style, a.bold_metric_adjust,
        source_code_overrides=overrides,
        source_code_aliases=aliases,
    )
    print(f"built {a.out} / cmap={n}")


if __name__ == "__main__":
    main()
