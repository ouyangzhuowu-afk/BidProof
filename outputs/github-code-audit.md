# GitHub 代码借鉴审查

审查日期：2026-08-21  
目标项目：Project-025 投标证据链 Agent  
审查原则：第三方仓库只作为待核验代码与设计参考；没有许可证或许可证与仓库声明不一致的代码不复制进本项目。

## 结论

`kuaizengji/kuaizengji` 有可借鉴的 OCR 结果契约、结果标准化、页级任务状态和测试组织方式，但它是学习资料/PDF/OCR 助手，不是投标合规系统；仓库根目录未发现许可证。因此不整体引入，也不直接复制实现。

本轮抽查的投标/RFP 仓库中，没有一个达到直接替换 Project-025 的门槛。当前工程继续保留 FastAPI + SQLite + PyMuPDF 的小型架构，按下面的“借鉴项”逐步增强。

## 仓库评估

| 仓库 | HEAD（审查时） | 许可证 | 可借鉴点 | 不能直接采用的原因 | 决定 |
|---|---|---|---|---|---|
| [kuaizengji/kuaizengji](https://github.com/kuaizengji/kuaizengji) | `14c951b` | 根目录无许可证 | `ocr/schema.ts` 的字段边界校验；`ocr/normalize.ts` 的规则兜底；Provider/JSON/Schema 分层；页级解析任务状态 | 领域不匹配；授权不清晰；OCR 提示词和字段是教育资料场景 | 只借鉴模式 |
| [guangshu100/BidMaster-Pro](https://github.com/guangshu100/BidMaster-Pro) | `a09716f` | 仓库 `LICENSE` 为 AGPL-3.0；README 徽章写 MIT，存在冲突 | 多阶段 Agent/Skill 编排；投标检查项目录；任务门禁思路 | 无测试文件；范围远超本项目；许可证冲突使复制和闭源商业化风险高 | 不引入代码 |
| [AmalVictor/tender-compliance-validator](https://github.com/AmalVictor/tender-compliance-validator) | `76ed111` | 未发现许可证 | PyMuPDF block/layout；OCR fallback；页码和 bbox；要求人工确认后再审计；混合检索与证据引用模型 | 授权不清晰；`document_parser.py` 含硬编码本机 Tesseract 路径；依赖和运行环境重；README 能力未由当前环境测试证明 | 只借鉴设计，重新实现 |
| [RichieGarafola/proposal-compliance-matrix](https://github.com/RichieGarafola/proposal-compliance-matrix) | `0f7e329` | MIT | 独立的 matcher → matrix_builder → data_loader；阈值外置；CSV 导出；pytest/CI | 输入是人工整理的 RFP/提案摘要；TF-IDF 相似度不是页级证据；没有 PDF/OCR/人工审计链 | 可参考小模块，不作为核心 |
| [agentbee0/RFP2Proposal](https://github.com/agentbee0/RFP2Proposal) | `6bc030a` | MIT | `compliance-mapping`、placeholder 分级、traceability matrix 的产品交互概念 | Claude 插件，重点是标书生成；依赖外部 MCP；不提供本项目所需的确定性资格/废标规则 | 只参考交互边界 |
| [wayanvota/proposal-compliance-checker](https://github.com/wayanvota/proposal-compliance-checker) | `c26f1de` | 未发现许可证 | 明确限制为完整性/合规性，不评价说服力；`NEEDS_HUMAN_REVIEW` 状态 | 无许可证；偏基金申请；需要 OpenAI API；无页级确定性证据实现 | 不引入代码 |
| [Shiwei1981/Compliance-Proposal-Agent-v2](https://github.com/Shiwei1981/Compliance-Proposal-Agent-v2) | `fdee52e` | 未发现许可证 | Agent 编排和 MCP/RAG 目录结构可作架构参考 | 数据样例和环境耦合明显；领域偏 Azure/法规问答；无可验证 CI | 不引入代码 |

## 具体借鉴清单

### 1. OCR/解析契约

从 `kuaizengji` 和 `tender-compliance-validator` 借鉴以下接口形状，但使用本项目自己的实现：

- 每页保存 `page`、`text`、`char_count`、`has_text`、`ocr_required`、`low_text_confidence`；短文本页保留文本层，不直接误判为扫描页。
- 解析结果先做 Schema 校验，再做规范化；正文和图片说明等不同来源字段不能混为一个结论。
- 每个要求项和证据项保存原文摘录、页码以及可选 bbox；引用缺失时状态只能是 `UNKNOWN`/`NEEDS_REVIEW`。
- OCR 是可替换 adapter，不能在业务路由中硬编码本机可执行文件路径。

### 2. 证据链与人工门禁

从 `tender-compliance-validator` 借鉴“候选抽取 → 人工确认 → 审计”的顺序，但收窄为 Project-025 的确定性规则：

1. 解析候选要求项。
2. 保存来源页码和原文 quote。
3. 企业证据只做候选匹配，不能自动把缺页码或否定表达判成 `PASS`。
4. 人工复核记录决定最终状态，并保留变更轨迹。

### 3. 可测试模块边界

从 `proposal-compliance-matrix` 借鉴纯函数模块边界和阈值外置方式：解析、规则、匹配、状态迁移分别测试；阈值和关键词表配置化。TF-IDF 只能作为后续“候选召回”，不能替代页级事实判定。

## 不采用的实现

- 不复制 `BidMaster-Pro` 的代码：实际许可证是 AGPL-3.0，且 README 的 MIT 徽章与之冲突。
- 不复制无许可证仓库的代码，即使代码看起来适合。
- 不引入长标书生成、自动报价、自动投标提交、法律意见、跨行业规则库等超出当前 MVP 边界的能力。
- 不把第三方仓库的市场规模、召回率、竞品结论或“生产级”描述写入产品承诺。

## 后续工程顺序

1. 为本项目实现带 bbox 的 PyMuPDF layout 抽取，并保留当前纯文本兼容路径。
2. 增加 OCR adapter 接口和扫描页 `NEEDS_REVIEW` 降级路径；先不强依赖 Tesseract 安装。
3. 将 `requirement`、`evidence`、`citation`、`review_event` 从嵌套 JSON 提升为可审计的数据契约。
4. 建立中文真实招标 PDF fixture 和人工 ground truth，再测召回率、严重风险漏报率和页码覆盖率。

当前结论：`kuaizengji` 值得借鉴“契约、规范化、失败兜底”的工程方法；没有发现可以安全、完整移植到 Project-025 的 GitHub 成品代码。
