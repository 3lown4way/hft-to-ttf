# 이전 세션 복구 메모

이 메모는 JH 프로젝트의 평가원/이감 재조판 작업을 다음 세션에서 그대로 이어가기 위한 체크포인트입니다.

## 기준

- rhwp upstream: `edwardkim/rhwp`
- pin: `496333b27d21ddb9114ba9ae340bcb895870c9a7` (v0.8.4)
- HFT→TTF 기준 산출물: 부모 저장소 `output_ttf/`

## 이전 세션에서 확인된 상태

- HFT 기반 본문 폰트 13종 생성 및 런타임 사용
- 따옴표 보정: composite TTF 4종에서 `‘’=230`, `“”=441`
- HY견고딕/한양견고딕 계열 검증 및 `홀수형` 렌더에 실제 폰트 적용
- HFT 기반 runtime font metric을 생성해 rhwp의 `src/renderer/font_metrics_data.rs`에 반영했던 작업 이력 존재
- 이전 임시 working tree는 `/tmp/rhwp`에 있었고 세션 종료 후 사라졌지만, 렌더/감사 산출물과 생성된 metric 파일은 별도 산출물로 복구됨

## 현재 가장 중요한 조판 이슈

`과당 입찰` 같은 평가원식 문장 내부 박스는 자유 배치 도형이 아니라 HWP의 GSO rectangle + `treat_as_char=true` 인라인 개체다.

rhwp에는 이미 TAC Shape의 폭 예약, `inline_shape_position`, 페이지 라우팅 수정(Issue #476 계열)이 들어 있으므로, KICE 재조판 생성 단계에서 이 구조를 그대로 만들고 renderer가 절대좌표 fallback으로 빠지지 않게 해야 한다.

다음 작업 순서:

1. 부모 저장소의 HFT TTF를 rhwp runtime에 연결
2. 이전 runtime font metric 재생성/반영
3. 평가원 원본 HWP의 인라인 GSO 구조를 기준으로 `과당 입찰` 재현
4. 4쪽부터 렌더 비교
5. HY견고딕/따옴표/밑줄 기존 수정이 회귀하지 않는지 재검증

폐기 대상으로 지정된 예전 HWPX 실작업본은 기준으로 사용하지 않는다.
