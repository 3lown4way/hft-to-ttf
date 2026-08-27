# JH/KICE customized rhwp recovery

This source snapshot is reconstructed from `edwardkim/rhwp` commit
`496333b27d21ddb9114ba9ae340bcb895870c9a7` (v0.8.4), then overlaid with
the rhwp source change that survived the previous JH working session:

- `src/renderer/font_metrics_data.rs` generated from the 13 HFT-derived
  KICE runtime fonts.

Preserved SHA-256 of that source file:
`5c0c65ced6f93236aac5279cbdbc9306672ec67dbcef2d1a77878af18385a007`.

The complete unmodified upstream repository remains pinned at
`rhwp/upstream`; this vendored tree intentionally keeps source/tests/build
metadata and omits upstream's very large binary/sample/document assets.

Other session work such as quote glyph placement and HY견고딕 lives in
the HFT/font pipeline and must not be replaced by arbitrary system fonts.

KICE inline boxed terms must follow the HWP GSO rectangle +
`treat_as_char=true` path, not a detached absolute-position shape.
