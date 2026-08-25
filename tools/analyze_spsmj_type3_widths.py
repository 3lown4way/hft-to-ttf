#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf as fitz
from fontTools.pens.boundsPen import BoundsPen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "converter" / "KICE09_HFT_converter_v3_4"))
from hft_core_v34 import iter_raw_records, read_meta, _char_for_record, _draw_ops  # noqa: E402


def ref_xref(doc, font_xref: int, key: str) -> int:
    kind, val = doc.xref_get_key(font_xref, key)
    if kind != "xref":
        raise RuntimeError(f"{key}: {kind} {val}")
    return int(val.split()[0])


def parse_encoding(doc, font_xref: int) -> dict[int, str]:
    obj = doc.xref_object(ref_xref(doc, font_xref, "Encoding"), compressed=False)
    m = re.search(r"/Differences\s*\[(.*?)\]", obj, re.S)
    if not m:
        return {}
    out: dict[int, str] = {}
    cur = None
    for tok in re.findall(r"/[^\s\[\]]+|\d+", m.group(1)):
        if tok.startswith("/"):
            if cur is None:
                raise RuntimeError("glyph name before code")
            out[cur] = tok[1:]
            cur += 1
        else:
            cur = int(tok)
    return out


def parse_tounicode(doc, font_xref: int) -> dict[int, int]:
    text = doc.xref_stream(ref_xref(doc, font_xref, "ToUnicode")).decode("latin1", "replace")
    out: dict[int, int] = {}

    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            out[int(src, 16)] = int(dst, 16)

    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        # <start> <end> <dst-start>
        for a, b, d in re.findall(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block
        ):
            aa, bb, dd = int(a, 16), int(b, 16), int(d, 16)
            for code in range(aa, bb + 1):
                out[code] = dd + (code - aa)
        # <start> <end> [<dst0> <dst1> ...]
        for m in re.finditer(
            r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", block, re.S
        ):
            aa, bb = int(m.group(1), 16), int(m.group(2), 16)
            vals = [int(x, 16) for x in re.findall(r"<([0-9A-Fa-f]+)>", m.group(3))]
            for i, code in enumerate(range(aa, bb + 1)):
                if i < len(vals):
                    out[code] = vals[i]
    return out


def parse_charprocs(doc, font_xref: int) -> dict[str, int]:
    obj = doc.xref_object(ref_xref(doc, font_xref, "CharProcs"), compressed=False)
    return {
        name: int(xref)
        for name, xref in re.findall(r"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R", obj)
    }


def path_x_extrema(text: str):
    toks = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)|[A-Za-z]+", text)
    nums: list[float] = []
    xs: list[float] = []
    arity = {"m": 2, "l": 2, "c": 6, "v": 4, "y": 4, "re": 4}
    for tok in toks:
        try:
            nums.append(float(tok))
            continue
        except ValueError:
            pass
        if tok in arity and len(nums) >= arity[tok]:
            a = nums[-arity[tok] :]
            if tok in ("m", "l"):
                xs.append(a[0])
            elif tok == "c":
                xs.extend((a[0], a[2], a[4]))
            elif tok in ("v", "y"):
                xs.extend((a[0], a[2]))
            else:
                xs.extend((a[0], a[0] + a[2]))
        nums = []
    return (min(xs), max(xs)) if xs else (None, None)


def load_spsmj(font_zip: Path):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        with zipfile.ZipFile(font_zip) as z:
            names = {Path(n).name.upper(): n for n in z.namelist()}
            z.extract(names["SPSMJ.HFT"], td)
            sp = td / names["SPSMJ.HFT"]
            if not sp.exists():
                # zip may contain a directory prefix
                sp = td / names["SPSMJ.HFT"]
            meta = read_meta(sp)
            source = {}
            for idx, code, advance, ops, enc in iter_raw_records(sp):
                ch = _char_for_record(meta, idx, code)
                if not ch:
                    continue
                pen = BoundsPen(None)
                _draw_ops(ops, pen, 0.0)
                if not pen.bounds:
                    continue
                x0, y0, x1, y1 = pen.bounds
                source[ord(ch)] = {
                    "char": ch,
                    "hnc": code,
                    "src_advance": advance,
                    "src_xmin": float(x0),
                    "src_xmax": float(x1),
                    "src_ink_w": float(x1 - x0),
                }
            return source


def contiguous_segments(rows):
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r["hnc"])
    segs = []
    start = prev = rows[0]["hnc"]
    width = rows[0]["pdf_width"]
    count = 1
    for r in rows[1:]:
        code, w = r["hnc"], r["pdf_width"]
        if code == prev + 1 and w == width:
            prev = code
            count += 1
            continue
        segs.append((start, prev, width, count))
        start = prev = code
        width = w
        count = 1
    segs.append((start, prev, width, count))
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--fonts-zip", type=Path, default=ROOT / "inputs" / "kice09-required48.zip")
    ap.add_argument("--font-name", default="T5")
    ap.add_argument("--csv", type=Path, default=Path("spsmj-type3-full.csv"))
    args = ap.parse_args()

    source = load_spsmj(args.fonts_zip)
    doc = fitz.open(args.pdf)
    page = doc[0]
    font_xref = None
    for f in page.get_fonts(full=True):
        xref, _ext, typ, basefont, resname, *_ = f
        if typ == "Type3" and args.font_name in {str(basefont), str(resname)}:
            font_xref = int(xref)
            break
    if font_xref is None:
        raise SystemExit(f"Type3 {args.font_name} not found")

    first = int(doc.xref_get_key(font_xref, "FirstChar")[1])
    widths_obj = doc.xref_object(ref_xref(doc, font_xref, "Widths"), compressed=False)
    widths = [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", widths_obj)]
    code_to_name = parse_encoding(doc, font_xref)
    code_to_unicode = parse_tounicode(doc, font_xref)
    name_to_xref = parse_charprocs(doc, font_xref)

    rows = []
    for pdf_code, ucp in sorted(code_to_unicode.items()):
        src = source.get(ucp)
        if not src:
            continue
        idx = pdf_code - first
        if not (0 <= idx < len(widths)):
            continue
        name = code_to_name.get(pdf_code)
        proc_xref = name_to_xref.get(name or "")
        if proc_xref is None:
            continue
        t0, t1 = path_x_extrema(doc.xref_stream(proc_xref).decode("latin1", "replace"))
        if t0 is None:
            continue
        sw = src["src_ink_w"]
        tw = t1 - t0
        scale_x = tw / sw if sw else 0.0
        shift_x = t0 - scale_x * src["src_xmin"] if sw else 0.0
        row = dict(src)
        row.update(
            pdf_code=pdf_code,
            pdf_width=widths[idx],
            t3_xmin=t0,
            t3_xmax=t1,
            t3_ink_w=tw,
            t3_center=(t0 + t1) / 2,
            center_err=(t0 + t1) / 2 - widths[idx] / 2,
            scale_x=scale_x,
            shift_x=shift_x,
        )
        rows.append(row)

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "char", "hnc", "src_advance", "src_xmin", "src_xmax", "src_ink_w",
        "pdf_code", "pdf_width", "t3_xmin", "t3_xmax", "t3_ink_w",
        "t3_center", "center_err", "scale_x", "shift_x",
    ]
    with args.csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            rr = dict(r)
            rr["hnc"] = f"0x{r['hnc']:04X}"
            rr["pdf_code"] = f"0x{r['pdf_code']:02X}"
            w.writerow({k: rr[k] for k in fields})

    print("=== FULL T5 ToUnicode JOIN AGAINST SPSMJ.HFT ===")
    print("tounicode_entries", len(code_to_unicode))
    print("joined_rows", len(rows))
    counts = Counter(r["pdf_width"] for r in rows)
    print("width_classes", sorted(counts.items()))
    print()

    by_width = defaultdict(list)
    for r in rows:
        by_width[r["pdf_width"]].append(r)
    for width in sorted(by_width):
        group = by_width[width]
        chars = "".join(r["char"] for r in group[:80])
        med_scale = sorted(r["scale_x"] for r in group)[len(group)//2]
        med_center = sorted(abs(r["center_err"]) for r in group)[len(group)//2]
        print(f"WIDTH {width:g}: n={len(group)} median_scale_x={med_scale:.4f} median_abs_center_err={med_center:.2f}")
        print(" chars", repr(chars))

    print("\n=== CONTIGUOUS HNC SEGMENTS BY OFFICIAL WIDTH ===")
    for a, b, w, n in contiguous_segments(rows):
        print(f"0x{a:04X}-0x{b:04X} width={w:g} n={n}")

    print("\n=== NON-1000 GLYPHS ===")
    for r in sorted((r for r in rows if r["pdf_width"] != 1000), key=lambda r: r["hnc"]):
        print(
            f"{r['char']!r} U+{ord(r['char']):04X} HNC=0x{r['hnc']:04X} "
            f"width={r['pdf_width']:g} src=({r['src_xmin']:.1f},{r['src_xmax']:.1f}) "
            f"t3=({r['t3_xmin']:.1f},{r['t3_xmax']:.1f}) scale={r['scale_x']:.4f} "
            f"center_err={r['center_err']:+.1f}"
        )


if __name__ == "__main__":
    main()
