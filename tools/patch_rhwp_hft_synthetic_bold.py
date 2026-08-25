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

Direct Skia has a second legacy-font issue on Linux: Typeface::family_name()
can lose Korean family names and return strings containing '?'.  The TTF name
table itself is intact, so custom font lookup must also be keyed by the Unicode
family names parsed directly from the TTF.  This is a generic font-resolution
fix, not a codepoint-specific glyph workaround.
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

    # DirectLayer custom-font loading: on Linux Skia may decode a Korean
    # Typeface::family_name() as question marks even though the TTF's Unicode
    # name table is correct.  Keep Skia's own key, but additionally alias the
    # same Typeface by all Unicode FAMILY records parsed from the TTF bytes.
    # This keeps --font-path resolution generic and preserves the font's cmap,
    # outlines, and hmtx untouched.
    p = root / "src/renderer/skia/renderer.rs"
    old = '''                    if let Ok(data) = std::fs::read(&path) {\n                        let skia_data = skia_safe::Data::new_copy(&data);\n                        if let Some(typeface) = font_mgr.new_from_data(&skia_data, None) {\n                            let family = typeface.family_name();\n                            into.entry(family).or_insert(typeface);\n                        }\n                    }\n'''
    new = '''                    if let Ok(data) = std::fs::read(&path) {\n                        let mut unicode_family_aliases = Vec::<String>::new();\n                        if let Ok(face) = ttf_parser::Face::parse(&data, 0) {\n                            for name in face.names() {\n                                if name.name_id == ttf_parser::name_id::FAMILY {\n                                    if let Some(value) = name.to_string() {\n                                        let value = value.trim();\n                                        if !value.is_empty()\n                                            && !unicode_family_aliases.iter().any(|v| v == value)\n                                        {\n                                            unicode_family_aliases.push(value.to_string());\n                                        }\n                                    }\n                                }\n                            }\n                        }\n                        let skia_data = skia_safe::Data::new_copy(&data);\n                        if let Some(typeface) = font_mgr.new_from_data(&skia_data, None) {\n                            let family = typeface.family_name();\n                            into.entry(family).or_insert_with(|| typeface.clone());\n                            for alias in unicode_family_aliases {\n                                into.entry(alias).or_insert_with(|| typeface.clone());\n                            }\n                        }\n                    }\n'''
    replace_once(p, old, new, "direct Unicode family aliases")

    old = '''        Self::load_typefaces_from_dirs(&self.font_mgr, &custom_dirs, &mut self.custom_typefaces);\n'''
    new = '''        Self::load_typefaces_from_dirs(&self.font_mgr, &custom_dirs, &mut self.custom_typefaces);\n        let mut hft_debug_families: Vec<String> = self.custom_typefaces.keys().cloned().collect();\n        hft_debug_families.sort();\n        eprintln!("RHWP_DIRECT_CUSTOM_FAMILIES={:?}", hft_debug_families);\n'''
    replace_once(p, old, new, "direct custom font census")

    p = root / "src/renderer/skia/text_replay.rs"
    old = '''                let primary_typeface = typeface_chain.first().cloned();\n'''
    new = '''                let primary_typeface = typeface_chain.first().cloned();\n                if text.contains('‘') || text.contains('’') || text.contains('신') {\n                    let hft_debug_chain: Vec<String> =\n                        typeface_chain.iter().map(|tf| tf.family_name()).collect();\n                    let hft_debug_sample: String = text.chars().take(48).collect();\n                    eprintln!(\n                        "RHWP_DIRECT_TEXT family={:?} custom_exact={} chain={:?} text={:?}",\n                        style.font_family,\n                        self.custom_typefaces.contains_key(style.font_family.as_str()),\n                        hft_debug_chain,\n                        hft_debug_sample\n                    );\n                }\n'''
    replace_once(p, old, new, "direct requested font trace")

    print("patched rhwp legacy HFT bold + Unicode TTF family aliases + direct font trace")


if __name__ == "__main__":
    main()
