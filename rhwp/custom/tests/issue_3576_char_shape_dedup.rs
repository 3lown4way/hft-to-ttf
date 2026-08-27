//! [#3576] `delete_text_at` 의 char_shape ref 중복 회귀 가드.
//!
//! 계약: 문단 텍스트를 삭제한 뒤 `char_shapes` 의 `start_pos` 는 유일해야 한다
//! (HWP5 규약상 오름차순의 서로 다른 경계). 삭제 범위 안의 ref 들이 클램프로
//! 한 위치에 몰려 중복이 남으면, 이후 삽입에서 뒤쪽 ref(보조 글자모양)가 새
//! 텍스트 일부를 덮어 의도하지 않은 크기·굵기로 렌더된다 — 양식 채우기가
//! `deleteTextInCell`(전체) → `insertTextInCell` 순서로 돌기 때문에 실전에서
//! "값 칸 하나만 글자가 작게 보인다" 로 발현했다.
//!
//! 가드하는 축 세 개:
//!   ① 전체 삭제 후 `start_pos` 유일 (수정 전 실패 = red-check)
//!   ② 전체 삭제 → 재삽입 후 새 텍스트가 주 글자모양 하나로 덮인다
//!   ③ 부분 삭제에서 살아남아야 하는 ref 가 사라지지 않는다 (과잉 dedup 방지)
//!
//! 손으로 `Paragraph` 를 만들면 `char_offsets` 불변식이 깨져 `delete_text_at` 이
//! 슬라이스 범위 패닉을 낸다. 따라서 전부 실제 편집 API 경로로 구성한다.
//!
//! fixture: `samples/2010-01-06.hwp` s0 p4 c0 cell0 — 9행 표의 첫 칸.
#![cfg(not(target_arch = "wasm32"))]

use rhwp::model::control::Control;
use rhwp::model::document::Document;
use rhwp::wasm_api::HwpDocument;
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

const SAMPLE: &str = "samples/2010-01-06.hwp";
const SEC: usize = 0;
const PARA: usize = 4;
const CTRL: usize = 0;
const CELL: usize = 0;

fn open_sample() -> HwpDocument {
    let bytes = fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join(SAMPLE))
        .unwrap_or_else(|e| panic!("fixture 읽기 실패 {SAMPLE}: {e}"));
    HwpDocument::from_bytes(&bytes).unwrap_or_else(|e| panic!("파싱: {e:?}"))
}

/// 대상 셀 첫 문단의 (start_pos, char_shape_id) 목록.
fn cell_char_shapes(doc: &Document) -> Vec<(u32, u32)> {
    let para = &doc.sections[SEC].paragraphs[PARA];
    match para.controls.get(CTRL) {
        Some(Control::Table(t)) => t
            .cells
            .get(CELL)
            .and_then(|c| c.paragraphs.first())
            .map(|p| {
                p.char_shapes
                    .iter()
                    .map(|cs| (cs.start_pos, cs.char_shape_id))
                    .collect()
            })
            .unwrap_or_default(),
        other => panic!("fixture 구조 변경: s{SEC} p{PARA} c{CTRL} 가 표가 아님 ({other:?})"),
    }
}

fn cell_text(doc: &Document) -> String {
    let para = &doc.sections[SEC].paragraphs[PARA];
    match para.controls.get(CTRL) {
        Some(Control::Table(t)) => t
            .cells
            .get(CELL)
            .and_then(|c| c.paragraphs.first())
            .map(|p| p.text.clone())
            .unwrap_or_default(),
        _ => String::new(),
    }
}

/// 셀 첫 문단에 `text` 를 넣고 `[split_at, 끝)` 구간만 8pt 로 바꿔 run 을 쪼갠다.
/// 반환: 쪼개진 뒤의 char_shapes.
fn seed_two_runs(doc: &mut HwpDocument, text: &str, split_at: usize) -> Vec<(u32, u32)> {
    // fixture 셀에는 원래 내용("구   분")이 있다 — 알려진 상태에서 출발하려면 먼저 비운다.
    let existing = cell_text(doc.document()).chars().count() as u32;
    if existing > 0 {
        doc.delete_text_in_cell(
            SEC as u32,
            PARA as u32,
            CTRL as u32,
            CELL as u32,
            0,
            0,
            existing,
        )
        .unwrap_or_else(|e| panic!("셀 기존 텍스트 비우기: {e:?}"));
    }

    doc.insert_text_in_cell(
        SEC as u32,
        PARA as u32,
        CTRL as u32,
        CELL as u32,
        0,
        0,
        text,
    )
    .unwrap_or_else(|e| panic!("셀 텍스트 삽입: {e:?}"));

    doc.apply_char_format_in_cell(
        SEC,
        PARA,
        CTRL,
        CELL,
        0,
        split_at,
        text.chars().count(),
        r#"{"fontSize":800}"#,
    )
    .unwrap_or_else(|e| panic!("셀 글자서식 적용: {e:?}"));

    let shapes = cell_char_shapes(doc.document());
    assert!(
        shapes.len() >= 2,
        "전제 붕괴: run 이 2개 이상으로 쪼개지지 않았다 ({shapes:?}) — \
         이 조건이 아니면 #3576 은 물리지 않는다",
    );
    shapes
}

#[test]
fn full_delete_leaves_unique_char_shape_positions() {
    let mut doc = open_sample();
    let text = "2026. 01. 05.";
    let before = seed_two_runs(&mut doc, text, 6);

    doc.delete_text_in_cell(
        SEC as u32,
        PARA as u32,
        CTRL as u32,
        CELL as u32,
        0,
        0,
        text.chars().count() as u32,
    )
    .unwrap_or_else(|e| panic!("셀 텍스트 전체 삭제: {e:?}"));

    let after = cell_char_shapes(doc.document());
    let positions: Vec<u32> = after.iter().map(|(p, _)| *p).collect();
    let distinct: BTreeSet<u32> = positions.iter().copied().collect();

    assert_eq!(
        positions.len(),
        distinct.len(),
        "#3576: 전체 삭제 후 char_shape start_pos 가 중복됐다 \
         (삭제 전 {before:?} → 삭제 후 {after:?}). 클램프만 하고 중복을 제거하지 않는다.",
    );
}

#[test]
fn refill_after_full_delete_uses_single_char_shape() {
    // 중복 ref 가 남으면 재삽입한 텍스트의 뒷부분이 보조 글자모양(8pt)으로 덮인다.
    let mut doc = open_sample();
    let text = "2026. 01. 05.";
    seed_two_runs(&mut doc, text, 6);

    doc.delete_text_in_cell(
        SEC as u32,
        PARA as u32,
        CTRL as u32,
        CELL as u32,
        0,
        0,
        text.chars().count() as u32,
    )
    .unwrap_or_else(|e| panic!("전체 삭제: {e:?}"));

    let refilled = "2026. 07. 30.";
    doc.insert_text_in_cell(
        SEC as u32,
        PARA as u32,
        CTRL as u32,
        CELL as u32,
        0,
        0,
        refilled,
    )
    .unwrap_or_else(|e| panic!("재삽입: {e:?}"));

    assert_eq!(cell_text(doc.document()), refilled, "재삽입 텍스트 불일치");

    let shapes = cell_char_shapes(doc.document());
    assert_eq!(
        shapes.len(),
        1,
        "#3576: 재삽입한 텍스트가 글자모양 하나로 덮이지 않았다 ({shapes:?}) — \
         보조 run 이 살아남아 새 텍스트 일부를 덮는다.",
    );
    assert_eq!(
        shapes[0].0, 0,
        "#3576: 유일한 char_shape ref 가 위치 0 에서 시작하지 않는다 ({shapes:?})",
    );
}

#[test]
fn partial_delete_keeps_surviving_refs() {
    // 과잉 dedup 방지: 삭제 범위가 run 경계 앞에서 끝나면 뒤 run 은 살아 있어야 하고
    // 위치만 앞으로 당겨져야 한다.
    let mut doc = open_sample();
    let text = "2026. 01. 05.";
    let before = seed_two_runs(&mut doc, text, 6);
    let before_ids: Vec<u32> = before.iter().map(|(_, id)| *id).collect();

    // 앞 3자만 삭제 — 두 번째 run(6) 은 3 으로 당겨지고 살아 있어야 한다.
    doc.delete_text_in_cell(SEC as u32, PARA as u32, CTRL as u32, CELL as u32, 0, 0, 3)
        .unwrap_or_else(|e| panic!("부분 삭제: {e:?}"));

    let after = cell_char_shapes(doc.document());
    let after_ids: Vec<u32> = after.iter().map(|(_, id)| *id).collect();

    assert_eq!(
        after_ids, before_ids,
        "#3576: 부분 삭제에서 살아남아야 하는 char_shape ref 가 사라졌다 \
         (삭제 전 {before:?} → 삭제 후 {after:?}) — dedup 이 과하다.",
    );
    let positions: Vec<u32> = after.iter().map(|(p, _)| *p).collect();
    let distinct: BTreeSet<u32> = positions.iter().copied().collect();
    assert_eq!(
        positions.len(),
        distinct.len(),
        "#3576: 부분 삭제 후에도 start_pos 는 유일해야 한다 ({after:?})",
    );
}
