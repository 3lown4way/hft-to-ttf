//! [#3552] 표 CommonObjAttr 편집의 저장 반영 무회귀 가드 (테스트 전용).
//!
//! **이 파일은 버그 수정이 아니다.** 이 축은 이미 닫혀 있다 — #2055 (커밋 902031fb)가
//! `set_table_properties_native` 뒷부분에서 attr 비트를 `raw_ctrl_data` FLAGS(0..4)에
//! 동기화한다(`table_ops.rs`). 계약을 테스트로 고정해 두는 것이 목적이다.
//!
//! 왜 필요한가: serializer 는 무손실 왕복을 위해 `table.raw_ctrl_data` 가 있으면 원본
//! 바이트를 그대로 재사용한다(`serializer/control.rs`). 따라서 표의 CommonObjAttr 를
//! 편집하는 경로는 IR 만 갱신해서는 안 되고 raw 쪽도 함께 맞춰야 한다. 이 결합은
//! 코드를 읽는 것만으로는 놓치기 쉬워서(#3552 등록 당시 실제로 놓쳤다) 테스트로
//! 못박아 둔다.
//!
//! 향후 이 축을 **무효화 계약**(`raw_ctrl_data.clear()` + #1916 의 IR 재합성 폴백)으로
//! 리팩터링하게 되면 3번이 사전 가드가 된다 — 재합성 경로에 손실 축이 있으면 그때
//! 다른 필드가 조용히 날아간다.
//!
//! 가드하는 축 다섯 개:
//!   ① CommonObjAttr 편집이 HWP5 저장→재파스에서 보존된다
//!      (FLAGS 동기화 한 줄을 되돌리면 실패한다 — 이 테스트가 그 축을 실제로 지킨다)
//!   ② HWPX 저장에서도 보존된다 (HWPX 는 IR 파생이라 raw 와 무관하게 통과해야 한다)
//!   ③ 저장 왕복이 **다른** CommonObjAttr 필드(여백/오프셋/크기/설명 등 23축)를
//!      손실시키지 않는다 — 무효화 리팩터링 시의 사전 가드
//!   ④ CommonObjAttr 와 무관한 표 편집(cellSpacing 등)은 raw 를 건드리지 않는다
//!      (과잉 무효화 방지)
//!   ⑤ 무편집 문서의 저장 왕복은 바이트 안정적이다 (raw 재사용 경로 무회귀)
//!
//! fixture: `samples/2010-01-06.hwp` s0 p4 c0 — 9행 표, raw_ctrl_data 40B 보유
//! (attr=0x082A2311 → treat_as_char=true). raw 가 채워진 평범한 HWP5 파스본이라
//! raw/IR 결합이 그대로 드러나는 조건이다.
#![cfg(not(target_arch = "wasm32"))]

use rhwp::model::control::Control;
use rhwp::model::document::Document;
use rhwp::model::shape::CommonObjAttr;
use rhwp::parser::hwpx::parse_hwpx;
use rhwp::parser::parse_document;
use rhwp::serializer::hwpx::serialize_hwpx;
use rhwp::serializer::serialize_document;
use rhwp::wasm_api::HwpDocument;
use std::fs;
use std::path::{Path, PathBuf};

const SAMPLE: &str = "samples/2010-01-06.hwp";
const SEC: usize = 0;
const PARA: usize = 4;
const CTRL: usize = 0;

fn sample_bytes() -> Vec<u8> {
    let p: PathBuf = Path::new(env!("CARGO_MANIFEST_DIR")).join(SAMPLE);
    fs::read(&p).unwrap_or_else(|e| panic!("fixture 읽기 실패 {SAMPLE}: {e}"))
}

/// 고정 좌표의 표를 집는다. 편집 전/후 같은 주소를 보므로 좌표계가 닫힌다.
fn table_at(doc: &Document) -> &rhwp::model::table::Table {
    let para = doc.sections[SEC]
        .paragraphs
        .get(PARA)
        .unwrap_or_else(|| panic!("fixture 구조 변경: s{SEC} p{PARA} 없음"));
    match para.controls.get(CTRL) {
        Some(Control::Table(t)) => t,
        other => panic!("fixture 구조 변경: s{SEC} p{PARA} c{CTRL} 가 표가 아님 ({other:?})"),
    }
}

/// 편집 대상이 아닌 CommonObjAttr 필드들 — 무효화 후에도 그대로여야 한다.
fn preserved_axes(c: &CommonObjAttr) -> Vec<(&'static str, String)> {
    vec![
        ("vertical_offset", c.vertical_offset.to_string()),
        ("horizontal_offset", c.horizontal_offset.to_string()),
        ("width", c.width.to_string()),
        ("height", c.height.to_string()),
        ("z_order", c.z_order.to_string()),
        ("margin.left", c.margin.left.to_string()),
        ("margin.right", c.margin.right.to_string()),
        ("margin.top", c.margin.top.to_string()),
        ("margin.bottom", c.margin.bottom.to_string()),
        ("instance_id", c.instance_id.to_string()),
        ("prevent_page_break", c.prevent_page_break.to_string()),
        ("description", c.description.clone()),
        ("flow_with_text", c.flow_with_text.to_string()),
        ("allow_overlap", c.allow_overlap.to_string()),
        ("size_protect", c.size_protect.to_string()),
        ("text_wrap", format!("{:?}", c.text_wrap)),
        ("text_flow", format!("{:?}", c.text_flow)),
        ("vert_rel_to", format!("{:?}", c.vert_rel_to)),
        ("vert_align", format!("{:?}", c.vert_align)),
        ("horz_rel_to", format!("{:?}", c.horz_rel_to)),
        ("horz_align", format!("{:?}", c.horz_align)),
        ("width_criterion", format!("{:?}", c.width_criterion)),
        ("height_criterion", format!("{:?}", c.height_criterion)),
    ]
}

/// fixture 를 열고 treat_as_char 를 반대로 뒤집는다. (원래값, 뒤집은 문서) 반환.
fn flip_treat_as_char() -> (bool, HwpDocument) {
    let bytes = sample_bytes();
    let mut doc = HwpDocument::from_bytes(&bytes).unwrap_or_else(|e| panic!("파싱: {e:?}"));

    let before = {
        let t = table_at(doc.document());
        assert!(
            !t.raw_ctrl_data.is_empty(),
            "전제 붕괴: fixture 표의 raw_ctrl_data 가 비어 있으면 이 축이 아니다 \
             (raw 부재 경로는 #1916 이 이미 가드한다)",
        );
        t.common.treat_as_char
    };

    let want = !before;
    doc.set_table_properties(
        SEC as u32,
        PARA as u32,
        CTRL as u32,
        &format!(r#"{{"treatAsChar":{want}}}"#),
    )
    .unwrap_or_else(|e| panic!("set_table_properties: {e:?}"));

    // IR 은 즉시 바뀌어야 한다 — 이게 안 되면 버그의 층이 다르다.
    assert_eq!(
        table_at(doc.document()).common.treat_as_char,
        want,
        "IR 갱신 자체가 안 됨 (편집 명령 문제이지 저장 문제가 아니다)",
    );

    (before, doc)
}

#[test]
fn treat_as_char_change_survives_hwp5_save() {
    let (before, doc) = flip_treat_as_char();
    let want = !before;

    let out = serialize_document(doc.document()).unwrap_or_else(|e| panic!("HWP5 직렬화: {e:?}"));
    let reparsed = parse_document(&out).unwrap_or_else(|e| panic!("HWP5 재파싱: {e:?}"));

    assert_eq!(
        table_at(&reparsed).common.treat_as_char,
        want,
        "#3552: treat_as_char 변경이 HWP5 저장에서 유실됨 (원본 {before} → 편집 {want} → \
         재파스 {}). raw_ctrl_data FLAGS 동기화가 빠지면 옛 바이트가 나간다.",
        table_at(&reparsed).common.treat_as_char,
    );
}

#[test]
fn treat_as_char_change_survives_hwpx_save() {
    let (before, doc) = flip_treat_as_char();
    let want = !before;

    let out = serialize_hwpx(doc.document()).unwrap_or_else(|e| panic!("HWPX 직렬화: {e:?}"));
    let reparsed = parse_hwpx(&out).unwrap_or_else(|e| panic!("HWPX 재파싱: {e:?}"));

    assert_eq!(
        table_at(&reparsed).common.treat_as_char,
        want,
        "#3552: treat_as_char 변경이 HWPX 저장에서 유실됨 (원본 {before} → 편집 {want})",
    );
}

#[test]
fn other_common_obj_attr_fields_survive_save_roundtrip() {
    // #3552 주의사항: 이 축을 무효화 계약으로 바꾸면 저장이 재합성 경로에 의존한다.
    // 재합성이 손실 축을 가지면 treat_as_char 를 살리는 대가로 여백·오프셋·설명 등이
    // 날아간다. 지금(동기화 방식)도 잔여 필드 보존은 계약이므로 함께 고정해 둔다.
    let bytes = sample_bytes();
    let pristine = parse_document(&bytes).unwrap_or_else(|e| panic!("원본 파싱: {e:?}"));
    let expected = preserved_axes(&table_at(&pristine).common);

    let (_, doc) = flip_treat_as_char();
    let out = serialize_document(doc.document()).unwrap_or_else(|e| panic!("직렬화: {e:?}"));
    let reparsed = parse_document(&out).unwrap_or_else(|e| panic!("재파싱: {e:?}"));
    let actual = preserved_axes(&table_at(&reparsed).common);

    let mut lost = Vec::new();
    for ((name, want), (_, got)) in expected.iter().zip(actual.iter()) {
        if want != got {
            lost.push(format!("{name}: {want} → {got}"));
        }
    }
    assert!(
        lost.is_empty(),
        "#3552: raw 무효화가 다른 CommonObjAttr 필드를 손실시켰다 — 재합성 경로에 구멍이 있다:\n  {}",
        lost.join("\n  "),
    );
}

#[test]
fn table_record_only_change_keeps_raw_ctrl_data() {
    // CommonObjAttr 와 무관한 편집(cellSpacing 은 HWPTAG_TABLE 레코드 축)은 raw 를
    // 건드릴 이유가 없다. 무조건 무효화/재작성하면 무변경 문서의 바이트 동등성이 깨진다.
    let bytes = sample_bytes();
    let mut doc = HwpDocument::from_bytes(&bytes).unwrap_or_else(|e| panic!("파싱: {e:?}"));
    let raw_before = table_at(doc.document()).raw_ctrl_data.clone();
    assert!(!raw_before.is_empty(), "전제: raw_ctrl_data 보유 표");

    doc.set_table_properties(
        SEC as u32,
        PARA as u32,
        CTRL as u32,
        r#"{"cellSpacing":42}"#,
    )
    .unwrap_or_else(|e| panic!("set_table_properties: {e:?}"));

    assert_eq!(
        table_at(doc.document()).raw_ctrl_data,
        raw_before,
        "#3552: CommonObjAttr 무관 편집이 raw_ctrl_data 를 무효화했다 (과잉 무효화)",
    );
}

#[test]
fn untouched_document_save_is_byte_stable() {
    // raw 재사용 경로 무회귀: 아무 편집도 하지 않은 문서의 저장 왕복은 안정적이어야 한다.
    let bytes = sample_bytes();
    let doc1 = parse_document(&bytes).unwrap_or_else(|e| panic!("파싱: {e:?}"));
    let out1 = serialize_document(&doc1).unwrap_or_else(|e| panic!("1차 직렬화: {e:?}"));
    let doc2 = parse_document(&out1).unwrap_or_else(|e| panic!("재파싱: {e:?}"));
    let out2 = serialize_document(&doc2).unwrap_or_else(|e| panic!("2차 직렬화: {e:?}"));

    assert_eq!(
        out1.len(),
        out2.len(),
        "#3552: 무편집 저장 왕복이 불안정 (raw 재사용 경로 회귀)",
    );
    assert!(
        out1 == out2,
        "#3552: 무편집 저장 왕복 바이트 불일치 (raw 재사용 경로 회귀)",
    );
    assert!(
        !table_at(&doc2).raw_ctrl_data.is_empty(),
        "#3552: 무편집인데 raw_ctrl_data 가 사라졌다",
    );
}
