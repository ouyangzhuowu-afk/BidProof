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
| Expanded public set (live OCR) | 4.96% | GATE_FAIL | 97.17% | GATE_PASS | 95.80% | GATE_PASS |
| Synthetic appendix (not in gate) | 3.17% | GATE_FAIL | 10.26% | GATE_FAIL | 86.63% | GATE_FAIL |

Overall expanded gate: **GATE_FAIL**. `product_pass=false`.

Expanded F1 counts: TP 103 / FP 3 / FN 3.

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

- **line_cer**: TOC pages still count. Before alignment, split 目录 headings are joined, dot leaders are removed, and a bare OCR page number is put back on the preceding title. Line CER remains above 2% on the same pages because non-leader characters still disagree.
- **key_field_f1**: Exact NFKC field match fails when RapidOCR drops or alters the authoritative span (dates, amounts, agency names).

## Improvement directions

- Keep thresholds at CER≤2%, F1≥97%, TEDS≥90%. Do not drop low-scoring public pages.
- TOC dot leaders are already segmented before line CER. Further CER gains have to come from the characters RapidOCR still misses on the same pages.
- Normalize key-field hypotheses with a constrained parser (amount, date, project code) instead of exact full-span equality, and keep the text-layer string as GT.
- Table hypotheses already use the PDF ruling-line grid. Remaining TEDS misses are OCR characters inside those cells, still scored against the text-layer HTML.
- Leave image-only pages not-scored until a human transcript exists. Do not promote OCR text to ground truth.
- Keep training-corpus PDFs and synthetic scans out of this gate so later fine-tunes cannot leak into the reported numbers.

## Reproduce

```bash
uv run --extra ocr python -m work.eval.public_expand --build
uv run python -m work.eval.public_expand --report
```

Generated at `2026-09-29T09:06:12.123118+00:00`.
