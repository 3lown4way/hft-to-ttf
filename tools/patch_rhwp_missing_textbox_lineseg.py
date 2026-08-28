#!/usr/bin/env python3
"""Patch rhwp so horizontal text boxes synthesize layout for missing PARA_LINE_SEG.

Hancom/Polaris lay out visible textbox text even when the stored paragraph has no
PARA_LINE_SEG records. rhwp's generic composer fallback uses fixed 400/320 HU
line geometry and segment_width=0, which can distort small treat-as-character
GSO labels. Keep the fix local to text boxes with a known inner width and no
nested controls, and let the normal reflow engine compute the line geometry.
"""
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_missing_textbox_lineseg.py <rhwp-source-root>")

    root = Path(sys.argv[1])
    target = root / "src/renderer/layout/shape_layout.rs"
    text = target.read_text(encoding="utf-8")

    old = '''        let text_direction = (text_box.list_attr & 0x07) as u8;\n        let reflowed_textbox_paragraphs = if should_reflow_matrix_textbox_lines(\n            matrix_positioned,\n            drawing,\n            text_box,\n            text_direction,\n            inner_area.width,\n            inner_area.height,\n            self.dpi,\n        ) {\n            let mut paragraphs = text_box.paragraphs.clone();\n            for para in paragraphs\n                .iter_mut()\n                .filter(|para| matrix_textbox_lines_need_reflow(para))\n            {\n                reflow_matrix_textbox_para(\n                    para,\n                    inner_area.width,\n                    inner_area.height,\n                    styles,\n                    self.dpi,\n                );\n            }\n            Some(paragraphs)\n        } else {\n            None\n        };\n'''

    new = '''        let text_direction = (text_box.list_attr & 0x07) as u8;\n\n        // JH/KICE: 한컴/폴라리스는 글상자 안의 visible paragraph 에 저장된\n        // PARA_LINE_SEG 가 없어도 글상자 inner width 와 글자/문단 속성으로 한 줄\n        // 레이아웃을 계산한다. 기존 compose_lines() 의 전역 fallback(400/320 HU,\n        // segment_width=0)은 작은 TAC GSO 라벨에서 baseline/box 높이를 왜곡한다.\n        // 이 보정은 가로쓰기 + 실제 텍스트 + 내부 control 없음으로 좁혀서 적용한다.\n        let has_missing_textbox_lines = text_direction == 0\n            && inner_area.width > 0.0\n            && text_box.paragraphs.iter().any(|para| {\n                para.line_segs.is_empty()\n                    && para.text.chars().any(|ch| !ch.is_whitespace())\n                    && para.controls.is_empty()\n            });\n\n        let needs_matrix_reflow = should_reflow_matrix_textbox_lines(\n            matrix_positioned,\n            drawing,\n            text_box,\n            text_direction,\n            inner_area.width,\n            inner_area.height,\n            self.dpi,\n        );\n\n        let reflowed_textbox_paragraphs = if has_missing_textbox_lines || needs_matrix_reflow {\n            let mut paragraphs = text_box.paragraphs.clone();\n            for para in paragraphs.iter_mut() {\n                if text_direction == 0\n                    && inner_area.width > 0.0\n                    && para.line_segs.is_empty()\n                    && para.text.chars().any(|ch| !ch.is_whitespace())\n                    && para.controls.is_empty()\n                {\n                    reflow_line_segs(para, inner_area.width, styles, self.dpi);\n                } else if needs_matrix_reflow && matrix_textbox_lines_need_reflow(para) {\n                    reflow_matrix_textbox_para(\n                        para,\n                        inner_area.width,\n                        inner_area.height,\n                        styles,\n                        self.dpi,\n                    );\n                }\n            }\n            Some(paragraphs)\n        } else {\n            None\n        };\n'''

    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one target block, found {count}")

    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {target}")


if __name__ == "__main__":
    main()
