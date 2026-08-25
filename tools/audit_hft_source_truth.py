#!/usr/bin/env python3
"""Audit source-of-truth HFT metrics against generated composite TTFs.

The source-truth assertions intentionally use only the supplied HFT files and
generated TTFs.  If the CI-downloaded official PDF is present, a clearly
separated comparison-only diagnostic is printed afterwards; it is never used
to build or repair runtime fonts.
"""
from __future__ import annotations

import subprocess
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


def _ensure_fitz():
    try:
        import fitz  # type: ignore
        return fitz
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pymupdf"], check=True)
        import fitz  # type: ignore
        return fitz


def audit_oracle_quote_horizontal(pdf_path: Path) -> None:
    """Comparison-only trace of the official PDF's quote origins and Type3 fonts."""
    if not pdf_path.exists():
        return
    fitz = _ensure_fitz()
    doc = fitz.open(pdf_path)
    targets = {"‘", "’", "“", "”"}
    print("\n=== ORACLE PDF COMPARISON ONLY: SMART QUOTE HORIZONTAL TRACE ===")
    print("NOTE: these PDF measurements are diagnostic only; no PDF glyph/metric is copied into TTF output.")
    quote_font_names: set[str] = set()
    quote_pages: set[int] = set()

    for pno in range(min(5, doc.page_count)):
        page = doc[pno]
        seq = []
        for span in page.get_texttrace():
            font = str(span.get("font", ""))
            size = float(span.get("size", 0.0) or 0.0)
            for raw in span.get("chars", []):
                cp, gid, origin, bbox = raw
                try:
                    ch = chr(cp)
                except Exception:
                    ch = ""
                seq.append({"ch": ch, "gid": gid, "origin": origin, "bbox": bbox, "font": font, "size": size})

        for i, cur in enumerate(seq):
            if cur["ch"] not in targets or cur["size"] <= 0:
                continue
            quote_pages.add(pno)
            quote_font_names.add(cur["font"])
            ox, oy = cur["origin"]
            x0, y0, x1, y1 = cur["bbox"]
            size = cur["size"]
            dx1000 = (x0 - ox) / size * 1000.0
            ink_w1000 = (x1 - x0) / size * 1000.0
            prev = seq[i - 1] if i else None
            nxt = seq[i + 1] if i + 1 < len(seq) else None
            print(
                f"PAGE {pno+1} QUOTE {cur['ch']!r} font={cur['font']!r} gid={cur['gid']} size={size:.4f} "
                f"origin=({ox:.3f},{oy:.3f}) bbox=({x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}) "
                f"bbox_left_minus_origin={x0-ox:+.3f}pt effective_xmin_1000={dx1000:+.1f} ink_width_1000={ink_w1000:.1f}"
            )
            if prev is not None and prev["size"] > 0:
                px, py = prev["origin"]
                dprev = (ox - px) / size * 1000.0
                print(
                    f"  PREV {prev['ch']!r} font={prev['font']!r} origin=({px:.3f},{py:.3f}) "
                    f"origin_step_prev_to_quote_1000={dprev:+.1f}"
                )
            if nxt is not None and nxt["size"] > 0:
                nx, ny = nxt["origin"]
                dnext = (nx - ox) / size * 1000.0
                print(
                    f"  NEXT {nxt['ch']!r} font={nxt['font']!r} origin=({nx:.3f},{ny:.3f}) "
                    f"origin_step_quote_to_next_1000={dnext:+.1f}"
                )

    print("\n=== ORACLE QUOTE FONT OBJECTS ===")
    print("quote texttrace fonts:", sorted(quote_font_names))
    seen_xref: set[int] = set()
    for pno in sorted(quote_pages):
        page = doc[pno]
        print(f"PAGE {pno+1} fonts:")
        for f in page.get_fonts(full=True):
            xref, ext, typ, basefont, resname, enc, *rest = f
            if xref in seen_xref:
                continue
            # Print every Type3 on a quote page, plus any font whose PDF name
            # resembles the texttrace font. This deliberately favors recall.
            relevant = typ == "Type3" or any(
                name and (name in str(basefont) or name in str(resname) or str(basefont) in name)
                for name in quote_font_names
            )
            if not relevant:
                continue
            seen_xref.add(xref)
            print(
                f"  FONT xref={xref} ext={ext!r} type={typ!r} basefont={basefont!r} "
                f"resname={resname!r} enc={enc!r}"
            )
            for key in ("FontMatrix", "FontBBox", "FirstChar", "LastChar", "Widths", "Encoding", "CharProcs", "ToUnicode"):
                try:
                    print("   ", key, doc.xref_get_key(xref, key))
                except Exception as exc:
                    print("   ", key, "ERR", exc)
            if typ == "Type3":
                try:
                    print(doc.xref_object(xref, compressed=False))
                except Exception as exc:
                    print("   object ERR", exc)
    doc.close()


def main() -> None:
    zip_path = ROOT / "inputs" / "kice09-required48.zip"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        with zipfile.ZipFile(zip_path) as zf:
            for name in ("ENGMJ.HFT", "ENSMJ.HFT", "SPSMJ.HFT"):
                zf.extract(name, td)

        # charPr 10 question-number Latin face: 한양견명조 / ENGMJ.HFT.
        qchars = "0123456789."
        qsrc = source_metrics(td / "ENGMJ.HFT", qchars)
        qttf = ttf_metrics(find_family("한양견명조"), qchars)
        assert_equal("question-number ENGMJ.HFT", qsrc, qttf)

        # Main body Latin punctuation: comma must come from ENSMJ.HFT with its
        # recovered narrow advance and original side bearing, not a CJK fallback.
        comma = ","
        csrc = source_metrics(td / "ENSMJ.HFT", comma)
        cttf = ttf_metrics(find_family("신명 중명조 - 한양문자"), comma)
        assert_equal("main-body comma ENSMJ.HFT", csrc, cttf)

        # Main Shinmyeong Myeongjo symbol face. Keep quotation marks separate in
        # the audit so a future symbol/fallback regression cannot hide among
        # unrelated brackets or wave-dash checks.
        quote_chars = "‘’“”"
        qtsrc = source_metrics(td / "SPSMJ.HFT", quote_chars)
        qtttf = ttf_metrics(find_family("신명 중명조 - 한양문자"), quote_chars)
        assert_equal("smart quotes SPSMJ.HFT", qtsrc, qtttf)

        symbol_chars = "【】～"
        ssrc = source_metrics(td / "SPSMJ.HFT", symbol_chars)
        sttf = ttf_metrics(find_family("신명 중명조 - 한양문자"), symbol_chars)
        assert_equal("SPSMJ.HFT brackets/wave-dash", ssrc, sttf)

    audit_oracle_quote_horizontal(ROOT / "original-2009-june-language.pdf")


if __name__ == "__main__":
    main()
