#!/usr/bin/env python3
"""Teach rhwp legacy Hancom HFT paint and placement semantics.

The 2009 KICE PDF is used only as a rendering oracle.  For legacy HFT-derived
faces, its regular and bold Type3 glyph programs have identical geometry; the
bold program changes only the PDF paint operator from fill (f) to fill+stroke
(B).  Therefore bold must keep the Regular HFT outline and metrics and add a
thin same-colour stroke at paint time, instead of selecting/synthesising a
separate bold outline.

Legacy HFT glyphs also use a substantial descent area below the baseline. rhwp
v0.8.4 places every bottom underline at a fixed baseline+2 SVG px, which can
make the 1 px rule touch HFT glyph ink.  For HFT-derived runtime faces, keep the
same underline style/thickness but place the rule at 0.20em below the baseline.
This is proportional to the legacy HFT cell rather than page- or glyph-specific.

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


def replace_all_exact(path: Path, old: str, new: str, expected: int, label: str) -> None:
    s = path.read_text(encoding="utf-8")
    count = s.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} blocks, found {count} in {path}")
    path.write_text(s.replace(old, new), encoding="utf-8")


RUNTIME_FAMILY_MATCH = '''    matches!(
        name,
        "#태고딕"
            | "신명 견명조"
            | "신명 궁서"
            | "신명 디나루"
            | "신명 신그래픽"
            | "신명 중고딕 - 혼합"
            | "신명 중고딕"
            | "신명 중명조 - 한양문자"
            | "신명 중명조 - 한양영문"
            | "신명 중명조"
            | "신명 태고딕"
            | "한양견명조"
            | "한양중고딕"
    )'''


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "rhwp-src")
    p = root / "src/renderer/svg.rs"

    # Family provenance helper.  These are the source-HFT composite faces made
    # by this repository, not arbitrary system fonts with similar names.
    anchor = '''const TEXT_MARK_CLIP_RIGHT_PAD: f64 = 48.0;\n'''
    helper = '''const TEXT_MARK_CLIP_RIGHT_PAD: f64 = 48.0;\n\n/// Legacy Hancom HFT-derived runtime faces.  Their HWP bold flag is rendered\n/// by painting the Regular outline with fill+stroke; metrics remain Regular.\nfn is_legacy_hft_runtime_family(name: &str) -> bool {\n''' + RUNTIME_FAMILY_MATCH + '''\n}\n\nconst LEGACY_HFT_BOLD_STROKE_PX: f64 = 0.16;\n/// HFT cells reserve a descent zone below the baseline.  A fixed +2px rule can\n/// touch that ink at normal exam body sizes, so keep proportional clearance.\nconst LEGACY_HFT_UNDERLINE_OFFSET_EM: f64 = 0.20;\n'''
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

    # SVG/compatibility PDF: v0.8.4 uses baseline+2px for every bottom underline.
    # Keep non-HFT behavior untouched; only HFT-derived faces use cell-relative
    # descent clearance.  There are two text paths with the same block.
    old = '''            let ul_y = match style.underline {\n                UnderlineType::Top => y - font_size + 1.0,\n                _ => y + 2.0,\n            };\n'''
    new = '''            let ul_y = match style.underline {\n                UnderlineType::Top => y - font_size + 1.0,\n                _ if is_legacy_hft_runtime_family(&style.font_family) => {\n                    y + font_size * LEGACY_HFT_UNDERLINE_OFFSET_EM\n                }\n                _ => y + 2.0,\n            };\n'''
    replace_all_exact(p, old, new, 2, "legacy HFT SVG underline clearance")

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

    # Direct Skia has its own underline paint path; apply the same HFT-only
    # proportional placement there so Direct and Compatibility stay aligned.
    anchor = '''use super::renderer::colorref_to_skia;\n\n'''
    helper = '''use super::renderer::colorref_to_skia;\n\nfn is_legacy_hft_runtime_family(name: &str) -> bool {\n''' + RUNTIME_FAMILY_MATCH + '''\n}\n\nconst LEGACY_HFT_UNDERLINE_OFFSET_EM: f32 = 0.20;\n\n'''
    replace_once(p, anchor, helper, "direct legacy HFT underline helper")

    old = '''                    let line_y = match style.underline {\n                        UnderlineType::Top => y as f32 - font_size + 1.0,\n                        _ => y as f32 + 2.0,\n                    };\n'''
    new = '''                    let line_y = match style.underline {\n                        UnderlineType::Top => y as f32 - font_size + 1.0,\n                        _ if is_legacy_hft_runtime_family(&style.font_family) => {\n                            y as f32 + font_size * LEGACY_HFT_UNDERLINE_OFFSET_EM\n                        }\n                        _ => y as f32 + 2.0,\n                    };\n'''
    replace_all_exact(p, old, new, 2, "direct legacy HFT underline clearance")

    old = '''                let primary_typeface = typeface_chain.first().cloned();\n'''
    new = '''                let primary_typeface = typeface_chain.first().cloned();\n                if text.contains('‘') || text.contains('’') || text.contains('신') {\n                    let hft_debug_chain: Vec<String> =\n                        typeface_chain.iter().map(|tf| tf.family_name()).collect();\n                    let hft_debug_sample: String = text.chars().take(48).collect();\n                    eprintln!(\n                        "RHWP_DIRECT_TEXT family={:?} custom_exact={} chain={:?} text={:?}",\n                        style.font_family,\n                        self.custom_typefaces.contains_key(style.font_family.as_str()),\n                        hft_debug_chain,\n                        hft_debug_sample\n                    );\n                }\n'''
    replace_once(p, old, new, "direct requested font trace")

    print("patched rhwp legacy HFT bold + underline clearance + Unicode TTF family aliases + direct font trace")


if __name__ == "__main__":
    main()
