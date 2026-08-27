//! `extract-pages` — 쪽 범위만 남겨 저장하는 진단 도구 (#3565).
//!
//! 387쪽 문서가 저장 후 한컴에서 열리지 않을 때, 절반씩 잘라 재현 여부를 보면 방아쇠를
//! 좁힐 수 있다. 그때 필요한 것이 이 기능이다.
//!
//! 계약은 셋이다.
//!
//! 1. 요청 범위에 걸친 문단은 남고, 나머지는 지워진다 (쪽수가 줄어든다).
//! 2. 잘라 낸 결과가 **다시 열리는 정상 문서**여야 한다 — 재파싱이 되어야 이분법이 성립한다.
//! 3. 범위가 잘못되면 조용히 넘어가지 않고 오류를 낸다.
//!
//! 결과 쪽수가 요청 범위와 정확히 같을 필요는 없다(잘라 낸 뒤 레이아웃이 다시 흐른다).
//! 목적은 재현 최소화이지 정밀한 페이지 오려내기가 아니다.
#![cfg(not(target_arch = "wasm32"))]

use rhwp::document_core::DocumentCore;

/// 여러 쪽·여러 구역이 있는 표본.
const SAMPLE: &str = "samples/issue2083_hide_fill_page.hwpx";

/// 원본 스트림 통과(`raw_stream`)를 들고 오는 HWP5 출처 표본.
const HWP5_SAMPLE: &str = "samples/2022년 국립국어원 업무계획.hwp";

fn load() -> DocumentCore {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(SAMPLE);
    let bytes = std::fs::read(&path).expect("표본 읽기");
    DocumentCore::from_bytes(&bytes).expect("파싱")
}

fn total_paragraphs(core: &DocumentCore) -> usize {
    core.document()
        .sections
        .iter()
        .map(|s| s.paragraphs.len())
        .sum()
}

/// 첫 쪽만 남기면 쪽수와 문단 수가 함께 줄어든다.
#[test]
fn extracting_first_page_shrinks_the_document() {
    let mut core = load();
    let pages_before = core.page_count();
    let paras_before = total_paragraphs(&core);
    assert!(
        pages_before >= 2,
        "표본이 1쪽뿐이라 추출을 검증할 수 없다 — 표본이 바뀌었는지 확인하라"
    );

    let report = core.extract_page_range(1, 1).expect("1쪽 추출");

    assert_eq!(report.pages_before, pages_before);
    assert!(
        report.pages_after < pages_before,
        "쪽수가 줄지 않았다: {} → {}",
        report.pages_before,
        report.pages_after
    );
    assert!(report.removed > 0, "지운 문단이 없다");
    assert!(
        total_paragraphs(&core) < paras_before,
        "문단이 줄지 않았다: {paras_before} → {}",
        total_paragraphs(&core)
    );
}

/// 잘라 낸 결과가 다시 열려야 이분법이 성립한다.
#[test]
fn extracted_document_is_still_loadable() {
    let mut core = load();
    core.extract_page_range(1, 1).expect("1쪽 추출");

    let saved = core.export_hwp_native().expect("저장");
    let reloaded = DocumentCore::from_bytes(&saved).expect("잘라 낸 산출물 재파싱");
    assert!(
        reloaded
            .document()
            .sections
            .iter()
            .any(|s| !s.paragraphs.is_empty()),
        "재파싱 결과가 비어 있다"
    );
}

/// HWP5 출처 문서에서도 추출이 **저장 결과에 실제로 반영**된다.
///
/// HWP5 로 연 문서는 구역마다 `raw_stream`(원본 바이트)을 들고 있고, 저장기는 그것이
/// 남아 있으면 원본을 그대로 되돌려 준다. 삭제하면서 이 통과를 무효화하지 않으면
/// **잘라 낸 결과가 저장본에서 조용히 사라진다** — 컴파일 에러도 테스트 실패도 없이.
/// `extract_page_range` 는 삭제를 `delete_paragraph_native` 에 위임해 그쪽이 무효화한다
/// (#2724 원장에 위임으로 등재). 그 위임이 실제로 듣는지 저장 결과로 확인한다.
#[test]
fn extraction_survives_saving_for_hwp5_source() {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(HWP5_SAMPLE);
    let bytes = std::fs::read(&path).expect("HWP5 표본 읽기");
    let mut core = DocumentCore::from_bytes(&bytes).expect("파싱");

    let had_passthrough = core
        .document()
        .sections
        .iter()
        .any(|s| s.raw_stream.is_some());
    assert!(
        had_passthrough,
        "HWP5 표본인데 raw_stream 이 없다 — 통과 경로를 검증할 수 없다"
    );

    let paras_before = total_paragraphs(&core);
    let report = core.extract_page_range(1, 1).expect("1쪽 추출");
    assert!(
        report.removed > 0,
        "지운 문단이 없어 검증이 성립하지 않는다"
    );

    let saved = core.export_hwp_native().expect("저장");
    let reloaded = DocumentCore::from_bytes(&saved).expect("재파싱");
    assert!(
        total_paragraphs(&reloaded) < paras_before,
        "저장본에 삭제가 반영되지 않았다 ({paras_before} → {}) — \
         원본 스트림 통과가 무효화되지 않아 편집이 사라진 것이다",
        total_paragraphs(&reloaded)
    );
}

/// 전체 범위를 요청하면 아무것도 지우지 않는다.
#[test]
fn full_range_keeps_everything() {
    let mut core = load();
    let pages = core.page_count();
    let paras = total_paragraphs(&core);

    let report = core.extract_page_range(1, pages).expect("전체 범위");

    assert_eq!(report.removed, 0, "전체 범위인데 문단을 지웠다");
    assert_eq!(report.pages_after, pages);
    assert_eq!(total_paragraphs(&core), paras);
}

/// 잘못된 범위는 조용히 넘어가지 않고 오류를 낸다.
#[test]
fn invalid_ranges_are_rejected() {
    let mut core = load();
    let pages = core.page_count();

    assert!(core.extract_page_range(0, 1).is_err(), "0쪽 시작을 받았다");
    assert!(
        core.extract_page_range(3, 2).is_err(),
        "from > to 를 받았다"
    );
    assert!(
        core.extract_page_range(pages + 1, pages + 2).is_err(),
        "문서 쪽수를 넘는 시작 쪽을 받았다"
    );
}
