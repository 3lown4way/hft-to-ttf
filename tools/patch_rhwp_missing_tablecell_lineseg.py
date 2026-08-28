#!/usr/bin/env python3
"""Patch rhwp table-cell rendering for paragraphs with no PARA_LINE_SEG.

Hancom/Polaris reflow a table-cell paragraph when HWP5 omits PARA_LINE_SEG,
using the cell's real text area. rhwp already knows how to synthesize lines for
that case, but two rendering paths can diverge:

1. the full/embedded-table path can keep compose_paragraph()'s one-line fallback;
2. the partial-table path can misread that fallback as a true overflow and shrink
   the cell's left/right padding to the 1 px safety minimum before reflow.

The second case is exactly what happens in the KICE-style 12번 <보기>: source
cell width 30615 HU with 850/850 HU horizontal cell margins should reflow at
28915 HU = 385.53 px (96 dpi). The overflow-shrink path instead expands the
usable width to about 406.20 px, changing the first line from
`...슬롯을 항공|사에...` to `...슬롯을 항공사에|...`.

Compatibility scope is deliberately narrow:
- horizontal cell
- visible paragraph text
- no stored LineSeg
- no nested controls in that paragraph
Stored-LineSeg cells and ordinary overflow handling remain untouched.
"""
from pathlib import Path
import sys


def missing_lineseg_expr(var: str = "para") -> str:
    return (
        f"{var}.line_segs.is_empty()\\n"
        f"                        && {var}.text.chars().any(|ch| !ch.is_whitespace())\\n"
        f"                        && {var}.controls.is_empty()"
    )


def patch_full_embedded(root: Path) -> None:
    target = root / "src/renderer/layout/table_cell_content.rs"
    text = target.read_text(encoding="utf-8")

    old_padding = '''            // 셀 패딩 (apply_inner_margin 고려)\n            let (mut pad_left, mut pad_right, pad_top, pad_bottom) =\n                self.resolve_cell_padding(cell, table);\n\n            // 셀 내 문단 레이아웃\n            let composed_paras: Vec<_> = cell\n'''
    new_padding = '''            // 셀 패딩 (apply_inner_margin 고려)\n            let (mut pad_left, mut pad_right, pad_top, pad_bottom) =\n                self.resolve_cell_padding(cell, table);\n\n            // Missing PARA_LINE_SEG 셀은 원본 text area를 그대로 사용한다.\n            let has_missing_cell_lines = cell.text_direction == 0\n                && cell.paragraphs.iter().any(|para| {\n                    para.line_segs.is_empty()\n                        && para.text.chars().any(|ch| !ch.is_whitespace())\n                        && para.controls.is_empty()\n                });\n            if has_missing_cell_lines && cell.apply_inner_margin {\n                if cell.padding.left >= 0 {\n                    pad_left = hwpunit_to_px(cell.padding.left as i32, self.dpi);\n                }\n                if cell.padding.right >= 0 {\n                    pad_right = hwpunit_to_px(cell.padding.right as i32, self.dpi);\n                }\n            }\n\n            // 셀 내 문단 레이아웃\n            let mut composed_paras: Vec<_> = cell\n'''
    count = text.count(old_padding)
    if count != 1:
        raise SystemExit(f"full path: expected one padding/composed block, found {count}")
    text = text.replace(old_padding, new_padding, 1)

    old_anchor = '''            let inner_x = cell_x + pad_left;\n            let inner_width = (cell_w - pad_left - pad_right).max(0.0);\n            let inner_height = (cell_h - pad_top - pad_bottom).max(0.0);\n            let has_nested = cell\n'''
    new_anchor = '''            let inner_x = cell_x + pad_left;\n            let inner_width = (cell_w - pad_left - pad_right).max(0.0);\n            let inner_height = (cell_h - pad_top - pad_bottom).max(0.0);\n\n            // Missing PARA_LINE_SEG: synthesize only the omitted line layout.\n            if has_missing_cell_lines && inner_width > 0.0 {\n                for (composed, para) in composed_paras.iter_mut().zip(cell.paragraphs.iter()) {\n                    if para.line_segs.is_empty()\n                        && para.text.chars().any(|ch| !ch.is_whitespace())\n                        && para.controls.is_empty()\n                    {\n                        crate::renderer::composer::recompose_for_cell_width(\n                            composed,\n                            para,\n                            inner_width,\n                            styles,\n                        );\n                    }\n                }\n            }\n\n            let has_nested = cell\n'''
    count = text.count(old_anchor)
    if count != 1:
        raise SystemExit(f"full path: expected one inner-width anchor, found {count}")
    text = text.replace(old_anchor, new_anchor, 1)

    target.write_text(text, encoding="utf-8")
    print(f"patched {target}")


def patch_partial(root: Path) -> None:
    target = root / "src/renderer/layout/table_partial.rs"
    text = target.read_text(encoding="utf-8")

    old = '''                // 텍스트 오버플로우 시 좌우 패딩 축소\n                let (new_pl, new_pr) = self.shrink_cell_padding_for_overflow(\n                    pad_left,\n                    pad_right,\n                    cell_w,\n                    &composed_paras,\n                    &cell.paragraphs,\n                    styles,\n                    cell.apply_inner_margin,\n                );\n'''
    new = '''                // Missing PARA_LINE_SEG의 compose_paragraph() 결과는 아직 실제\n                // 셀 폭으로 재조판되기 전의 단일 fallback line이다. 그 자연폭을\n                // 진짜 overflow로 해석해 padding을 1px까지 깎으면, 바로 아래\n                // recompose_for_cell_width()가 잘못 넓어진 폭을 받는다. 이 경우에만\n                // source에서 해소된 셀 padding을 보존하고 그 폭으로 먼저 재조판한다.\n                let preserve_missing_lineseg_padding = cell.text_direction == 0\n                    && cell.paragraphs.iter().any(|para| {\n                        para.line_segs.is_empty()\n                            && para.text.chars().any(|ch| !ch.is_whitespace())\n                            && para.controls.is_empty()\n                    });\n                // 텍스트 오버플로우 시 좌우 패딩 축소\n                let (new_pl, new_pr) = self.shrink_cell_padding_for_overflow(\n                    pad_left,\n                    pad_right,\n                    cell_w,\n                    &composed_paras,\n                    &cell.paragraphs,\n                    styles,\n                    cell.apply_inner_margin || preserve_missing_lineseg_padding,\n                );\n'''
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"partial path: expected one shrink block, found {count}")
    text = text.replace(old, new, 1)

    target.write_text(text, encoding="utf-8")
    print(f"patched {target}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_missing_tablecell_lineseg.py <rhwp-source-root>")
    root = Path(sys.argv[1])
    patch_full_embedded(root)
    patch_partial(root)


if __name__ == "__main__":
    main()
