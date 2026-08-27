//! Issue #3236 회귀 가드 — 쪽 잔여를 넘는 1×1 표 셀 내용의 다음 쪽 분할.
//!
//! 리포터 fixture 의 표(1행 1열, RowBreak, 선언 322.6px vs 셀 내용 측정 910.8px)는
//! #1891 의 단일행 선언-신뢰 특례에 걸려 통짜 배치됐고, 셀 내용 588px 가 쪽 하단
//! 밖에서 clip 되어 소실됐다(`LAYOUT_OVERFLOW_CELL` 23건). 한컴 2020 정답지 PDF 는
//! 이 셀을 쪽 경계에서 분할해 p2 를 "경과되지 않은 외국인투자기업인…" 으로 잇는다.
//!
//! 수정: 특례에 `SINGLE_ROW_DECLARED_TRUST_MAX_RATIO`(1.5배) 상한을 추가 — 측정이
//! 선언의 1.5배를 넘으면 폰트 팽창이 아니라 진짜 큰 내용이므로 인트라-로우 분할
//! 경로에 맡긴다. 분할점은 한컴과 글자 단위로 일치한다.

use rhwp::wasm_api::HwpDocument;

const FIXTURE: &str = "samples/task3236/issue3236_split_table.hwpx";

/// 한컴 정답지 p2 의 시작 텍스트 — 셀 분할 경계의 결정 증거.
/// 수정 전에는 이 텍스트가 p1 의 쪽 밖 clip 구간에 방출되고 p2 에는 없었다.
const P2_BOUNDARY_TEXT: &str = "경과되지";

fn svg_text(svg: &str) -> String {
    let mut out = String::new();
    let mut rest = svg;
    while let Some(start) = rest.find("<text") {
        let Some(open_end) = rest[start..].find('>') else {
            break;
        };
        let after = &rest[start + open_end + 1..];
        let Some(close) = after.find("</text>") else {
            break;
        };
        out.push_str(&after[..close]);
        rest = &after[close..];
    }
    out
}

#[test]
fn single_cell_table_content_splits_to_next_page() {
    let bytes = std::fs::read(FIXTURE).unwrap();
    let doc = HwpDocument::from_bytes(&bytes).unwrap();

    // 분할이 새 쪽을 만들지 않아야 한다 — 한컴 정답지도 2쪽이다.
    assert_eq!(
        doc.page_count(),
        2,
        "쪽수는 한컴 정답지와 같은 2가 유지되어야 한다"
    );

    let p1 = svg_text(&doc.render_page_svg(0).unwrap());
    let p2 = svg_text(&doc.render_page_svg(1).unwrap());

    // 분할 경계: 한컴 p2 시작 텍스트가 rhwp p2 에 있어야 하고, p1 에 남아 있으면
    // 통짜 배치(쪽 밖 clip 소실)로 돌아간 것이다.
    assert!(
        p2.contains(P2_BOUNDARY_TEXT),
        "셀 분할 후반부가 p2 로 이어져야 한다 (한컴 정답지 p2 시작 텍스트 부재)"
    );
    assert!(
        !p1.contains(P2_BOUNDARY_TEXT),
        "p1 에 경계 텍스트가 남아 있으면 표가 통짜 배치되어 쪽 밖으로 넘친 것이다"
    );

    // 분포 가드: 통짜 배치 시 p1/p2 텍스트량이 84%/16% 로 쏠린다(정상 46%/54%).
    let (l1, l2) = (p1.chars().count() as f64, p2.chars().count() as f64);
    let p1_share = l1 / (l1 + l2);
    assert!(
        (0.35..=0.60).contains(&p1_share),
        "p1 텍스트 비중 {p1_share:.2} — 한컴 분포(0.45)에서 크게 벗어났다"
    );
}
