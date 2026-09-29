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
| Expanded public set (live OCR) | 15.19% | GATE_FAIL | 97.17% | GATE_PASS | 44.03% | GATE_FAIL |
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

## Failure causes

- **line_cer**: Most pages are near the 2% line-CER band, but table-of-contents pages blow up the micro-average. The text layer splits 目录 and keeps dot leaders; RapidOCR drops the dots and merges the title with the page number, so greedy line alignment charges almost the whole leader string as an edit.
- **key_field_f1**: Exact NFKC field match fails when RapidOCR drops or alters the authoritative span (dates, amounts, agency names).
- **teds**: Box clustering inside the text-layer table region splits multi-line cells and does not recover merged headers, so tree edit distance stays high.

## Improvement directions

- Keep thresholds at CER≤2%, F1≥97%, TEDS≥90%. Do not drop low-scoring public pages.
- Segment headers, footers, and dot-leader tables of contents before line CER so reading-order noise is not scored as character error.
- Normalize key-field hypotheses with a constrained parser (amount, date, project code) instead of exact full-span equality, and keep the text-layer string as GT.
- Replace y/x box clustering with a table-structure model or ruling-line grid, scored against the same single-page text-layer HTML.
- Leave image-only pages not-scored until a human transcript exists. Do not promote OCR text to ground truth.
- Keep training-corpus PDFs and synthetic scans out of this gate so later fine-tunes cannot leak into the reported numbers.

## Reproduce

```bash
uv run --extra ocr python -m work.eval.public_expand --build
uv run python -m work.eval.public_expand --report
```

Generated at `2026-09-29T07:17:02.965131+00:00`.
