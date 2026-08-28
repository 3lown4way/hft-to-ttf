#!/usr/bin/env python3
"""Use the source-derived HFT runtime TTF families when they are available.

The JH runtime font package contains converted faces whose Unicode name tables
preserve the original Hancom HFT family names (e.g. `신명 중명조`). The generic
upstream substitution table maps those source HFT names to unrelated installed
HY/system faces. On Linux direct-Skia that can leave the resolved family absent
and paint with Noto fallback, while the generated JH font-metrics DB is keyed by
the converted source family.

This patch only changes HFT names for which the JH runtime package contains a
matching converted face. It does not use document charPr IDs and therefore is
not the KICE09 document-scoped composite bridge.
"""
from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_runtime_hft_families.py <rhwp-source-root>")
    root = Path(sys.argv[1])
    p = root / "src/renderer/style_resolver.rs"
    text = p.read_text(encoding="utf-8")

    direct = {
        '        "신명 태고딕" => Some("HY중고딕"),\n':
            '        "신명 태고딕" => Some("신명 태고딕"),\n',
        '        "신명 견명조" => Some("HY견명조"),\n':
            '        "신명 견명조" => Some("신명 견명조"),\n',
        '        "신명 중고딕" => Some("HY중고딕"),\n':
            '        "신명 중고딕" => Some("신명 중고딕"),\n',
    }
    for old, new in direct.items():
        text = replace_once(text, old, new, old.strip())

    text = replace_once(
        text,
        '''        "신명 세명조"\n        | "신명 신명조"\n        | "신명 신신명조"\n        | "신명 중명조"\n        | "신명 순명조"\n        | "신명 신문명조" => Some("HY신명조"),\n''',
        '''        "신명 중명조" => Some("신명 중명조"),\n        "신명 세명조"\n        | "신명 신명조"\n        | "신명 신신명조"\n        | "신명 순명조"\n        | "신명 신문명조" => Some("HY신명조"),\n''',
        "신명 중명조 direct runtime family",
    )

    text = replace_once(
        text,
        '        "신명 세고딕" | "신명 디나루" | "신명 세나루" => Some("돋움"),\n',
        '        "신명 디나루" => Some("신명 디나루"),\n        "신명 세고딕" | "신명 세나루" => Some("돋움"),\n',
        "신명 디나루 direct runtime family",
    )

    text = replace_once(
        text,
        '''        "#세고딕" | "#신세고딕" | "#중고딕" | "#태고딕" | "#신문고딕" | "#신문태고" | "#세나루"\n        | "#신세나루" | "#디나루" | "#신디나루" => Some("돋움"),\n''',
        '''        "#태고딕" => Some("#태고딕"),\n        "#세고딕" | "#신세고딕" | "#중고딕" | "#신문고딕" | "#신문태고" | "#세나루"\n        | "#신세나루" | "#디나루" | "#신디나루" => Some("돋움"),\n''',
        "#태고딕 direct runtime family",
    )

    text = replace_once(
        text,
        '        "신명 신그래픽" | "강낭콩" => Some("굴림"),\n',
        '        "신명 신그래픽" => Some("신명 신그래픽"),\n        "강낭콩" => Some("굴림"),\n',
        "신명 신그래픽 direct runtime family",
    )

    text = replace_once(
        text,
        '        "신명 궁서" | "#궁서" => Some("궁서"),\n',
        '        "신명 궁서" => Some("신명 궁서"),\n        "#궁서" => Some("궁서"),\n',
        "신명 궁서 direct runtime family",
    )

    p.write_text(text, encoding="utf-8")
    print(f"patched {p}")


if __name__ == "__main__":
    main()
