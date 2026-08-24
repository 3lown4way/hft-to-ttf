# Converter core

Place the previously generated **KICE09_HFT_converter_v3_3** source package here.

The Actions wrapper recognizes these entrypoints automatically:

- `build_all_fonts.bat`
- `build_needed_fonts.bat`
- `build_47_fonts.bat`
- `convert_all.py`
- `hft_to_ttf.py`
- `converter.py`
- `main.py`

If the recovered package uses another command, set `HFT_CONVERTER_COMMAND` in `.github/workflows/convert-fonts.yml`.

Do not replace the v3.3 decoder with an older partial decoder: different HFT families can use different internal glyph streams.
