//! Issue #3311 회귀 가드 — malformed CFB 입력은 패닉이 아니라 `Err` 로 끝난다.
//!
//! 외부 리포터(cargo-fuzz, 격리 CDR 파이프라인 하드닝 중)가 `LenientCfbReader::open`
//! 의 OOB 슬라이스 패닉을 보고했다(`cfb_reader.rs:407`, "range end index 8020 out of
//! range for slice of length 3072"). 표준 CFB 파서가 `Malformed FAT` 로 실패한 뒤
//! lenient 재시도 경로에서 손상된 섹터 id(예: 1851072928)를 경계 검사 없이 오프셋으로
//! 쓰는 것이 원인이었다.
//!
//! 결함 자체는 `6a761a793`(#3220 악성 입력 방어 6건, 2026-07-24)에서 해소됐다 —
//! 리포터 커밋 `8d3bfa4b`(07-17)에 이 하니스를 적용하면 같은 지점에서 패닉이 재현되고,
//! `6a761a793` 부터 통과한다(worktree 실측, task #3311 Stage 1). 다만 그 수정들은
//! **개별 방어를 추가했을 뿐 "손상 입력은 패닉하지 않는다"는 계약을 고정하지 않았다.**
//! 이 테스트가 그 계약을 못박아 같은 클래스의 재유입을 검출한다.
//!
//! 패닉은 라이브러리 소비자(WASM 모듈 포함)를 통째로 죽이므로, 신뢰 경계에서 파싱하는
//! 이용자에게는 DoS 다. 열기 실패(`Err`)로 끝나는 것이 언제나 낫다.

use rhwp::wasm_api::HwpDocument;

/// 리포터가 보고한 실측 값 — 이 조합이 구 커밋에서 패닉을 냈다.
const REPORTED_FAT_ENTRIES: u32 = 824;
const REPORTED_POISON_SECTOR: u32 = 1_851_072_928;
const REPORTED_FIRST_DIFAT: u32 = 128;
const REPORTED_LEN: usize = 3072;

/// 손상 CFB 를 합성한다. 헤더는 유효 매직·섹터 크기를 갖되, DIFAT·FAT 엔트리를
/// 손상 섹터 id 로 채워 체인 순회가 파일 범위를 벗어난 오프셋을 만들게 한다.
fn synth_malformed_cfb(
    len: usize,
    fat_count: u32,
    difat_count: u32,
    first_difat: u32,
    poison: u32,
) -> Vec<u8> {
    let mut d = vec![0u8; len];
    d[0..8].copy_from_slice(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1");
    d[30..32].copy_from_slice(&9u16.to_le_bytes()); // sector size 512
    d[32..34].copy_from_slice(&6u16.to_le_bytes()); // mini sector 64
    d[44..48].copy_from_slice(&fat_count.to_le_bytes());
    d[48..52].copy_from_slice(&0u32.to_le_bytes()); // first dir sector
    d[56..60].copy_from_slice(&4096u32.to_le_bytes()); // mini stream cutoff
    d[60..64].copy_from_slice(&poison.to_le_bytes()); // first mini FAT
    d[64..68].copy_from_slice(&fat_count.to_le_bytes());
    d[68..72].copy_from_slice(&first_difat.to_le_bytes());
    d[72..76].copy_from_slice(&difat_count.to_le_bytes());
    // 헤더 DIFAT 109 슬롯
    for i in 0..109usize {
        let off = 76 + i * 4;
        let sid = if i == 0 { first_difat } else { poison };
        d[off..off + 4].copy_from_slice(&sid.to_le_bytes());
    }
    // 본문을 손상 FAT 엔트리로 채운다
    for off in (512..len.saturating_sub(4)).step_by(4) {
        d[off..off + 4].copy_from_slice(&poison.to_le_bytes());
    }
    d
}

/// 손상 입력 목록: 리포터 조건 + 경계 스윕 + 실 샘플 뮤테이션/절단.
fn malformed_cases() -> Vec<(String, Vec<u8>)> {
    let mut cases = vec![(
        "reporter_exact".to_string(),
        synth_malformed_cfb(
            REPORTED_LEN,
            REPORTED_FAT_ENTRIES,
            REPORTED_FAT_ENTRIES,
            REPORTED_FIRST_DIFAT,
            REPORTED_POISON_SECTOR,
        ),
    )];

    for &len in &[512usize, 513, 1024, REPORTED_LEN, 4096, 8192] {
        for &fat in &[0u32, 1, REPORTED_FAT_ENTRIES, 65_535, u32::MAX] {
            for &poison in &[0u32, 1, 128, REPORTED_POISON_SECTOR, u32::MAX - 1] {
                cases.push((
                    format!("synth_len{len}_fat{fat}_poison{poison}"),
                    synth_malformed_cfb(len, fat, fat, REPORTED_FIRST_DIFAT, poison),
                ));
            }
        }
    }

    // 실 HWP5 샘플의 헤더 필드를 손상시켜 "정상 문서에서 한 필드만 깨진" 경로도 덮는다.
    if let Ok(real) = std::fs::read("samples/hwpers_test4_complex_table.hwp") {
        for &field_off in &[30usize, 44, 48, 60, 64, 68, 72] {
            for &val in &[0u32, u32::MAX, REPORTED_POISON_SECTOR] {
                if field_off + 4 <= real.len() {
                    let mut m = real.clone();
                    m[field_off..field_off + 4].copy_from_slice(&val.to_le_bytes());
                    cases.push((format!("real_field{field_off}_val{val}"), m));
                }
            }
        }
        for frac in [2usize, 3, 4, 8, 16] {
            cases.push((
                format!("real_truncated_1_over_{frac}"),
                real[..real.len() / frac].to_vec(),
            ));
        }
    }

    cases
}

#[test]
fn malformed_cfb_returns_err_instead_of_panicking() {
    let cases = malformed_cases();
    assert!(
        cases.len() >= 150,
        "케이스 수가 급감했다 — 샘플 경로 변경 등으로 커버리지가 줄었는지 확인할 것"
    );

    let mut opened = 0usize;
    for (name, bytes) in &cases {
        // 패닉하면 이 지점에 도달하지 못하고 테스트가 실패한다 —
        // 그것이 이 가드가 잡으려는 회귀다.
        match HwpDocument::from_bytes(bytes) {
            Ok(_) => opened += 1,
            Err(_) => {}
        }
        let _ = name;
    }

    // 전부 열려버리면 손상 입력이 아니게 된 것이므로 케이스 자체를 재점검해야 한다.
    assert!(
        opened < cases.len(),
        "손상 입력이 모두 정상 개봉됐다 — 케이스가 더 이상 malformed 가 아니다"
    );
}
