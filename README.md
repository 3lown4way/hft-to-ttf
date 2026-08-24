# HFT → TTF Actions

Private GitHub Actions project for converting the supplied Hancom/HFT font collection to TTF with the previously built KICE09 HFT converter.

## Repository layout

- `source_archives/` — supplied font set split into four GitHub-safe ZIP files
- `scripts/extract_sources.py` — restores the original `fonts/` folder during CI
- `converter/` — location for the recovered `KICE09_HFT_converter_v3_3` source
- `scripts/run_converter.py` — stable CI adapter
- `scripts/validate_ttf.py` — validates generated TTF files with fontTools
- `output_ttf/` — generated TTFs
- `.github/workflows/convert-fonts.yml` — Windows Server 2025 GitHub Actions workflow

## Workflow

1. Checkout repository on `windows-2025`.
2. Set up Python 3.12.
3. Expand `source_archives/fonts-part-*.zip` into `fonts/`.
4. Inventory the restored HFT/TTF collection.
5. Run the recovered v3.3 converter.
6. Validate every generated TTF with fontTools.
7. Upload generated TTFs as a workflow artifact.
8. Optionally commit changed TTFs back to `output_ttf/`.

The workflow is manual (`workflow_dispatch`) until the converter core is restored, so incomplete setup does not create repeated failed runs.

## Source inventory

The supplied set contains 420 files: 387 HFT files, 32 existing TTF files, and 1 INF file.

The four source ZIPs are intentionally below GitHub's per-file size limit. Their SHA-256 values are recorded in `source_archives/README.md`.

## Converter core

The previously built `KICE09_HFT_converter_v3_3` source was not found in the current GitHub repositories or File Library search. Put the recovered converter source under `converter/` (or set `HFT_CONVERTER_COMMAND`) before running the workflow.

## Redistribution

Keep this repository private unless redistribution rights have been verified for every source and converted font. Format conversion does not itself grant redistribution rights.
