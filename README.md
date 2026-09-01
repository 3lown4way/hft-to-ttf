# HFT → TTF Actions

`KICE09_HFT_converter_v3_4`를 사용하여 KICE09의 HFT 폰트 환경을 재구성하기 위한 비공개 GitHub Actions 프로젝트입니다.

## 현재 입력 방식

Windows PC, Google Drive, 195 MB 원본 파일 업로드가 필요하지 않습니다.

아래 파일 하나만 업로드하면 됩니다.

- `inputs/kice09-required48.zip`

준비된 ZIP 파일의 크기는 약 20 MB이며, 실제 사용이 확인된 HFT 파일 47개와 추후 옛한글 fallback 후보로 유지하는 `HGOLD.HFT`가 들어 있습니다.

## 작업 흐름

1. `windows-2025` 환경에서 저장소를 checkout합니다.
2. Python 3.12와 fontTools를 설정합니다.
3. `inputs/kice09-required48.zip`을 `manifests/kice09_required48_sha256.txt`와 대조하여 검증합니다.
4. KICE09에서 실제 사용되는 13개 fontRef 조합을 병렬로 빌드합니다.
5. 생성된 모든 TTF를 fontTools와 문서 전용 CI 검사로 검증합니다.
6. 13개 TTF를 모아 artifact로 업로드하고 `output_ttf/`에도 커밋합니다.

생성 파일은 숫자형 `KICE09_combo_XX` 이름 대신 복원된 원래 한글 글꼴명을 사용합니다. 동일한 한글 글꼴이 서로 실질적으로 다른 영문/한자/일본어/기호 조합과 함께 사용되는 경우에만 구분용 이름을 추가합니다.

## KICE09 문서 전용 매핑

아래 규칙은 이 문서를 재구성하기 위한 규칙이며, 모든 Unicode/HFT에 공통으로 적용되는 범용 매핑 규칙은 아닙니다.

- `USER.HFT` HNC `0x3C30` → `U+F076`.
- `SPSMJ.HFT` HNC `0x341A/0x341B`는 일반적인 서명 괄호 문자를 그대로 유지하면서, KICE09용 `U+A854/U+A855` alias도 추가로 제공합니다.
- 원본 `U+A2EE`는 legacy 목록 표시 문자입니다. 이 문자는 현대 Yi 음절로 렌더링해서는 **안 되며**, 일반적인 전각 크기의 `U+25C6` 검은 마름모도 사용해서는 **안 됩니다**. Combo 6에는 제공된 `HBATANG.TTF`에서 복원한 Hancom legacy `U+F02EE`의 작은 마름모 윤곽을 사용하고, composite의 1000 UPM에 맞게 스케일링합니다. 일반 `U+25C6` 문자는 별도로 유지됩니다.

## Bold 처리 정책

원본 HWPX는 Regular와 Bold 텍스트 모두에 대해 **동일한 script-wise 기본 fontRef**를 사용합니다. Bold는 별도의 Bold HFT 글꼴로 교체하는 방식이 아니라 문자 속성인 `charPr bold=1`에 의해 렌더링됩니다.

Hancom/HWPX와 최대한 동일하게 조판하려면 다음 원칙을 따릅니다.

- 재구성된 Regular composite TTF를 설치하거나 사용합니다.
- 원본의 `bold=1` 문자 속성을 그대로 유지합니다.
- Hancom renderer가 같은 Regular 글꼴을 기반으로 Bold 윤곽을 합성하도록 합니다.
- 다른 굵은 글꼴로 대체하지 말고, TTF 자체를 미리 굵게 만든 뒤 다시 `bold=1`을 적용해서도 **안 됩니다**.

v3.4의 metric-only `--with-provisional-bold` 모드는 진단용이며, 실제 배포용 Actions workflow에서는 사용하지 않습니다.

## 옛한글 / HGOLD

`HGOLD.HFT`는 아직 해결되지 않은 Hanyang-PUA 옛한글 fallback을 위해 보관합니다. 현재 13개 production composite에는 병합하지 않습니다. 정확한 PUA-to-HGOLD 대응 관계에 대한 추가 검증이 필요하고, 일반적인 한국어 모의고사 대부분의 페이지에는 필수적이지 않기 때문에 옛한글 복원은 의도적으로 이후 작업으로 미뤄 두었습니다.

## Converter 소스

필요한 v3.4 core는 이 저장소에 포함되어 있으며, 주요 파일은 다음과 같습니다.

- `hft_core_v34.py`
- `build_composite.py`
- `build_kice09_all_composites.py`
- `build_one_combo_ci.py`
- `kice09_document_patches.py`
- `analysis_v34/KICE09_fontref_combinations_v34.csv`

## 적용 범위

v3.4는 검증된 HFT 세트를 사용하여 KICE09 문서의 폰트 환경을 재구성합니다. 아직 387개 HFT 전체를 각각 하나의 TTF로 변환하는 범용 one-HFT-to-one-TTF converter는 아닙니다. JP HFT의 범용 Unicode 매핑과 일부 legacy layout은 추가 작업이 필요합니다.

## 재배포

원본 및 변환 폰트에 대한 재배포 권한이 확인되기 전까지는 이 저장소를 비공개로 유지하십시오.
