#!/usr/bin/env python3
"""Keep source-derived HFT faces in rhwp when matching runtime TTFs exist.

The stock rhwp v0.8.4 substitution table maps legacy HFT names such as
"신명 중명조" to modern aliases such as "HY신명조". That is sensible for a
normal system-font renderer, but wrong for this project because runtime_fonts
contains TTFs reconstructed directly from the source HFTs.

This patch runs after patch_rhwp_hft_native.py and makes those reconstructed
families win before the stock substitution table. It deliberately does not
change CharShape size/ratio/spacing or document layout.
"""
from pathlib import Path
import sys


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "rhwp-src")
    p = root / "src/renderer/style_resolver.rs"
    s = p.read_text(encoding="utf-8")

    old = '''fn resolve_hft_font(name: &str, lang_index: usize) -> Option<&'static str> {\n    // === 직접 TTF 매핑 (모든 언어 공통) ===\n'''
    new = '''fn resolve_hft_font(name: &str, lang_index: usize) -> Option<&'static str> {\n    // Project runtime: these families are TTF composites reconstructed directly\n    // from the source HFT files. Preserve them instead of substituting to HY*/\n    // system fonts, otherwise native-skia falls back to Noto and changes glyphs.\n    let source_hft_runtime = match name {\n        "#태고딕" => Some("#태고딕"),\n        "신명 견명조" => Some("신명 견명조"),\n        "신명 궁서" => Some("신명 궁서"),\n        "신명 디나루" => Some("신명 디나루"),\n        "신명 신그래픽" => Some("신명 신그래픽"),\n        "신명 중고딕" => Some("신명 중고딕"),\n        "신명 중명조" => Some("신명 중명조"),\n        "신명 태고딕" => Some("신명 태고딕"),\n        // The symbol slot of this official face is TETGRSP.HFT, already carried\n        // by the source-derived 신명태고딕 composite. This keeps ⓐ~ⓔ out of Noto.\n        "신명 태그래픽" => Some("신명 태고딕"),\n        "한양견명조" => Some("한양견명조"),\n        "한양중고딕" => Some("한양중고딕"),\n        // The source package provides 한양신명조 script glyphs inside the\n        // reconstructed 중명조 composites. This alias is used for Latin/other/\n        // symbol slots in the official KICE template, not for its Hangul body.\n        "한양신명조" => Some("신명 중명조 - 한양영문"),\n        // Legacy Japanese slot paired with the same 중명조 body family.\n        "신명 신명조" => Some("신명 중명조 - 한양문자"),\n        // USER-script 명조 is covered by the source-derived 중명조 composite.\n        "명조" => Some("신명 중명조"),\n        _ => None,\n    };\n    if source_hft_runtime.is_some() {\n        return source_hft_runtime;\n    }\n\n    // === 직접 TTF 매핑 (모든 언어 공통) ===\n'''
    if old not in s:
        raise SystemExit("resolve_hft_font insertion point not found")
    s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")
    print("patched rhwp to preserve source-derived official HFT runtime faces")


if __name__ == "__main__":
    main()
