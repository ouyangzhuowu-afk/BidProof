# Redacted hospital cryostat consultation — offline process

- Generated: `2026-09-15T21:32:54.021821+08:00`
- Egress / OCR: **disabled** (customer: no outbound)
- Redacted DOCX: `work/eval/meddevice-redacted/consult-cryostat-redacted.docx`
- Units / chars: 990 / 30629
- Requirements extracted: **105**
- Residual PII scan: `clean`

## Categories

| Category | Count |
|---|---:|
| CREDENTIAL | 15 |
| DEADLINE | 3 |
| FATAL | 5 |
| QUALIFICATION | 35 |
| SCORING | 10 |
| SIGNATURE | 37 |

## Labels

| Label | Count |
|---|---:|
| 关键日期 | 3 |
| 医疗器械资质 | 7 |
| 医院业绩/售后 | 8 |
| 废标/否决 | 5 |
| 授权配送 | 6 |
| 签章要求 | 37 |
| 评分项 | 10 |
| 资格条件 | 29 |

## Key field checks

```json
{
  "device_license_clause": true,
  "budget_present": true,
  "deadline_present": true,
  "no_bond": true
}
```

## Sample requirements (redacted quotes only)

- `REQ-0001` [QUALIFICATION/资格条件] unit=25: [医院A]病理科冷冻切片机采购项目,委托代理编号:REDACTED-CG-0001,进行竞争性磋商采购,现采用发布公告方式,邀请符合资格条件的供应商参与竞争性磋商采购活动。
- `REQ-0002` [QUALIFICATION/资格条件] unit=45: 二、供应商资格条件:
- `REQ-0003` [QUALIFICATION/资格条件] unit=46: 1、供应商的基本资格条件:应当符合《政府采购法》第二十二条第一款的规定,即:
- `REQ-0004` [QUALIFICATION/资格条件] unit=53: 2、供应商特定资格条件:
- `REQ-0005` [CREDENTIAL/医疗器械资质] unit=54: (1)所投货物纳入医疗器械管理的,须具有相应的医疗器械经营许可证(或备案凭证)、或有效的医疗器械生产许可证(或备案凭证)、且证件在有效期内。
- `REQ-0007` [CREDENTIAL/医疗器械资质] unit=55: (2)所投货物纳入医疗器械管理的,货物须具有有效的医疗器械注册证(或备案凭证)且在证件有效期内生产。
- `REQ-0008` [QUALIFICATION/资格条件] unit=106: 供应商资格条件
- `REQ-0009` [QUALIFICATION/资格条件] unit=107: 1、供应商基本资格条件: 供应商必须是在中华人民共和国境内注册登记的法人、其他组织或者自然人,且应当符合 《政府采购法》第二十二条第一款的规定,即: (1)具有独立承担民事责任的能力; (2)具有良好的商业信誉和健全的财务会计制度; (3)具
- `REQ-0010` [QUALIFICATION/资格条件] unit=107: 务会计制度; (3)具有履行合同所必需的设备和专业技术能力; (4)有依法缴纳税收和社会保障资金的良好记录; (5)参加政府采购活动前三年内,在经营活动中没有重大违法记录; (6)法律、行政法规规定的其他条件。 2、特定资格条件: (1) 所投货物纳入医疗器械管理的,须具有相应的医疗器械经营许可证(或备案凭证)、或有效的医疗器械生产许可证(或备案凭证)、且证
- `REQ-0011` [CREDENTIAL/医疗器械资质] unit=107: (4)有依法缴纳税收和社会保障资金的良好记录; (5)参加政府采购活动前三年内,在经营活动中没有重大违法记录; (6)法律、行政法规规定的其他条件。 2、特定资格条件: (1) 所投货物纳入医疗器械管理的,须具有相应的医疗器械经营许可证(或备案凭证)、或有效的医疗器械生产许可证(或备案凭证)、且证件在有效期内 。 所投货物纳入医疗器械管理的,货物须具有有效的
- `REQ-0012` [CREDENTIAL/医疗器械资质] unit=107: 记录; (5)参加政府采购活动前三年内,在经营活动中没有重大违法记录; (6)法律、行政法规规定的其他条件。 2、特定资格条件: (1) 所投货物纳入医疗器械管理的,须具有相应的医疗器械经营许可证(或备案凭证)、或有效的医疗器械生产许可证(或备案凭证)、且证件在有效期内 。 所投货物纳入医疗器械管理的,货物须具有有效的医疗器械注册证(或备案凭证)且在证件有效
- `REQ-0013` [CREDENTIAL/医疗器械资质] unit=107: 他条件。 2、特定资格条件: (1) 所投货物纳入医疗器械管理的,须具有相应的医疗器械经营许可证(或备案凭证)、或有效的医疗器械生产许可证(或备案凭证)、且证件在有效期内 。 所投货物纳入医疗器械管理的,货物须具有有效的医疗器械注册证(或备案凭证)且在证件有效期内生产 。 3、单位负责人为同一人或者存在直接控股、管理关系的不同供应商,不得参加同一合同项下的采

## Redaction map (placeholders)

| Original class | Placeholder |
|---|---|
| Hospital name | `[医院A]` |
| Agency | `[代理机构A]` |
| Contacts | `[联系人甲/乙]` |
| Phones / addresses | `0000-…` / `[采购人地址A]` / `[代理地址A]` |
| Agency project id | `REDACTED-CG-0001` |

Raw WeChat temp file and `work/uploads/_incoming-private/raw-*` must not be committed.
