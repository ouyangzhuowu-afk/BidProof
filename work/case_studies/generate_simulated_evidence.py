"""Generate high-fidelity simulated enterprise qualification PDFs for tender verification.

This script creates two test enterprise evidence bundles:
1. enterprise_alpha_compliant.pdf (Fully compliant IT vendor)
2. enterprise_beta_disqualified.pdf (Typical disqualified vendor mirroring public invalidation cases:
   - Defect 1: Legal authorization letter missing company seal (violates star ★ fatal clause)
   - Defect 2: Project manager social security paid by 3rd-party agency, not the bidder
   - Defect 3: ISO9001 certificate expired before bid submission date
"""

import sys
from pathlib import Path
import pymupdf

OUTPUT_DIR = Path("work/case_studies")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FONT = "china-s"


def create_page(doc, title: str):
    page = doc.new_page(width=595, height=842)
    # Header line
    page.insert_text((50, 45), title, fontsize=12, fontname=FONT, color=(0.4, 0.4, 0.4))
    page.draw_line((50, 55), (545, 55), color=(0.7, 0.7, 0.7), width=0.8)
    return page


def add_alpha_compliant_pdf():
    doc = pymupdf.open()
    
    # Page 1: 营业执照
    p1 = create_page(doc, "企业资质证明 - 营业执照")
    p1.insert_text((180, 100), "营业执照（正本）", fontsize=20, fontname=FONT, color=(0.1, 0.1, 0.1))
    p1.insert_text((160, 130), "统一社会信用代码：91110108MA01789X0Q", fontsize=11, fontname=FONT)
    lines_p1 = [
        "名称：北京华科智创科技有限公司",
        "类型：有限责任公司（自然人投资或控股）",
        "法定代表人：赵建华",
        "注册资本：人民币 2000.00 万元整",
        "成立日期：2016年03月15日",
        "营业期限：2016年03月15日至长期",
        "住所：北京市海淀区中关村南大街18号科技大厦B座801室",
        "经营范围：技术开发、技术咨询、技术服务、软件开发、信息系统集成服务；计算机系统测评技术服务；数据处理；销售计算机、软件及辅助设备。（市场主体依法自主选择经营项目，开展经营活动；依法须经批准的项目，经相关部门批准后依批准的内容开展经营活动）",
        "登记机关：北京市海淀区市场监督管理局",
        "发证日期：2023年06月10日",
        "【核验标识】：国家企业信用信息公示系统（北京）已核准在册，经营状态：存续（在营）。"
    ]
    y = 170
    for line in lines_p1:
        p1.insert_text((60, y), line, fontsize=10, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 24
    p1.draw_rect((50, 70, 545, 450), color=(0.2, 0.4, 0.6), width=1.0)
    
    # Page 2: 法定代表人授权委托书与身份证 (带公章与签名)
    p2 = create_page(doc, "★ 商务资格文件 - 法定代表人授权委托书")
    p2.insert_text((160, 90), "法定代表人授权委托书", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p2 = [
        "致：南京市公共资源交易中心",
        "    本授权委托书声明：本公司 赵建华（法定代表人）特授权 张建国（委托代理人，身份证号：11010819850612431X）为本公司的合法代理人，就贵方组织的“招标投标交易系统第三方软件测评服务采购文件”（项目编号：NJ-2024-0730）项目进行投标、谈判、签署响应文件、签署合同及处理一切与本项目有关的事务。",
        "    委托代理人在本项目采购活动中所签署的一切文件和处理的一切相关事务，本公司均予以承认并承担法律责任。委托代理人无转委托权。",
        "",
        "授权期限：自签署之日起至本项目合同履行完毕止。",
        "",
        "投标人名称（盖章）：北京华科智创科技有限公司 [已加盖公章]",
        "法定代表人（签字或签章）：赵建华 [已签名]",
        "委托代理人（签字）：张建国 [已签名]",
        "签署日期：2024年08月02日",
        "",
        "【附：法定代表人及授权委托代理人身份证正反面复印件完整有效，已加盖投标人电子印章】"
    ]
    y = 130
    for line in lines_p2:
        p2.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 22

    # Page 3: 供应商资格承诺函
    p3 = create_page(doc, "★ 商务资格文件 - 供应商资格承诺函")
    p3.insert_text((160, 90), "《供应商资格承诺函》", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p3 = [
        "致：南京市公共资源交易中心",
        "    本公司（北京华科智创科技有限公司）参加“招标投标交易系统第三方软件测评服务”采购活动，郑重承诺满足以下条件：",
        "    1. 具有独立承担民事责任的能力；",
        "    2. 具有良好的商业信誉和健全的财务会计制度；",
        "    3. 具有履行合同所必需的设备和专业技术能力；",
        "    4. 有依法缴纳税收和社会保障资金的良好记录（2024年依法纳税，近6个月连续缴纳社保）；",
        "    5. 参加本次采购活动前三年内，在经营活动中没有重大违法记录；",
        "    6. 经在“信用中国”网站(www.creditchina.gov.cn)、中国政府采购网(www.ccgp.gov.cn)查询，本公司未被列入失信被执行人、重大税收违法失信主体、政府采购严重违法失信行为记录名单。",
        "",
        "    本公司保证上述声明事项真实、客观。如经查实存在虚假承诺，愿承担由此产生的一切法律责任并接受无效投标处理及没收投标保证金等处罚。",
        "",
        "承诺单位（盖章）：北京华科智创科技有限公司 [已加盖公章]",
        "法定代表人或授权代表（签字）：张建国 [已签名]",
        "日期：2024年08月02日"
    ]
    y = 130
    for line in lines_p3:
        p3.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 22

    # Page 4: 质量管理体系认证证书 ISO9001
    p4 = create_page(doc, "履约能力证明 - ISO9001质量管理体系认证")
    p4.insert_text((160, 90), "质量管理体系认证证书", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p4 = [
        "证书编号：00123Q34567R2M/1100",
        "兹证明：北京华科智创科技有限公司",
        "统一社会信用代码：91110108MA01789X0Q",
        "认证范围：计算机应用软件开发、系统集成实施及软件测评技术服务与技术咨询",
        "其质量管理体系符合标准：GB/T 19001-2016 / ISO 9001:2015",
        "发证日期：2023年09月12日    有效期至：2026年09月11日",
        "认证机构：中质协质量保证中心（经国家认监委 CNCA 批准认可）",
        "国家认监委全国认证认可信息公共服务平台(http://cx.cnca.cn)核验状态：【有效】",
        "上一次年度监督审核合格日期：2024年06月18日"
    ]
    y = 130
    for line in lines_p4:
        p4.insert_text((60, y), line, fontsize=10, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 24

    # Page 5: 项目负责人资格证书与社保证明 (张建国)
    p5 = create_page(doc, "履约能力证明 - 项目负责人资格及社保证明")
    p5.insert_text((150, 90), "拟投入项目负责人资格证明", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p5 = [
        "项目负责人姓名：张建国    岗位：项目总监 / 软件测评技术负责人",
        "1. 人社部和工信部颁发的信息系统项目管理师证书",
        "   证书管理号：20210511010800098    职业资格名称：信息系统项目管理师（高级）",
        "   发证机关：中华人民共和国人力资源和社会保障部、中华人民共和国工业和信息化部",
        "   发证日期：2021年05月    状态：全国有效并在注册有效期内",
        "2. 电子信息类高级工程师职称证书",
        "   职称级别：高级工程师（副高级）    专业领域：电子信息工程 / 计算机软件",
        "   评定机构：北京市工程技术系列高级职称评审委员会",
        "3. 中国信息安全测评中心注册信息安全专业人员证书（CISP）",
        "   证书编号：CISP-2022-P-88992    状态：有效",
        "",
        "【社保缴纳证明】：",
        "出具机构：北京市海淀区社会保险基金管理中心（社保专用章）",
        "参保单位：北京华科智创科技有限公司（统一代码：91110108MA01789X0Q）",
        "参保人员：张建国（身份证号：11010819850612431X）",
        "缴费明细：2024年01月至2024年07月（连续正常缴纳基本养老、失业、工伤、医疗保险），符合“2024年1月1日以来任意一个月的社保证明”招标文件要求。"
    ]
    y = 125
    for line in lines_p5:
        p5.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 21

    # Page 6: 类似软件测试业绩合同与报告
    p6 = create_page(doc, "业绩证明 - 类似第三方软件测试服务业绩")
    p6.insert_text((160, 90), "同类项目业绩证明材料", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p6 = [
        "项目一：江苏省某市公共资源交易平台信创改造第三方软件评测项目",
        "合同签订日期：2023年04月18日（符合2021年1月1日以来要求）",
        "采购单位：某市公共资源交易中心    服务金额：48.50 万元",
        "服务内容：对公共资源网上交易系统、电子辅助评标系统进行第三方功能、性能及安全测评，出具软件评测报告。",
        "【附：合同关键页、甲乙双方盖章页、第三方测评报告验收合格证明复印件】",
        "",
        "项目二：某省电子政务一体化数据交换平台软件测试服务项目",
        "合同签订日期：2022年11月05日",
        "服务内容：包含性能测试（并发用户数达1500）、代码审计、渗透测试，已顺利通过最终专家验收。",
        "【附：采购合同与第三方测试报告关键页】"
    ]
    y = 130
    for line in lines_p6:
        p6.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 23

    target_path = OUTPUT_DIR / "enterprise_alpha_compliant.pdf"
    doc.save(str(target_path))
    doc.close()
    print(f"Generated: {target_path} (6 pages)")


def add_beta_disqualified_pdf():
    doc = pymupdf.open()
    
    # Page 1: 营业执照
    p1 = create_page(doc, "企业资质证明 - 营业执照")
    p1.insert_text((180, 100), "营业执照（正本）", fontsize=20, fontname=FONT, color=(0.1, 0.1, 0.1))
    p1.insert_text((160, 130), "统一社会信用代码：91110105MA02998Y7R", fontsize=11, fontname=FONT)
    lines_p1 = [
        "名称：盛世云图信息技术有限公司",
        "类型：有限责任公司",
        "法定代表人：王浩",
        "注册资本：500.00 万元",
        "成立日期：2019年05月20日",
        "住所：北京市朝阳区北苑路168号",
        "经营范围：软件开发、信息系统技术服务、计算机软硬件零售。"
    ]
    y = 170
    for line in lines_p1:
        p1.insert_text((60, y), line, fontsize=10, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 24
        
    # Page 2: ★ 法定代表人授权委托书 【致命伤 1：漏盖公章！】
    p2 = create_page(doc, "★ 商务资格文件 - 法定代表人授权委托书")
    p2.insert_text((160, 90), "法定代表人授权委托书", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p2 = [
        "致：南京市公共资源交易中心",
        "    本授权委托书声明：本公司 王浩（法定代表人）特授权 李明（委托代理人，身份证号：110105198803152231）为本公司的合法代理人，参与“招标投标交易系统第三方软件测评服务采购”（项目编号：NJ-2024-0730）项目的投标响应及合同签署。",
        "",
        "授权期限：2024年08月01日至2024年10月01日。",
        "",
        "投标人名称：盛世云图信息技术有限公司",
        "法定代表人签字：王浩 [手写签字]",
        "委托代理人签字：李明 [手写签字]",
        "【特别缺陷记录】：本授权委托书落款处【未加盖单位公章】！",
        "（违反招标文件第5页第5.1条加★项目“不得有缺失或无效”及第7页第10.2.2.4条“未按照采购文件要求签章，资格审查直接作无效报价处理”！）"
    ]
    y = 130
    for line in lines_p2:
        p2.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 23

    # Page 3: 供应商资格承诺函
    p3 = create_page(doc, "★ 商务资格文件 - 供应商资格承诺函")
    p3.insert_text((160, 90), "《供应商资格承诺函》", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p3 = [
        "致：南京市公共资源交易中心",
        "    本公司（盛世云图信息技术有限公司）郑重承诺符合《中华人民共和国政府采购法》第二十二条规定条件，具有独立承担民事责任能力，未被列入失信被执行人名单。",
        "",
        "承诺单位（盖章）：盛世云图信息技术有限公司 [已盖章]",
        "法定代表人签字：王浩",
        "日期：2024年08月02日"
    ]
    y = 130
    for line in lines_p3:
        p3.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 23

    # Page 4: ISO9001 证书 【致命伤 2：证书已过有效期未年审】
    p4 = create_page(doc, "履约能力证明 - ISO9001质量管理体系认证")
    p4.insert_text((160, 90), "质量管理体系认证证书", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p4 = [
        "证书编号：03521Q11029R0S",
        "获证组织：盛世云图信息技术有限公司",
        "标准：GB/T 19001-2016 / ISO 9001:2015",
        "发证日期：2021年05月16日    有效期至：2024年05月15日",
        "【特别缺陷记录】：当前投标日期为 2024 年 08 月！该认证证书有效期截至 2024 年 05 月 15 日，已逾期失效 2 个月且未提供换证或监督审核凭证！",
        "（违反招标文件评分标准要求“提供以上证书且须在有效期内，否则不予认可”！）"
    ]
    y = 130
    for line in lines_p4:
        p4.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 24

    # Page 5: 项目负责人社保证明 【致命伤 3：社保单位与投标企业不一致，第三方挂靠断缴】
    p5 = create_page(doc, "履约能力证明 - 项目负责人资格及社保证明")
    p5.insert_text((150, 90), "拟投入项目负责人资格与社保证明", fontsize=18, fontname=FONT, color=(0.1, 0.1, 0.1))
    lines_p5 = [
        "拟派项目负责人：李明",
        "持有证书：信息系统项目管理师证书（高级），证书编号：20190511010091",
        "",
        "【提交的个人社会保险参保缴费证明】：",
        "缴费人员：李明（身份证号：110105198803152231）",
        "参保缴费单位：北京诚聘人力资源服务有限公司（社保代缴机构）",
        "缴费月份：仅体现 2024年06月（且无盛世云图公司的任何社保缴纳记录，亦无合法有效的劳务派遣协议与工伤代缴核准凭据）",
        "",
        "【特别缺陷记录】：招标文件第 12 页 4.2 条明文硬性规定：",
        "“提供上述项目负责人证书、供应商为其缴纳的2024年1月1日以来任意一个月的社保证明，缺一不可”。",
        "盛世云图公司未能提供本供应商为其缴纳社保的有效凭证，实质性不符合招标文件硬性资格与人员履约条件！"
    ]
    y = 125
    for line in lines_p5:
        p5.insert_text((60, y), line, fontsize=9.5, fontname=FONT, color=(0.15, 0.15, 0.15))
        y += 22

    target_path = OUTPUT_DIR / "enterprise_beta_disqualified.pdf"
    doc.save(str(target_path))
    doc.close()
    print(f"Generated: {target_path} (5 pages)")


if __name__ == "__main__":
    add_alpha_compliant_pdf()
    add_beta_disqualified_pdf()

