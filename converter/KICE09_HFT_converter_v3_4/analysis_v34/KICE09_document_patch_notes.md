# KICE09 document-specific patch notes

These bindings are specific to the 2009-06 KICE Korean-language HWPX/PDF environment and must not be treated as universal Unicode mappings.

## U+A2EE list marker

- Source scalar in the recovered HWPX/PDF text layer: `U+A2EE` (`ꋮ`), 5 occurrences, charPr 9 / font combo 6.
- Modern Unicode semantics (`YI SYLLABLE NZIX`) are irrelevant to the original document rendering.
- A direct alias to `SPSMJ.HFT` HNC `0x343F` was tested and rejected: that HNC code is the ordinary, full-size `U+25C6` BLACK DIAMOND.
- The recovered Hancom document rendering is the legacy `U+F02EE` list marker (`󰋮`). The supplied `HBATANG.TTF` contains that marker as a centered small diamond.
- Production composite rule: preserve source `U+A2EE`, but bind it to the supplied-Hancom `U+F02EE` small-diamond outline scaled from 1024 UPM to 1000 UPM.
- `U+25C6` remains mapped to its ordinary full-size diamond and must not alias `U+A2EE`.

Recovered HBATANG `U+F02EE` metrics before scaling:

- UPEM: 1024
- advance: 1024
- LSB: 194
- outline points: `(512,685) (194,367) (512,50) (829,367)`

Composite 1000-UPM patch:

- advance: 1000
- LSB: 189
- outline points: `(500,669) (189,358) (500,49) (810,358)`
- bbox: `(189,49)-(810,669)`

## U+A854 / U+A855

- `U+A854` → alias of `SPSMJ.HFT` HNC `0x341A` (`『`).
- `U+A855` → alias of `SPSMJ.HFT` HNC `0x341B` (`』`).
- Ordinary bracket Unicode mappings remain intact.

## U+F076

- `USER.HFT` HNC `0x3C30` → `U+F076`.
- This is the black decorative marker used in the source document (e.g. 강연 목적/전략).

## Bold

- 12 actually used charPr records have `bold=1`.
- Bold uses the same script-wise HFT fontRefs as Regular; it is synthetic rendering, not a bold-face substitution.
- Production HWPX path therefore keeps Regular composite TTFs and preserves `bold=1` in the character properties.
- The v3.4 metric-only bold mode is diagnostic and must not be used as the production rendering model.
