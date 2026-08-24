# Input

Upload exactly one file here:

- `kice09-required48.zip`

This ZIP must contain the 48 HFT files required by `KICE09_HFT_converter_v3_4` at the ZIP root. The GitHub Actions workflow extracts it to `fonts/` and verifies every file against `manifests/kice09_required48_sha256.txt` before conversion.
