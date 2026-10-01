# Line-edit seven-bucket classification (pending_audit)

Evidence note only. Recognition, the scoring formula, the thresholds, the ground truth, render scale, `max_side_len`, and the OCR model are unchanged. OCR was not re-run. No character was deleted. No letterhead was masked. OCR text was not copied into the ground truth. `outputs/pilot-ledger.csv` and `outputs/icp-outreach.csv` were not touched. T-005 stays blocked.

This table does not pass any gate. The underlying line CER stays **1302/29835 (4.36%) GATE_FAIL**. Key-field F1 stays **97.17%**. TEDS stays **95.80%**. Overall gate stays **GATE_FAIL**. `product_pass` stays false.

Scored pages: **54**. Denominator: **29835**. Classified edits: **1302**. Seven-bucket sum: **1302**. Remainder: **0**.

## Exclusive rule

Each of the 1302 edit characters is assigned by the first matching rule. A character that also fits a later description stays in the earlier bucket. 1) Fragment: a still-separate text-layer piece of length 1–2 that contains a CJK character and tiles an unused OCR line from left to right, plus that OCR line; or an unmatched one-character date particle (年/月/日/时/分/点) and the unused OCR line that contains it. 2) Header or letterhead: an inserted character of an OCR line that is a masthead, logo, English legal-name line, short agency fragment of that masthead, garbled logo token 帐iii, or a 第N章 running header; plus a substitution on a paired line whose whole OCR line is a masthead or logo and is not itself in the page text layer. A deletion of a body character stays a missing span even when the paired OCR line is a letterhead. 3) Not in the text layer: a remaining insertion, either a whole unused OCR line or one consecutive insertion run inside a paired line, whose text is not a substring of the normalized page text layer. 4) Whole-line miss: a remaining character of a ground-truth line the greedy matcher never paired, of any length. 5) Missing span: a remaining deletion inside a line that was paired. 6) Wrong character: a remaining substitution. 7) Extra insertion: a remaining insertion whose text is a substring of the page text layer. Short deletions are not a bucket. An unmatched short line is rule 4 unless rule 1 took it. A short gap inside a paired line is rule 5.

Earlier splits are hints, not targets. The counts below are this assignment. They are not forced back onto 337, 100, 242, 369, 50, or 32.

## Bucket totals

| # | Bucket | Characters |
|---:|---|---:|
| 1 | 1. Not in the text layer | 47 |
| 2 | 2. Header or letterhead | 286 |
| 3 | 3. Whole-line miss | 151 |
| 4 | 4. Missing span inside an already paired line | 363 |
| 5 | 5. Wrong character (substitution) | 395 |
| 6 | 6. Extra characters the recognizer inserted | 28 |
| 7 | 7. Fragment lines that never aligned | 32 |
| | Sum | 1302 |
| | Remainder against 1302 | 0 |

1302 = 47 + 286 + 151 + 363 + 395 + 28 + 32. Remainder 0. Denominator 29835 across 54 pages.

## 1. Not in the text layer

Total: **47** characters.

Pages that dominate this bucket:

| source file | page | characters in this bucket |
|---|---:|---:|
| source2-shaanxi.pdf | 6 | 24 |
| pub-gx-youjiang-ultrasound.pdf | 6 | 9 |
| source4-zbtb.pdf | 4 | 8 |
| pub-gx-nanning-vascular-doppler.pdf | 17 | 2 |
| source2-shaanxi.pdf | 3 | 2 |
| source2-nanjing.pdf | 2 | 1 |
| source4-zbtb.pdf | 29 | 1 |

## 2. Header or letterhead

Total: **286** characters.

Pages that dominate this bucket:

| source file | page | characters in this bucket |
|---|---:|---:|
| source4-zbtb.pdf | 4 | 76 |
| source4-zbtb.pdf | 5 | 76 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 1 | 51 |
| source4-zbtb.pdf | 29 | 20 |
| source4-zbtb.pdf | 9 | 16 |
| source4-zbtb.pdf | 35 | 16 |
| source2-nanjing.pdf | 2 | 7 |
| source2-nanjing.pdf | 14 | 7 |

## 3. Whole-line miss

Total: **151** characters.

Pages that dominate this bucket:

| source file | page | characters in this bucket |
|---|---:|---:|
| source4-zbtb.pdf | 5 | 22 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 21 |
| source2-shaanxi.pdf | 6 | 18 |
| pub-gx-minzu-ultrasound-2026.pdf | 2 | 15 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 73 | 13 |
| pub-gx-info-center-compute-2026.pdf | 5 | 8 |
| pub-gx-minzu-ultrasound-2026.pdf | 1 | 7 |
| pub-gx-nanning-vascular-doppler.pdf | 17 | 7 |

## 4. Missing span inside an already paired line

Total: **363** characters.

Pages that dominate this bucket:

| source file | page | characters in this bucket |
|---|---:|---:|
| pub-gx-minzu-ultrasound-2026.pdf | 1 | 54 |
| pub-gx-youjiang-ultrasound.pdf | 6 | 44 |
| source2-shaanxi.pdf | 6 | 41 |
| source4-zbtb.pdf | 5 | 41 |
| pub-gx-info-center-compute-2026.pdf | 5 | 34 |
| pub-gx-minzu-ultrasound-2026.pdf | 2 | 30 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 25 |
| pub-gx-ventilator-monitors.pdf | 5 | 23 |

## 5. Wrong character (substitution)

Total: **395** characters.

Pages that dominate this bucket:

| source file | page | characters in this bucket |
|---|---:|---:|
| source4-zbtb.pdf | 5 | 105 |
| source2-shaanxi.pdf | 6 | 48 |
| pub-gx-minzu-ultrasound-2026.pdf | 2 | 47 |
| pub-gx-info-center-compute-2026.pdf | 5 | 43 |
| pub-gx-youjiang-ultrasound.pdf | 6 | 37 |
| source4-zbtb.pdf | 4 | 33 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 21 |
| pub-gx-minzu-ultrasound-2026.pdf | 1 | 16 |

## 6. Extra characters the recognizer inserted

Total: **28** characters.

Pages that dominate this bucket:

| source file | page | characters in this bucket |
|---|---:|---:|
| pub-gx-nanning-vascular-doppler.pdf | 17 | 6 |
| source4-zbtb.pdf | 5 | 5 |
| pub-gx-youjiang-ultrasound.pdf | 6 | 4 |
| source2-shaanxi.pdf | 6 | 4 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 3 |
| pub-gx-info-center-compute-2026.pdf | 5 | 2 |
| pub-gx-nanning-vascular-doppler.pdf | 3 | 2 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 2 |

## 7. Fragment lines that never aligned

Total: **32** characters.

Pages that dominate this bucket:

| source file | page | characters in this bucket |
|---|---:|---:|
| pub-gx-minzu-ultrasound-2026.pdf | 6 | 20 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 8 |
| source2-nanjing.pdf | 32 | 4 |

## Page breakdown

Every scored page with at least one edit. The seven columns sum to the page edit count, and the page edit counts sum to 1302.

| source file | page | edits | not in text | header | whole line | paired gap | substitution | extra | fragment |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source4-zbtb.pdf | 5 | 249 | 0 | 76 | 22 | 41 | 105 | 5 | 0 |
| source4-zbtb.pdf | 4 | 139 | 8 | 76 | 0 | 22 | 33 | 0 | 0 |
| source2-shaanxi.pdf | 6 | 135 | 24 | 0 | 18 | 41 | 48 | 4 | 0 |
| pub-gx-youjiang-ultrasound.pdf | 6 | 94 | 9 | 0 | 0 | 44 | 37 | 4 | 0 |
| pub-gx-minzu-ultrasound-2026.pdf | 2 | 92 | 0 | 0 | 15 | 30 | 47 | 0 | 0 |
| pub-gx-info-center-compute-2026.pdf | 5 | 87 | 0 | 0 | 8 | 34 | 43 | 2 | 0 |
| pub-gx-minzu-ultrasound-2026.pdf | 1 | 77 | 0 | 0 | 7 | 54 | 16 | 0 | 0 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 69 | 0 | 0 | 21 | 25 | 21 | 2 | 0 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 1 | 51 | 0 | 51 | 0 | 0 | 0 | 0 | 0 |
| pub-gx-ventilator-monitors.pdf | 5 | 42 | 0 | 0 | 7 | 23 | 12 | 0 | 0 |
| pub-gx-minzu-ultrasound-2026.pdf | 6 | 24 | 0 | 0 | 0 | 1 | 3 | 0 | 20 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 23 | 0 | 0 | 7 | 2 | 3 | 3 | 8 |
| source4-zbtb.pdf | 9 | 23 | 0 | 16 | 1 | 4 | 2 | 0 | 0 |
| source4-zbtb.pdf | 29 | 22 | 1 | 20 | 1 | 0 | 0 | 0 | 0 |
| source2-nanjing.pdf | 32 | 17 | 0 | 0 | 1 | 12 | 0 | 0 | 4 |
| pub-gx-nanning-vascular-doppler.pdf | 17 | 16 | 2 | 0 | 7 | 1 | 0 | 6 | 0 |
| source4-zbtb.pdf | 35 | 16 | 0 | 16 | 0 | 0 | 0 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 73 | 13 | 0 | 0 | 13 | 0 | 0 | 0 | 0 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 2 | 12 | 0 | 4 | 2 | 6 | 0 | 0 | 0 |
| pub-gx-yibiatong-phase2-2026.pdf | 2 | 8 | 0 | 4 | 3 | 1 | 0 | 0 | 0 |
| source2-nanjing.pdf | 2 | 8 | 1 | 7 | 0 | 0 | 0 | 0 | 0 |
| source2-nanjing.pdf | 14 | 7 | 0 | 7 | 0 | 0 | 0 | 0 | 0 |
| pub-gx-hechi-mine-safety-2026.pdf | 1 | 6 | 0 | 5 | 1 | 0 | 0 | 0 | 0 |
| pub-gx-nanxishan-dr-mammo-2026.pdf | 2 | 6 | 0 | 0 | 0 | 4 | 2 | 0 | 0 |
| pub-gx-qintang-flow-cytometer.pdf | 3 | 6 | 0 | 0 | 0 | 2 | 4 | 0 | 0 |
| source2-shaanxi.pdf | 3 | 6 | 2 | 0 | 2 | 0 | 2 | 0 | 0 |
| source2-shaanxi.pdf | 37 | 6 | 0 | 0 | 1 | 5 | 0 | 0 | 0 |
| pub-gx-hechi-mine-safety-2026.pdf | 2 | 4 | 0 | 0 | 1 | 3 | 0 | 0 | 0 |
| pub-gx-nanning-vascular-doppler.pdf | 3 | 4 | 0 | 0 | 1 | 1 | 0 | 2 | 0 |
| pub-gx-nanxishan-dr-mammo-2026.pdf | 9 | 4 | 0 | 0 | 2 | 2 | 0 | 0 | 0 |
| pub-gx-nonggang-patrol-2026.pdf | 9 | 4 | 0 | 0 | 1 | 0 | 3 | 0 | 0 |
| pub-gx-qintang-flow-cytometer.pdf | 1 | 4 | 0 | 4 | 0 | 0 | 0 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 3 | 3 | 0 | 0 | 2 | 0 | 1 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 4 | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| pub-gx-nanning-vascular-doppler.pdf | 16 | 3 | 0 | 0 | 0 | 2 | 1 | 0 | 0 |
| pub-gx-ventilator-monitors.pdf | 3 | 3 | 0 | 0 | 1 | 0 | 2 | 0 | 0 |
| pub-gx-nonggang-patrol-2026.pdf | 2 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| pub-gx-ventilator-monitors.pdf | 4 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 0 |
| pub-gx-ventilator-monitors.pdf | 15 | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| pub-gx-yibiatong-phase2-2026.pdf | 3 | 2 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 51 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| pub-gx-hechi-mine-safety-2026.pdf | 3 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| pub-gx-info-center-compute-2026.pdf | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| pub-gx-youjiang-ultrasound.pdf | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| pub-gx-youjiang-ultrasound.pdf | 4 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| source2-nanjing.pdf | 3 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| source4-zbtb.pdf | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |

## Boundary examples

On `source4-zbtb.pdf` page 4 the greedy matcher paired a body line with `北京数字支点国际项目管理有限公司`, which is not in that page's text layer. The 15 substitution edits on that pair are bucket 2. The deleted body characters on that same pair stay in bucket 4, because those characters are the body line, not the letterhead.

`pub-gx-tianlin-yuegui-devices-2026.pdf` page 1 puts both the Chinese masthead `广西恒桥项目管理有限公司` (also present in the body, so this is a repeated header) and the English legal-name line into bucket 2. They are not left in bucket 1 or bucket 6.

Running headers `第一章响应邀请` and `第四章采购需求` on `source2-nanjing.pdf` are bucket 2. The garbled logo token `帐iii` on the two 目录 pages is bucket 2. Garbage that is not a header stays in bucket 1, including the 24-character line on `source2-shaanxi.pdf` page 6 and `中,中,中,()` on `source4-zbtb.pdf` page 4.

Bucket 7 is three pages only: `pub-gx-minzu-ultrasound-2026.pdf` page 6 (20), `pub-gx-tianlin-yuegui-devices-2026.pdf` page 8 (8), and `source2-nanjing.pdf` page 32 (4).

The counts differ from the earlier hints where the definitions differ. Bucket 1 is 47 rather than about 337 because letterheads that used to sit inside the absent pile are bucket 2. Bucket 3 is 151 rather than about 100 because every unmatched ground-truth line is included, not only deletions of 6 or more characters. Bucket 4 is 363 rather than about 242 because short gaps inside paired lines are included. Bucket 5 is 395 rather than about 369. Bucket 6 is 28 rather than about 50 because repeated headers that are in the text layer were pulled into bucket 2. Bucket 7 is 32. None of these labels changes the 1302.

## What went into header / letterhead and fragments

Shown so the exclusive cut can be checked. A preview is the OCR or ground-truth span, truncated at 80 characters. Paired letterhead substitutions on one page are one row.

| bucket | source file | page | chars | kind | preview |
|---|---|---:|---:|---|---|
| header_letterhead | source2-nanjing.pdf | 2 | 7 | unused_header_line | 第一章响应邀请 |
| header_letterhead | source2-nanjing.pdf | 14 | 7 | unused_header_line | 第四章采购需求 |
| fragment | source2-nanjing.pdf | 32 | 1 | unmatched_gt_piece | 日 |
| fragment | source2-nanjing.pdf | 32 | 3 | unused_fragment_line | 日期: |
| header_letterhead | source4-zbtb.pdf | 4 | 15 | paired_letterhead_substitution | 15 substitutions; first 业/北 |
| header_letterhead | source4-zbtb.pdf | 4 | 4 | unused_header_line | cpil |
| header_letterhead | source4-zbtb.pdf | 4 | 57 | unused_header_line | beijingdigitalpivotinternationalprojectmanagementco.,ltod |
| header_letterhead | source4-zbtb.pdf | 5 | 4 | unused_header_line | cpil |
| header_letterhead | source4-zbtb.pdf | 5 | 16 | unused_header_line | 北京数字支点国际项目管理有限公司 |
| header_letterhead | source4-zbtb.pdf | 5 | 56 | unused_header_line | beijingdigitalpivotinternationalprojectmanagementco.,lto |
| header_letterhead | source4-zbtb.pdf | 9 | 16 | unused_header_line | 北京数字支点国际项目管理有限公司 |
| header_letterhead | source4-zbtb.pdf | 29 | 4 | unused_header_line | cpil |
| header_letterhead | source4-zbtb.pdf | 29 | 16 | unused_header_line | 北京数字支点国际项目管理有限公司 |
| header_letterhead | source4-zbtb.pdf | 35 | 16 | unused_header_line | 北京数字支点国际项目管理有限公司 |
| header_letterhead | pub-gx-qintang-flow-cytometer.pdf | 1 | 4 | unused_header_line | 广西鑫远 |
| header_letterhead | pub-gx-tianlin-yuegui-devices-2026.pdf | 1 | 12 | unused_header_line | 广西恒桥项目管理有限公司 |
| header_letterhead | pub-gx-tianlin-yuegui-devices-2026.pdf | 1 | 39 | unused_header_line | guangxihengqiaoprojectmanagementco.,ltd |
| header_letterhead | pub-gx-tianlin-yuegui-devices-2026.pdf | 2 | 4 | unused_header_line | 帐iii |
| fragment | pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 2 | unmatched_gt_piece | 数量 |
| fragment | pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 2 | unmatched_gt_piece | 单位 |
| fragment | pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 4 | unused_fragment_line | 数量单位 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 1 | unmatched_gt_piece | 项 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 1 | unmatched_gt_piece | 号 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 2 | unmatched_gt_piece | 货物 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 2 | unmatched_gt_piece | 名称 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 1 | unmatched_gt_piece | 数 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 1 | unmatched_gt_piece | 量 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 1 | unmatched_gt_piece | 单 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 1 | unmatched_gt_piece | 位 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 5 | unused_fragment_line | 项货物数单 |
| fragment | pub-gx-minzu-ultrasound-2026.pdf | 6 | 5 | unused_fragment_line | 号名称量位 |
| header_letterhead | pub-gx-hechi-mine-safety-2026.pdf | 1 | 1 | unused_header_line | k |
| header_letterhead | pub-gx-hechi-mine-safety-2026.pdf | 1 | 4 | unused_header_line | 科文招标 |
| header_letterhead | pub-gx-yibiatong-phase2-2026.pdf | 2 | 4 | unused_header_line | 帐iii |

## Reproduce

```bash
uv run python -m work.eval.line_edit_buckets
```

The command rewrites only `outputs/ocr-benchmark/line-edit-seven-buckets.md` and `.json`. It does not write a pilot or ICP ledger and it does not call OCR.

Generated at `2026-10-01T16:15:29.439250+00:00`. Status: `pending_audit`.
