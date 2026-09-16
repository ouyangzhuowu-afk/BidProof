# S-A-05 TEDS table-structure GT seed report

Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**,
and **does not evaluate TEDS**. Missing GT is `INSUFFICIENT`, not a high score.
The TEDS ≥ 90% product gate remains **NOT_EVALUATED**.

- Generated_at: `2026-09-16T15:35:53Z`
- Coverage status: **SUFFICIENT_SEED**
- `product_pass`: `false`
- `business_pass`: `false`
- `teds_status`: `NOT_EVALUATED` (gate TEDS≥90% remains unevaluated)
- `teds_gt_pages`: **16** (was 0 before this leaf)

## Counts

| Metric | Count | Minimum |
|---|---:|---:|
| TEDS GT pages (`table_html` with `<table>`) | 16 | 15 |
| public documents with table GT | 6 | 3 |
| synthetic documents | 4 | — |

## Limitations

- Public rows must match `work/public-eval/manifest.json` `source_url` + `sha256`.
- Synthetic rows are labeled `origin=synthetic` and `doc_id` prefix `synthetic-`.
- Week-1 labels are **single-page complete tables only**; cross-page tables are out of scope.
- S-A-06 TEDS similarity / ≥90% gate is **not** computed here.
- Seal / handwriting GT (S-A-07) and key-field F1 (S-A-03) are out of scope.
- No PII or enterprise pilot rows. T-005 ledgers were not written.

Insufficient reasons:

- `none`

## Documents

| doc_id | origin | pages | titles | sha256 |
|---|---|---:|---|---|
| `fixture-001` | public | 2 | 采购清单; 开标报价表 | `b90b22d14736…` |
| `fixture-002` | public | 2 | 符合性审查表; 货物清单 | `a6c1f042b077…` |
| `fixture-003` | public | 2 | 资格审查与符合性审查; 投标报价表 | `e233f7b45ec3…` |
| `pub-gx-nanning-vascular-doppler` | public | 3 | 分标最高限价一览表; 母婴中央监护系统配置清单; 胎儿监护仪配置清单 | `59e5b5814d4b…` |
| `pub-gx-ventilator-monitors` | public | 1 | 遥测与患者监护仪配置清单 | `c52e7d6e84dd…` |
| `pub-gx-daxin-ultrasound-anesthesia` | public | 2 | 代理服务费费率表; 分项报价表 | `ee2a69cba1ae…` |
| `synthetic-teds-bid-opening` | synthetic | 1 | 开标一览表 | — |
| `synthetic-teds-quote-detail` | synthetic | 1 | 报价明细表 | — |
| `synthetic-teds-score` | synthetic | 1 | 综合评分标准表 | — |
| `synthetic-teds-deviation` | synthetic | 1 | 技术偏离表 | — |

## Reproduce

```bash
uv run python -m work.eval.teds_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/teds_gt.jsonl
uv run --group dev pytest -q tests/test_teds_gt.py tests/test_page_annotation.py
```

Exit `0` = schema valid and seed minima met (`SUFFICIENT_SEED`).  
Exit `2` = schema valid but coverage `INSUFFICIENT`.  
Exit `1` = validation / IO error.

`SUFFICIENT_SEED` is not TEDS ≥ 90% and is not a product/business PASS.
