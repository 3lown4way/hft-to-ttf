#!/usr/bin/env python3
"""Teach rhwp how legacy Hancom HFT faux-bold is painted.

The 2009 KICE PDF is used only as a rendering oracle.  For legacy HFT-derived
faces, its regular and bold Type3 glyph programs have identical geometry; the
bold program changes only the PDF paint operator from fill (f) to fill+stroke
(B).  Therefore bold must keep the Regular HFT outline and metrics and add a
thin same-colour stroke at paint time, instead of selecting/synthesising a
separate bold outline.

The runtime families below are composites reconstructed solely from the source
HFT fontRefs.  0.16 SVG px corresponds to the legacy PDF's 1-unit text stroke
under its ~0.1199 pt/user-unit page transform at rhwp's 96 dpi SVG scale.
"""
from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    s = path.read_text(encoding="utf-8")
    if old not in s:
        raise SystemExit(f"{label}: target block not found in {path}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "rhwp-src")
    p = root / "src/renderer/svg.rs"

    # Family provenance helper.  These are the source-HFT composite faces made
    # by this repository, not arbitrary system fonts with similar names.
    anchor = '''const TEXT_MARK_CLIP_RIGHT_PAD: f64 = 48.0;\n'''
    helper = '''const TEXT_MARK_CLIP_RIGHT_PAD: f64 = 48.0;\n\n/// Legacy Hancom HFT-derived runtime faces.  Their HWP bold flag is rendered\n/// by painting the Regular outline with fill+stroke; metrics remain Regular.\nfn is_legacy_hft_runtime_family(name: &str) -> bool {\n    matches!(\n        name,\n        "#태고딕"\n            | "신명 견명조"\n            | "신명 궁서"\n            | "신명 디나루"\n            | "신명 신그래픽"\n            | "신명 중고딕 - 혼합"\n            | "신명 중고딕"\n            | "신명 중명조 - 한양문자"\n            | "신명 중명조 - 한양영문"\n            | "신명 중명조"\n            | "신명 태고딕"\n            | "한양견명조"\n            | "한양중고딕"\n    )\n}\n\nconst LEGACY_HFT_BOLD_STROKE_PX: f64 = 0.16;\n'''
    replace_once(p, anchor, helper, "legacy HFT family helper")

    # Do not ask the embedder for a separate Bold face for these families.
    old = '''                    if run.style.is_visually_bold() {\n                        self.font_bold_families\n                            .insert(run.style.font_family.clone());\n                    }\n'''
    new = '''                    if run.style.is_visually_bold()\n                        && !is_legacy_hft_runtime_family(&run.style.font_family)\n                    {\n                        self.font_bold_families\n                            .insert(run.style.font_family.clone());\n                    }\n'''
    replace_once(p, old, new, "bold family collection")

    # Normal text path: keep Regular face/metrics and add same-colour stroke.
    old = '''        // 공통 스타일 속성 구성 (fill 제외 — 그림자/원본에서 각각 설정)\n        let mut base_attrs = format!("font-size=\\\"{}\\\"", font_size);\n        if style.is_visually_bold() {\n            base_attrs.push_str(" font-weight=\\\"bold\\\"");\n        } else if style.is_medium_weight() {\n            base_attrs.push_str(" font-weight=\\\"500\\\"");\n        }\n        if style.italic {\n            base_attrs.push_str(" font-style=\\\"italic\\\"");\n        }\n        let attrs_for_cluster = |cluster_str: &str, fill: &str| {\n            let cluster_font_family = if super::contains_old_hangul_jamo(cluster_str) {\n                &old_hangul_font_family\n            } else {\n                &font_family\n            };\n            format!(\n                "font-family=\\\"{}\\\" {} fill=\\\"{}\\\"",\n                escape_xml(cluster_font_family),\n                base_attrs,\n                fill,\n            )\n        };\n'''
    new = '''        // 공통 스타일 속성 구성 (fill 제외 — 그림자/원본에서 각각 설정)\n        // Legacy HFT bold is not a separate outline.  Hancom paints the same\n        // Regular glyph with fill+stroke, so keep Regular font metrics/face.\n        let legacy_hft_bold =\n            style.is_visually_bold() && is_legacy_hft_runtime_family(&style.font_family);\n        let mut base_attrs = format!("font-size=\\\"{}\\\"", font_size);\n        if style.is_visually_bold() && !legacy_hft_bold {\n            base_attrs.push_str(" font-weight=\\\"bold\\\"");\n        } else if style.is_medium_weight() {\n            base_attrs.push_str(" font-weight=\\\"500\\\"");\n        }\n        if style.italic {\n            base_attrs.push_str(" font-style=\\\"italic\\\"");\n        }\n        let attrs_for_cluster = |cluster_str: &str, fill: &str| {\n            let cluster_font_family = if super::contains_old_hangul_jamo(cluster_str) {\n                &old_hangul_font_family\n            } else {\n                &font_family\n            };\n            let mut attrs = format!(\n                "font-family=\\\"{}\\\" {} fill=\\\"{}\\\"",\n                escape_xml(cluster_font_family),\n                base_attrs,\n                fill,\n            );\n            if legacy_hft_bold {\n                attrs.push_str(&format!(\n                    " stroke=\\\"{}\\\" stroke-width=\\\"{:.2}\\\"",\n                    fill, LEGACY_HFT_BOLD_STROKE_PX\n                ));\n            }\n            attrs\n        };\n'''
    replace_once(p, old, new, "legacy HFT fill+stroke text")

    # Rotated text uses a separate direct-attribute path; preserve the same rule.
    old = '''                    if run.style.is_visually_bold() {\n                        attrs.push_str(" font-weight=\\\"bold\\\"");\n                    } else if run.style.is_medium_weight() {\n                        attrs.push_str(" font-weight=\\\"500\\\"");\n                    }\n'''
    new = '''                    let legacy_hft_bold = run.style.is_visually_bold()\n                        && is_legacy_hft_runtime_family(&run.style.font_family);\n                    if run.style.is_visually_bold() && !legacy_hft_bold {\n                        attrs.push_str(" font-weight=\\\"bold\\\"");\n                    } else if run.style.is_medium_weight() {\n                        attrs.push_str(" font-weight=\\\"500\\\"");\n                    }\n                    if legacy_hft_bold {\n                        attrs.push_str(&format!(\n                            " stroke=\\\"{}\\\" stroke-width=\\\"{:.2}\\\"",\n                            color, LEGACY_HFT_BOLD_STROKE_PX\n                        ));\n                    }\n'''
    replace_once(p, old, new, "legacy HFT rotated bold")

    print("patched rhwp legacy HFT bold as Regular fill+stroke")


if __name__ == "__main__":
    main()
