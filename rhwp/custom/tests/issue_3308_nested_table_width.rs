//! Issue #3308 회귀 가드 — 좁은 중첩 표의 선언 폭 유지 + 셀 내 가운데 배치.
//!
//! 직인 표시는 1×2 중첩 표(|…요구권자(직위)|직인|)의 오른쪽 셀(바깥 4변 주황
//! 테두리)이다. 종전에는 전면 스트레치 정규화가 이 표(선언 435.1px, 부모 셀 폭
//! 대비 0.679)를 셀 폭 641.3px 로 늘려 직인 셀이 한컴 대비 +97.5px 밀렸다.
//!
//! 한컴 권위: 편집기 크기 판독 115.13mm = 선언 폭 정확 일치, 재저장본 선언 유지,
//! 정답지 픽셀(직인 x=598.7px). 저장된 h_offset(21.96mm)은 한컴도 조판에 쓰지
//! 않음을 실측으로 확인(작업지시자 판정) — 셀 내 가운데 모델이 0.6px 정합.
//!
//! 수정: ①스트레치에 비율 하한 0.9(#2195 보호 대상 0.956~0.995 는 유지)
//! ②하한 미만 비-TAC 중첩 표는 선언 폭 + 셀 내 가운데.

use std::process::Command;

fn rhwp_bin() -> String {
    std::env::var("CARGO_BIN_EXE_rhwp").unwrap_or_else(|_| env!("CARGO_BIN_EXE_rhwp").to_string())
}

const FIXTURE: &str = "samples/task3307/issue3307_outline_number.hwpx";
/// 한컴 2020 정답지 p7 실측 (96dpi px).
const HANCOM_SEAL_X: f64 = 598.7;
const HANCOM_NESTED_WIDTH: f64 = 435.1;
const TOLERANCE_PX: f64 = 5.0;

#[test]
fn narrow_nested_table_keeps_declared_width_and_centers() {
    let out_dir = std::env::temp_dir().join("issue3308_render_tree");
    let _ = std::fs::remove_dir_all(&out_dir);
    std::fs::create_dir_all(&out_dir).unwrap();

    let status = Command::new(rhwp_bin())
        .args([
            "export-render-tree",
            FIXTURE,
            "-p",
            "6",
            "-o",
            out_dir.to_str().unwrap(),
        ])
        .status()
        .expect("rhwp 실행");
    assert!(status.success(), "export-render-tree 실패");

    let json_path = out_dir.join("render_tree_007.json");
    let tree: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&json_path).unwrap()).unwrap();

    let mut seal_x = None;
    let mut nested_w = None;
    fn walk(n: &serde_json::Value, seal_x: &mut Option<f64>, nested_w: &mut Option<f64>) {
        let text = n["text"].as_str().unwrap_or("");
        if text.starts_with("직인") {
            *seal_x = n["bbox"]["x"].as_f64();
        }
        // 직인을 담은 중첩 표 노드 — Table 이면서 폭이 선언 폭 부근(스트레치 시 641)
        if n["type"] == "Table" {
            if let Some(w) = n["bbox"]["w"].as_f64() {
                let holds_seal = n.to_string().contains("직인");
                if holds_seal && w < 500.0 {
                    *nested_w = Some(w);
                }
            }
        }
        if let Some(children) = n["children"].as_array() {
            for c in children {
                walk(c, seal_x, nested_w);
            }
        }
    }
    walk(&tree, &mut seal_x, &mut nested_w);

    let seal_x = seal_x.expect("직인 TextRun 을 찾지 못했다 — 통짜 스트레치로 회귀?");
    assert!(
        (seal_x - HANCOM_SEAL_X).abs() <= TOLERANCE_PX,
        "직인 x={seal_x:.1} — 한컴 {HANCOM_SEAL_X} 대비 허용 오차({TOLERANCE_PX}px) 초과. \
         중첩 표 스트레치/배치 회귀"
    );
    let nested_w = nested_w.expect("선언 폭 중첩 표 노드 부재 — 스트레치(641px)로 회귀한 것");
    assert!(
        (nested_w - HANCOM_NESTED_WIDTH).abs() <= TOLERANCE_PX,
        "중첩 표 폭 {nested_w:.1} — 선언 {HANCOM_NESTED_WIDTH} 유지 실패"
    );

    let _ = std::fs::remove_dir_all(&out_dir);
}
