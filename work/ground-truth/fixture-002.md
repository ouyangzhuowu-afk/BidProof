# fixture-002 人工 Ground Truth

- 文件：`source2-shaanxi.pdf`
- 来源：陕西省省级单位政府采购中心
- 项目编号：`SNCG-FM-2024123`
- 标注状态：初版人工标注，需第二人复核

| ID | 类别 | 严重性 | PDF 页码 | 原文 quote | 无企业证据预期 | 有匹配证据预期 |
|---|---|---|---:|---|---|---|
| REQ-002-01 | QUALIFICATION | HIGH | 3 | 投标人资格要求：符合《中华人民共和国政府采购法》第二十二条的规定。 | UNKNOWN | NEEDS_REVIEW |
| REQ-002-02 | CREDENTIAL | HIGH | 3 | 提供有效存续的企业营业执照（副本）/事业单位法人证书/专业服务机构执业许可证/民办非企业单位登记证书。 | UNKNOWN | PASS（需企业证据页码） |
| REQ-002-03 | DEADLINE | HIGH | 3 | 于2024-11-11 09:30:00前递交投标文件。 | NEEDS_REVIEW | NEEDS_REVIEW |
| REQ-002-04 | QUALIFICATION | HIGH | 5 | 以上资格要求为特定资格，须提供相应证明文件；缺少其中任何一项，投标文件为无效文件。 | UNKNOWN | PASS（需企业证据页码） |
| REQ-002-05 | BOND | MEDIUM | 7 | 投标人应按规定提交投标保证金。 | UNKNOWN | NEEDS_REVIEW |

企业证据页码暂空；`PASS` 只有在上传企业证据并由人工确认双页码后才成立。
