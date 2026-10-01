## Remaining line-edit recount (1302)

Evidence note only. The scorer is unchanged. These counts are the current line edits on the same 54 pages (1302/29835, CER 4.36%), each edit assigned once. `product_pass` stays false. Overall gate stays GATE_FAIL.

| Bucket | Edits | What it is |
|---|---:|---|
| 1. Fragment lines still unaligned | 32 | Short CJK text-layer lines still separate, while one OCR line already contains them, and the current rule did not join them |
| 2. OCR characters absent from the text layer | 337 | Letterheads, English company names, and other OCR text that is not in the page text layer |
| 3. Real misses or wrong characters | 933 | Wrong line pairing, substitutions, and text-layer lines OCR did not produce |
| Sum | 1302 | |

32 + 337 + 933 = 1302. The non-binding split 304 + 339 + 659 does not match this recount. 337 is near the 339 insertion estimate. The other 304 are not residual fragment lines; they are in bucket 3.

Bucket 1 is three pages: `pub-gx-minzu-ultrasound-2026` page 6 (20, table cells 项/号/货物/名称/数/量/单/位 against `项货物数单` and `号名称量位`), `pub-gx-tianlin-yuegui-devices-2026` page 8 (8, `数量` + `单位` against `数量单位`), `fixture-001` page 32 (4, `日` against `日期:`). `fixture-003` page 5 and `pub-gx-youjiang-ultrasound` page 5 stay at 0 in this bucket.

Bucket 2 is dominated by `fixture-003` pages 5 and 4 (93 and 84: `cpil`, `北京数字支点`, the English letterhead, and one garbled line), then `pub-gx-tianlin-yuegui-devices-2026` page 1 (39, the English 广西恒桥 line). The Chinese 广西恒桥 header is also in the body, so that extra 12-character copy is bucket 3.

Bucket 3 is dominated by `fixture-003` page 5 (156), `fixture-002` page 6 (105), `pub-gx-minzu-ultrasound-2026` page 2 (92), `pub-gx-info-center-compute-2026` page 5 (87), `pub-gx-youjiang-ultrasound` page 6 (82), `pub-gx-minzu-ultrasound-2026` page 1 (77), and `pub-gx-youjiang-ultrasound` page 5 (69).

| doc | page | edits | fragment | absent | miss |
|---|---:|---:|---:|---:|---:|
| fixture-003 | 5 | 249 | 0 | 93 | 156 |
| fixture-003 | 4 | 139 | 0 | 84 | 55 |
| fixture-002 | 6 | 135 | 0 | 30 | 105 |
| pub-gx-youjiang-ultrasound | 6 | 94 | 0 | 12 | 82 |
| pub-gx-minzu-ultrasound-2026 | 2 | 92 | 0 | 0 | 92 |
| pub-gx-info-center-compute-2026 | 5 | 87 | 0 | 0 | 87 |
| pub-gx-minzu-ultrasound-2026 | 1 | 77 | 0 | 0 | 77 |
| pub-gx-youjiang-ultrasound | 5 | 69 | 0 | 0 | 69 |
| pub-gx-tianlin-yuegui-devices-2026 | 1 | 51 | 0 | 39 | 12 |
| pub-gx-ventilator-monitors | 5 | 42 | 0 | 0 | 42 |
| pub-gx-minzu-ultrasound-2026 | 6 | 24 | 20 | 0 | 4 |
| fixture-003 | 9 | 23 | 0 | 16 | 7 |
| pub-gx-tianlin-yuegui-devices-2026 | 8 | 23 | 8 | 0 | 15 |
| fixture-003 | 29 | 22 | 0 | 21 | 1 |
| fixture-001 | 32 | 17 | 4 | 0 | 13 |
| fixture-003 | 35 | 16 | 0 | 16 | 0 |
| pub-gx-nanning-vascular-doppler | 17 | 16 | 0 | 2 | 14 |
| pub-gx-daxin-ultrasound-anesthesia | 73 | 13 | 0 | 0 | 13 |
| pub-gx-tianlin-yuegui-devices-2026 | 2 | 12 | 0 | 4 | 8 |
| fixture-001 | 2 | 8 | 0 | 7 | 1 |
| pub-gx-yibiatong-phase2-2026 | 2 | 8 | 0 | 4 | 4 |
| fixture-001 | 14 | 7 | 0 | 7 | 0 |
| fixture-002 | 3 | 6 | 0 | 2 | 4 |
| fixture-002 | 37 | 6 | 0 | 0 | 6 |
| pub-gx-hechi-mine-safety-2026 | 1 | 6 | 0 | 0 | 6 |
| pub-gx-nanxishan-dr-mammo-2026 | 2 | 6 | 0 | 0 | 6 |
| pub-gx-qintang-flow-cytometer | 3 | 6 | 0 | 0 | 6 |
| pub-gx-hechi-mine-safety-2026 | 2 | 4 | 0 | 0 | 4 |
| pub-gx-nanning-vascular-doppler | 3 | 4 | 0 | 0 | 4 |
| pub-gx-nanxishan-dr-mammo-2026 | 9 | 4 | 0 | 0 | 4 |
| pub-gx-nonggang-patrol-2026 | 9 | 4 | 0 | 0 | 4 |
| pub-gx-qintang-flow-cytometer | 1 | 4 | 0 | 0 | 4 |
| pub-gx-daxin-ultrasound-anesthesia | 3 | 3 | 0 | 0 | 3 |
| pub-gx-daxin-ultrasound-anesthesia | 4 | 3 | 0 | 0 | 3 |
| pub-gx-nanning-vascular-doppler | 16 | 3 | 0 | 0 | 3 |
| pub-gx-ventilator-monitors | 3 | 3 | 0 | 0 | 3 |
| pub-gx-nonggang-patrol-2026 | 2 | 2 | 0 | 0 | 2 |
| pub-gx-ventilator-monitors | 4 | 2 | 0 | 0 | 2 |
| pub-gx-ventilator-monitors | 15 | 2 | 0 | 0 | 2 |
| pub-gx-yibiatong-phase2-2026 | 3 | 2 | 0 | 0 | 2 |
| fixture-001 | 3 | 1 | 0 | 0 | 1 |
| fixture-003 | 1 | 1 | 0 | 0 | 1 |
| pub-gx-daxin-ultrasound-anesthesia | 1 | 1 | 0 | 0 | 1 |
| pub-gx-daxin-ultrasound-anesthesia | 51 | 1 | 0 | 0 | 1 |
| pub-gx-hechi-mine-safety-2026 | 3 | 1 | 0 | 0 | 1 |
| pub-gx-info-center-compute-2026 | 2 | 1 | 0 | 0 | 1 |
| pub-gx-youjiang-ultrasound | 2 | 1 | 0 | 0 | 1 |
| pub-gx-youjiang-ultrasound | 4 | 1 | 0 | 0 | 1 |

Six pages have 0 edits: `fixture-002` pages 1 and 33, `pub-gx-qintang-flow-cytometer` page 4, `pub-gx-nanxishan-dr-mammo-2026` page 1, `pub-gx-info-center-compute-2026` page 1, `pub-gx-nonggang-patrol-2026` page 3.

## Bucket 3 split (933)

Evidence note only. The scorer is unchanged. This splits the 933 real misses only. The 32 still-unaligned fragments and the 337 text-layer-absent edits stay where they are.

Alignment is the current greedy line match, then a substitution-preferring optimal Levenshtein path. A deletion run is consecutive delete operations; a substitution or an insertion ends the run. An unmatched text-layer line is one run of its full length. `product_pass` stays false. Overall gate stays GATE_FAIL.

| Sub-bucket | Edits |
|---|---:|
| Consecutive deletions of 6 or more characters | 342 |
| Short deletions of 1 to 5 characters | 172 |
| Substitutions | 369 |
| In-text-layer insertions still inside these 933 | 50 |
| Sum | 933 |

342 + 172 + 369 + 50 = 933. The three named classes sum to 883. The other 50 are OCR characters that already occur in the page text layer, so they were not part of the 337. Twenty-nine of them are a whole unused OCR line, including the extra `广西恒桥项目管理有限公司` header on `pub-gx-tianlin-yuegui-devices-2026` page 1 (12). Twenty-one are extra characters inside a paired line. They are not substitutions.

The non-binding split 435 + 154 + 70 does not match. That description was for the older 659, on the 1481-edit score.

Long deletions are dominated by `pub-gx-minzu-ultrasound-2026` page 1 (49) and page 2 (40), `fixture-002` page 6 (46), `pub-gx-info-center-compute-2026` page 5 (39), `pub-gx-youjiang-ultrasound` page 6 (35) and page 5 (34), and `fixture-003` page 5 (33). Substitutions are dominated by `fixture-003` page 5 (88), `pub-gx-minzu-ultrasound-2026` page 2 (47), `pub-gx-info-center-compute-2026` page 5 (43), and `fixture-002` page 6 (42).

| doc | page | miss | long | short | sub | ins |
|---|---:|---:|---:|---:|---:|---:|
| fixture-003 | 5 | 156 | 33 | 30 | 88 | 5 |
| fixture-002 | 6 | 105 | 46 | 13 | 42 | 4 |
| pub-gx-minzu-ultrasound-2026 | 2 | 92 | 40 | 5 | 47 | 0 |
| pub-gx-info-center-compute-2026 | 5 | 87 | 39 | 3 | 43 | 2 |
| pub-gx-youjiang-ultrasound | 6 | 82 | 35 | 9 | 34 | 4 |
| pub-gx-minzu-ultrasound-2026 | 1 | 77 | 49 | 12 | 16 | 0 |
| pub-gx-youjiang-ultrasound | 5 | 69 | 34 | 12 | 21 | 2 |
| fixture-003 | 4 | 55 | 21 | 1 | 33 | 0 |
| pub-gx-ventilator-monitors | 5 | 42 | 25 | 5 | 12 | 0 |
| pub-gx-tianlin-yuegui-devices-2026 | 8 | 15 | 0 | 9 | 3 | 3 |
| pub-gx-nanning-vascular-doppler | 17 | 14 | 0 | 8 | 0 | 6 |
| fixture-001 | 32 | 13 | 8 | 5 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia | 73 | 13 | 12 | 1 | 0 | 0 |
| pub-gx-tianlin-yuegui-devices-2026 | 1 | 12 | 0 | 0 | 0 | 12 |
| pub-gx-tianlin-yuegui-devices-2026 | 2 | 8 | 0 | 8 | 0 | 0 |
| fixture-003 | 9 | 7 | 0 | 5 | 2 | 0 |
| fixture-002 | 37 | 6 | 0 | 6 | 0 | 0 |
| pub-gx-hechi-mine-safety-2026 | 1 | 6 | 0 | 1 | 0 | 5 |
| pub-gx-nanxishan-dr-mammo-2026 | 2 | 6 | 0 | 4 | 2 | 0 |
| pub-gx-qintang-flow-cytometer | 3 | 6 | 0 | 2 | 4 | 0 |
| fixture-002 | 3 | 4 | 0 | 2 | 2 | 0 |
| pub-gx-hechi-mine-safety-2026 | 2 | 4 | 0 | 4 | 0 | 0 |
| pub-gx-minzu-ultrasound-2026 | 6 | 4 | 0 | 1 | 3 | 0 |
| pub-gx-nanning-vascular-doppler | 3 | 4 | 0 | 2 | 0 | 2 |
| pub-gx-nanxishan-dr-mammo-2026 | 9 | 4 | 0 | 4 | 0 | 0 |
| pub-gx-nonggang-patrol-2026 | 9 | 4 | 0 | 1 | 3 | 0 |
| pub-gx-qintang-flow-cytometer | 1 | 4 | 0 | 0 | 0 | 4 |
| pub-gx-yibiatong-phase2-2026 | 2 | 4 | 0 | 4 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia | 3 | 3 | 0 | 2 | 1 | 0 |
| pub-gx-daxin-ultrasound-anesthesia | 4 | 3 | 0 | 0 | 3 | 0 |
| pub-gx-nanning-vascular-doppler | 16 | 3 | 0 | 2 | 1 | 0 |
| pub-gx-ventilator-monitors | 3 | 3 | 0 | 1 | 2 | 0 |
| pub-gx-nonggang-patrol-2026 | 2 | 2 | 0 | 2 | 0 | 0 |
| pub-gx-ventilator-monitors | 4 | 2 | 0 | 0 | 2 | 0 |
| pub-gx-ventilator-monitors | 15 | 2 | 0 | 2 | 0 | 0 |
| pub-gx-yibiatong-phase2-2026 | 3 | 2 | 0 | 1 | 1 | 0 |
| fixture-001 | 2 | 1 | 0 | 0 | 0 | 1 |
| fixture-001 | 3 | 1 | 0 | 0 | 1 | 0 |
| fixture-003 | 1 | 1 | 0 | 0 | 1 | 0 |
| fixture-003 | 29 | 1 | 0 | 1 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia | 1 | 1 | 0 | 1 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia | 51 | 1 | 0 | 0 | 1 | 0 |
| pub-gx-hechi-mine-safety-2026 | 3 | 1 | 0 | 1 | 0 | 0 |
| pub-gx-info-center-compute-2026 | 2 | 1 | 0 | 0 | 1 | 0 |
| pub-gx-youjiang-ultrasound | 2 | 1 | 0 | 1 | 0 | 0 |
| pub-gx-youjiang-ultrasound | 4 | 1 | 0 | 1 | 0 | 0 |

These 46 rows sum to 933, with 342 long deletions, 172 short deletions, 369 substitutions, and 50 insertions. Eight pages have a bucket-3 total of 0.

## Long-deletion split (342)

Evidence note only. The scorer is unchanged. This splits only the 342 consecutive deletions of 6 or more characters, on the same alignment. The 337 text-layer-absent edits, the 50 in-text-layer insertions, the 172 short deletions, and the 369 substitutions stay where they are. `product_pass` stays false. Overall gate stays GATE_FAIL.

| Kind | Edits |
|---|---:|
| Whole text-layer line that matches no OCR line | 100 |
| Gap inside a line already paired with an OCR line | 242 |
| Remainder | 0 |
| Sum | 342 |

100 + 242 = 342. There is no remainder. Every long deletion is one of those two kinds.

Whole unmatched lines are dominated by `fixture-003` page 5 (21), `pub-gx-youjiang-ultrasound` page 5 (20), `fixture-002` page 6 (18), and `pub-gx-minzu-ultrasound-2026` page 2 (15). Gaps inside paired lines are dominated by `pub-gx-minzu-ultrasound-2026` page 1 (49), `pub-gx-youjiang-ultrasound` page 6 (35), `pub-gx-info-center-compute-2026` page 5 (32), and `fixture-002` page 6 (28). `pub-gx-minzu-ultrasound-2026` page 1 and `pub-gx-youjiang-ultrasound` page 6 are entirely gaps.

| doc | page | long | whole | gap |
|---|---:|---:|---:|---:|
| pub-gx-minzu-ultrasound-2026 | 1 | 49 | 0 | 49 |
| fixture-002 | 6 | 46 | 18 | 28 |
| pub-gx-minzu-ultrasound-2026 | 2 | 40 | 15 | 25 |
| pub-gx-info-center-compute-2026 | 5 | 39 | 7 | 32 |
| pub-gx-youjiang-ultrasound | 6 | 35 | 0 | 35 |
| pub-gx-youjiang-ultrasound | 5 | 34 | 20 | 14 |
| fixture-003 | 5 | 33 | 21 | 12 |
| pub-gx-ventilator-monitors | 5 | 25 | 7 | 18 |
| fixture-003 | 4 | 21 | 0 | 21 |
| pub-gx-daxin-ultrasound-anesthesia | 73 | 12 | 12 | 0 |
| fixture-001 | 32 | 8 | 0 | 8 |

These 11 rows sum to 342, with 100 whole unmatched lines and 242 paired-line gaps. The other 43 pages have no long deletion.

