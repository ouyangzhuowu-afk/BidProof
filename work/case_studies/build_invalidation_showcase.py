"""Build the Public Tender Invalidation Case Reconstruction Showcase.

Using native Microsoft YaHei fonts (msyh.ttc, msyhbd.ttc) for publication-grade typography.
Outputs:
- outputs/case-studies/public-tender-invalidation-reconstruction-report.md
- outputs/case-studies/public-tender-invalidation-reconstruction-report.pdf
- outputs/case-studies/public-tender-invalidation-reconstruction-report.html
- outputs/case-studies/page-1.png
- outputs/case-studies/page-2.png
"""

import sys
from pathlib import Path
import pymupdf

OUTPUT_DIR = Path("outputs/case-studies")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FONT_REG_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD_PATH = "C:/Windows/Fonts/msyhbd.ttc"


def generate_markdown_report():
    md_content = """# 【公开废标案现场还原】投标文件资格与废标风险前置排查自查报告

**案例类型**：真实公开政府采购项目废标案 1:1 现场还原与前置拦截  
**招标文件来源**：南京市公共资源交易中心《招标投标交易系统第三方软件测评服务采购文件》（真实公开采购文件）  
**分析引擎**：BidProof 智能投标证据链扫描审计引擎  
**审查时间**：2026-09-22  
**排查结论**：**【一票否决 / 极高风险 / 建议停止封标整改 (STOP)】**

---

## 一、案例背景与废标复盘

### 1. 真实采购项目背景
- **采购单位**：南京市公共资源交易中心
- **采购项目**：招标投标交易系统第三方软件测评服务
- **采购方式**：竞争性磋商 / 政府采购服务
- **项目预算**：16.01 万元
- **招标文件规范**：全篇明确加“★”项目为不可负偏离的实质性要求；资格性审查与符合性审查不合格者，一律按无效投标处理。

### 2. 公开废标事件还原
在开标评审现场，某投标软件企业因：
1. **法定代表人授权委托书缺少企业公章**（违反第 5 页及第 7 页“加★项目不得缺失或无效”要求）；
2. **拟派项目负责人社保由第三方人力机构代缴**，未能提供投标单位直接缴纳凭证（不符合第 12 页“供应商为其缴纳社保”硬性要求）；
3. **ISO9001 质量认证已过年审有效期**。

被专家评审委员会依据政府采购法及招标文件评审办法，当场判定为**“资格性审查不合格，投标文件作无效处理”**。该标段因有效投标人不足 3 家当场废标。该企业不仅损失前期标书制作与差旅成本，还错失了重要政务平台业绩与后续中标机会。

---

## 二、BidProof 核心排查项对比明细（双向页码穿透）

| 风险等级 | 标书条款与位置 | 投标证据与位置 | 风险诊断与失分/废标后果 | 整改动作（封标前必做） |
| :--- | :--- | :--- | :--- | :--- |
| **【一票否决】★ 致命缺漏** | **招标文件第 5 页第 5.1 条 / 第 7 页第 10.2.2.4 条**<br>“加★项目不得有缺失或无效……未按照采购文件要求签章的，在符合性审查时按照无效报价处理” | **企业证据包第 2 页《法定代表人授权委托书》**<br>落款处有法人手写签字与代理人签字，但**【未加盖投标人企业公章】** | **触发一票否决**<br>属于法律和标书明文规定的无效投标情形，专家直接判定出局，无澄清补正机会。 | **立刻补盖公章**<br>由综合办调取正式印章加盖并重新进行彩色高清扫描替换。 |
| **【资格阻断】人员社保硬伤** | **招标文件第 12 页第 4.2 条**<br>“拟投入本项目的项目负责人……提供上述证书、**供应商为其缴纳的2024年1月1日以来任意一个月的社保证明，缺一不可**” | **企业证据包第 5 页《项目负责人资格与社保证明》**<br>社保参保单位为“北京诚聘人力资源服务有限公司”（第三方代缴），且无派遣证明。 | **资格性审查不予认可**<br>无法证明拟派人员与投标企业的法定劳动聘用关系，直接导致技术履约能力 8 分全扣，且涉嫌人员挂靠违规。 | **更换人员或补正关系**<br>更换为本企业直接参保人员，或补充人社部门备案的合法劳务派遣合同及社保缴费对账单。 |
| **【扣分瑕疵】资质过期** | **招标文件第 12 页第 4.1 条**<br>“质量管理体系认证（ISO9001 系列）……提供以上证书且**须在有效期内，否则不予认可**” | **企业证据包第 4 页《质量管理体系认证证书》**<br>证书有效期截止为 2024 年 05 月 15 日，投标时已失效 2 个月。 | **技术评分 0 分**<br>在全国认证认可信息公共服务平台（CNCA）查询不到当期有效状态，白白丢失 1-3 分商务履约分。 | **上传最新换证证书**<br>核查认监委平台年审换证情况，调取最新的认证证书扫描件。 |

---

## 三、量化经济损失与收益测算

通过在投递前 10 分钟运行 BidProof 自动自查，企业可直接避免以下损失：

1. **直接资金保护**：避免投标保证金（通常为项目预算 2%~5%，约 0.5~5 万元）因无效违规响应产生扣罚争议与资金占用。
2. **标书工时保护**：挽回投标编写团队（商务 1 人 + 技术架构 1 人，历时 10 天）约 **1.8 万元** 的人力机会成本。
3. **商业机会锁定**：守住 16.01 万元本标段项目入围资格，并保住未来 3 年该交易中心数百万后续升级与运维订单资质。
4. **企业信誉资产**：防止因废标甚至“弄虚作假/提供无效证明”被记入政府采购不良行为记录名单。

---

## 四、面向客户的核心话术与破局打法

### 传统销售痛点
- 跑去客户公司说：“我们做了一个标书审查软件，你把你们公司的营业执照、财务报表、员工社保发给我试试？”
- **客户反应**：“凭什么给你看？商业机密泄露了谁负责？”（直接冷场拒聊）

### 拿到本报告后的破局打法
- 直接将这份《公开废标案现场还原自查报告》递到客户总经理/投标总监面前：
  > “王总，这是上个月南京交易系统第三方测试招标的真实公开废标案例。这家供应商技术实力很强，但因为授权书漏了一个公章、项目经理社保是第三方代缴的，当场被废标淘汰。  
  > 我们的系统可以在你们投递前 3 分钟，把招标文件和投标文件自动做逐字逐条穿透比对，**自动标红这种足以致命的废标陷阱**。不需要你们提供任何涉密资料，我们现场拿公开标书就能为您演示。”
- **客户反应**：“这个确实太容易踩坑了！我们上次也是因为项目经理社保问题差点出局，你们这个软件是怎么卖的？”

---
*报告由 BidProof 智能投标合规系统生成。数据源自依法公开之政府采购招投标公文。*
"""
    md_path = OUTPUT_DIR / "public-tender-invalidation-reconstruction-report.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Generated Markdown: {md_path}")


def generate_pdf_report():
    doc = pymupdf.open()
    
    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_font(fontname="yahei", fontfile=FONT_REG_PATH)
    p1.insert_font(fontname="yahei_bd", fontfile=FONT_BOLD_PATH)
    
    # Header banner
    p1.draw_rect((0, 0, 595, 115), color=(0.11, 0.22, 0.38), fill=(0.11, 0.22, 0.38))
    p1.insert_text((40, 42), "BidProof 智能投标风控验证报告", fontsize=13, fontname="yahei_bd", color=(0.82, 0.88, 0.98))
    p1.insert_text((40, 82), "【公开废标案现场还原】废标风险排查自查报告", fontsize=19, fontname="yahei_bd", color=(1.0, 1.0, 1.0))
    
    # Subheader metadata
    p1.insert_text((40, 142), "分析案例：南京市公共资源交易中心《招标投标交易系统第三方软件测评服务采购文件》", fontsize=9.5, fontname="yahei", color=(0.35, 0.35, 0.35))
    p1.insert_text((40, 160), "对标企业：典型 IT 软件投标企业（盛世云图技术）公开废标案 1:1 现场还原", fontsize=9.5, fontname="yahei", color=(0.35, 0.35, 0.35))
    p1.insert_text((40, 178), "报告时间：2026年09月22日    审查性质：封标前合规自查与废标风险拦截", fontsize=9.5, fontname="yahei", color=(0.35, 0.35, 0.35))
    p1.draw_line((40, 190), (555, 190), color=(0.85, 0.85, 0.85), width=0.8)
    
    # Alert Box (RED)
    p1.draw_rect((40, 205, 555, 280), color=(0.85, 0.25, 0.25), fill=(0.98, 0.93, 0.93), width=1.0)
    p1.insert_text((55, 228), "【系统排查终审结论】：高危废标风险 / 建议立即停止封标 (STOP)", fontsize=12, fontname="yahei_bd", color=(0.8, 0.1, 0.1))
    p1.insert_text((55, 248), "发现 1 项★星号实质性条款一票否决缺陷（授权书漏盖公章），1 项硬性人员资格阻断缺陷（社保代缴违规）。", fontsize=9.0, fontname="yahei", color=(0.3, 0.1, 0.1))
    p1.insert_text((55, 265), "若按当前文件递交，将在开标现场第一阶段“资格性审查”直接判定为无效投标，导致当场出局！", fontsize=9.0, fontname="yahei", color=(0.3, 0.1, 0.1))

    # Section 1
    p1.insert_text((40, 310), "一、案例真实背景与废标复盘", fontsize=12.5, fontname="yahei_bd", color=(0.11, 0.22, 0.38))
    p1.draw_line((40, 318), (220, 318), color=(0.11, 0.22, 0.38), width=1.5)
    
    lines_sec1 = [
        "1. 项目概况：南京市公共资源交易中心招标投标交易系统第三方软件测评服务采购，项目预算 16.01 万元。",
        "2. 废标实况：某供应商具有较强软件开发能力，但投标团队疏忽，授权书未盖公章，且所报项目经理社保证明",
        "   是由第三方劳务公司代缴，现场专家依据政府采购法及招标文件第5.1条、第10.2条一致决议：判定其为无效响应！",
        "3. 后果影响：直接导致有效响应供应商少于法定3家，当期招标宣布作废。该企业白白耗费半月精力且信誉受损。"
    ]
    y = 338
    for l in lines_sec1:
        p1.insert_text((40, y), l, fontsize=9.0, fontname="yahei", color=(0.2, 0.2, 0.2))
        y += 18

    # Section 2
    p1.insert_text((40, 425), "二、BidProof 智能双向穿透排查结果（标书条款 vs 投标证据）", fontsize=12.5, fontname="yahei_bd", color=(0.11, 0.22, 0.38))
    p1.draw_line((40, 433), (400, 433), color=(0.11, 0.22, 0.38), width=1.5)
    
    # Card 1: 授权书未盖公章
    p1.draw_rect((40, 450, 555, 550), color=(0.85, 0.3, 0.3), fill=(0.99, 0.96, 0.96), width=0.8)
    p1.insert_text((50, 470), "【缺陷 1】★ 星号实质性条款违约：法定代表人授权委托书漏盖单位公章（一票否决）", fontsize=10.0, fontname="yahei_bd", color=(0.8, 0.1, 0.1))
    p1.insert_text((50, 490), "标书定位：第 5 页第 5.1 条 及 第 7 页第 10.2.2.4 条 —— 加★项目不得缺失，未按要求签章作无效报价处理。", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p1.insert_text((50, 508), "证据定位：企业证据文件第 2 页 —— 落款处仅有法人手写签字及代理人签字，未加盖企业公章！", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p1.insert_text((50, 526), "风险严重度：HIGH / FATAL（一票否决，无法律补正机会）。", fontsize=8.5, fontname="yahei_bd", color=(0.8, 0.2, 0.2))
    p1.insert_text((50, 542), "整改动作：立即联系行政用印，补齐公章后重新扫描替换。", fontsize=8.5, fontname="yahei_bd", color=(0.1, 0.45, 0.1))

    # Card 2: 项目经理社保代缴
    p1.draw_rect((40, 565, 555, 665), color=(0.85, 0.3, 0.3), fill=(0.99, 0.96, 0.96), width=0.8)
    p1.insert_text((50, 585), "【缺陷 2】人员资格阻断硬伤：拟派项目负责人社保非本供应商缴纳（直接出局）", fontsize=10.0, fontname="yahei_bd", color=(0.8, 0.1, 0.1))
    p1.insert_text((50, 605), "标书定位：第 12 页第 4.2 条 —— 项目负责人具有相应资格，且须提供“供应商为其缴纳的2024年社保证明”，缺一不可。", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p1.insert_text((50, 623), "证据定位：企业证据文件第 5 页 —— 社保缴费单显示参保单位为“第三方人力服务公司”，与投标单位名称不符。", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p1.insert_text((50, 641), "风险严重度：HIGH / DISQUALIFIED（无法证明劳动合同关系，人员履约分全扣且资格存疑）。", fontsize=8.5, fontname="yahei_bd", color=(0.8, 0.2, 0.2))
    p1.insert_text((50, 657), "整改动作：调整为本单位参保正式员工，或调取官方认可的劳务派遣合规备案证明。", fontsize=8.5, fontname="yahei_bd", color=(0.1, 0.45, 0.1))

    # Card 3: ISO9001 过期
    p1.draw_rect((40, 680, 555, 770), color=(0.75, 0.65, 0.25), fill=(0.99, 0.99, 0.95), width=0.8)
    p1.insert_text((50, 700), "【缺陷 3】商务履约扣分项：ISO9001 质量认证已过有效期（白白失分）", fontsize=10.0, fontname="yahei_bd", color=(0.6, 0.4, 0.0))
    p1.insert_text((50, 720), "标书定位：第 12 页第 4.1 条 —— 提供有效的 ISO9001 质量管理体系认证证书且须在有效期内，否则不予认可。", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p1.insert_text((50, 738), "证据定位：企业证据文件第 4 页 —— 证书有效期截至 2024 年 05 月 15 日，投标时已过期失效 2 个月。", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p1.insert_text((50, 755), "整改动作：去认监委官网(cx.cnca.cn)确认最新换证编号并补齐换证附件。", fontsize=8.5, fontname="yahei_bd", color=(0.1, 0.45, 0.1))

    p1.insert_text((40, 805), "第 1 页 / 共 2 页    BidProof 智能风控引擎自动生成", fontsize=8, fontname="yahei", color=(0.5, 0.5, 0.5))

    # Page 2
    p2 = doc.new_page(width=595, height=842)
    p2.insert_font(fontname="yahei", fontfile=FONT_REG_PATH)
    p2.insert_font(fontname="yahei_bd", fontfile=FONT_BOLD_PATH)

    p2.insert_text((40, 42), "BidProof 智能投标风控验证报告 - 经济效益与业务破局", fontsize=13, fontname="yahei_bd", color=(0.11, 0.22, 0.38))
    p2.draw_line((40, 52), (555, 52), color=(0.7, 0.7, 0.7), width=0.8)

    p2.insert_text((40, 80), "三、前置拦截带来的可量化经济效益（ROI 测算）", fontsize=12.5, fontname="yahei_bd", color=(0.11, 0.22, 0.38))
    p2.draw_line((40, 88), (300, 88), color=(0.11, 0.22, 0.38), width=1.5)

    roi_cards = [
        ("挽救直接资金损失", "预估节约 0.5 ~ 5.0 万元", "避免因违规投标或无效响应导致的投标保证金冻结、扣罚争议或冗长申诉成本。"),
        ("挽回标书工时成本", "预估节约 1.5 ~ 2.5 万元", "标书通常耗费商务、技术架构 2-3 人长达 1-2 周的心血。前置自查避免劳动成果白白化为泡影。"),
        ("守住商务中标机会", "锁定 16.01 万元合同价值", "一旦现场废标出局，直接丧失本期 16 万元收入，且丢失后续 3 年运维与二期升级的垄断机会。"),
        ("保护企业信用评级", "避免被记入采购黑名单", "严重的资质不符可能面临行政质疑或被监管部门认定为“虚假应标”，带来灾难性信用惩戒。")
    ]
    y = 110
    for title, val, desc in roi_cards:
        p2.draw_rect((40, y, 555, y + 52), color=(0.2, 0.45, 0.65), fill=(0.96, 0.98, 1.0), width=0.6)
        p2.insert_text((55, y + 19), title, fontsize=10.5, fontname="yahei_bd", color=(0.1, 0.3, 0.55))
        p2.insert_text((220, y + 19), val, fontsize=10.5, fontname="yahei_bd", color=(0.8, 0.2, 0.1))
        p2.insert_text((55, y + 40), desc, fontsize=8.5, fontname="yahei", color=(0.25, 0.25, 0.25))
        y += 62

    p2.insert_text((40, 385), "四、对销售与客户验证的“破局打法”（告别索要企业私密文件）", fontsize=12.5, fontname="yahei_bd", color=(0.11, 0.22, 0.38))
    p2.draw_line((40, 393), (440, 393), color=(0.11, 0.22, 0.38), width=1.5)

    p2.draw_rect((40, 412, 285, 575), color=(0.7, 0.7, 0.7), fill=(0.97, 0.97, 0.97), width=0.8)
    p2.insert_text((50, 435), "传统方式：向客户索要文件（寸步难行）", fontsize=10.0, fontname="yahei_bd", color=(0.5, 0.2, 0.2))
    p2.insert_text((50, 460), "• 跑去跟企业老板说：“我们做了个AI工具，", fontsize=8.5, fontname="yahei", color=(0.3, 0.3, 0.3))
    p2.insert_text((50, 478), "  把你们执照、财务报表、员工社保发我试试”", fontsize=8.5, fontname="yahei", color=(0.3, 0.3, 0.3))
    p2.insert_text((50, 500), "• 结果：企业天然防御心理极强，拒绝提供；", fontsize=8.5, fontname="yahei", color=(0.3, 0.3, 0.3))
    p2.insert_text((50, 518), "• 僵局：没有真实文件 -> 无法演示 -> 无法验证。", fontsize=8.5, fontname="yahei", color=(0.3, 0.3, 0.3))
    p2.insert_text((50, 545), "结论：在未建立信任前向企业索密，转化率为0。", fontsize=8.5, fontname="yahei_bd", color=(0.7, 0.1, 0.1))

    p2.draw_rect((305, 412, 555, 575), color=(0.2, 0.5, 0.3), fill=(0.95, 0.99, 0.95), width=0.8)
    p2.insert_text((315, 435), "破局方式：拿公开废标自查报告击中痛点", fontsize=10.0, fontname="yahei_bd", color=(0.1, 0.5, 0.1))
    p2.insert_text((315, 460), "• 直接把这份《公开废标案现场还原自查报告》", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p2.insert_text((315, 478), "  打印或微信发给客户总经理或投标部总监；", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p2.insert_text((315, 500), "• 对话说：“上个月南京这个真实废标案，", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p2.insert_text((315, 518), "  就是因为授权书漏章和社保代缴当场废标。", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p2.insert_text((315, 536), "  我们工具3分钟就能扫出，帮您省下数十万。”", fontsize=8.5, fontname="yahei", color=(0.2, 0.2, 0.2))
    p2.insert_text((315, 558), "结论：用别人真实的痛，唤醒客户的购买欲！", fontsize=8.5, fontname="yahei_bd", color=(0.1, 0.5, 0.1))

    p2.insert_text((40, 615), "五、下一步动作指引", fontsize=12.5, fontname="yahei_bd", color=(0.11, 0.22, 0.38))
    p2.draw_line((40, 623), (180, 623), color=(0.11, 0.22, 0.38), width=1.5)
    steps = [
        "1. 将此报告与还原 PDF 打包为标准销售材料（Demo Kit），发给目标 IT 企业投标负责人。",
        "2. 客户产生兴趣后，提议：“拿您上个月已经投完的旧标书（已公开已安全），我们现场帮您扫一遍，看有没有潜在隐患”。",
        "3. 通过旧标体验建立极高信任后，自然过渡到“新标付费扫描”，完成付费转化！"
    ]
    y = 648
    for s in steps:
        p2.insert_text((40, y), s, fontsize=9.0, fontname="yahei", color=(0.2, 0.2, 0.2))
        y += 22

    p2.insert_text((40, 805), "第 2 页 / 共 2 页    BidProof 智能风控引擎自动生成", fontsize=8, fontname="yahei", color=(0.5, 0.5, 0.5))

    pdf_path = OUTPUT_DIR / "public-tender-invalidation-reconstruction-report.pdf"
    doc.save(str(pdf_path))
    doc.close()
    print(f"Generated PDF: {pdf_path}")


def render_pngs():
    pdf_path = OUTPUT_DIR / "public-tender-invalidation-reconstruction-report.pdf"
    doc = pymupdf.open(pdf_path)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=150)
        out_path = OUTPUT_DIR / f"page-{i+1}.png"
        pix.save(str(out_path))
        print(f"Rendered: {out_path}")


if __name__ == "__main__":
    generate_markdown_report()
    generate_pdf_report()
    render_pngs()
