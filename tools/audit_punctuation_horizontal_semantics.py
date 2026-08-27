#!/usr/bin/env python3
"""Audit horizontal placement semantics of legacy HFT punctuation.

The official KICE PDF is comparison-only.  This script never copies PDF
outlines or metrics into a runtime font.  Instead it compares:

* oracle PDF text origin -> next-character origin;
* generated PDF text origin -> next-character origin;
* the source-derived runtime TTF glyph xMin / hmtx LSB / advance.

This catches a specific class of renderer mismatch: HWP layout can allocate a
narrow punctuation cell while the converted legacy HFT glyph still carries its
original full-cell x offset.  If glyph xMin is to the right of the next
character origin, the glyph necessarily intrudes into the following character
cell even though the layout positions themselves are reasonable.

No codepoint correction is performed here; target characters are only probes.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import fitz
from fontTools.ttLib import TTFont

TARGETS = (",", "‘", "’", "“", "”", "【", "】", "～")


@dataclass
class Rec:
    ch: str
    x: float
    y: float
    bbox: tuple[float, float, float, float]
    size: float
    font: str
    line_id: int
    order: int


@dataclass
class FontGlyphMetric:
    file: str
    family: str
    ps_name: str
    upem: int
    advance: int
    lsb: int
    xmin: int | None
    xmax: int | None


def chars_by_page(page: fitz.Page) -> list[Rec]:
    raw = page.get_text("rawdict")
    out: list[Rec] = []
    line_id = 0
    order = 0
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_id += 1
            for span in line.get("spans", []):
                size = float(span.get("size", 0.0))
                font = str(span.get("font", ""))
                for c in span.get("chars", []):
                    ch = c.get("c", "")
                    if not ch:
                        continue
                    x, y = c.get("origin", (0.0, 0.0))
                    bbox = tuple(float(v) for v in c.get("bbox", (0, 0, 0, 0)))
                    out.append(Rec(ch, float(x), float(y), bbox, size, font, line_id, order))
                    order += 1
    return out


def next_visible_same_line(chars: list[Rec], i: int) -> Rec | None:
    a = chars[i]
    for b in chars[i + 1 :]:
        if b.line_id != a.line_id:
            if b.line_id > a.line_id:
                break
            continue
        if not b.ch.isspace():
            return b
    return None


def sfnt_name(font: TTFont, name_id: int) -> str:
    # Prefer Unicode records, then any decodable record.
    records = [n for n in font["name"].names if n.nameID == name_id]
    records.sort(key=lambda n: (0 if n.isUnicode() else 1, n.platformID, n.platEncID, n.langID))
    for n in records:
        try:
            value = n.toUnicode().strip()
        except Exception:
            continue
        if value:
            return value
    return ""


def load_runtime_metrics(font_dir: Path) -> tuple[dict[str, TTFont], dict[str, Path]]:
    by_ps: dict[str, TTFont] = {}
    paths: dict[str, Path] = {}
    for p in sorted(font_dir.glob("*.ttf")):
        try:
            f = TTFont(p, lazy=False)
        except Exception:
            continue
        ps = sfnt_name(f, 6)
        if ps:
            by_ps[ps] = f
            paths[ps] = p
    return by_ps, paths


def metric_for(font: TTFont, path: Path, ch: str) -> FontGlyphMetric | None:
    cmap = font.getBestCmap() or {}
    gname = cmap.get(ord(ch))
    if not gname:
        return None
    advance, lsb = font["hmtx"].metrics[gname]
    upem = int(font["head"].unitsPerEm)
    xmin = xmax = None
    if "glyf" in font:
        glyph = font["glyf"][gname]
        try:
            glyph.recalcBounds(font["glyf"])
        except Exception:
            pass
        xmin = getattr(glyph, "xMin", None)
        xmax = getattr(glyph, "xMax", None)
    return FontGlyphMetric(
        file=path.name,
        family=sfnt_name(font, 1),
        ps_name=sfnt_name(font, 6),
        upem=upem,
        advance=int(advance),
        lsb=int(lsb),
        xmin=None if xmin is None else int(xmin),
        xmax=None if xmax is None else int(xmax),
    )


def med(values: list[float]) -> float | None:
    return None if not values else float(median(values))


def fmt(v: float | None, digits: int = 3) -> str:
    return "NA" if v is None or not math.isfinite(v) else f"{v:+.{digits}f}"


def collect_pdf(doc: fitz.Document, page_no: int):
    chars = chars_by_page(doc[page_no])
    rows = []
    for i, a in enumerate(chars):
        if a.ch not in TARGETS or a.size <= 0:
            continue
        b = next_visible_same_line(chars, i)
        step_pt = None if b is None else b.x - a.x
        step_em = None if step_pt is None else step_pt / a.size
        bbox_left_em = (a.bbox[0] - a.x) / a.size
        bbox_width_em = (a.bbox[2] - a.bbox[0]) / a.size
        rows.append((a, b, step_pt, step_em, bbox_left_em, bbox_width_em))
    return rows


def summarize_oracle(doc: fitz.Document, pages: int) -> list[str]:
    lines = ["=== ORACLE PDF: horizontal punctuation behavior (comparison only) ==="]
    by_char: dict[str, list[tuple[float, float, float]]] = {ch: [] for ch in TARGETS}
    for pno in range(min(pages, doc.page_count)):
        for a, _b, _step_pt, step_em, bbox_left_em, bbox_width_em in collect_pdf(doc, pno):
            if step_em is not None:
                by_char[a.ch].append((step_em, bbox_left_em, bbox_width_em))
    for ch in TARGETS:
        vals = by_char[ch]
        if not vals:
            continue
        lines.append(
            f"ORACLE {ch!r}: n={len(vals)} "
            f"next_origin_step_em={fmt(med([v[0] for v in vals]))} "
            f"bbox_left_minus_origin_em={fmt(med([v[1] for v in vals]))} "
            f"char_bbox_width_em={fmt(med([v[2] for v in vals]))}"
        )
    return lines


def summarize_generated(
    generated_dir: Path,
    runtime_fonts: Path,
    pages: int,
) -> list[str]:
    lines = ["=== GENERATED PDF + source-derived runtime TTF semantics ==="]
    fonts, font_paths = load_runtime_metrics(runtime_fonts)
    lines.append(f"runtime_ps_fonts={len(fonts)}")
    aggregate: dict[str, list[dict]] = {ch: [] for ch in TARGETS}

    for pno in range(pages):
        path = generated_dir / f"page-{pno+1}-embedded.pdf"
        if not path.exists():
            lines.append(f"PAGE {pno+1}: missing {path}")
            continue
        doc = fitz.open(path)
        rows = collect_pdf(doc, 0)
        for a, b, step_pt, step_em, bbox_left_em, bbox_width_em in rows:
            f = fonts.get(a.font)
            m = None if f is None else metric_for(f, font_paths[a.font], a.ch)
            xmin_em = None if m is None or m.xmin is None else m.xmin / m.upem
            lsb_em = None if m is None else m.lsb / m.upem
            advance_em = None if m is None else m.advance / m.upem
            overrun = None if xmin_em is None or step_em is None else xmin_em - step_em
            aggregate[a.ch].append({
                "page": pno + 1,
                "font": a.font,
                "next": None if b is None else b.ch,
                "step_pt": step_pt,
                "step_em": step_em,
                "bbox_left_em": bbox_left_em,
                "bbox_width_em": bbox_width_em,
                "xmin_em": xmin_em,
                "lsb_em": lsb_em,
                "advance_em": advance_em,
                "overrun_em": overrun,
                "metric": m,
            })

    for ch in TARGETS:
        rows = aggregate[ch]
        if not rows:
            continue
        step_vals = [r["step_em"] for r in rows if r["step_em"] is not None]
        xmin_vals = [r["xmin_em"] for r in rows if r["xmin_em"] is not None]
        lsb_vals = [r["lsb_em"] for r in rows if r["lsb_em"] is not None]
        adv_vals = [r["advance_em"] for r in rows if r["advance_em"] is not None]
        over_vals = [r["overrun_em"] for r in rows if r["overrun_em"] is not None]
        metric = next((r["metric"] for r in rows if r["metric"] is not None), None)
        font_names = sorted({r["font"] for r in rows})
        lines.append(
            f"GENERATED {ch!r}: n={len(rows)} fonts={font_names} "
            f"next_origin_step_em={fmt(med(step_vals))} "
            f"TTF_xmin_em={fmt(med(xmin_vals))} "
            f"TTF_lsb_em={fmt(med(lsb_vals))} "
            f"TTF_advance_em={fmt(med(adv_vals))} "
            f"xmin_minus_next_origin_step_em={fmt(med(over_vals))}"
        )
        if metric is not None:
            lines.append(
                f"  source={metric.file!r} family={metric.family!r} ps={metric.ps_name!r} "
                f"upem={metric.upem} advance={metric.advance} lsb={metric.lsb} "
                f"xMin={metric.xmin} xMax={metric.xmax}"
            )
        positive = [v for v in over_vals if v > 0]
        if over_vals:
            lines.append(
                f"  intrusion_signature={len(positive)}/{len(over_vals)} "
                f"(xMin lies to the right of next-character origin when positive)"
            )
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", type=Path, required=True)
    ap.add_argument("--generated-dir", type=Path, required=True)
    ap.add_argument("--runtime-fonts", type=Path, required=True)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    oracle = fitz.open(args.oracle)
    lines = summarize_oracle(oracle, args.pages)
    lines.append("")
    lines.extend(summarize_generated(args.generated_dir, args.runtime_fonts, args.pages))
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
