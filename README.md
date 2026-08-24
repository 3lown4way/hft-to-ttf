# HFT → TTF Actions

Private GitHub Actions project for reconstructing the KICE09 HFT font environment with `KICE09_HFT_converter_v3_4`.

## Current input method

No Windows PC, Google Drive, or 195 MB source upload is required.

Upload one file only:

- `inputs/kice09-required48.zip`

The prepared ZIP is about 20 MB and contains 47 explicitly used HFT files plus `HGOLD.HFT`, retained as the deferred old-Hangul fallback candidate.

## Workflow

1. Checkout on `windows-2025`.
2. Set up Python 3.12 and fontTools.
3. Verify `inputs/kice09-required48.zip` against `manifests/kice09_required48_sha256.txt`.
4. Build the 13 actually used KICE09 fontRef combinations in parallel.
5. Validate every generated TTF with fontTools and document-specific CI checks.
6. Collect the 13 TTFs, upload an artifact, and commit them to `output_ttf/`.

Generated files use the recovered original Korean face names rather than numeric `KICE09_combo_XX` names. A qualifier is added only when the same Hangul face occurs with a materially different Latin/Hanja/Japanese/symbol combination.

## KICE09 document-specific mappings

These are reconstruction rules for this document, not universal Unicode/HFT mappings.

- `USER.HFT` HNC `0x3C30` → `U+F076`.
- `SPSMJ.HFT` HNC `0x341A/0x341B` retain their ordinary book-title brackets and additionally expose the KICE09 `U+A854/U+A855` aliases.
- Source `U+A2EE` is a legacy list marker. It must **not** render as the modern Yi syllable and must **not** use the ordinary full-size `U+25C6` black diamond. Combo 6 receives the recovered Hancom legacy `U+F02EE` small-diamond outline, reconstructed from the supplied `HBATANG.TTF` and scaled to the composite 1000 UPM. Ordinary `U+25C6` remains independent.

## Bold policy

The original HWPX uses the **same script-wise base fontRefs** for Regular and Bold text. Bold is a character-property (`charPr bold=1`) rendering operation, not a substitution with a separate bold HFT face.

For exact Hancom/HWPX retypesetting:

- install/use the reconstructed Regular composite TTF;
- preserve the original `bold=1` character property;
- let the Hancom renderer synthesize the bold outline from that same Regular face;
- do **not** substitute another bold-looking font and do **not** pre-embolden a TTF and then apply `bold=1` again.

The v3.4 metric-only `--with-provisional-bold` mode is diagnostic only and is not used by the production Actions workflow.

## Old Hangul / HGOLD

`HGOLD.HFT` is kept for the unresolved Hanyang-PUA old-Hangul fallback. It is not currently merged into the 13 production composites. Old-Hangul recovery is deliberately deferred because the exact PUA-to-HGOLD bindings remain to be audited and it is not required for most ordinary Korean mock-exam pages.

## Converter source

The required v3.4 core is committed in this repository, including:

- `hft_core_v34.py`
- `build_composite.py`
- `build_kice09_all_composites.py`
- `build_one_combo_ci.py`
- `kice09_document_patches.py`
- `analysis_v34/KICE09_fontref_combinations_v34.csv`

## Scope

v3.4 reconstructs the KICE09 document font environment from the validated HFT set. It is not yet a universal one-HFT-to-one-TTF converter for all 387 HFT files; JP HFT generic Unicode mapping and some legacy layouts still require additional work.

## Redistribution

Keep this repository private unless redistribution rights have been verified for the source and converted fonts.
