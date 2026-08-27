#!/usr/bin/env python3
"""Visual baseline audit for comma and smart quotation marks.

The official PDF is comparison-only.  No glyph outline or metric from it is
used to build the runtime TTFs.

The audit separates two independent quantities:
  * text-origin delta: layout / charPr / script-baseline placement;
  * ink-relative-to-origin delta: vertical placement of the glyph outline.

For every target glyph we also calculate the median origin delta of nearby
non-target characters on the same oracle text line.  A target-specific excess
near zero means a whole line moved, not just punctuation.
"""
from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz
import numpy as np
from PIL import Image, ImageDraw

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
                    ox, oy = c.get("origin", (0.0, 0.0))
                    bbox = tuple(float(v) for v in c.get("bbox", (0, 0, 0, 0)))
                    out.append(CharRec(ch, page_no, float(ox), float(oy), bbox, size, font, line_id))
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


def median(vals: Iterable[float]) -> float | None:
    vals = sorted(float(v) for v in vals)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def fmt(v: float | None) -> str:
    return "NA" if v is None else f"{v:+.3f}"


def match_by_position(oracle: list[CharRec], generated: list[CharRec], max_dist: float = 24.0):
    """Greedy same-character nearest neighbour matching in page coordinates."""
    by_char: dict[str, list[int]] = {}
    for j, c in enumerate(generated):
        by_char.setdefault(c.ch, []).append(j)
    used: set[int] = set()
    pairs: list[tuple[CharRec, CharRec, float]] = []
    for a in oracle:
        best_j = None
        best_d = float("inf")
        for j in by_char.get(a.ch, []):
            if j in used:
                continue
            b = generated[j]
            d = math.hypot(a.x - b.x, a.y - b.y)
            if d < best_d:
                best_j, best_d = j, d
        if best_j is not None and best_d <= max_dist:
            used.add(best_j)
            pairs.append((a, generated[best_j], best_d))
    return pairs


def render_gray(page: fitz.Page, dpi: int) -> np.ndarray:
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def components_in_char(img: np.ndarray, rec: CharRec, dpi: int):
    """Return connected ink components in a baseline-relative character window."""
    scale = dpi / 72.0
    x0, _y0, x1, _y1 = rec.bbox
    mx = max(0.45, rec.size * 0.035)
    left = max(0, int(math.floor((x0 - mx) * scale)))
    right = min(img.shape[1], int(math.ceil((x1 + mx) * scale)))
    top = max(0, int(math.floor((rec.y - 1.25 * rec.size) * scale)))
    bottom = min(img.shape[0], int(math.ceil((rec.y + 0.45 * rec.size) * scale)))
    if right <= left or bottom <= top:
        return []
    crop = img[top:bottom, left:right]
    mask = crop < 170
    if not mask.any():
        return []

    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=np.uint8)
    comps = []
    base_px = rec.y * scale
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
            if len(pts) < 2:
                continue
            ys = np.array([p[0] for p in pts])
            xs = np.array([p[1] for p in pts])
            abs_top = top + int(ys.min())
            abs_bottom = top + int(ys.max()) + 1
            abs_centroid = top + float(ys.mean())
            comps.append({
                "area": len(pts),
                "xfrac": float(xs.mean()) / max(w - 1, 1),
                "top_rel": (abs_top - base_px) / scale,
                "bottom_rel": (abs_bottom - base_px) / scale,
                "centroid_rel": (abs_centroid - base_px) / scale,
            })
    return comps


def pick_oracle_component(comps, ch: str):
    if not comps:
        return None
    # Smart opening marks in SPSMJ occupy the right side of their full-width
    # cell; closing marks occupy the left.  Comma is selected near the baseline.
    if ch in {"‘", "“"}:
        desired_x = 0.78
        cand = [c for c in comps if c["centroid_rel"] < -1.0 and c["area"] <= 500] or comps
        return min(cand, key=lambda c: abs(c["xfrac"] - desired_x) + 0.0015 * c["area"])
    if ch in {"’", "”"}:
        desired_x = 0.22
        cand = [c for c in comps if c["centroid_rel"] < -1.0 and c["area"] <= 500] or comps
        return min(cand, key=lambda c: abs(c["xfrac"] - desired_x) + 0.0015 * c["area"])
    cand = [c for c in comps if -2.5 <= c["centroid_rel"] <= 3.5 and c["area"] <= 500] or comps
    return min(cand, key=lambda c: abs(c["centroid_rel"]) + 0.001 * c["area"])


def pick_matching_component(comps, ref):
    if not comps or ref is None:
        return None
    # Match visual component identity, not character-cell centre.  This avoids
    # selecting a neighbouring Hangul stroke for quotes whose LSB is extreme.
    def score(c):
        area_term = abs(math.log(max(c["area"], 1) / max(ref["area"], 1)))
        x_term = abs(c["xfrac"] - ref["xfrac"])
        vertical_term = abs(c["centroid_rel"] - ref["centroid_rel"]) / 12.0
        return area_term + 1.6 * x_term + 0.20 * vertical_term
    return min(comps, key=score)


def make_sheet(rows, oracle_img: np.ndarray, gen_img: np.ndarray, out: Path, dpi: int):
    scale = dpi / 72.0
    cards = []
    for row in rows[:50]:
        a: CharRec = row["oracle"]
        b: CharRec = row["generated"]
        half_w_pt = max(8.0, a.size * 0.9)
        half_h_pt = max(10.0, a.size * 1.1)

        def crop_for(img, rec):
            l = max(0, int((rec.x - half_w_pt) * scale))
            r = min(img.shape[1], int((rec.x + half_w_pt) * scale))
            t = max(0, int((rec.y - half_h_pt) * scale))
            bb = min(img.shape[0], int((rec.y + half_h_pt * 0.55) * scale))
            return Image.fromarray(img[t:bb, l:r]).convert("RGB")

        oa, gb = crop_for(oracle_img, a), crop_for(gen_img, b)
        h = max(oa.height, gb.height, 120)
        card = Image.new("RGB", (oa.width + gb.width + 30, h + 52), "white")
        card.paste(oa, (0, 38))
        card.paste(gb, (oa.width + 30, 38))
        draw = ImageDraw.Draw(card)
        ink = row.get("ink_centroid_delta")
        excess = row.get("origin_excess_vs_line")
        draw.text((4, 4), f"{a.ch} origin dy={row['origin_dy']:+.3f}pt line-excess={fmt(excess)} ink-delta={fmt(ink)}", fill="black")
        draw.text((4, 22), "oracle", fill="black")
        draw.text((oa.width + 34, 22), "generated", fill="black")
        cards.append(card)
    if not cards:
        return
    width = max(c.width for c in cards)
    sheet = Image.new("RGB", (width, sum(c.height for c in cards)), "white")
    y = 0
    for c in cards:
        sheet.paste(c, (0, y)); y += c.height
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
        op, gp = oracle_doc[pno], gen_doc[0]
        oc, gc = iter_chars(op, pno + 1), iter_chars(gp, pno + 1)
        pairs = match_by_position(oc, gc)
        report.append(
            f"PAGE {pno+1}: oracle_chars={len(oc)} generated_chars={len(gc)} matched={len(pairs)} "
            f"page_size_oracle={op.rect.width:.2f}x{op.rect.height:.2f} generated={gp.rect.width:.2f}x{gp.rect.height:.2f}"
        )

        controls: dict[str, list[float]] = {"hangul": [], "latin": [], "ascii-punct": [], "target": []}
        for a, b, _ in pairs:
            cls = classify(a.ch)
            if cls in controls:
                controls[cls].append(b.y - a.y)
        report.append("  origin dy medians (generated-oracle pt): " + ", ".join(
            f"{k}={fmt(median(v))} n={len(v)}" for k, v in controls.items()))

        oracle_img, gen_img = render_gray(op, args.dpi), render_gray(gp, args.dpi)
        target_rows = []
        for a, b, dist in pairs:
            if a.ch not in TARGETS:
                continue
            line_controls = [
                bb.y - aa.y for aa, bb, _ in pairs
                if aa.line == a.line and aa.ch not in TARGETS and not aa.ch.isspace()
                and abs(aa.x - a.x) <= 140.0
            ]
            local_line_dy = median(line_controls)
            origin_dy = b.y - a.y

            ocomp = pick_oracle_component(components_in_char(oracle_img, a, args.dpi), a.ch)
            gcomp = pick_matching_component(components_in_char(gen_img, b, args.dpi), ocomp)
            row = {
                "page": pno + 1, "char": a.ch, "oracle": a, "generated": b, "distance": dist,
                "oracle_x": a.x, "oracle_origin_y": a.y, "generated_x": b.x, "generated_origin_y": b.y,
                "origin_dx": b.x - a.x, "origin_dy": origin_dy,
                "local_line_origin_dy": local_line_dy,
                "origin_excess_vs_line": None if local_line_dy is None else origin_dy - local_line_dy,
                "local_line_control_n": len(line_controls),
                "oracle_font": a.font, "generated_font": b.font,
                "oracle_size": a.size, "generated_size": b.size,
            }
            if ocomp and gcomp:
                row.update(
                    oracle_ink_top_rel=ocomp["top_rel"], oracle_ink_bottom_rel=ocomp["bottom_rel"],
                    oracle_ink_centroid_rel=ocomp["centroid_rel"], oracle_ink_area=ocomp["area"],
                    oracle_ink_xfrac=ocomp["xfrac"],
                    generated_ink_top_rel=gcomp["top_rel"], generated_ink_bottom_rel=gcomp["bottom_rel"],
                    generated_ink_centroid_rel=gcomp["centroid_rel"], generated_ink_area=gcomp["area"],
                    generated_ink_xfrac=gcomp["xfrac"],
                    ink_top_delta=gcomp["top_rel"] - ocomp["top_rel"],
                    ink_bottom_delta=gcomp["bottom_rel"] - ocomp["bottom_rel"],
                    ink_centroid_delta=gcomp["centroid_rel"] - ocomp["centroid_rel"],
                )
            target_rows.append(row); all_csv.append(row)

        make_sheet(target_rows, oracle_img, gen_img, args.out_dir / f"page-{pno+1}-punctuation-sheet.png", args.dpi)
        by_char: dict[str, list[dict]] = {}
        for r in target_rows:
            by_char.setdefault(r["char"], []).append(r)
        for ch in sorted(by_char):
            rr = by_char[ch]
            report.append(
                f"  {ch!r}: n={len(rr)} origin_dy_med={fmt(median(r['origin_dy'] for r in rr))} "
                f"line_excess_med={fmt(median(r['origin_excess_vs_line'] for r in rr if r['origin_excess_vs_line'] is not None))} "
                f"ink_centroid_delta_med={fmt(median(r.get('ink_centroid_delta') for r in rr if r.get('ink_centroid_delta') is not None))}"
            )

    fields = [
        "page", "char", "distance", "oracle_x", "oracle_origin_y", "generated_x", "generated_origin_y",
        "origin_dx", "origin_dy", "local_line_origin_dy", "origin_excess_vs_line", "local_line_control_n",
        "oracle_font", "generated_font", "oracle_size", "generated_size",
        "oracle_ink_top_rel", "oracle_ink_bottom_rel", "oracle_ink_centroid_rel", "oracle_ink_area", "oracle_ink_xfrac",
        "generated_ink_top_rel", "generated_ink_bottom_rel", "generated_ink_centroid_rel", "generated_ink_area", "generated_ink_xfrac",
        "ink_top_delta", "ink_bottom_delta", "ink_centroid_delta",
    ]
    with (args.out_dir / "punctuation-baseline-audit.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
        for r in all_csv:
            w.writerow(r)
    text = "\n".join(report) + "\n"
    (args.out_dir / "punctuation-baseline-audit.txt").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
