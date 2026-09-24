"""Synthetic, readable starter documents. Never customer evidence or benchmarks."""

from typing import Literal

import pymupdf as fitz

Scenario = Literal["software", "operations"]
DocumentKind = Literal["tender", "evidence"]

SCENARIOS = {
    "software": ("软件实施", "项目经理须具有有效的软件项目管理资格证书。"),
    "operations": ("系统运维", "投标人须提供近三年类似系统运维项目的业绩合同。"),
}


def document(scenario: Scenario, kind: DocumentKind) -> bytes:
    title, requirement = SCENARIOS[scenario]
    if kind == "tender":
        lines = [f"【合成示例】{title}项目招标文件", "仅用于体验产品，不属于真实采购项目。", "",
                 "一、资格要求", "投标人须提供有效的营业执照。", requirement,
                 "", "二、否决条款", "未提供有效营业执照的，投标无效。",
                 "", "三、交付要求", "服务期为合同签订后一年。"]
    else:
        lines = [f"【合成示例】{title}企业材料", "以下为虚构材料，不具有证明效力。", "",
                 "营业执照", "企业名称：示例软件服务企业", "营业期限：长期有效。", "",
                 "此样例故意未附其他资格或业绩材料，供体验补件核对。"]
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((54, 60), "\n".join(lines), fontname="china-s", fontsize=12, lineheight=1.8)
        return pdf.tobytes(garbage=4, deflate=True)
