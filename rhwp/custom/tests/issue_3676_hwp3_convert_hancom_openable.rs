//! Issue #3676: HWP3 → HWP5 변환본을 한컴이 열지 못한다.
//!
//! ## 증상
//!
//! `rhwp convert` 로 만든 HWP3 → HWP5 변환본을 한컴 오피스가 거부한다. 표본 20건
//! 전수(100%) 실패였다. **rhwp 자신은 같은 파일을 정상으로 읽으므로** rhwp 리더를
//! 오라클로 쓰는 왕복 검증에서는 드러나지 않았다 — `export-text` 바이트가 원본과
//! 완전히 일치(136,021 = 136,021)하는데도 한컴은 못 연다.
//!
//! ## 근인 (한컴 저장본과의 바이트 대조로 규명)
//!
//! | # | 항목 | 한컴 저장본 | HWP3 변환본 |
//! |---|---|---|---|
//! | 1 | 구역당 `HWPTAG_PAGE_BORDER_FILL` | **3** (양쪽/짝수/홀수) | 1 |
//! | 2 | 그림 개체의 사각형 4점·자르기 | 채워짐 | **전부 0** |
//! | 3 | 개체 요소 `local file version` | **1** | 0 |
//!
//! 셋 중 하나라도 어긋나면 한컴은 **문서 전체**를 거부한다. 그림 5개 중 4개만 채운
//! 상태에서도 거부됐다 — 부분 수정으로는 통과 여부가 갈리지 않는다.
//!
//! ## 이 테스트가 필요한 이유
//!
//! 판정의 정답지는 한컴이지만 CI 에는 한컴이 없다. 대신 위 세 계약을 **저장 바이트에서**
//! 검사한다. 계약이 깨지면 한컴이 거부하므로, 이 테스트가 CI 의 유일한 방어선이다.
#![cfg(not(target_arch = "wasm32"))]

use std::io::Read;

/// HWP3 표본. 그림 5개(본문·표 셀·묶음 개체에 분산)와 도형을 함께 가진다 —
/// 세 계약을 한 문서로 덮는다.
const SAMPLE: &str = "samples/hwp3-sample.hwp";
/// 실제 HWPX는 pageBorderFill BOTH 하나만 가진다. HWP 저장 어댑터가 이 IR을
/// 변형하면 이어지는 HWPX 저장에서 원래 없던 EVEN/ODD가 생긴다.
const SINGLE_BOTH_HWPX: &str = "samples/task2093/saved_single_line_spacing_after.hwpx";

const HWPTAG_BEGIN: u16 = 0x10;
const HWPTAG_PAGE_BORDER_FILL: u16 = HWPTAG_BEGIN + 59;
const HWPTAG_SHAPE_COMPONENT: u16 = HWPTAG_BEGIN + 60;
const HWPTAG_SHAPE_COMPONENT_PICTURE: u16 = HWPTAG_BEGIN + 69;

fn sample_path() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(SAMPLE)
}

/// HWP3 원본을 HWP5 바이트로 변환한다 (CLI `convert` 와 같은 경로).
fn convert_to_hwp5_bytes() -> Vec<u8> {
    let raw = std::fs::read(sample_path()).expect("표본 읽기");
    let mut doc = rhwp::parser::hwp3::parse_hwp3(&raw).expect("HWP3 파싱");
    rhwp::document_core::converters::hwpx_to_hwp::convert_if_hwpx_source(
        &mut doc,
        rhwp::parser::FileFormat::Hwp3,
    );
    rhwp::serializer::cfb_writer::serialize_hwp(&doc).expect("HWP5 직렬화")
}

/// Public HWP3 API도 source format을 보존한 채 같은 adapter 경로를 탄다.
fn convert_to_hwp5_bytes_via_document_core() -> Vec<u8> {
    let raw = std::fs::read(sample_path()).expect("표본 읽기");
    let mut core = rhwp::document_core::DocumentCore::from_bytes(&raw).expect("HWP3 파싱");
    core.export_hwp_with_adapter().expect("HWP5 직렬화")
}

/// 레코드 헤더를 걷으며 `(tag, level, data)` 를 넘긴다.
fn walk_records(raw: &[u8], mut visit: impl FnMut(u16, u16, &[u8])) {
    let mut i = 0usize;
    while i + 4 <= raw.len() {
        let h = u32::from_le_bytes([raw[i], raw[i + 1], raw[i + 2], raw[i + 3]]);
        let tag = (h & 0x3FF) as u16;
        let level = ((h >> 10) & 0x3FF) as u16;
        let mut size = ((h >> 20) & 0xFFF) as usize;
        i += 4;
        if size == 0xFFF {
            if i + 4 > raw.len() {
                return;
            }
            size = u32::from_le_bytes([raw[i], raw[i + 1], raw[i + 2], raw[i + 3]]) as usize;
            i += 4;
        }
        if i + size > raw.len() {
            return;
        }
        visit(tag, level, &raw[i..i + size]);
        i += size;
    }
}

fn inflate(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    flate2::read::DeflateDecoder::new(data)
        .read_to_end(&mut out)
        .expect("Section 압축 해제");
    out
}

fn section_streams(bytes: &[u8]) -> Vec<Vec<u8>> {
    let mut cfb = rhwp::parser::cfb_reader::CfbReader::open(bytes).expect("CFB 열기");
    let mut out = Vec::new();
    for idx in 0..64 {
        let path = format!("/BodyText/Section{idx}");
        if !cfb.has_stream(&path) {
            break;
        }
        out.push(inflate(&cfb.read_stream_raw(&path).expect("Section 읽기")));
    }
    assert!(
        !out.is_empty(),
        "BodyText 스트림이 없다 — 표본/저장 경로 확인"
    );
    out
}

fn section0_xml(bytes: &[u8]) -> String {
    let mut archive = zip::ZipArchive::new(std::io::Cursor::new(bytes)).expect("HWPX ZIP 열기");
    let mut section = archive
        .by_name("Contents/section0.xml")
        .expect("section0.xml 찾기");
    let mut xml = String::new();
    section.read_to_string(&mut xml).expect("section0.xml 읽기");
    xml
}

/// ① 구역마다 쪽 테두리/배경 레코드가 3개다.
#[test]
fn each_section_has_three_page_border_fills() {
    for (idx, raw) in section_streams(&convert_to_hwp5_bytes()).iter().enumerate() {
        let mut n = 0;
        walk_records(raw, |tag, _, _| {
            if tag == HWPTAG_PAGE_BORDER_FILL {
                n += 1;
            }
        });
        assert_eq!(
            n, 3,
            "구역 {idx} 의 PAGE_BORDER_FILL 이 {n}개다. 한컴은 양쪽/짝수쪽/홀수쪽 \
             3개를 요구하며, 하나라도 모자라면 문서 전체를 거부한다."
        );
    }
}

/// 실제 public 저장 경로도 HWP3 출처에만 세 PAGE_BORDER_FILL을 materialize한다.
#[test]
fn public_hwp3_export_has_three_page_border_fills() {
    for (idx, raw) in section_streams(&convert_to_hwp5_bytes_via_document_core())
        .iter()
        .enumerate()
    {
        let mut n = 0;
        walk_records(raw, |tag, _, _| {
            if tag == HWPTAG_PAGE_BORDER_FILL {
                n += 1;
            }
        });
        assert_eq!(n, 3, "public HWP3 export section {idx} PBF count={n}");
    }
}

/// HWP3에만 필요한 세 pageBorderFill 레코드를 HWPX에도 채우면, HWP를 한 번
/// 내보낸 뒤 다시 HWPX로 저장하는 사용 흐름에서 원래 단일 BOTH 문서에 EVEN/ODD가
/// 생긴다. HWPX 출처 IR은 저장 어댑터를 거쳐도 그 구조를 유지해야 한다.
#[test]
fn hwpx_single_both_stays_single_after_hwp_then_hwpx_export() {
    let input =
        std::fs::read(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(SINGLE_BOTH_HWPX))
            .expect("HWPX 표본 읽기");
    let mut core = rhwp::document_core::DocumentCore::from_bytes(&input).expect("HWPX 파싱");

    assert!(
        core.document().sections[0]
            .section_def
            .extra_page_border_fills
            .is_empty(),
        "표본은 BOTH 하나만 가져야 한다"
    );

    let hwp = core.export_hwp_with_adapter().expect("HWP 저장");
    for (idx, raw) in section_streams(&hwp).iter().enumerate() {
        let mut n = 0;
        walk_records(raw, |tag, _, _| {
            if tag == HWPTAG_PAGE_BORDER_FILL {
                n += 1;
            }
        });
        assert_eq!(n, 3, "HWPX export section {idx} PBF count={n}");
    }
    assert!(
        core.document().sections[0]
            .section_def
            .extra_page_border_fills
            .is_empty(),
        "HWPX live IR에 HWP5 전용 EVEN/ODD를 주입하면 안 된다"
    );
    for section in &core.document().sections {
        for paragraph in &section.paragraphs {
            for control in &paragraph.controls {
                let rhwp::model::control::Control::SectionDef(section_def) = control else {
                    continue;
                };
                assert!(
                    section_def.extra_page_border_fills.is_empty(),
                    "HWPX live SectionDef control에 HWP5 전용 EVEN/ODD를 남기면 안 된다"
                );
            }
        }
    }

    let hwpx = core.export_hwpx_native().expect("HWPX 재저장");
    let xml = section0_xml(&hwpx);
    assert!(xml.contains(r#"<hp:pageBorderFill type="BOTH""#));
    assert!(
        !xml.contains(r#"<hp:pageBorderFill type="EVEN""#)
            && !xml.contains(r#"<hp:pageBorderFill type="ODD""#),
        "HWPX 재저장본에 원래 없던 EVEN/ODD pageBorderFill이 생기면 안 된다: {xml}"
    );
}

/// ② 그림 개체의 사각형 4점이 채워져 있다.
#[test]
fn every_picture_has_non_zero_geometry() {
    let mut total = 0;
    let mut zero = 0;
    for raw in section_streams(&convert_to_hwp5_bytes()) {
        walk_records(&raw, |tag, _, data| {
            if tag != HWPTAG_SHAPE_COMPONENT_PICTURE || data.len() < 44 {
                return;
            }
            total += 1;
            // 12..44 = (x,y) 쌍 4개. 전부 0 이면 크기 0 짜리 그림이다.
            if data[12..44].iter().all(|&b| b == 0) {
                zero += 1;
            }
        });
    }
    assert!(total > 0, "표본에 그림이 없다 — 표본이 바뀌었는지 확인하라");
    assert_eq!(
        zero, 0,
        "그림 {total}개 중 {zero}개의 사각형 좌표가 전부 0 이다. 크기 0 짜리 그림이 \
         하나라도 있으면 한컴이 문서 전체를 거부한다."
    );
}

/// ③ 모든 개체 요소의 local file version 이 1 이상이다.
#[test]
fn every_shape_component_has_local_file_version() {
    let mut total = 0;
    let mut zero = 0;
    for raw in section_streams(&convert_to_hwp5_bytes()) {
        walk_records(&raw, |tag, _, data| {
            if tag != HWPTAG_SHAPE_COMPONENT || data.len() < 24 {
                return;
            }
            // ctrl_id 가 1번 또는 2번 기록된다 — 앞 8바이트가 같으면 2번이다.
            let two = data[0..4] == data[4..8];
            let base = if two { 8 } else { 4 };
            // offset_x(4) + offset_y(4) + group_level(2) 다음이 local file version(2).
            let off = base + 10;
            if off + 2 > data.len() {
                return;
            }
            total += 1;
            if u16::from_le_bytes([data[off], data[off + 1]]) == 0 {
                zero += 1;
            }
        });
    }
    assert!(total > 0, "표본에 개체가 없다 — 표본이 바뀌었는지 확인하라");
    assert_eq!(
        zero, 0,
        "개체 {total}개 중 {zero}개의 local file version 이 0 이다. 한컴 저장본은 \
         예외 없이 1 이고, 0 이면 문서 전체가 거부된다(그림만 고치고 도형을 빠뜨렸을 때 \
         20건 중 2건이 이것으로 잔존했다)."
    );
}
