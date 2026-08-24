# HFT → TTF Actions

Private GitHub Actions project for reconstructing TTF fonts from the supplied Hancom/HFT font collection with `KICE09_HFT_converter_v3_4`.

## Repository layout

- `source_archives/` — supplied font set split into GitHub-safe ZIP files
- `scripts/extract_sources.py` — restores the original `fonts/` folder during CI
- `converter/` — `KICE09_HFT_converter_v3_4` package/source
- `scripts/run_converter.py` — v3.4 Windows CI adapter
- `scripts/validate_ttf.py` — validates generated TTF files with fontTools
- `output_ttf/` — generated TTFs
- `.github/workflows/convert-fonts.yml` — Windows Server 2025 GitHub Actions workflow

## Workflow

1. Checkout on `windows-2025`.
2. Set up Python 3.12 and fontTools.
3. Expand `source_archives/fonts-part-*.zip` into `fonts/`.
4. Inventory the restored HFT/TTF collection.
5. Run `KICE09_HFT_converter_v3_4` using its validated KICE09 fontRef-combination builder.
6. Validate generated TTFs with fontTools.
7. Upload generated TTFs as a workflow artifact.
8. Optionally commit changed TTFs back to `output_ttf/`.

## Source inventory

The supplied set contains 420 files: 387 HFT files, 32 existing TTF files, and 1 INF file.

## Converter v3.4 scope

The supplied v3.4 package contains `hft_core_v34.py`, `build_composite.py`, `build_kice09_body_from_zip.py`, and `build_kice09_all_composites.py`.  Its own status document reports successful layout/decode regression checks for the 47 HFT files explicitly used by the KICE09 document environment.

v3.4 is not yet a universal one-HFT-to-one-TTF converter for all 387 HFT files. In particular, generic Unicode mapping for JP HFT is intentionally not implemented, and some legacy layouts outside the validated KICE09 set need additional parser work. The Actions workflow therefore uses the validated KICE09 v3.4 composite path rather than pretending unsupported files were converted correctly.

## Converter package placement

Commit either of these under `converter/`:

- `converter/KICE09_HFT_converter_v3_4/` (expanded source directory), or
- `converter/KICE09_HFT_converter_v3_4.zip` (the package ZIP; the CI adapter extracts it automatically).

## Redistribution

Keep this repository private unless redistribution rights have been verified for every source and converted font. Format conversion does not itself grant redistribution rights.
