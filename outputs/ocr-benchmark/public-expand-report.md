# S-A-OCR-PUBLIC-EXPAND OCR gate report

Engineering measurement only. This is not a product PASS, not T-005, and not business acceptance.
Synthetic rows are in the appendix and are not in the expanded gate. Thresholds were not changed.

## Counts

- Prior completed public-eval documents: **12**
- New completed documents (this leaf): **7**
- New not-scored documents: **2**
- Expanded scored pages: CER **54**, TEDS **19**, key-field rows **34**

## Gates

| Set | CER | CER gate | F1 | F1 gate | TEDS | TEDS gate |
|---|---:|---|---:|---|---:|---|
| Old published set | 3.17% | GATE_FAIL | 76.00% | GATE_FAIL | 87.85% | GATE_FAIL |
| Expanded public set (live OCR) | 4.36% | GATE_FAIL | 97.17% | GATE_PASS | 95.80% | GATE_PASS |
| Synthetic appendix (not in gate) | 3.17% | GATE_FAIL | 10.26% | GATE_FAIL | 86.63% | GATE_FAIL |

Overall expanded gate: **GATE_FAIL**. `product_pass=false`.

Expanded F1 counts: TP 103 / FP 3 / FN 3.

Expanded line edits: **1302** / **29835** on **54** pages. Baseline before fragment alignment, same pages: **1481/29835** (CER 4.96%). Unconstrained adjacent joins (remeasured 485 edits; prior hypothesis 483) are not applied. Rejected false candidates: fixture-003 page 5, two paragraphs; pub-gx-youjiang-ultrasound page 5, 开标时间 with 开标地点 and the acquisition-time wrap.

## Sources

| document | URL | fetched | license | scored |
|---|---|---|---|---|
| pub-gx-tianlin-yuegui-devices-2026 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/451002/10007840528/20269/f8eed91a-ced0-4f90-b3e5-3f52cb0310e8.pdf | 2026-09-29T07:03:43Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | yes |
| pub-gx-nanxishan-dr-mammo-2026 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/undefined/451023/10007869185/20266/63b1529b-f21d-4882-9b25-8e28cd0ea795.pdf | 2026-09-29T07:03:43Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | yes |
| pub-gx-minzu-ultrasound-2026 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/450105/10007739021/20268/73fe9f93-b477-45e4-aca4-82575e2fddb3.pdf | 2026-09-29T07:03:43Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | yes |
| pub-gx-hechi-mine-safety-2026 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/459900/10007955488/20268/f3024e4f-b0c8-4028-a41c-a104f84170ac.pdf | 2026-09-29T07:03:43Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | yes |
| pub-gx-info-center-compute-2026 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1014AN/450105/10007739021/20264/0c3ffbda-fcea-4b8c-9c68-79ffa275b205.pdf | 2026-09-29T07:03:43Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | yes |
| pub-gx-yibiatong-phase2-2026 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1023FP/450602/10007282833/20264/86bddd9d-c42f-4aff-bb47-0f411e1f0875.pdf | 2026-09-29T07:03:43Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | yes |
| pub-gx-nonggang-patrol-2026 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/undefined/451402/10011601115/20266/87f8411e-98ac-4d46-b6f1-5a029b9a9ace.pdf | 2026-09-29T07:03:43Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | yes |
| pub-gx-ventilator-monitors | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/undefined/450103/10007341141/20266/264475cd-19b9-493f-b4e3-142276a4f506.pdf | 2026-09-16T11:47:36Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | no: embedded text layer too short; OCR was not used as ground truth |
| pub-ccgp-zycg-ac-award-202609 | http://www.ccgp.gov.cn/cggg/zygg/zbgg/202609/t20260914_27319969.htm | 2026-09-29T07:16:40Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | no: Published HTML is authoritative, but the notice has no official PDF page image. A synthetic render was not created and is excluded from CER/F1/TEDS. |
| pub-gxggzy-femtosecond-2026 | http://gxggzy.gxzf.gov.cn/yxcgptrk/yxcgpt_tzgg_234096/tzgg_hc/t28134257.shtml | 2026-09-29T07:16:40Z | 公开政府采购/公共资源交易平台公开发布的招标采购文件，仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。 | no: Published HTML is authoritative, but the notice has no official PDF page image. A synthetic render was not created and is excluded from CER/F1/TEDS. |

## Joe local PDF intake (2026-09-29)

Twelve PDFs from Joe's local `work/public-eval/pdfs`, approved by Edith for eval use. Same filename or same SHA-256 as a completed manifest row is a duplicate and is not counted again. Provenance below is copied from that existing row.

- Duplicate: **12** · newly added (scored): **0** · newly added (not-scored): **0** · provenance-unverified: **0**

| submitted file | class | existing document | fetched | existing CER pages | source URL |
|---|---|---|---|---:|---|
| pub-gx-daxin-ultrasound-anesthesia.pdf | duplicate | pub-gx-daxin-ultrasound-anesthesia | 2026-09-16T11:47:36Z | 1, 3, 4, 51, 73 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-gov-open-doc/1023FP/450103/10007339275/20261/be962ee4-51f0-46f2-a542-3bf7fe68bd71.pdf |
| pub-gx-guiping-hospital-it.pdf | duplicate | pub-gx-guiping-hospital-it | 2026-09-16T11:47:36Z | 0 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1014AN/450103/10007300794/20268/ba5ac90a-96fe-4f8f-bd50-361317e042e4.pdf |
| pub-gx-luocheng-smart-hospital.pdf | duplicate | pub-gx-luocheng-smart-hospital | 2026-09-16T11:47:36Z | 0 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/450502/10009782286/20267/cfbe15f8-d793-487c-9c11-f255d321062d.pdf |
| pub-gx-nanning-vascular-doppler.pdf | duplicate | pub-gx-nanning-vascular-doppler | 2026-09-16T11:43:11Z | 3, 16, 17 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-gov-open-doc/1024FPA/450103/10007339269/20262/e485f8f3-9a31-4bc8-9a18-404b826dcb1a.pdf |
| pub-gx-niv-sleep-monitor.pdf | duplicate | pub-gx-niv-sleep-monitor | 2026-09-16T11:47:36Z | 0 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/450103/10007339432/20268/d1063021-8810-48f4-9b0b-58a7e3f1a227.pdf |
| pub-gx-qintang-flow-cytometer.pdf | duplicate | pub-gx-qintang-flow-cytometer | 2026-09-16T11:47:36Z | 1, 3, 4 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/undefined/450899/10009653243/20266/b75de483-40d0-4916-93de-a1dbbc97d84a.pdf |
| pub-gx-ventilator-monitors.pdf | duplicate | pub-gx-ventilator-monitors | 2026-09-16T11:47:36Z | 3, 4, 5, 15 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/undefined/450103/10007341141/20266/264475cd-19b9-493f-b4e3-142276a4f506.pdf |
| pub-gx-youjiang-ultrasound.pdf | duplicate | pub-gx-youjiang-ultrasound | 2026-09-16T11:43:11Z | 2, 4, 5, 6 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/undefined/450103/10007339425/20266/572479dc-2493-43cc-8e66-5186ff6dab02.pdf |
| pub-gx-yulin-dermatology-his.pdf | duplicate | pub-gx-yulin-dermatology-his | 2026-09-16T11:47:36Z | 0 | https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-gov-open-doc/1023FP/450999/10008210707/20263/434f78b2-57f6-44a1-8840-28a423677952.pdf |
| source2-nanjing.pdf | duplicate | fixture-001 | 2026-08-24 | 2, 3, 14, 32 | https://njggzy.nanjing.gov.cn/njweb/tz/20240730/676b45b5-113e-4aff-b074-1e6fd738090e.html |
| source2-shaanxi.pdf | duplicate | fixture-002 | 2026-08-24 | 1, 3, 6, 33, 37 | https://www.ccgp-shaanxi.gov.cn/gpx-bid-file/ZF_JGBM_000003/610001/2024/10/21/8a69c58e90e72f300192ac9d3d5b467b/gpx-template/8a69c2509211dc7a0192adb56a814416.pdf?accessCode=9b3feae299491ee3179981e5e497afd4 |
| source4-zbtb.pdf | duplicate | fixture-003 | 2026-08-24 | 1, 4, 5, 9, 29, 35 | https://weekly.zbtb.org.cn/2024/1b3441f1ffc3d22.pdf |

## Failure causes

- **line_cer**: TOC pages still count. Before alignment, split 目录 headings are joined, dot leaders are removed, and a bare OCR page number is put back on the preceding title. Short text-layer fragments (月/日/点/分, a 第N章 marker plus its title, or a vertical one-glyph run) are concatenated only when that concatenation equals one OCR line. Two long lines are not joined. Stored ground truth is not rewritten. Line CER remains above 2% on the same pages because non-fragment characters still disagree.
- **key_field_f1**: Exact NFKC field match fails when RapidOCR drops or alters the authoritative span (dates, amounts, agency names).

## Improvement directions

- Keep thresholds at CER≤2%, F1≥97%, TEDS≥90%. Do not drop low-scoring public pages.
- TOC dot leaders are already segmented, and text-layer fragments that equal one OCR line are already joined. Further CER gains have to come from characters RapidOCR still misses or inserts on the same pages. Do not join two long lines to move the number.
- Normalize key-field hypotheses with a constrained parser (amount, date, project code) instead of exact full-span equality, and keep the text-layer string as GT.
- Table hypotheses already use the PDF ruling-line grid. Remaining TEDS misses are OCR characters inside those cells, still scored against the text-layer HTML.
- Leave image-only pages not-scored until a human transcript exists. Do not promote OCR text to ground truth.
- Keep training-corpus PDFs and synthetic scans out of this gate so later fine-tunes cannot leak into the reported numbers.

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

## Reproduce

```bash
uv run --extra ocr python -m work.eval.public_expand --build
uv run python -m work.eval.public_expand --report
```

Generated at `2026-10-01T12:21:36.109905+00:00`.
