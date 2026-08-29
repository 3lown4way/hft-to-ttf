#!/usr/bin/env python3
"""Use the embedded font's own U+0020 advance when rhwp measures text.

The KICE HFT-derived metric table already contains the real U+0020 advance
(`신명 중명조` = 400/1000 em).  rhwp's generic half-em fallback discards that
value and widens every word space to 500/1000 em, changing fresh line breaking.

This script runs *after* patch_rhwp_hft_native.py, which adapts the upstream
MetricMatch consumer from `mm.metric.*` to the generated DB's direct `mm.*` API.
Explicit Hancom-PDF space overrides keep priority; the embedded metric is the
next source of truth; half-em remains only the last fallback.
"""
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_embedded_space_metric.py <rhwp-source-root>")

    root = Path(sys.argv[1])
    target = root / "src/renderer/layout/text_measurement.rs"
    text = target.read_text(encoding="utf-8")

    old = """    let w = if c == ' ' {\n        hancom_pdf_space_width(primary_name, font_size).unwrap_or(mm.em_size / 2)\n    } else {\n"""
    new = """    let w = if c == ' ' {\n        // KICE/HFT: use the font's encoded word-space advance when present.\n        hancom_pdf_space_width(primary_name, font_size)\n            .or_else(|| mm.get_width(' '))\n            .unwrap_or(mm.em_size / 2)\n    } else {\n"""

    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one adapted embedded-space block, found {count}")

    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {target}")


if __name__ == "__main__":
    main()
