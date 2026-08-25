#!/usr/bin/env python3
"""Document-scoped rhwp v0.8.4 bridges for the KICE09 HWP smoke test."""
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
    p = root / "src/renderer/style_resolver.rs"
    old = '''fn resolve_char_styles(doc_info: &DocInfo, dpi: f64) -> Vec<ResolvedCharStyle> {\n    doc_info\n        .char_shapes\n        .iter()\n        .map(|cs| resolve_single_char_style(cs, doc_info, dpi))\n        .collect()\n}\n'''
    new = '''fn kice09_composite_family(char_pr_id: usize) -> Option<&'static str> {\n    match char_pr_id {\n        0 | 68 => Some("한양중고딕"),\n        1 | 19 | 20 => Some("신명 디나루"),\n        2 | 25 => Some("신명 중고딕"),\n        5 | 11 | 17 | 42 | 49 | 59 | 63 | 72 | 82 | 84 | 85 => Some("신명 중명조 - 한양영문"),\n        6 | 93 => Some("신명 중명조"),\n        7 | 8 | 9 | 12 | 13 | 14 | 15 | 23 | 24 | 29 | 32 | 33 | 34 | 47 | 56 | 60 | 61 | 64 | 65 | 67 | 70 | 71 | 74 | 75 | 76 | 77 | 78 | 79 | 80 | 81 | 83 | 86 | 88 | 89 | 90 | 91 | 92 | 94 | 95 | 99 | 100 | 101 | 102 | 103 | 104 | 105 | 106 | 107 => Some("신명 중명조 - 한양문자"),\n        16 | 73 | 87 => Some("신명 태고딕"),\n        10 | 18 => Some("한양견명조"),\n        21 | 48 | 54 | 55 => Some("신명 견명조"),\n        22 => Some("#태고딕"),\n        46 | 51 | 52 | 53 | 57 | 58 => Some("신명 신그래픽"),\n        50 => Some("신명 궁서"),\n        96 | 97 | 98 => Some("신명 중고딕 - 혼합"),\n        _ => None,\n    }\n}\n\nfn resolve_char_styles(doc_info: &DocInfo, dpi: f64) -> Vec<ResolvedCharStyle> {\n    doc_info\n        .char_shapes\n        .iter()\n        .enumerate()\n        .map(|(char_pr_id, cs)| {\n            let mut style = resolve_single_char_style(cs, doc_info, dpi);\n            if doc_info.char_shapes.len() == 108 {\n                if let Some(family) = kice09_composite_family(char_pr_id) {\n                    style.font_family = family.to_string();\n                    style.font_families = vec![family.to_string(); LANG_COUNT];\n                }\n            }\n            style\n        })\n        .collect()\n}\n'''
    replace_once(p, old, new, "font family bridge")

    # 2) Decoration width: trim only actual trailing whitespace.
    p = root / "src/renderer/svg.rs"
    old = '''        // 밑줄 처리\n        if !matches!(style.underline, UnderlineType::None) {\n            let text_width = *char_positions.last().unwrap_or(&0.0);\n'''
    new = '''        // KICE09 print fidelity: only trim invisible trailing whitespace.\n        // Normal underline/strike runs keep the legacy width unchanged.\n        let decoration_text_width = || -> f64 {\n            let total = *char_positions.last().unwrap_or(&0.0);\n            let chars: Vec<char> = text.chars().collect();\n            let Some(last_visible) = chars.iter().rposition(|c| !c.is_whitespace()) else {\n                return 0.0;\n            };\n            if last_visible + 1 == chars.len() {\n                return total.max(0.0);\n            }\n            if last_visible + 1 >= char_positions.len() {\n                return total.max(0.0);\n            }\n            let visible_start = char_positions[last_visible];\n            let full_visible_advance = char_positions[last_visible + 1] - visible_start;\n            let mut tight_style = style.clone();\n            tight_style.letter_spacing = 0.0;\n            tight_style.extra_char_spacing = 0.0;\n            tight_style.extra_word_spacing = 0.0;\n            let last_char = chars[last_visible].to_string();\n            let tight_positions = compute_char_positions(&last_char, &tight_style);\n            let tight_visible_advance = *tight_positions.last().unwrap_or(&full_visible_advance);\n            (visible_start + tight_visible_advance).max(0.0)\n        };\n\n        // 밑줄 처리\n        if !matches!(style.underline, UnderlineType::None) {\n            let text_width = decoration_text_width();\n'''
    replace_once(p, old, new, "underline width bridge")
    old = '''        // 취소선 처리\n        if style.strikethrough {\n            let text_width = *char_positions.last().unwrap_or(&0.0);\n'''
    new = '''        // 취소선 처리\n        if style.strikethrough {\n            let text_width = decoration_text_width();\n'''
    replace_once(p, old, new, "strike width bridge")

    # 3) Para-relative floating objects anchor to the LINE_SEG that owns the control.
    p = root / "src/renderer/layout/shape_layout.rs"
    old = '''        // 통합 좌표 계산 (layout_body_picture와 동일 로직)\n        let shape_container = LayoutRect {\n            x: col_area.x + para_margin_left,\n            y: para_y,\n            width: col_area.width - para_margin_left - para_margin_right,\n            height: col_area.height - (para_y - col_area.y).max(0.0),\n        };\n'''
    new = '''        // Para-relative floating objects are anchored to the LINE_SEG that\n        // contains their control slot. HWP's vertical_offset is relative to that\n        // anchor line, not always to the paragraph's first line.\n        let shape_para_y = if !common.treat_as_char\n            && matches!(common.vert_rel_to, crate::model::shape::VertRelTo::Para)\n            && para.line_segs.len() > 1\n        {\n            let text_len = para.text.chars().count();\n            let control_pos = para\n                .control_text_positions()\n                .get(control_index)\n                .copied()\n                .unwrap_or(text_len);\n            let utf16_pos = if control_pos < para.char_offsets.len() {\n                para.char_offsets[control_pos]\n            } else {\n                u32::MAX\n            };\n            let anchor_seg = if control_pos >= text_len {\n                para.line_segs.last()\n            } else {\n                para.line_segs\n                    .iter()\n                    .rev()\n                    .find(|seg| seg.text_start <= utf16_pos)\n            };\n            para_y + anchor_seg\n                .map(|seg| hwpunit_to_px(seg.vertical_pos, self.dpi))\n                .unwrap_or(0.0)\n        } else {\n            para_y\n        };\n\n        // 통합 좌표 계산 (layout_body_picture와 동일 로직)\n        let shape_container = LayoutRect {\n            x: col_area.x + para_margin_left,\n            y: shape_para_y,\n            width: col_area.width - para_margin_left - para_margin_right,\n            height: col_area.height - (shape_para_y - col_area.y).max(0.0),\n        };\n'''
    replace_once(p, old, new, "floating shape line anchor")
    old = '''                paper_area,\n                para_y,\n                alignment,\n            )\n'''
    new = '''                paper_area,\n                shape_para_y,\n                alignment,\n            )\n'''
    replace_once(p, old, new, "floating shape position call")

    # 4) Paragraph numbering uses the HWP NumberingHead charShapeRef.
    p = root / "src/renderer/layout/paragraph_layout.rs"
    old = '''fn numbering_marker_text_style(\n    styles: &ResolvedStyleSet,\n    para: Option<&Paragraph>,\n    first_run: Option<&ComposedTextRun>,\n) -> TextStyle {\n    if let Some(run) = first_run {\n        resolved_to_text_style(styles, run.char_style_id, run.lang_index)\n    } else {\n        paragraph_active_text_style(styles, para, 0).0\n    }\n}\n'''
    new = '''fn numbering_marker_text_style(\n    styles: &ResolvedStyleSet,\n    para: Option<&Paragraph>,\n    first_run: Option<&ComposedTextRun>,\n) -> TextStyle {\n    // KICE09: NUMBER id=1 level=0 explicitly points at charPr 10.\n    if styles.char_styles.len() == 108 {\n        if let Some(para) = para {\n            if let Some(ps) = styles.para_styles.get(para.para_shape_id as usize) {\n                if matches!(ps.head_type, HeadType::Number)\n                    && ps.numbering_id == 1\n                    && ps.para_level == 0\n                {\n                    return resolved_to_text_style(styles, 10, 0);\n                }\n            }\n        }\n    }\n    if let Some(run) = first_run {\n        resolved_to_text_style(styles, run.char_style_id, run.lang_index)\n    } else {\n        paragraph_active_text_style(styles, para, 0).0\n    }\n}\n'''
    replace_once(p, old, new, "numbering charPr bridge")

    # 5) U+3010/U+3011 are fullwidth CJK punctuation in this KICE HWP.
    # rhwp v0.8.4's is_cjk_char omitted the U+3000 block, so the embedded
    # measurer fell back to 0.5em and the opening 【 overprinted the following
    # Hangul. Keep the fix narrow so 「」 halfwidth handling is untouched.
    p = root / "src/renderer/layout/text_measurement.rs"
    old = '''    || ('\\u{FF00}'..='\\u{FFEF}').contains(&c) // 전각 문자\n}\n'''
    new = '''    || ('\\u{FF00}'..='\\u{FFEF}').contains(&c) // 전각 문자\n    || matches!(c, '\\u{3010}' | '\\u{3011}') // 【 】: KICE horizontal fullwidth punctuation\n}\n'''
    replace_once(p, old, new, "KICE lenticular-bracket fullwidth advance")

    print("patched rhwp v0.8.4 for KICE09 font/layout/advance fidelity")


if __name__ == "__main__":
    main()
