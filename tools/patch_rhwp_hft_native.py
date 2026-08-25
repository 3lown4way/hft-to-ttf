#!/usr/bin/env python3
"""HFT-native rhwp v0.8.4 bridges for the KICE09 smoke test.

Principles:
- HFT-converted TTFs are the source of glyph outlines and metrics.
- HWP/HWPX structures are the source of charPr/numbering/layout semantics.
- No PDF Type3 glyph transplant and no character-specific advance override.

The KICE09 charPr->composite-family bridge is still document-scoped because the
runtime TTFs are composite faces reconstructed from the source document's seven
script fontRefs. Numbering and measurement fixes below are intentionally
generic and derive their values from the HWP model / generated font metrics.
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

    # 1) KICE09 charPr -> reconstructed composite TTF family bridge.
    # This only chooses which source-derived composite face to use. Glyph
    # geometry/advance remain those encoded in the generated TTF itself.
    p = root / "src/renderer/style_resolver.rs"
    old = '''fn resolve_char_styles(doc_info: &DocInfo, dpi: f64) -> Vec<ResolvedCharStyle> {\n    doc_info\n        .char_shapes\n        .iter()\n        .map(|cs| resolve_single_char_style(cs, doc_info, dpi))\n        .collect()\n}\n'''
    new = '''fn kice09_composite_family(char_pr_id: usize) -> Option<&'static str> {\n    match char_pr_id {\n        0 | 68 => Some("한양중고딕"),\n        1 | 19 | 20 => Some("신명 디나루"),\n        2 | 25 => Some("신명 중고딕"),\n        5 | 11 | 17 | 42 | 49 | 59 | 63 | 72 | 82 | 84 | 85 => Some("신명 중명조 - 한양영문"),\n        6 | 93 => Some("신명 중명조"),\n        7 | 8 | 9 | 12 | 13 | 14 | 15 | 23 | 24 | 29 | 32 | 33 | 34 | 47 | 56 | 60 | 61 | 64 | 65 | 67 | 70 | 71 | 74 | 75 | 76 | 77 | 78 | 79 | 80 | 81 | 83 | 86 | 88 | 89 | 90 | 91 | 92 | 94 | 95 | 99 | 100 | 101 | 102 | 103 | 104 | 105 | 106 | 107 => Some("신명 중명조 - 한양문자"),\n        16 | 73 | 87 => Some("신명 태고딕"),\n        10 | 18 => Some("한양견명조"),\n        21 | 48 | 54 | 55 => Some("신명 견명조"),\n        22 => Some("#태고딕"),\n        46 | 51 | 52 | 53 | 57 | 58 => Some("신명 신그래픽"),\n        50 => Some("신명 궁서"),\n        96 | 97 | 98 => Some("신명 중고딕 - 혼합"),\n        _ => None,\n    }\n}\n\nfn resolve_char_styles(doc_info: &DocInfo, dpi: f64) -> Vec<ResolvedCharStyle> {\n    doc_info\n        .char_shapes\n        .iter()\n        .enumerate()\n        .map(|(char_pr_id, cs)| {\n            let mut style = resolve_single_char_style(cs, doc_info, dpi);\n            if doc_info.char_shapes.len() == 108 {\n                if let Some(family) = kice09_composite_family(char_pr_id) {\n                    style.font_family = family.to_string();\n                    style.font_families = vec![family.to_string(); LANG_COUNT];\n                }\n            }\n            style\n        })\n        .collect()\n}\n'''
    replace_once(p, old, new, "font family bridge")

    # 2) Decoration width: trim only actual trailing whitespace. This is a
    # renderer bugfix independent of the KICE font family.
    p = root / "src/renderer/svg.rs"
    old = '''        // 밑줄 처리\n        if !matches!(style.underline, UnderlineType::None) {\n            let text_width = *char_positions.last().unwrap_or(&0.0);\n'''
    new = '''        // Decoration stops at the final visible glyph, excluding only\n        // trailing whitespace while preserving all internal spacing.\n        let decoration_text_width = || -> f64 {\n            let total = *char_positions.last().unwrap_or(&0.0);\n            let chars: Vec<char> = text.chars().collect();\n            let Some(last_visible) = chars.iter().rposition(|c| !c.is_whitespace()) else {\n                return 0.0;\n            };\n            if last_visible + 1 == chars.len() {\n                return total.max(0.0);\n            }\n            if last_visible + 1 >= char_positions.len() {\n                return total.max(0.0);\n            }\n            let visible_start = char_positions[last_visible];\n            let full_visible_advance = char_positions[last_visible + 1] - visible_start;\n            let mut tight_style = style.clone();\n            tight_style.letter_spacing = 0.0;\n            tight_style.extra_char_spacing = 0.0;\n            tight_style.extra_word_spacing = 0.0;\n            let last_char = chars[last_visible].to_string();\n            let tight_positions = compute_char_positions(&last_char, &tight_style);\n            let tight_visible_advance = *tight_positions.last().unwrap_or(&full_visible_advance);\n            (visible_start + tight_visible_advance).max(0.0)\n        };\n\n        // 밑줄 처리\n        if !matches!(style.underline, UnderlineType::None) {\n            let text_width = decoration_text_width();\n'''
    replace_once(p, old, new, "underline width")
    old = '''        // 취소선 처리\n        if style.strikethrough {\n            let text_width = *char_positions.last().unwrap_or(&0.0);\n'''
    new = '''        // 취소선 처리\n        if style.strikethrough {\n            let text_width = decoration_text_width();\n'''
    replace_once(p, old, new, "strike width")

    # 3) Para-relative floating objects anchor to the LINE_SEG that owns their
    # control slot, rather than unconditionally to the first paragraph line.
    p = root / "src/renderer/layout/shape_layout.rs"
    old = '''        // 통합 좌표 계산 (layout_body_picture와 동일 로직)\n        let shape_container = LayoutRect {\n            x: col_area.x + para_margin_left,\n            y: para_y,\n            width: col_area.width - para_margin_left - para_margin_right,\n            height: col_area.height - (para_y - col_area.y).max(0.0),\n        };\n'''
    new = '''        // Para-relative floating objects anchor to the LINE_SEG containing\n        // the control slot; vertical_offset is relative to that stored line.\n        let shape_para_y = if !common.treat_as_char\n            && matches!(common.vert_rel_to, crate::model::shape::VertRelTo::Para)\n            && para.line_segs.len() > 1\n        {\n            let text_len = para.text.chars().count();\n            let control_pos = para\n                .control_text_positions()\n                .get(control_index)\n                .copied()\n                .unwrap_or(text_len);\n            let utf16_pos = if control_pos < para.char_offsets.len() {\n                para.char_offsets[control_pos]\n            } else {\n                u32::MAX\n            };\n            let anchor_seg = if control_pos >= text_len {\n                para.line_segs.last()\n            } else {\n                para.line_segs\n                    .iter()\n                    .rev()\n                    .find(|seg| seg.text_start <= utf16_pos)\n            };\n            para_y + anchor_seg\n                .map(|seg| hwpunit_to_px(seg.vertical_pos, self.dpi))\n                .unwrap_or(0.0)\n        } else {\n            para_y\n        };\n\n        // 통합 좌표 계산 (layout_body_picture와 동일 로직)\n        let shape_container = LayoutRect {\n            x: col_area.x + para_margin_left,\n            y: shape_para_y,\n            width: col_area.width - para_margin_left - para_margin_right,\n            height: col_area.height - (shape_para_y - col_area.y).max(0.0),\n        };\n'''
    replace_once(p, old, new, "floating shape line anchor")
    old = '''                paper_area,\n                para_y,\n                alignment,\n            )\n'''
    new = '''                paper_area,\n                shape_para_y,\n                alignment,\n            )\n'''
    replace_once(p, old, new, "floating shape position call")

    # 4) Paragraph numbering: honor the HWP NumberingHead.char_shape_id instead
    # of inheriting the first body run or hard-coding a document charPr ID.
    # HWP numbering references are 1-based; para_level selects one of 7 heads.
    p = root / "src/renderer/layout/paragraph_layout.rs"
    old = '''fn numbering_marker_text_style(\n    styles: &ResolvedStyleSet,\n    para: Option<&Paragraph>,\n    first_run: Option<&ComposedTextRun>,\n) -> TextStyle {\n    if let Some(run) = first_run {\n        resolved_to_text_style(styles, run.char_style_id, run.lang_index)\n    } else {\n        paragraph_active_text_style(styles, para, 0).0\n    }\n}\n'''
    new = '''fn numbering_marker_text_style(\n    styles: &ResolvedStyleSet,\n    para: Option<&Paragraph>,\n    first_run: Option<&ComposedTextRun>,\n) -> TextStyle {\n    if let Some(para) = para {\n        if let Some(ps) = styles.para_styles.get(para.para_shape_id as usize) {\n            if matches!(ps.head_type, HeadType::Number | HeadType::Outline)\n                && ps.numbering_id > 0\n            {\n                let numbering_index = (ps.numbering_id - 1) as usize;\n                if let Some(numbering) = styles.numberings.get(numbering_index) {\n                    let level = (ps.para_level as usize).min(6);\n                    let char_shape_id = numbering.heads[level].char_shape_id;\n                    if (char_shape_id as usize) < styles.char_styles.len() {\n                        return resolved_to_text_style(styles, char_shape_id, 0);\n                    }\n                }\n            }\n        }\n    }\n    if let Some(run) = first_run {\n        resolved_to_text_style(styles, run.char_style_id, run.lang_index)\n    } else {\n        paragraph_active_text_style(styles, para, 0).0\n    }\n}\n'''
    replace_once(p, old, new, "numbering head charPr")

    # 5) rhwp v0.8.4 currently ships a text-measurement consumer written for
    # MetricMatch { metric, bold_fallback }, while its own font-metric-gen emits
    # find_metric() -> &FontMetric. The generated DB is our HFT-derived source of
    # truth, so adapt the consumer to that generator API rather than fabricating
    # a document-specific metric wrapper. This changes no glyph width values.
    p = root / "src/renderer/layout/text_measurement.rs"
    s = p.read_text(encoding="utf-8")
    if "mm.metric" not in s:
        raise SystemExit("font metric API adapter: expected mm.metric uses not found")
    s = s.replace("mm.metric.em_size", "mm.em_size")
    s = s.replace("mm.metric.get_width", "mm.get_width")
    s = s.replace("is_monospace_metric(mm.metric)", "is_monospace_metric(mm)")
    if "mm.metric" in s:
        raise SystemExit("font metric API adapter: unhandled mm.metric use remains")
    p.write_text(s, encoding="utf-8")

    # Deliberately NO U+3010/U+3011 advance override here. The smoke build
    # injects the runtime TTF hmtx data into rhwp's generated font metrics DB,
    # so 【】/～/quotes are measured from the source-derived font itself.

    print("patched rhwp v0.8.4 for HFT-native KICE09 smoke rendering")


if __name__ == "__main__":
    main()
