#!/usr/bin/env python3
"""Make NO_LINE_SEG body reflow account for middle treat-as-char shapes.

KICE documents can store an inline rectangle (for example the boxed label in
question text) between two visible text runs.  The shape has a real text anchor
and `treat_as_char`, so Hancom lays it out like a character: if the remaining
line width cannot hold the shape, the shape starts the next physical line and
that line has the shape width removed from its text capacity.

rhwp already emits the shape at the correct text anchor and advances x by the
shape width.  The missing piece is fresh line breaking: NO_LINE_SEG body reflow
currently considers only visible text, so the line is split without reserving
the shape footprint.  The result is a box protruding past the column and text
that was broken one line too late.

This patch is intentionally narrow:
- body reflow only (recompose_for_body_width)
- no authoritative LINE_SEG
- exactly one render-inline control in the paragraph
- that control must be a middle-anchored treat-as-char Shape
- only fires when the text prefix + shape actually cannot fit the current line

It does not move the shape or synthesize coordinates.  It changes only the
fresh line partition so the existing TAC placement code receives the correct
physical line ownership.
"""
from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_rhwp_inline_tac_shape_reflow.py <rhwp-source-root>")

    root = Path(sys.argv[1])
    target = root / "src/renderer/composer.rs"
    text = target.read_text(encoding="utf-8")

    old = '''pub fn recompose_for_body_width(
    composed: &mut ComposedParagraph,
    para: &Paragraph,
    column_inner_width_px: f64,
    styles: &ResolvedStyleSet,
) {
    restyle_fallback_runs_by_char_shapes(composed, para);
    recompose_for_cell_width(composed, para, column_inner_width_px, styles);
}
'''

    new = r'''fn split_composed_line_at_absolute_char(
    src: &ComposedLine,
    split_abs: usize,
) -> Option<(ComposedLine, ComposedLine)> {
    if split_abs <= src.char_start {
        return None;
    }
    let total_chars: usize = src.runs.iter().map(|run| run.text.chars().count()).sum();
    let local = split_abs.checked_sub(src.char_start)?;
    if local >= total_chars {
        return None;
    }

    let mut before_runs = Vec::new();
    let mut after_runs = Vec::new();
    let mut seen = 0usize;
    for run in &src.runs {
        let run_len = run.text.chars().count();
        if local >= seen + run_len {
            before_runs.push(run.clone());
        } else if local <= seen {
            after_runs.push(run.clone());
        } else {
            let cut = local - seen;
            let before_text: String = run.text.chars().take(cut).collect();
            let after_text: String = run.text.chars().skip(cut).collect();
            if !before_text.is_empty() {
                let mut before = run.clone();
                before.text = before_text;
                // display_text is a projection of the original complete run.
                // A split run must be projected again by the normal render path.
                before.display_text = None;
                before_runs.push(before);
            }
            if !after_text.is_empty() {
                let mut after = run.clone();
                after.text = after_text;
                after.display_text = None;
                after_runs.push(after);
            }
        }
        seen += run_len;
    }

    if before_runs.is_empty() || after_runs.is_empty() {
        return None;
    }

    let mut before = src.clone();
    before.runs = before_runs;
    before.has_line_break = false;

    let mut after = src.clone();
    after.runs = after_runs;
    after.char_start = split_abs;
    after.has_line_break = false;
    Some((before, after))
}

/// Fresh body reflow must count a middle treat-as-char shape as an inline
/// footprint.  Existing layout code already draws the shape at the anchor and
/// advances x by its width; this helper only makes the physical line break
/// agree with that placement.
fn reflow_single_middle_tac_shape_for_body(
    composed: &mut ComposedParagraph,
    para: &Paragraph,
    column_inner_width_px: f64,
    styles: &ResolvedStyleSet,
) {
    if column_inner_width_px <= 0.0
        || !para.line_segs.is_empty()
        || composed.lines.is_empty()
        || para.text.contains('\n')
    {
        return;
    }

    let control_positions = find_render_inline_control_positions(para);
    let mut inline_candidates = para
        .controls
        .iter()
        .enumerate()
        .filter_map(|(control_index, ctrl)| {
            if !is_render_inline_control(ctrl) {
                return None;
            }
            let Control::Shape(shape) = ctrl else {
                // Keep this first fix narrow: tables/equations/pictures retain
                // their existing, separately tested flow paths.
                return Some((usize::MAX, 0usize, 0.0f64));
            };
            let common = shape.common();
            if !common.treat_as_char {
                return None;
            }
            let pos = *control_positions.get(control_index)?;
            let width_px = hwpunit_to_px(common.width as i32, super::DEFAULT_DPI);
            Some((control_index, pos, width_px))
        });

    let Some((control_index, control_pos, control_width_px)) = inline_candidates.next() else {
        return;
    };
    // Exactly one render-inline control and it must be the Shape candidate.
    if control_index == usize::MAX || inline_candidates.next().is_some() {
        return;
    }
    let text_len = para.text.chars().count();
    if control_pos == 0 || control_pos >= text_len || control_width_px <= 0.0 {
        return;
    }

    // If normal text-only reflow already starts a line at the shape anchor,
    // ownership is already correct and no intervention is needed.
    if composed
        .lines
        .iter()
        .any(|line| line.char_start == control_pos)
    {
        return;
    }

    // Reconstruct one style-preserving logical line.  This helper is limited to
    // paragraphs without hard line breaks, so concatenating fresh-wrap lines is
    // lossless with respect to the source text and CharShape boundaries.
    let mut source = composed.lines[0].clone();
    source.char_start = composed.lines[0].char_start;
    source.has_line_break = false;
    source.runs = composed
        .lines
        .iter()
        .flat_map(|line| line.runs.iter().cloned())
        .collect();

    let Some((prefix, suffix)) = split_composed_line_at_absolute_char(&source, control_pos) else {
        return;
    };

    let para_style = styles.para_styles.get(para.para_shape_id as usize);
    let char_break = para_style
        .map(|ps| ps.korean_break_unit == 1)
        .unwrap_or(false);
    let space_condense = para_style
        .map(|ps| ps.condense_min_space as f64 / 100.0)
        .unwrap_or(0.0);

    let prefix_lines = split_composed_line_by_width(
        &prefix,
        column_inner_width_px,
        column_inner_width_px,
        styles,
        char_break,
        space_condense,
    );
    let Some(last_prefix) = prefix_lines.last() else {
        return;
    };
    let prefix_width = estimate_composed_line_width(last_prefix, styles);

    // This path only owns the case Hancom wraps: the shape cannot fit after the
    // visible prefix on the current line.  If it fits, leave ordinary reflow
    // untouched rather than trying to model every mixed inline-object case here.
    if prefix_width + control_width_px <= column_inner_width_px + 0.5 {
        return;
    }

    let first_suffix_width = (column_inner_width_px - control_width_px).max(1.0);
    let suffix_lines = split_composed_line_by_width(
        &suffix,
        first_suffix_width,
        column_inner_width_px,
        styles,
        char_break,
        space_condense,
    );
    if suffix_lines.is_empty() {
        return;
    }

    let mut rebuilt = prefix_lines;
    rebuilt.extend(suffix_lines);
    composed.lines = rebuilt;

    if std::env::var("RHWP_DIAG_INLINE_TAC_REWRAP").is_ok() {
        eprintln!(
            "DIAG_INLINE_TAC_REWRAP ctrl={} pos={} shape_w={:.2} prefix_w={:.2} limit={:.2} lines={} text='{}'",
            control_index,
            control_pos,
            control_width_px,
            prefix_width,
            column_inner_width_px,
            composed.lines.len(),
            para.text.chars().take(48).collect::<String>(),
        );
    }
}

pub fn recompose_for_body_width(
    composed: &mut ComposedParagraph,
    para: &Paragraph,
    column_inner_width_px: f64,
    styles: &ResolvedStyleSet,
) {
    restyle_fallback_runs_by_char_shapes(composed, para);
    recompose_for_cell_width(composed, para, column_inner_width_px, styles);
    reflow_single_middle_tac_shape_for_body(composed, para, column_inner_width_px, styles);
}
'''

    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one recompose_for_body_width block, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched {target}")


if __name__ == "__main__":
    main()
