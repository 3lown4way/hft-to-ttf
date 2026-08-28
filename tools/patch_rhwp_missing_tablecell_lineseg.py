#!/usr/bin/env python3
"""Patch rhwp table-cell rendering for paragraphs with no PARA_LINE_SEG.

Hancom/Polaris reflow a table-cell paragraph when HWP5 omits PARA_LINE_SEG,
using the cell's real text area. In rhwp the partial/measurement path already
uses the correct inner width, but the final full/embedded-table path can reach
compose_paragraph() without reflow and can also resolve that missing-LineSeg
cell against a wider text area. KICE-style <보기> then wraps differently even
though neighboring <보기> cells with stored LineSeg are fine.

Compatibility scope is deliberately narrow:
- horizontal cell
- visible paragraph text
- no stored LineSeg
- no nested controls in that paragraph
- raw cell horizontal margins are restored only when apply_inner_margin=true
Existing stored-LineSeg cells remain untouched.
"""
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_missing_tablecell_lineseg.py <rhwp-source-root>")

    root = Path(sys.argv[1])
    target = root / "src/renderer/layout/table_cell_content.rs"
    text = target.read_text(encoding="utf-8")

    old_padding = '''            // 셀 패딩 (apply_inner_margin 고려)\n            let (mut pad_left, mut pad_right, pad_top, pad_bottom) =\n                self.resolve_cell_padding(cell, table);\n\n            // 셀 내 문단 레이아웃\n            let composed_paras: Vec<_> = cell\n'''
    new_padding = '''            // 셀 패딩 (apply_inner_margin 고려)\n            let (mut pad_left, mut pad_right, pad_top, pad_bottom) =\n                self.resolve_cell_padding(cell, table);\n\n            // JH/KICE: 저장 LineSeg가 없는 셀은 최종 paint 경로도 측정 경로와\n            // 동일한 실제 text area를 써야 한다. 12번 <보기> 실파일에서 셀 폭은\n            // 30615HU, 좌/우 셀 안여백은 850/850HU이므로 정답 inner width는\n            // 28915HU(96dpi 385.53px)이다. 최종 경로가 406.20px를 쓰면 한컴의\n            // `...슬롯을 항공|사에...` 대신 `...슬롯을 항공사에|...`가 된다.\n            // apply_inner_margin=true는 HWP 계약상 셀 고유 margin이 source of truth다.\n            let has_missing_cell_lines = cell.text_direction == 0\n                && cell.paragraphs.iter().any(|para| {\n                    para.line_segs.is_empty()\n                        && para.text.chars().any(|ch| !ch.is_whitespace())\n                        && para.controls.is_empty()\n                });\n            if has_missing_cell_lines && cell.apply_inner_margin {\n                if cell.padding.left >= 0 {\n                    pad_left = hwpunit_to_px(cell.padding.left as i32, self.dpi);\n                }\n                if cell.padding.right >= 0 {\n                    pad_right = hwpunit_to_px(cell.padding.right as i32, self.dpi);\n                }\n            }\n\n            // 셀 내 문단 레이아웃\n            let mut composed_paras: Vec<_> = cell\n'''
    count = text.count(old_padding)
    if count != 1:
        raise SystemExit(f"expected one padding/composed block, found {count}")
    text = text.replace(old_padding, new_padding, 1)

    old_anchor = '''            let inner_x = cell_x + pad_left;\n            let inner_width = (cell_w - pad_left - pad_right).max(0.0);\n            let inner_height = (cell_h - pad_top - pad_bottom).max(0.0);\n            let has_nested = cell\n'''
    new_anchor = '''            let inner_x = cell_x + pad_left;\n            let inner_width = (cell_w - pad_left - pad_right).max(0.0);\n            let inner_height = (cell_h - pad_top - pad_bottom).max(0.0);\n\n            // Missing PARA_LINE_SEG: synthesize only the omitted layout from the\n            // resolved cell text width. Stored-LineSeg cells never enter here.\n            if has_missing_cell_lines && inner_width > 0.0 {\n                for (composed, para) in composed_paras.iter_mut().zip(cell.paragraphs.iter()) {\n                    if para.line_segs.is_empty()\n                        && para.text.chars().any(|ch| !ch.is_whitespace())\n                        && para.controls.is_empty()\n                    {\n                        crate::renderer::composer::recompose_for_cell_width(\n                            composed,\n                            para,\n                            inner_width,\n                            styles,\n                        );\n                    }\n                }\n            }\n\n            let has_nested = cell\n'''
    count = text.count(old_anchor)
    if count != 1:
        raise SystemExit(f"expected one inner-width anchor, found {count}")
    text = text.replace(old_anchor, new_anchor, 1)

    target.write_text(text, encoding="utf-8")
    print(f"patched {target}")


if __name__ == "__main__":
    main()
