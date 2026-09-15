# Customer playbook: 医疗器械经销 → 医院招标

## Context

First design partner: medical-device company selling into hospitals. Tender packs are
mostly **hospital / 卫健委 / 集采代理** 采购文件（电子 PDF + 扫描盖章件 + 授权委托书复印件）。

## Compliance tier: **T1 (confirmed 2026-09-16)**

Redacted crops may leave the machine; **original pages never do**.

Architecture: `outputs/HYBRID_PRIVACY_OCR_PLAN.md`  
Hardware notes: `outputs/LOCAL_OCR_OPTIONS.md`

| Setting | Value |
|---|---|
| `BID_OCR_PROVIDER` | `rapid` (Windows) / `paddle` (WSL) |
| `BIDPROOF_OCR_EGRESS_MODE` | `redacted_only` |
| `BIDPROOF_OCR_EGRESS_ALLOWED` | `1` (only with key + DPA) |
| `BID_OCR_CLOUD_PROVIDER` | `qwen` |
| `BID_OCR_TILE_ENABLED` | `1` |

```powershell
uv sync --extra ocr
$env:BID_OCR_PROVIDER="rapid"
$env:BIDPROOF_OCR_EGRESS_MODE="redacted_only"
$env:BIDPROOF_OCR_EGRESS_ALLOWED="1"
$env:QWEN_OCR_API_KEY="<from secret store>"
```

### What leaves the network under T1

- Only pages that fail local quality gates (low confidence / truncation / TOC·dense table hints).
- Image is scrubbed first: header/footer bands + PII line boxes from local OCR.
- Never escalates: 公章/身份证/许可证复印件/银行回单/联系人信息页.

### Audit fields on each page JSON

`ocr_egress`, `ocr_egress_mode`, `ocr_escalation_reason`, `ocr_page_types`,
`ocr_redaction_version`, `ocr_redaction_sha256` (when scrubbed).

## Domain requirements already wired

`app/rules.py` flags 医疗器械证照 / 授权两票制 / 三甲业绩. Evidence stays **NEEDS_REVIEW**.

## First offline hospital sample

- Redacted cryostat consultation: `work/eval/meddevice-redacted/`
- Electronic DOCX → text layer only (no OCR needed).

## Rollback

```powershell
$env:BIDPROOF_OCR_EGRESS_ALLOWED="0"
$env:BIDPROOF_OCR_EGRESS_MODE="never"
```
