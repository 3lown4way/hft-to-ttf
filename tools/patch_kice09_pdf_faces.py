#!/usr/bin/env python3
"""KICE09 PDF-oracle face repairs for the rhwp smoke test.

Uses the official 2009-06 KICE PDF Type3 fonts as the visual oracle.

Repairs/builds:
* Hanyang GyeonMyeongjo regular: T4 glyphs (question numbers 0-9, '.', and
  the same face's Korean glyphs used by '제 1 교시').
* ShinMyeong JungMyeongjo composite bold faces: T8 Hangul + T9 punctuation.
* ShinMyeong ShinGraphic bold face: T3 header glyphs ('언어 영역').

The source HWP stores bold as a charPr flag while keeping the same HFT face.
Therefore a real Bold TTF sibling is generated instead of substituting a
heavier, different HFT family.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys

from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from pypdf import PdfReader


def _decode_pdf_unicode(hex_text: str) -> str:
    raw = bytes.fromhex(hex_text)
    # ToUnicode destinations are UTF-16BE code units.
    try:
        return raw.decode("utf-16-be")
    except UnicodeDecodeError:
        return ""


def parse_tounicode(data: bytes) -> dict[int, str]:
    text = data.decode("latin1")
    out: dict[int, str] = {}

    # bfchar blocks
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            ch = _decode_pdf_unicode(dst)
            if ch:
                out[int(src, 16)] = ch

    # bfrange blocks; KICE file uses scalar starts, but also accept arrays.
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
                line,
            )
            if m:
                lo, hi, dst = (int(m.group(i), 16) for i in range(1, 4))
                dst_len = len(m.group(3))
                for off, code in enumerate(range(lo, hi + 1)):
                    val = dst + off
                    ch = _decode_pdf_unicode(f"{val:0{dst_len}X}")
                    if ch:
                        out[code] = ch
                continue
            m = re.match(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]",
                line,
            )
            if m:
                lo, hi = int(m.group(1), 16), int(m.group(2), 16)
                vals = re.findall(r"<([0-9A-Fa-f]+)>", m.group(3))
                for code, dst in zip(range(lo, hi + 1), vals):
                    ch = _decode_pdf_unicode(dst)
                    if ch:
                        out[code] = ch
    return out


def encoding_names(font) -> dict[int, str]:
    enc = font["/Encoding"].get_object()
    diffs = enc.get("/Differences", [])
    out: dict[int, str] = {}
    code = None
    for item in diffs:
        if isinstance(item, int):
            code = item
        elif code is not None:
            out[code] = str(item)
            code += 1
    return out


def parse_type3_glyph(stream: bytes):
    toks = stream.decode("latin1").split()
    pen_out = TTGlyphPen(None)
    pen = Cu2QuPen(pen_out, max_err=0.7, reverse_direction=False)
    nums: list[float] = []
    advance = None

    def take(n: int):
        if len(nums) < n:
            raise ValueError(f"Type3 operand underflow for {n}: {nums}")
        vals = nums[-n:]
        del nums[-n:]
        return vals

    for tok in toks:
        try:
            nums.append(float(tok))
            continue
        except ValueError:
            pass

        if tok == "d1":
            vals = take(6)
            advance = int(round(vals[0]))
            nums.clear()
        elif tok == "m":
            x, y = take(2)
            pen.moveTo((x, y))
        elif tok == "l":
            x, y = take(2)
            pen.lineTo((x, y))
        elif tok == "c":
            x1, y1, x2, y2, x3, y3 = take(6)
            pen.curveTo((x1, y1), (x2, y2), (x3, y3))
        elif tok == "h":
            try:
                pen.closePath()
            except Exception:
                pass
        elif tok in {"f", "B"}:
            nums.clear()
        else:
            # KICE Type3 oracle fonts used here contain only d1/m/l/c/h/f/B.
            nums.clear()

    glyph = pen_out.glyph()
    return advance, glyph


def extract_type3(reader: PdfReader, page_index: int, resource_name: str):
    page = reader.pages[page_index]
    fonts = page["/Resources"]["/Font"]
    font = fonts[resource_name].get_object()
    cmap = parse_tounicode(font["/ToUnicode"].get_object().get_data())
    names = encoding_names(font)
    widths = list(font["/Widths"].get_object())
    first = int(font["/FirstChar"])
    procs = font["/CharProcs"].get_object()

    out = {}
    for code, ch in cmap.items():
        if len(ch) != 1 or code not in names:
            continue
        name = names[code]
        if name not in procs:
            continue
        parsed_adv, glyph = parse_type3_glyph(procs[name].get_object().get_data())
        idx = code - first
        if not (0 <= idx < len(widths)):
            continue
        adv = int(round(float(widths[idx])))
        if parsed_adv is not None and abs(parsed_adv - adv) > 1:
            raise ValueError(f"advance mismatch {resource_name} {ch}: {parsed_adv} vs {adv}")
        out[ord(ch)] = (adv, glyph)
    return out


def patch_glyphs(font: TTFont, glyph_map: dict[int, tuple[int, object]]) -> int:
    cmap = font.getBestCmap() or {}
    count = 0
    for cp, (advance, glyph) in glyph_map.items():
        name = cmap.get(cp)
        if not name or name not in font["glyf"]:
            continue
        g = glyph
        g.recalcBounds(font["glyf"])
        font["glyf"][name] = g
        font["hmtx"][name] = (advance, g.xMin if hasattr(g, "xMin") else 0)
        count += 1
    return count


def get_name(font: TTFont, name_id: int) -> str | None:
    for n in font["name"].names:
        if n.nameID == name_id:
            try:
                return n.toUnicode()
            except Exception:
                pass
    return None


def set_name(font: TTFont, name_id: int, text: str) -> None:
    seen = False
    for n in font["name"].names:
        if n.nameID != name_id:
            continue
        seen = True
        if n.isUnicode():
            n.string = text.encode("utf-16-be")
        else:
            try:
                n.string = text.encode("latin1")
            except UnicodeEncodeError:
                # Do not add invalid legacy-platform records for Korean names.
                pass
    if not seen:
        font["name"].setName(text, name_id, 3, 1, 0x409)


def make_bold_sibling(src: Path, glyph_maps: list[dict[int, tuple[int, object]]]) -> Path:
    font = TTFont(src)
    n = 0
    for gm in glyph_maps:
        n += patch_glyphs(font, gm)

    family = get_name(font, 16) or get_name(font, 1) or src.stem
    ps = get_name(font, 6) or re.sub(r"\s+", "", src.stem)
    ps = re.sub(r"-Regular$", "", ps) + "-Bold"

    # Keep the same family so fontdb can resolve CSS weight=700 to this sibling.
    set_name(font, 1, family)
    set_name(font, 2, "Bold")
    set_name(font, 4, f"{family} Bold")
    set_name(font, 6, ps)
    if any(x.nameID == 16 for x in font["name"].names):
        set_name(font, 16, family)
    set_name(font, 17, "Bold")

    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.usWeightClass = 700
        os2.fsSelection = (os2.fsSelection | 0x20) & ~0x40  # BOLD on, REGULAR off
    if "head" in font:
        font["head"].macStyle |= 0x1

    out = src.with_name(src.stem + "-Bold.ttf")
    font.save(out)
    print(f"built bold face: {out.name}, oracle glyphs={n}, family={family!r}")
    return out


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_kice09_pdf_faces.py <runtime_fonts> <official_pdf>")
    root = Path(sys.argv[1])
    pdf = Path(sys.argv[2])
    reader = PdfReader(str(pdf))

    # Page 2 contains all shared Type3 resources used by pages 1-5.
    t4 = extract_type3(reader, 1, "/T4")  # question-number / Hanyang GMJ
    t8 = extract_type3(reader, 1, "/T8")  # bold ShinMyeong JungMyeongjo Hangul
    t9 = extract_type3(reader, 1, "/T9")  # bold punctuation / symbols
    t3 = extract_type3(reader, 1, "/T3")  # bold ShinGraphic header

    qfont = root / "한양견명조.ttf"
    if not qfont.exists():
        raise SystemExit(f"missing question-number composite: {qfont}")
    f = TTFont(qfont)
    qn = patch_glyphs(f, t4)
    f.save(qfont)
    print(f"patched T4 question-number face: {qfont.name}, glyphs={qn}")

    # Exact PDF-oracle bold glyphs for the main JungMyeongjo composites.
    for filename in ("신명중명조-한양문자.ttf", "신명중명조-한양영문.ttf"):
        p = root / filename
        if p.exists():
            make_bold_sibling(p, [t8, t9])

    sg = root / "신명신그래픽.ttf"
    if sg.exists():
        make_bold_sibling(sg, [t3])


if __name__ == "__main__":
    main()
