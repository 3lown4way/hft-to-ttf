# HFT → TTF Actions

Private GitHub Actions project for reconstructing the KICE09 HFT font environment with `KICE09_HFT_converter_v3_4`.

## Current input method

No Windows PC, Google Drive, or 195 MB source upload is required.

Upload one file only:

- `inputs/kice09-required48.zip`

The prepared ZIP is about 20 MB and contains the 48 HFT files required by v3.4. It is below GitHub's browser upload limit.

## Workflow

1. Checkout on `windows-2025`.
2. Set up Python 3.12 and fontTools.
3. Extract `inputs/kice09-required48.zip` to `fonts/`.
4. Require exactly 48 HFT files.
5. Verify every HFT against `manifests/kice09_required48_sha256.txt`.
6. Run the committed `converter/KICE09_HFT_converter_v3_4` source.
7. Validate generated TTFs with fontTools.
8. Upload generated TTFs as a workflow artifact.
9. Optionally commit generated TTFs to `output_ttf/`.

## Converter source

The required v3.4 core is already committed in this repository, including:

- `hft_core_v34.py`
- `build_composite.py`
- `build_kice09_all_composites.py`
- `analysis_v34/KICE09_fontref_combinations_v34.csv`

## Scope

v3.4 reconstructs the KICE09 document font environment from the validated HFT set. It is not yet a universal one-HFT-to-one-TTF converter for all 387 HFT files; JP HFT generic Unicode mapping and some legacy layouts still require additional work.

## Redistribution

Keep this repository private unless redistribution rights have been verified for the source and converted fonts.
