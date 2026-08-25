#!/usr/bin/env python3
"""Compare punctuation baseline/ink placement between an oracle PDF and rhwp output.

This is a diagnostic only.  It never reads glyph geometry or metrics from the
oracle PDF for font generation.  The PDF is used only after rendering, as a
visual-position oracle.

For each of , ‘ ’ “ ” the script records:
  * text origin (baseline) in PDF points,
  * rendered ink top/bottom/centroid relative to that origin,
  * delta between oracle and generated PDF,
  * page-level control deltas for Hangul and Latin characters.

That lets us distinguish three cases:
  1) ink-relative-to-origin differs -> converted glyph vertical geometry issue;
  2) origins differ for a whole script class -> charPr/script baseline issue;
  3) both agree -> the apparent mismatch comes from another layout factor.
"""
from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TARGETS = {",", "‘", "’", "“", "”"}


@dataclass
class CharRec:
    ch: str
    page: int
    x: float
    y: float
    bbox: tuple[float, float, float, float]
    size: float
    font: str
    line: int


def iter_chars(page: fitz.Page, page_no: int) -> list[CharRec]:
    raw = page.get_text("rawdict")
    out: list[CharRec] = []
    line_id = 0
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
                    origin = c.get("origin", (0.0, 0.0))
                    bbox = tuple(float(v) for v in c.get("bbox", (0, 0, 0, 0)))
                    out.append(
                        CharRec(
                            ch=ch,
                            page=page_no,
                            x=float(origin[0]),
                            y=float(origin[1]),
                            bbox=bbox,
                            size=size,
                            font=font,
                            line=line_id,
                        )
                    )
    return out


def classify(ch: str) -> str:
    cp = ord(ch)
    if ch in TARGETS:
        return "target"
    if 0xAC00 <= cp <= 0xD7A3 or 0x3130 <= cp <= 0x318F:
        return "hangul"
    if ch.isascii() and (ch.isalpha() or ch.isdigit()):
        return "latin"
    if ch.isascii() and not ch.isspace():
        return "ascii-punct"
    return "other"


def match_by_position(oracle: list[CharRec], generated: list[CharRec], max_dist: float = 24.0):
    """Greedy same-character nearest-neighbour matching in page coordinates."""
    by_char: dict[str, list[int]] = {}
    for j, c in enumerate(generated):
        by_char.setdefault(c.ch, []).append(j)
    used: set[int] = set()
    pairs: list[tuple[CharRec, CharRec, float]] = []
    for a in oracle:
        candidates = by_char.get(a.ch, [])
        best = None
        best_d = float("inf")
        for j in candidates:
            if j in used:
                continue
            b = generated[j]
            d = math.hypot(a.x - b.x, a.y - b.y)
            if d < best_d:
                best_d = d
                best = j
        if best is not None and best_d <= max_dist:
            used.add(best)
            pairs.append((a, generated[best], best_d))
    return pairs


def render_gray(page: fitz.Page, dpi: int) -> np.ndarray:
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def component_near_char(img: np.ndarray, rec: CharRec, dpi: int):
    """Find the ink component nearest the character cell center.

    Returns (top_rel_pt, bottom_rel_pt, centroid_rel_pt, area, crop_box_px),
    where relative values are measured from the text origin/baseline.
    """
    scale = dpi / 72.0
    x0, _y0, x1, _y1 = rec.bbox
    # Use the extracted character cell horizontally, but a baseline-relative
    # vertical window so font ascender/descender metadata cannot bias the audit.
    mx = max(0.45, rec.size * 0.035)
    left = max(0, int(math.floor((x0 - mx) * scale)))
    right = min(img.shape[1], int(math.ceil((x1 + mx) * scale)))
    top = max(0, int(math.floor((rec.y - 1.25 * rec.size) * scale)))
    bottom = min(img.shape[0], int(math.ceil((rec.y + 0.45 * rec.size) * scale)))
    if right <= left or bottom <= top:
        return None

    crop = img[top:bottom, left:right]
    mask = crop < 170
    if not mask.any():
        return None

    # 8-connected components, implemented locally to avoid scipy dependency.
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=np.uint8)
    comps = []
    for yy in range(h):
        for xx in range(w):
            if not mask[yy, xx] or seen[yy, xx]:
                continue
            stack = [(yy, xx)]
            seen[yy, xx] = 1
            pts = []
            while stack:
                cy, cx = stack.pop()
                pts.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = 1
                            stack.append((ny, nx))
            if len(pts) >= 2:
                ys = np.array([p[0] for p in pts])
                xs = np.array([p[1] for p in pts])
                comps.append((len(pts), xs.mean(), ys.mean(), xs.min(), xs.max(), ys.min(), ys.max()))
    if not comps:
        return None

    target_x = ((x0 + x1) * 0.5 * scale) - left
    # Prefer a component close to the character-cell center; area weakly helps
    # reject antialiasing specks without forcing commas/quotes to be large.
    def score(c):
        area, cx, cy, *_ = c
        return abs(cx - target_x) - min(area, 80) * 0.015

    area, cx, cy, cx0, cx1, cy0, cy1 = min(comps, key=score)
    base_px = rec.y * scale
    abs_top = top + cy0
    abs_bottom = top + cy1 + 1
    abs_centroid = top + cy
    return (
        (abs_top - base_px) / scale,
        (abs_bottom - base_px) / scale,
        (abs_centroid - base_px) / scale,
        int(area),
        (left, top, right, bottom),
    )


def median(vals: Iterable[float]) -> float | None:
    vals = sorted(float(v) for v in vals)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def fmt(v: float | None) -> str:
    return "NA" if v is None else f"{v:+.3f}"


def make_sheet(rows, oracle_img: np.ndarray, gen_img: np.ndarray, out: Path, dpi: int):
    scale = dpi / 72.0
    cards = []
    for row in rows[:40]:
        a: CharRec = row["oracle"]
        b: CharRec = row["generated"]
        half_w_pt = max(8.0, a.size * 0.9)
        half_h_pt = max(10.0, a.size * 1.1)

        def crop_for(img, rec):
            l = max(0, int((rec.x - half_w_pt) * scale))
            r = min(img.shape[1], int((rec.x + half_w_pt) * scale))
            t = max(0, int((rec.y - half_h_pt) * scale))
            bb = min(img.shape[0], int((rec.y + half_h_pt * 0.55) * scale))
            arr = img[t:bb, l:r]
            return Image.fromarray(arr).convert("RGB")

        oa = crop_for(oracle_img, a)
        gb = crop_for(gen_img, b)
        h = max(oa.height, gb.height, 120)
        w = oa.width + gb.width + 30
        card = Image.new("RGB", (w, h + 44), "white")
        card.paste(oa, (0, 32))
        card.paste(gb, (oa.width + 30, 32))
        draw = ImageDraw.Draw(card)
        label = f"{a.ch}  origin Δy={row['origin_dy']:+.3f}pt  ink-centroid Δ={row.get('ink_centroid_delta', float('nan')):+.3f}pt"
        draw.text((4, 4), label, fill="black")
        draw.text((4, 20), "oracle", fill="black")
        draw.text((oa.width + 34, 20), "generated", fill="black")
        cards.append(card)
    if not cards:
        return
    width = max(c.width for c in cards)
    height = sum(c.height for c in cards)
    sheet = Image.new("RGB", (width, height), "white")
    y = 0
    for c in cards:
        sheet.paste(c, (0, y))
        y += c.height
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", type=Path, required=True)
    ap.add_argument("--generated-dir", type=Path, required=True)
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--dpi", type=int, default=600)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    oracle_doc = fitz.open(args.oracle)
    all_csv = []
    report = []

    for pno in range(min(args.pages, oracle_doc.page_count)):
        gen_path = args.generated_dir / f"page-{pno+1}-embedded.pdf"
        if not gen_path.exists():
            report.append(f"PAGE {pno+1}: generated PDF missing: {gen_path}")
            continue
        gen_doc = fitz.open(gen_path)
        op = oracle_doc[pno]
        gp = gen_doc[0]
        oc = iter_chars(op, pno + 1)
        gc = iter_chars(gp, pno + 1)
        pairs = match_by_position(oc, gc)
        report.append(
            f"PAGE {pno+1}: oracle_chars={len(oc)} generated_chars={len(gc)} matched={len(pairs)} "
            f"page_size_oracle={op.rect.width:.2f}x{op.rect.height:.2f} generated={gp.rect.width:.2f}x{gp.rect.height:.2f}"
        )

        controls: dict[str, list[float]] = {"hangul": [], "latin": [], "ascii-punct": [], "target": []}
        for a, b, _d in pairs:
            cls = classify(a.ch)
            if cls in controls:
                controls[cls].append(b.y - a.y)
        report.append(
            "  origin Δy medians (generated-oracle pt): "
            + ", ".join(f"{k}={fmt(median(v))} n={len(v)}" for k, v in controls.items())
        )

        oracle_img = render_gray(op, args.dpi)
        gen_img = render_gray(gp, args.dpi)
        target_rows = []
        for a, b, d in pairs:
            if a.ch not in TARGETS:
                continue
            oa = component_near_char(oracle_img, a, args.dpi)
            gb = component_near_char(gen_img, b, args.dpi)
            row = {
                "page": pno + 1,
                "char": a.ch,
                "oracle": a,
                "generated": b,
                "distance": d,
                "oracle_x": a.x,
                "oracle_origin_y": a.y,
                "generated_x": b.x,
                "generated_origin_y": b.y,
                "origin_dx": b.x - a.x,
                "origin_dy": b.y - a.y,
                "oracle_font": a.font,
                "generated_font": b.font,
                "oracle_size": a.size,
                "generated_size": b.size,
            }
            if oa and gb:
                row.update(
                    oracle_ink_top_rel=oa[0],
                    oracle_ink_bottom_rel=oa[1],
                    oracle_ink_centroid_rel=oa[2],
                    generated_ink_top_rel=gb[0],
                    generated_ink_bottom_rel=gb[1],
                    generated_ink_centroid_rel=gb[2],
                    ink_top_delta=gb[0] - oa[0],
                    ink_bottom_delta=gb[1] - oa[1],
                    ink_centroid_delta=gb[2] - oa[2],
                    oracle_ink_area=oa[3],
                    generated_ink_area=gb[3],
                )
            target_rows.append(row)
            all_csv.append(row)

        make_sheet(target_rows, oracle_img, gen_img, args.out_dir / f"page-{pno+1}-punctuation-sheet.png", args.dpi)
        by_char = {}
        for r in target_rows:
            by_char.setdefault(r["char"], []).append(r)
        for ch in sorted(by_char):
            rr = by_char[ch]
            report.append(
                f"  {ch!r}: n={len(rr)} origin_dy_med={fmt(median(r['origin_dy'] for r in rr))} "
                f"ink_centroid_delta_med={fmt(median(r.get('ink_centroid_delta') for r in rr if r.get('ink_centroid_delta') is not None))}"
            )

    # Flatten records for CSV; omit dataclass objects.
    fields = [
        "page", "char", "distance", "oracle_x", "oracle_origin_y", "generated_x", "generated_origin_y",
        "origin_dx", "origin_dy", "oracle_font", "generated_font", "oracle_size", "generated_size",
        "oracle_ink_top_rel", "oracle_ink_bottom_rel", "oracle_ink_centroid_rel",
        "generated_ink_top_rel", "generated_ink_bottom_rel", "generated_ink_centroid_rel",
        "ink_top_delta", "ink_bottom_delta", "ink_centroid_delta", "oracle_ink_area", "generated_ink_area",
    ]
    with (args.out_dir / "punctuation-baseline-audit.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in all_csv:
            w.writerow(r)
    text = "\n".join(report) + "\n"
    (args.out_dir / "punctuation-baseline-audit.txt").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
