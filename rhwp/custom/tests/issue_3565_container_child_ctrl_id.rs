//! Issue #3565: 저장한 HWP 를 한컴이 열지 못한다 (387쪽 편람, `open=False`).
//!
//! ## 근인
//!
//! 그룹('$con') 의 `SHAPE_COMPONENT` 는 **자식 개수와 자식별 ctrl_id 목록**을 담는다.
//! 한컴은 이 목록으로 자식 트리를 세우므로, 선언한 종류와 실제로 뒤따르는 자식
//! `SHAPE_COMPONENT` 의 ctrl_id 가 다르면 문서를 열지 못한다.
//!
//! `group_container_component_data` 의 종류 판정이 `serialize_group_child` 의 실제
//! 방출과 두 곳에서 어긋나 있었다.
//!
//! | 자식 | 목록에 쓴 값 | 실제 레코드 |
//! |---|---|---|
//! | 중첩 그룹 | `gso ` | `$con` |
//! | 연결선(connector) | `$lin` | `$col` |
//!
//! rhwp 자기 파서는 이 목록을 참조하지 않고 레코드를 직접 읽으므로 `convert --verify`
//! 가 그대로 통과했다 — 재파스로는 잡히지 않는 계열이다.
//!
//! ## 검증
//!
//! 저장 결과 바이트에서 모든 `$con` 레코드를 찾아, **선언한 자식 ctrl_id 목록**과
//! **실제 자식 레코드의 ctrl_id** 가 일치하는지 본다. 한컴 개방 여부(COM)에 기대지
//! 않고 계약 자체를 고정한다.
#![cfg(not(target_arch = "wasm32"))]

use rhwp::model::control::Control;
use rhwp::model::document::{Document, Section};
use rhwp::model::paragraph::Paragraph;
use rhwp::model::shape::{ConnectorData, GroupShape, LineShape, RectangleShape, ShapeObject};

/// 중첩 그룹이 실제로 들어 있는 추적 샘플 (Task #1771 회귀 형상).
const NESTED_GROUP_SAMPLE: &str = "samples/task1771/nested_group_vectors.hwpx";

const TAG_SHAPE_COMPONENT: u16 = 76;
const ID_CONTAINER: &[u8; 4] = b"$con";

/// 레코드 하나: (태그, 레벨, 데이터)
type Rec = (u16, u16, Vec<u8>);

fn sample(rel: &str) -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(rel)
}

/// 저장 바이트에서 BodyText 전 구역의 레코드를 순서대로 읽는다.
fn body_records(hwp_bytes: &[u8]) -> Vec<Rec> {
    use std::io::Read;
    let cursor = std::io::Cursor::new(hwp_bytes);
    let mut comp = cfb::CompoundFile::open(cursor).expect("cfb 열기");

    let mut fh = comp.open_stream("/FileHeader").expect("FileHeader");
    let mut fh_data = Vec::new();
    fh.read_to_end(&mut fh_data).expect("FileHeader 읽기");
    let compressed = fh_data.get(36).map(|b| (b & 0x01) != 0).unwrap_or(false);
    drop(fh);

    let names: Vec<String> = comp
        .walk()
        .filter(|e| e.is_stream())
        .map(|e| e.path().to_string_lossy().replace('\\', "/"))
        .filter(|p| p.starts_with("/BodyText/Section"))
        .collect();

    let mut out = Vec::new();
    for name in names {
        let mut s = comp.open_stream(&name).expect("Section 스트림");
        let mut raw = Vec::new();
        s.read_to_end(&mut raw).expect("Section 읽기");
        drop(s);
        let data = if compressed {
            let mut d = flate2::read::DeflateDecoder::new(&raw[..]);
            let mut v = Vec::new();
            d.read_to_end(&mut v).expect("inflate");
            v
        } else {
            raw
        };
        let mut pos = 0usize;
        while pos + 4 <= data.len() {
            let header = u32::from_le_bytes(data[pos..pos + 4].try_into().expect("헤더 4B"));
            let tag = (header & 0x3FF) as u16;
            let level = ((header >> 10) & 0x3FF) as u16;
            let mut size = ((header >> 20) & 0xFFF) as usize;
            pos += 4;
            if size == 0xFFF {
                if pos + 4 > data.len() {
                    break;
                }
                size =
                    u32::from_le_bytes(data[pos..pos + 4].try_into().expect("확장 크기")) as usize;
                pos += 4;
            }
            if pos + size > data.len() {
                break;
            }
            out.push((tag, level, data[pos..pos + size].to_vec()));
            pos += size;
        }
    }
    out
}

/// ctrl_id 는 리틀엔디안 u32 로 저장된다(`$con` → `6E 6F 63 24`). 비교·표시가
/// 헷갈리지 않도록 읽는 즉시 사람이 읽는 순서로 뒤집어 돌려준다.
fn ctrl_id_of(data: &[u8]) -> Option<[u8; 4]> {
    let raw: [u8; 4] = data.get(..4)?.try_into().ok()?;
    let mut id = raw;
    id.reverse();
    Some(id)
}

/// `$con` 데이터 꼬리에서 자식 ctrl_id 목록을 되읽는다.
///
/// 꼬리 배치는 `[자식 수 u16][자식 ctrl_id u32 × N][instance_id u32]` 다. 앞쪽 공통부
/// 길이는 도형마다 달라 앞에서부터 셀 수 없으므로 뒤에서 역산하고, 모든 id 가 인쇄
/// 가능한 4글자여야 한다는 조건으로 후보를 가른다.
fn declared_child_ids(data: &[u8]) -> Option<Vec<[u8; 4]>> {
    for n in 1..=256usize {
        let tail = 2 + 4 * n + 4;
        if data.len() < tail {
            break;
        }
        let off = data.len() - tail;
        let count = u16::from_le_bytes(data[off..off + 2].try_into().expect("2B")) as usize;
        if count != n {
            continue;
        }
        let ids: Vec<[u8; 4]> = (0..n)
            .map(|i| {
                let s = off + 2 + 4 * i;
                let mut id: [u8; 4] = data[s..s + 4].try_into().expect("4B");
                id.reverse();
                id
            })
            .collect();
        if ids
            .iter()
            .all(|id| id.iter().all(|b| b.is_ascii_graphic() || *b == b' '))
        {
            return Some(ids);
        }
    }
    None
}

/// 모든 `$con` 레코드에 대해 (선언한 자식 목록, 실제 자식 ctrl_id 목록) 을 모은다.
fn container_child_pairs(recs: &[Rec]) -> Vec<(Vec<[u8; 4]>, Vec<[u8; 4]>)> {
    let mut out = Vec::new();
    for (i, (tag, level, data)) in recs.iter().enumerate() {
        if *tag != TAG_SHAPE_COMPONENT || ctrl_id_of(data).as_ref() != Some(ID_CONTAINER) {
            continue;
        }
        let Some(declared) = declared_child_ids(data) else {
            continue;
        };
        // 직계 자식 = 이 레코드보다 한 단계 깊은 SHAPE_COMPONENT. 레벨이 다시
        // 컨테이너 이하로 올라오면 형제 구간이므로 중단한다.
        let mut actual = Vec::new();
        for (t, lv, d) in &recs[i + 1..] {
            if *lv <= *level {
                break;
            }
            if *t == TAG_SHAPE_COMPONENT && *lv == *level + 1 {
                if let Some(id) = ctrl_id_of(d) {
                    actual.push(id);
                }
            }
        }
        out.push((declared, actual));
    }
    out
}

fn show(ids: &[[u8; 4]]) -> String {
    ids.iter()
        .map(|id| String::from_utf8_lossy(id).to_string())
        .collect::<Vec<_>>()
        .join(", ")
}

fn assert_declarations_match(hwp_bytes: &[u8], context: &str, want_child: &[u8; 4]) {
    let recs = body_records(hwp_bytes);
    let pairs = container_child_pairs(&recs);
    assert!(
        !pairs.is_empty(),
        "{context}: 그룹('$con') 레코드를 찾지 못했다 — 표본이 바뀌었는지 확인하라"
    );
    let mut saw_target = false;
    for (declared, actual) in &pairs {
        if declared.iter().any(|id| id == want_child) {
            saw_target = true;
        }
        assert_eq!(
            show(declared),
            show(actual),
            "{context}: 그룹이 선언한 자식 종류와 실제 자식 레코드가 다르다.\n\
             한컴은 이 목록으로 자식 트리를 세우므로 어긋나면 문서를 열지 못한다."
        );
    }
    assert!(
        saw_target,
        "{context}: 검증 대상 자식 종류({})가 표본에 없다 — 표본이 바뀌었는지 확인하라",
        show(&[*want_child])
    );
}

/// 중첩 그룹: 자식 목록이 `gso ` 가 아니라 `$con` 이어야 한다.
#[test]
fn nested_group_child_is_declared_as_container() {
    let bytes = std::fs::read(sample(NESTED_GROUP_SAMPLE)).expect("표본 읽기");
    let doc = rhwp::parser::parse_document(&bytes).expect("파싱");
    let saved = rhwp::serializer::serialize_document(&doc).expect("직렬화");
    assert_declarations_match(&saved, "중첩 그룹 표본", b"$con");
}

/// 연결선: 자식 목록이 `$lin` 이 아니라 `$col` 이어야 한다.
#[test]
fn connector_child_is_declared_as_connector() {
    let mut connector = LineShape::default();
    connector.connector = Some(ConnectorData::default());

    let group = GroupShape {
        children: vec![
            ShapeObject::Group(GroupShape {
                children: vec![ShapeObject::Rectangle(RectangleShape::default())],
                ..Default::default()
            }),
            ShapeObject::Line(connector),
            ShapeObject::Line(LineShape::default()),
            ShapeObject::Rectangle(RectangleShape::default()),
        ],
        ..Default::default()
    };

    let mut para = Paragraph::default();
    para.controls
        .push(Control::Shape(Box::new(ShapeObject::Group(group))));
    // 확장 컨트롤 1개 = 8 코드 유닛 + 문단 종결자.
    para.char_count = 9;

    let mut doc = Document::default();
    doc.sections.push(Section {
        paragraphs: vec![para],
        ..Default::default()
    });
    doc.doc_properties.section_count = 1;

    let saved = rhwp::serializer::serialize_document(&doc).expect("직렬화");
    assert_declarations_match(&saved, "연결선 합성 표본", b"$col");
}
