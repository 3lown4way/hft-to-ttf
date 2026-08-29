#!/usr/bin/env python3
"""Use the embedded font's own U+0020 advance when rhwp measures text.

The embedded metric table generated from KICE HFT fonts already contains the
real space advance.  For example, `신명 중명조` has U+0020 = 400/1000 em.
The upstream renderer currently discards that value and substitutes em/2
(500/1000) unless a narrowly measured Hancom-PDF override exists.  That makes
spaces 25% too wide and changes fresh line breaking for HWP paragraphs that do
not carry PARA_LINE_SEG (notably KICE question 12 <보기> and reconstructed body
paragraphs).

Keep explicit `hancom_pdf_space_width` overrides authoritative, then use the
font metric's own space advance, and only use half-em when neither exists.
"""
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_embedded_space_metric.py <rhwp-source-root>")

    root = Path(sys.argv[1])
    target = root / "src/renderer/layout/text_measurement.rs"
    text = target.read_text(encoding="utf-8")

    old = """    let w = if c == ' ' {\n        hancom_pdf_space_width(primary_name, font_size).unwrap_or(mm.metric.em_size / 2)\n    } else {\n"""
    new = """    let w = if c == ' ' {\n        // JH/KICE: embedded HFT-derived metrics carry the actual word-space\n        // advance.  Do not discard it in favor of a generic half-em.\n        // Explicit Hancom-PDF measurements remain the highest-priority override.\n        hancom_pdf_space_width(primary_name, font_size)\n            .or_else(|| mm.metric.get_width(' '))\n            .unwrap_or(mm.metric.em_size / 2)\n    } else {\n"""

    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one embedded-space block, found {count}")

    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {target}")


if __name__ == "__main__":
    main()
