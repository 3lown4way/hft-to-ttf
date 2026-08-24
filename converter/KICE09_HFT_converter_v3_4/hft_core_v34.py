#!/usr/bin/env python3
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

SIGNATURE = b"Han Unified Font File 1.0\x1a"
TARGET_UPEM = 1000

# Prefix command arities.
# 0x40..0x43 are stem-hint operators.  They affect rasterization/hinting,
# not the outline geometry, so they are decoded but ignored while drawing.
ARITY = {
    0x00: 0,
    0x01: 1,
    0x02: 1,
    0x03: 2,
    0x04: 0,
    0x05: 1,
    0x06: 1,
    0x07: 2,
    0x09: 4,
    0x0A: 4,
    0x0B: 6,
    0x40: 2,
    0x42: 2,
    0x41: 6,
    0x43: 6,
}

MARKER_TO_CATEGORY = {
    0x01: "HG",
    0x02: "EN",
    0x04: "HJ",
    0x08: "JP",
    0x10: "OTHER",
    0x20: "SP",
    0x40: "USER",
}


@dataclass(frozen=True)
class HftMeta:
    path: Path
    category: str
    upem: int
    baseline: int
    start_code: int
    end_code: int
    record_count: int
    encrypted: Optional[bool] = None


@dataclass
class GlyphItem:
    char: str
    internal_code: int
    glyph: object
    advance: int
    source_upem: int
    encryption: str


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def read_num(data: bytes, i: int):
    if i >= len(data):
        raise ValueError("truncated compact number")
    b = data[i]
    i += 1
    if b <= 0x7B:
        return b, i
    if 0x7C <= b <= 0x7F:
        if i >= len(data):
            raise ValueError("truncated positive extended number")
        return 124 + 256 * (b - 0x7C) + data[i], i + 1
    if b == 0x80:
        if i + 1 >= len(data):
            raise ValueError("truncated 16-bit compact number")
        return struct.unpack_from("<h", data, i)[0], i + 2
    if 0x81 <= b <= 0x84:
        if i >= len(data):
            raise ValueError("truncated negative extended number")
        return -(124 + 256 * (0x84 - b) + data[i]), i + 1
    return b - 256, i


def decrypt_hanyang(program: bytes) -> bytes:
    """Decrypt Hanyang HFT glyph program stream.

    Reverse engineered from the supplied legacy HFT set.  The ciphertext
    byte itself participates in the state update.
    """
    state = 0xE695
    out = bytearray()
    for c in program:
        out.append(c ^ (state >> 8))
        state = ((state + c) * 0xC73E + 0x8FA0) & 0xFFFF
    return bytes(out)


def decode_program(program: bytes):
    i = 0
    ops = []
    while i < len(program):
        op = program[i]
        i += 1
        if op not in ARITY:
            raise ValueError(f"unknown HFT opcode 0x{op:02X} at {i-1}")
        vals = []
        for _ in range(ARITY[op]):
            v, i = read_num(program, i)
            vals.append(v)
        ops.append((op, vals))
        if op == 0:
            if any(program[i:]):
                raise ValueError(f"nonzero trailing bytes after END: {program[i:i+16].hex()}")
            return ops
    raise ValueError("HFT program has no END opcode")


def decode_program_auto(program: bytes):
    try:
        return decode_program(program), "direct"
    except Exception as direct_error:
        dec = decrypt_hanyang(program)
        try:
            return decode_program(dec), "hanyang-encrypted"
        except Exception:
            raise direct_error


def _draw_ops(ops, pen, y_shift: float = 0.0):
    x = 0.0
    y = 0.0
    contour_open = False
    start = None

    def ensure_contour():
        nonlocal contour_open, start
        if not contour_open:
            pen.moveTo((x, y + y_shift))
            start = (x, y)
            contour_open = True

    for op, v in ops:
        if op == 0x00:
            break
        if op in (0x40, 0x41, 0x42, 0x43):
            continue
        if op in (0x01, 0x02, 0x03):
            if contour_open:
                pen.endPath()
                contour_open = False
                start = None
            if op == 0x01:
                x += v[0]
            elif op == 0x02:
                y += v[0]
            else:
                x += v[0]
                y += v[1]
        elif op == 0x04:
            if contour_open:
                pen.closePath()
                if start is not None:
                    x, y = start
                contour_open = False
                start = None
        elif op == 0x05:
            ensure_contour()
            x += v[0]
            pen.lineTo((x, y + y_shift))
        elif op == 0x06:
            ensure_contour()
            y += v[0]
            pen.lineTo((x, y + y_shift))
        elif op == 0x07:
            ensure_contour()
            x += v[0]
            y += v[1]
            pen.lineTo((x, y + y_shift))
        elif op == 0x09:
            ensure_contour()
            c1 = (x + v[0], y)
            c2 = (c1[0] + v[1], c1[1] + v[2])
            p3 = (c2[0], c2[1] + v[3])
            pen.curveTo((c1[0], c1[1] + y_shift),(c2[0], c2[1] + y_shift),(p3[0], p3[1] + y_shift))
            x, y = p3
        elif op == 0x0A:
            ensure_contour()
            c1 = (x, y + v[0])
            c2 = (c1[0] + v[1], c1[1] + v[2])
            p3 = (c2[0] + v[3], c2[1])
            pen.curveTo((c1[0], c1[1] + y_shift),(c2[0], c2[1] + y_shift),(p3[0], p3[1] + y_shift))
            x, y = p3
        elif op == 0x0B:
            ensure_contour()
            c1 = (x + v[0], y + v[1])
            c2 = (c1[0] + v[2], c1[1] + v[3])
            p3 = (c2[0] + v[4], c2[1] + v[5])
            pen.curveTo((c1[0], c1[1] + y_shift),(c2[0], c2[1] + y_shift),(p3[0], p3[1] + y_shift))
            x, y = p3
    if contour_open:
        pen.endPath()


def ops_to_glyph(ops, source_upem: int, baseline: int, target_upem: int = TARGET_UPEM):
    scale = target_upem / float(source_upem)
    ttpen = TTGlyphPen(None)
    quad = Cu2QuPen(ttpen, max_err=max(0.5, source_upem / 1500.0), reverse_direction=False)
    pen = TransformPen(quad, (scale, 0, 0, scale, 0, 0))
    _draw_ops(ops, pen, y_shift=-baseline)
    return ttpen.glyph()


def _validate_signature(data: bytes, path: Path):
    if not data.startswith(SIGNATURE):
        raise ValueError(f"not a Han Unified HFT: {path}")


def read_meta(path: Path) -> HftMeta:
    data = path.read_bytes()
    _validate_signature(data, path)
    marker = _u16(data, 0x1A0)
    cat = MARKER_TO_CATEGORY.get(marker, f"UNKNOWN_{marker:04X}")
    upem = _u16(data, 0x17A)
    baseline = _u16(data, 0x194)
    start, end = struct.unpack_from("<HH", data, 0x204)
    if cat in ("HG", "HJ", "JP", "SP"):
        count = _u16(data, 0x224)
    elif cat in ("EN", "OTHER"):
        count = end - start + 1
    elif cat == "USER":
        u_start = _u16(data, 0x22C) if len(data) >= 0x234 else 0
        u_end = _u16(data, 0x22E) if len(data) >= 0x234 else 0
        u_count = _u16(data, 0x230) if len(data) >= 0x234 else 0
        u_upem = _u16(data, 0x232) if len(data) >= 0x234 else 0
        if 0 < u_count <= 0x1000 and u_start <= u_end and u_end - u_start + 1 >= u_count:
            start, end, count = u_start, u_end, u_count
            if 256 <= u_upem <= 4096:
                upem = u_upem
        else:
            count = 0
    else:
        count = 0
    return HftMeta(path, cat, upem, baseline, start, end, count)


def find_variable_offset_base(data: bytes, count: int, search_start: int = 0x220, search_end: int = 0x5000):
    need = min(count, 8)
    candidates = []
    upper = min(len(data) - 4 * need, search_end)
    for pos in range(search_start, upper):
        try:
            vals = [_u32(data, pos + 4 * j) for j in range(need)]
        except struct.error:
            continue
        if not (count * 4 <= vals[0] <= count * 4 + 4096):
            continue
        if not all(vals[j] <= vals[j + 1] for j in range(len(vals) - 1)):
            continue
        if vals[-1] > len(data) - pos:
            continue
        ok = 0
        for rel in vals:
            o = pos + rel
            if o + 10 <= len(data):
                L = _u16(data, o + 8)
                if L <= 16384 and o + 10 + L <= len(data):
                    ok += 1
        if ok >= max(4, need - 1):
            candidates.append((abs(vals[0] - count * 4), pos))
    return min(candidates)[1] if candidates else None


def find_embedded_wansung_block(data: bytes):
    n = len(data)
    for b in range(0x200, max(0x200, n - 0x20)):
        if b + 0x1E > n:
            break
        try:
            block_size = _u32(data, b); marker = _u16(data, b + 0x04); count = _u16(data, b + 0x0A); upem = _u16(data, b + 0x0C)
        except struct.error:
            continue
        if block_size != n - b or marker != 0x0011 or count != 2350:
            continue
        if not (256 <= upem <= 4096):
            continue
        base = b + 0x1A
        if base + 4 * count > n or _u32(data, base) != 4 * count:
            continue
        prev = -1; ok = True
        for i in range(count):
            rel = _u32(data, base + 4 * i)
            if rel < 4 * count or rel < prev or base + rel + 2 > n:
                ok = False; break
            prev = rel
        if not ok:
            continue
        last_rel = _u32(data, base + 4 * (count - 1)); last_o = base + last_rel; last_len = _u16(data, last_o)
        if last_o + 2 + last_len != n:
            continue
        return {"block_offset": b,"base": base,"count": count,"upem": upem}
    return None


def _embedded_wansung_records(data: bytes, block):
    base = block["base"]; count = block["count"]; upem = block["upem"]
    for i in range(count):
        rel = _u32(data, base + 4 * i); o = base + rel; L = _u16(data, o); prog = data[o + 2:o + 2 + L]
        if len(prog) != L:
            raise ValueError(f"truncated embedded Wansung program {i}")
        yield i, i, upem, prog


def _user_single_record(data: bytes, meta: HftMeta):
    if meta.record_count != 1:
        raise NotImplementedError(f"{meta.path.name}: USER parser currently supports the validated single-glyph layout only (count={meta.record_count})")
    rec_base = 0x23C
    if rec_base + 4 > len(data):
        raise ValueError(f"{meta.path.name}: truncated USER record header")
    rel_to_len = _u32(data, rec_base); len_off = rec_base + rel_to_len
    if not (rec_base + 4 <= len_off <= min(len(data) - 2, rec_base + 0x400)):
        raise ValueError(f"{meta.path.name}: implausible USER program-length offset 0x{len_off:X}")
    L = _u16(data, len_off); prog = data[len_off + 2:len_off + 2 + L]
    if len(prog) != L:
        raise ValueError(f"{meta.path.name}: truncated USER outline program")
    ops = decode_program(prog)
    if not any(op in (0x05, 0x06, 0x07, 0x09, 0x0A, 0x0B) for op, _ in ops):
        raise ValueError(f"{meta.path.name}: USER record has no outline operations")
    yield 0, meta.start_code, meta.upem, prog


def user_code_to_pua(code: int, start_code: int) -> str:
    idx = max(0, code - start_code); cp = 0xE000 + idx
    if cp > 0xF8FF:
        raise ValueError("too many USER glyphs for BMP PUA fallback")
    return chr(cp)


def _program_records(path: Path):
    data = path.read_bytes(); meta = read_meta(path); cat = meta.category
    if cat in ("EN", "OTHER"):
        count = meta.record_count; base = find_variable_offset_base(data, count)
        if base is None:
            raise ValueError(f"cannot find EN-like offset table in {path.name}")
        widths = [_u16(data, 0x20A + 2 * i) for i in range(count)]
        for i in range(count):
            rel = _u32(data, base + 4 * i); o = base + rel
            if o + 10 > len(data): raise ValueError(f"truncated glyph record {i} in {path.name}")
            L = _u16(data, o + 8); prog = data[o + 10:o + 10 + L]
            if len(prog) != L: raise ValueError(f"truncated glyph program {i} in {path.name}")
            yield i, meta.start_code + i, widths[i], prog
        return
    if cat == "HG":
        count = meta.record_count
        if count == 2350:
            base = 0x234
        else:
            embedded = find_embedded_wansung_block(data)
            if embedded is not None:
                yield from _embedded_wansung_records(data, embedded); return
            key_base = 0x234; base = key_base + 2 * count; first_rel = _u32(data, base) if base + 4 <= len(data) else 0
            if first_rel != 4 * count:
                raise NotImplementedError(f"{path.name}: unknown special HG layout (count={count}, first_rel=0x{first_rel:X})")
            for i in range(count):
                code = _u16(data, key_base + 2 * i); rel = _u32(data, base + 4 * i); o = base + rel
                if o + 2 > len(data): raise ValueError(f"truncated special HG record {i} in {path.name}")
                L = _u16(data, o); prog = data[o + 2:o + 2 + L]
                if len(prog) != L: raise ValueError(f"truncated special HG program {i} in {path.name}")
                yield i, code, meta.upem, prog
            return
    elif cat in ("HJ", "JP", "SP"):
        base = 0x230; count = meta.record_count
    elif cat == "USER":
        yield from _user_single_record(data, meta); return
    else:
        raise NotImplementedError(f"{path.name}: category {cat} is not supported")
    for i in range(count):
        rel = _u32(data, base + 4 * i); o = base + rel
        if o + 2 > len(data): raise ValueError(f"truncated glyph record {i} in {path.name}")
        L = _u16(data, o); prog = data[o + 2:o + 2 + L]
        if len(prog) != L: raise ValueError(f"truncated glyph program {i} in {path.name}")
        yield i, meta.start_code + i, meta.upem, prog


def _wansung_hangul_chars():
    return [bytes([hi, lo]).decode("euc_kr") for hi in range(0xB0, 0xC9) for lo in range(0xA1, 0xFF)]


def _ksc_hanja_chars():
    return [bytes([hi, lo]).decode("euc_kr") for hi in range(0xCA, 0xFE) for lo in range(0xA1, 0xFF)]


def hnc_symbol_to_unicode(code: int):
    if code < 0x3401: return None
    idx = code - 0x3401; row, col = divmod(idx, 0x60)
    if col >= 94: return None
    hi, lo = 0xA1 + row, 0xA1 + col
    if not (0xA1 <= hi <= 0xFE): return None
    try: return bytes([hi, lo]).decode("euc_kr")
    except UnicodeDecodeError: return None


def hnc_other_to_unicode(code: int):
    cp = None
    if 0x0400 <= code <= 0x0458: cp = 0x0250 + (code - 0x0400)
    elif 0x0460 <= code <= 0x048E: cp = 0x02B0 + (code - 0x0460)
    elif 0x0490 <= code <= 0x0499: cp = 0x02E0 + (code - 0x0490)
    elif 0x04A0 <= code <= 0x04E5: cp = 0x0300 + (code - 0x04A0)
    elif code == 0x04E6: cp = 0x0360
    elif code == 0x04E7: cp = 0x0361
    return chr(cp) if cp is not None else None


def _char_for_record(meta: HftMeta, index: int, code: int):
    if meta.category == "HG":
        chars = _wansung_hangul_chars(); return chars[index] if index < len(chars) else None
    if meta.category == "HJ":
        chars = _ksc_hanja_chars(); return chars[index] if index < len(chars) else None
    if meta.category == "EN": return chr(code) if 0x20 <= code <= 0x7E else None
    if meta.category == "OTHER": return hnc_other_to_unicode(code)
    if meta.category == "SP": return hnc_symbol_to_unicode(code)
    if meta.category == "USER": return user_code_to_pua(code, meta.start_code)
    return None


def iter_unicode_glyphs(path: Path,target_upem: int = TARGET_UPEM,code_overrides: Optional[dict[int, str]] = None,code_aliases: Optional[dict[int, Iterable[str]]] = None) -> Iterator[GlyphItem]:
    meta = read_meta(path)
    if meta.category not in ("HG", "EN", "HJ", "OTHER", "SP", "USER"):
        raise NotImplementedError(f"{path.name}: Unicode mapping for category {meta.category} is not implemented in v3.4")
    code_overrides = code_overrides or {}; code_aliases = code_aliases or {}
    for index, code, advance, raw_prog in _program_records(path):
        ch = code_overrides.get(code, _char_for_record(meta, index, code)); aliases = list(code_aliases.get(code, ()))
        if not ch and not aliases: continue
        ops, encryption = decode_program_auto(raw_prog); glyph = ops_to_glyph(ops, meta.upem, meta.baseline, target_upem); adv = int(round(advance * target_upem / meta.upem))
        if ch: yield GlyphItem(ch, code, glyph, adv, meta.upem, encryption)
        for alias in aliases:
            if alias and alias != ch: yield GlyphItem(alias, code, glyph, adv, meta.upem, encryption)


def iter_raw_records(path: Path):
    meta = read_meta(path)
    for index, code, advance, raw_prog in _program_records(path):
        ops, encryption = decode_program_auto(raw_prog); yield index, code, advance, ops, encryption


def probe(path: Path):
    meta = read_meta(path); data = path.read_bytes(); embedded = find_embedded_wansung_block(data) if meta.category == "HG" else None; effective_count = embedded["count"] if embedded is not None else meta.record_count
    result = {"file": path.name,"category": meta.category,"upem": meta.upem,"baseline": meta.baseline,"start_code": f"0x{meta.start_code:04X}","end_code": f"0x{meta.end_code:04X}","record_count": meta.record_count,"effective_outline_records": effective_count,"direct": 0,"hanyang_encrypted": 0,"fail": 0,"hint_ops": {"40": 0, "41": 0, "42": 0, "43": 0}}
    if embedded is not None:
        result["embedded_wansung_block"] = {"block_offset": f"0x{embedded['block_offset']:X}","offset_table_base": f"0x{embedded['base']:X}","count": embedded["count"],"upem": embedded["upem"]}
    if meta.category == "OTHER":
        mapped = sum(1 for c in range(meta.start_code, meta.end_code + 1) if hnc_other_to_unicode(c)); result["unicode_mapping"] = f"libhwp hnc2uni page0 exact slice / mapped={mapped}, undefined={meta.record_count-mapped}"
    if meta.category == "USER" and meta.record_count:
        result["unicode_fallback"] = f"U+E000..U+{0xE000 + meta.record_count - 1:04X} (converter-local generic fallback; document override supported)"
    try:
        recs = _program_records(path)
        for _, _, _, raw in recs:
            try:
                ops, enc = decode_program_auto(raw)
                if enc == "direct": result["direct"] += 1
                else: result["hanyang_encrypted"] += 1
                for op, _ in ops:
                    if op in (0x40, 0x41, 0x42, 0x43): result["hint_ops"][f"{op:02X}"] += 1
            except Exception: result["fail"] += 1
    except Exception as e:
        result["layout_error"] = str(e)
    return result
