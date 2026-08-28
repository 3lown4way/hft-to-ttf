#!/usr/bin/env python3
"""Patch rhwp full-table cell rendering for paragraphs with no PARA_LINE_SEG.

Some HWP5 documents omit PARA_LINE_SEG for a table-cell paragraph even though
Hancom/Polaris lay it out normally from the cell's actual inner width. The
partial-table path already runs recompose_for_cell_width(), but the full/nested
cell path in table_cell_content.rs only calls compose_paragraph(), leaving the
single-line fallback untouched. That makes isolated cells (e.g. KICE-style
<보기> content) wrap differently from Hancom while neighboring cells with stored
LineSeg render correctly.

Keep the compatibility fix intentionally narrow:
- horizontal cells only
- visible text
- no stored LineSeg
- no nested controls in that paragraph
Existing stored-LineSeg cells are byte-for-byte behaviorally unchanged.
"""
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_missing_tablecell_lineseg.py <rhwp-source-root>")

    root = Path(sys.argv[1])
    target = root / "src/renderer/layout/table_cell_content.rs"
    text = target.read_text(encoding="utf-8")

    old_decl = '''            let composed_paras: Vec<_> = cell\n                .paragraphs\n                .iter()\n                .map(|p| compose_paragraph(p))\n                .collect();\n'''
    new_decl = '''            let mut composed_paras: Vec<_> = cell\n                .paragraphs\n                .iter()\n                .map(|p| compose_paragraph(p))\n                .collect();\n'''
    if text.count(old_decl) != 1:
        raise SystemExit(f"expected one composed_paras declaration, found {text.count(old_decl)}")
    text = text.replace(old_decl, new_decl, 1)

    old_anchor = '''            let inner_x = cell_x + pad_left;\n            let inner_width = (cell_w - pad_left - pad_right).max(0.0);\n            let inner_height = (cell_h - pad_top - pad_bottom).max(0.0);\n            let has_nested = cell\n'''
    new_anchor = '''            let inner_x = cell_x + pad_left;\n            let inner_width = (cell_w - pad_left - pad_right).max(0.0);\n            let inner_height = (cell_h - pad_top - pad_bottom).max(0.0);\n\n            // JH/KICE: HWP5 can omit PARA_LINE_SEG for an otherwise ordinary\n            // horizontal table-cell paragraph. Hancom/Polaris then derive the\n            // line breaks from the actual cell inner width. The partial-table\n            // path already does this through recompose_for_cell_width(), while\n            // this full/nested-table path previously kept compose_paragraph()'s\n            // one-line fallback. Recompose only the missing-LineSeg case so all\n            // cells with stored layout metadata remain untouched.\n            if cell.text_direction == 0 && inner_width > 0.0 {\n                for (composed, para) in composed_paras.iter_mut().zip(cell.paragraphs.iter()) {\n                    if para.line_segs.is_empty()\n                        && para.text.chars().any(|ch| !ch.is_whitespace())\n                        && para.controls.is_empty()\n                    {\n                        crate::renderer::composer::recompose_for_cell_width(\n                            composed,\n                            para,\n                            inner_width,\n                            styles,\n                        );\n                    }\n                }\n            }\n\n            let has_nested = cell\n'''
    if text.count(old_anchor) != 1:
        raise SystemExit(f"expected one inner-width anchor, found {text.count(old_anchor)}")
    text = text.replace(old_anchor, new_anchor, 1)

    target.write_text(text, encoding="utf-8")
    print(f"patched {target}")


if __name__ == "__main__":
    main()
