import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.extraction import extract_text_file
from app.presenters import tender_blocks_for_run
from app.services import scan_service
from app.tender_blocks import extract_tender_blocks, sanitize_tender_blocks

ROOT = Path(__file__).resolve().parents[1]


def _page(number: int, text: str, **extra) -> dict:
    page = {
        "page": number,
        "text": text,
        "locator": {"kind": "page", "label": f"第 {number} 页", "index": number},
    }
    page.update(extra)
    return page


def _blocks(result: dict) -> dict[str, list[dict]]:
    return {key: result["blocks"][key]["items"] for key in ("qualification", "scoring", "materials", "rejection")}


def _quotes(items: list[dict]) -> str:
    return "\n".join(item["quote"] for item in items)


def test_four_blocks_each_item_keeps_its_original_page():
    pages = [
        _page(2, "二、申请人的资格要求：\n1.满足《中华人民共和国政府采购法》第二十二条的规定。"),
        _page(6, "评分办法\n售后服务方案完善的计 14 分，未提供售后服务方案的不计分。"),
        _page(8, "第六章 响应文件组成\n一、响应函\n二、授权委托书"),
        _page(9, "有下列情形之一的，应予以废标：\n（1）符合专业条件的供应商不足2家的。"),
    ]
    result = extract_tender_blocks(pages, filename="sample.pdf")
    found = _blocks(result)

    assert found["qualification"]
    assert found["scoring"]
    assert found["materials"]
    assert found["rejection"]
    assert {item["page"] for item in found["qualification"]} == {2}
    assert {item["page"] for item in found["scoring"]} == {6}
    assert {item["page"] for item in found["materials"]} == {8}
    assert {item["page"] for item in found["rejection"]} == {9}
    assert result["product_pass"] is False
    assert result["audit_status"] == "pending_audit"
    assert result["uncited"] == []
    assert all(item["status"] == "NEEDS_REVIEW" for group in found.values() for item in group)


def test_table_rejection_reads_the_header_when_the_cell_has_no_keyword():
    pages = [
        _page(
            5,
            "评审表",
            tables=[{"header": ["废标情形"], "rows": [["未按要求密封"]]}],
        )
    ]
    result = extract_tender_blocks(pages, filename="table.pdf")
    rejection = _blocks(result)["rejection"]

    assert len(rejection) == 1
    assert rejection[0]["pages"] == [5]
    assert rejection[0]["detection"] == "table"
    assert "未按要求密封" in rejection[0]["quote"]
    assert "否决投标" not in rejection[0]["quote"]
    assert "不予受理" not in rejection[0]["quote"]
    assert "废标" not in rejection[0]["quote"].split("：", 1)[-1]


def test_yes_no_column_decides_rejection_instead_of_the_word_in_the_cell():
    pages = [
        _page(
            4,
            "",
            tables=[{
                "header": ["条款", "是否废标"],
                "rows": [["未提供授权书", "是"], ["报价笔误，文中出现否决投标四字", "否"]],
            }],
        )
    ]
    rejection = _blocks(extract_tender_blocks(pages))["rejection"]

    assert len(rejection) == 1
    assert "未提供授权书" in rejection[0]["quote"]
    assert "报价笔误" not in rejection[0]["quote"]
    assert rejection[0]["page"] == 4


def test_outcome_column_is_read_as_a_clause():
    pages = [
        _page(
            7,
            "",
            tables=[{"header": ["序号", "情形", "处理"], "rows": [["1", "投标文件未按要求密封", "按无效投标处理"]]}],
        )
    ]
    rejection = _blocks(extract_tender_blocks(pages))["rejection"]

    assert rejection
    assert rejection[0]["pages"] == [7]
    assert "未按要求密封" in rejection[0]["quote"]


def test_negated_rejection_list_is_not_a_rejection_item():
    pages = [
        _page(1, "下列情形不作为否决投标的情形：\n（1）单位名称笔误；\n（2）报价大小写不一致但可以修正的。"),
        _page(2, "技术方案按优劣打分，未提供方案不得分，但不否决投标。本项目不因此废标。"),
    ]
    result = extract_tender_blocks(pages, filename="negation.pdf")
    found = _blocks(result)

    assert found["rejection"] == []
    assert found["scoring"]
    assert found["scoring"][0]["page"] == 2
    assert all(item["status"] != "PASS" for item in result["uncited"])


def test_line_break_inside_a_page_rejoins_the_sentence():
    pages = [
        _page(
            24,
            "14.2 在进入磋商阶段之前,磋商小组将对首次响应文件进行审查。\n"
            "如果供应商资格审查和实质性响应审查不合格,则其响应文件将被磋商小组否\n"
            "决,按无效处理,不进入磋商阶段,磋商小组将告知有关供应商。\n"
            "14.2.1 供应商有下列情况之一者,其响应文件按无效处理。",
        )
    ]
    rejection = _blocks(extract_tender_blocks(pages, filename="wrap.pdf"))["rejection"]
    joined = [
        item for item in rejection
        if "资格审查和实质性响应审查不合格" in item["quote"] and "否决" in item["quote"]
    ]

    assert len(joined) == 1
    assert joined[0]["page"] == 24
    assert joined[0]["pages"] == [24]
    assert joined[0]["status"] == "NEEDS_REVIEW"
    assert "按无效处理" in joined[0]["quote"]
    assert "14.2 在进入磋商阶段之前" not in joined[0]["quote"]
    assert all(not item["quote"].startswith("决,") for item in rejection)
    assert all(item["status"] == "NEEDS_REVIEW" for item in rejection)


def test_cross_page_sentence_keeps_both_pages():
    pages = [
        _page(3, "未按招标文件要求签署、盖章的，其投标"),
        _page(4, "无效。"),
    ]
    rejection = _blocks(extract_tender_blocks(pages, filename="span.pdf"))["rejection"]

    assert len(rejection) == 1
    assert rejection[0]["pages"] == [3, 4]
    assert rejection[0]["page"] == 3
    assert rejection[0]["detection"] == "cross_page"
    assert "无效" in rejection[0]["quote"]
    assert rejection[0]["locator"]["label"] == "PDF 第3-4页"


def test_rejection_list_continues_on_the_next_page_without_those_keywords():
    pages = [
        _page(8, "11.废标\n11.1 如出现下列情况之一的，应予以废标："),
        _page(9, "（1）符合专业条件的供应商不足2家的；\n（2）供应商的报价均超过采购预算的。"),
    ]
    rejection = _blocks(extract_tender_blocks(pages, filename="list.pdf"))["rejection"]
    quotes = _quotes(rejection)

    assert any(item["pages"] == [9] and "不足2家" in item["quote"] for item in rejection)
    assert "超过采购预算" in quotes
    assert all("不予受理" not in item["quote"] for item in rejection if 9 in item["pages"])
    assert all(item["status"] == "NEEDS_REVIEW" for item in rejection)


def test_rejection_list_stops_at_the_next_numbered_section():
    pages = [
        _page(3, "有下列情形之一的，应予以废标：\n（1）供应商不足2家的。\n26.澄清\n26.1 磋商小组可以要求供应商作出澄清。"),
    ]
    rejection = _blocks(extract_tender_blocks(pages, filename="list-end.pdf"))["rejection"]

    assert any("不足2家" in item["quote"] for item in rejection)
    assert all("澄清" not in item["quote"] for item in rejection)


def test_clock_time_is_not_scored_as_points():
    pages = [
        _page(2, "提交首次响应文件的截止时间: 2025年07月14日15时00分。"),
        _page(3, "二、申请人的资格要求：\n供应商须在开标开始后30分钟内完成解密。"),
    ]
    found = _blocks(extract_tender_blocks(pages, filename="clock.pdf"))
    assert found["scoring"] == []
    assert all("保证金" not in item["quote"] for item in found["qualification"])
    model = _blocks(extract_tender_blocks([_page(1, "分体变频壁挂机1.5P 海尔 2088 249 分体变频柜机2P")], filename="award.txt"))
    assert model["scoring"] == []


def test_missing_original_page_is_listed_apart_and_cannot_pass():
    pages = [
        {
            "page": 3,
            "text": "资格要求：依法设立并提供营业执照。",
            "locator": {"kind": "paragraph", "label": "段落 3", "index": 3},
        },
        {"text": "有下列情形之一的，应予以废标：（1）未密封的。"},
    ]
    result = extract_tender_blocks(pages, filename="notes.docx")
    found = _blocks(result)

    assert all(group == [] for group in found.values())
    assert result["uncited"]
    assert {item["status"] for item in result["uncited"]} <= {"UNKNOWN", "NEEDS_REVIEW"}
    assert all(item["status"] != "PASS" for item in result["uncited"])
    assert all(item["pages"] == [] and item["page"] is None for item in result["uncited"])
    assert all(item["filename"] == "notes.docx" for item in result["uncited"])
    assert any("段落" in item["uncited_reason"] for item in result["uncited"])
    assert any(item["block"] == "qualification" for item in result["uncited"])
    assert any(item["block"] == "rejection" for item in result["uncited"])


def test_office_table_cells_do_not_invent_a_page_number():
    pages = [
        {"page": 1, "text": "条款", "locator": {"kind": "table_cell", "label": "表格 1 · 第 1 行 · 第 1 列", "table": 1, "row": 1, "column": 1}},
        {"page": 2, "text": "是否废标", "locator": {"kind": "table_cell", "label": "表格 1 · 第 1 行 · 第 2 列", "table": 1, "row": 1, "column": 2}},
        {"page": 3, "text": "未提供授权书", "locator": {"kind": "table_cell", "label": "表格 1 · 第 2 行 · 第 1 列", "table": 1, "row": 2, "column": 1}},
        {"page": 4, "text": "是", "locator": {"kind": "table_cell", "label": "表格 1 · 第 2 行 · 第 2 列", "table": 1, "row": 2, "column": 2}},
    ]
    result = extract_tender_blocks(pages, filename="cells.docx")

    assert _blocks(result)["rejection"] == []
    assert any(item["block"] == "rejection" and item["status"] in {"UNKNOWN", "NEEDS_REVIEW"} for item in result["uncited"])
    assert all(item["page"] is None for item in result["uncited"])


def test_flat_qualification_table_becomes_materials_with_a_page():
    text = "附表1资格审查表\n序号\n审查项目\n审查标准\n1\n法人营业执照等主体资格证明文件\n提供并加盖公章\n2\n法定代表人身份证明或授权委托书\n提供原件并加盖公章"
    materials = _blocks(extract_tender_blocks([_page(12, text)], filename="review.pdf"))["materials"]

    assert {item["page"] for item in materials} == {12}
    assert any("营业执照" in item["quote"] for item in materials)
    assert any("授权委托书" in item["quote"] for item in materials)


def test_sanitize_moves_a_pass_without_a_page_to_uncited():
    payload = {
        "audit_status": "pending_audit",
        "product_pass": True,
        "blocks": {
            "qualification": {
                "label": "资格要求",
                "items": [{
                    "block": "qualification",
                    "label": "资格要求",
                    "summary": "资格要求：依法设立",
                    "quote": "资格要求：依法设立",
                    "pages": [],
                    "page": None,
                    "status": "PASS",
                    "locator": {"kind": "line_range", "label": "第 2 行"},
                    "filename": "loose.txt",
                }],
            }
        },
        "uncited": [],
    }
    result = sanitize_tender_blocks(payload)

    assert result["product_pass"] is False
    assert result["blocks"]["qualification"]["items"] == []
    assert result["uncited"][0]["status"] in {"UNKNOWN", "NEEDS_REVIEW"}
    assert result["uncited"][0]["status"] != "PASS"
    assert result["uncited"][0]["pages"] == []


def test_public_redacted_tender_has_no_original_pages():
    path = ROOT / "work" / "eval" / "meddevice-redacted" / "consult-cryostat-redacted.txt"
    result = extract_tender_blocks(extract_text_file(path), filename=path.name)
    found = _blocks(result)

    assert result["product_pass"] is False
    assert result["audit_status"] == "pending_audit"
    assert all(group == [] for group in found.values())
    assert result["uncited"]
    assert all(item["pages"] == [] and item["page"] is None for item in result["uncited"])
    assert all(item["status"] in {"UNKNOWN", "NEEDS_REVIEW"} for item in result["uncited"])
    assert any(item["block"] == "qualification" and "资格" in item["quote"] for item in result["uncited"])
    assert any(item["block"] == "rejection" for item in result["uncited"])
    assert any(item["block"] == "materials" for item in result["uncited"])
    assert any(item["block"] == "scoring" for item in result["uncited"])
    assert all("没有给出原文页码" in item["uncited_reason"] or "没有可用的原文页码" in item["uncited_reason"] for item in result["uncited"])


def test_scan_response_includes_paged_blocks(monkeypatch):
    client = TestClient(main.app)

    def fake_extract(_path):
        return [
            _page(4, "投标人资格要求：具有软件企业资质，并须提供营业执照。"),
            _page(5, "评分标准：实施方案满分 20 分。"),
        ]

    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    response = client.post("/api/runs", files={"tender": ("tender.txt", "资格要求".encode(), "text/plain")})
    assert response.status_code == 200
    run = response.json()
    blocks = run["tender_blocks"]["blocks"]

    assert run["tender_blocks"]["product_pass"] is False
    assert blocks["qualification"]["items"][0]["pages"] == [4]
    assert blocks["materials"]["items"][0]["page"] == 4
    assert blocks["scoring"]["items"][0]["page"] == 5
    assert run["tender_blocks"]["uncited"] == []
    stored = tender_blocks_for_run({"state": {"tender_blocks": run["tender_blocks"]}})
    assert stored["product_pass"] is False
    client.delete(f"/api/runs/{run['run_id']}")


def test_rejected_response_and_invalid_quote_use_the_pdf_sentences():
    """The six missed 废标 sentences, with the PDF's own line breaks and commas."""
    cases = (
        (
            19,
            (
                "第19 页共66 页\n"
                "供应商有责任检查自身情况,在响应文件中对是否违反以上一般规定做出\n"
                "如实声明,否则其响应文件将被否决。"
            ),
            "供应商有责任检查自身情况,在响应文件中对是否违反以上一般规定做出如实声明,否则其响应文件将被否决。",
        ),
        (
            20,
            (
                "第 20 页 共 66 页\n"
                "(6)如本项目不接受联合体报价而供应商为联合体的,或者本项目接受联\n"
                "合体报价但供应商组成的联合体不符合本章第3.2 条规定的,其报价无效。"
            ),
            "(6)如本项目不接受联合体报价而供应商为联合体的,或者本项目接受联合体报价但供应商组成的联合体不符合本章第3.2 条规定的,其报价无效。",
        ),
        (
            21,
            (
                "7.1 供应商可按照采购包号,对竞争性磋商文件中载明的全部或部分采购包\n"
                "进行响应。对于能够详细列明采购标的技术、服务要求的采购项目,供应商响应\n"
                "时,对同一个采购包内所有的采购内容和要求必须进行完整响应,否则其相应采\n"
                "购包的响应文件将被否决。"
            ),
            "对于能够详细列明采购标的技术、服务要求的采购项目,供应商响应时,对同一个采购包内所有的采购内容和要求必须进行完整响应,否则其相应采购包的响应文件将被否决。",
        ),
        (
            21,
            (
                "7.2 供应商代表在同一个合同项下只能接受一个供应商的委托参加响应磋\n"
                "商,否则其响应文件将被否决。"
            ),
            "7.2 供应商代表在同一个合同项下只能接受一个供应商的委托参加响应磋商,否则其响应文件将被否决。",
        ),
        (
            22,
            (
                "9.1 响应文件有效期见竞争性磋商须知前附表第4 项,响应文件承诺的有效\n"
                "期不得少于磋商文件载明的有效期,否则其响应文件将被否决。"
            ),
            "9.1 响应文件有效期见竞争性磋商须知前附表第4 项,响应文件承诺的有效期不得少于磋商文件载明的有效期,否则其响应文件将被否决。",
        ),
        (
            22,
            (
                "10.2 磋商保证金为响应文件的重要组成部分之一。磋商保证金用于保护本\n"
                "次磋商活动免受供应商的违约或失信行为而引起的风险。未按规定提交磋商保证\n"
                "金的,其响应文件将被否决。"
            ),
            "未按规定提交磋商保证金的,其响应文件将被否决。",
        ),
    )
    footer = re.compile(r"第\s*\d+\s*页\s*共\s*\d+\s*页")
    for page, source, sentence in cases:
        result = extract_tender_blocks([_page(page, source)], filename="pub-gl-fzsc339.pdf")
        found = _blocks(result)
        matched = [item for item in found["rejection"] if sentence in item["quote"]]

        assert len(matched) == 1
        assert matched[0]["page"] == page
        assert matched[0]["pages"] == [page]
        assert matched[0]["status"] == "NEEDS_REVIEW"
        assert matched[0]["status"] != "PASS"
        assert footer.search(matched[0]["quote"]) is None
        assert result["product_pass"] is False
        assert result["audit_status"] == "pending_audit"
        assert all(item["status"] == "NEEDS_REVIEW" for group in found.values() for item in group)


def test_page_footer_inside_a_wrapped_sentence_is_not_kept():
    pages = [
        _page(
            22,
            "未按规定提交磋商保证\n第22 页共66 页\n金的,其响应文件将被否决。",
        )
    ]
    rejection = _blocks(extract_tender_blocks(pages, filename="footer.pdf"))["rejection"]

    assert len(rejection) == 1
    assert rejection[0]["quote"] == "未按规定提交磋商保证金的,其响应文件将被否决。"
    assert "页" not in rejection[0]["quote"]
    assert rejection[0]["page"] == 22
    assert rejection[0]["status"] == "NEEDS_REVIEW"


def test_complaint_rules_and_deposit_forfeit_are_not_rejection_or_materials():
    pages = [
        _page(
            22,
            "10.4 如果供应商发生以下任何一种情况时,其磋商保证金将被不予退还或\n"
            "通过保函进行索赔:\n"
            "(1)供应商在提交响应文件截止时间后撤回响应文件的;\n"
            "(2)供应商在响应文件中提供虚假材料的;",
        ),
        _page(
            28,
            "2所质疑项目的基本信息,至少包括:项目编号、项目名称等;\n"
            "3所质疑的具体事项(以下简称:“质疑事项”);\n"
            "4质疑人自身权益受到损害的事实依据和证明材料,至少包括:\n"
            "备注:若证据无法有效表明信息或证明材料为合法或公开渠道获得,则前述信息或证明材料视为无效。\n"
            "5针对质疑事项提出的明确请求和法律依据,如:暂停采购活动、修改磋商文件、成交结果无效、废标、重新采购等。",
        ),
        _page(22, "未按规定提交磋商保证金的,其响应文件将被否决。"),
    ]
    found = _blocks(extract_tender_blocks(pages, filename="procedure.pdf"))
    kept = _quotes(found["rejection"] + found["materials"] + found["qualification"] + found["scoring"])

    assert "虚假材料" not in kept
    assert "保证金将被不予退还" not in kept
    assert "通过保函进行索赔" not in kept
    assert "质疑事项" not in kept
    assert "视为无效" not in kept
    assert "废标、重新采购" not in kept
    assert any("其响应文件将被否决" in item["quote"] and item["page"] == 22 for item in found["rejection"])
    assert all(item["status"] == "NEEDS_REVIEW" for group in found.values() for item in group)


def test_invalid_response_stays_rejection_when_it_also_mentions_a_deposit_claim():
    pages = [
        _page(
            18,
            "5.1.3 若供应商有任何试图干扰具体评审事务,影响磋商小组独立履行职责的行为,其响应无效且不予退还磋商保证金或通过保函进行索赔。",
        )
    ]
    found = _blocks(extract_tender_blocks(pages, filename="claim.pdf"))

    assert len(found["rejection"]) == 1
    assert "其响应无效" in found["rejection"][0]["quote"]
    assert found["rejection"][0]["page"] == 18
    assert found["rejection"][0]["status"] == "NEEDS_REVIEW"
    assert found["materials"] == []


def test_pdf_participation_limits_and_refused_file_keep_their_pages():
    """Three missed sentences from the Gulou PDF, on the page where each one starts."""
    cases = (
        (
            19,
            "qualification",
            (
                "3.1.2 为采购项目提供整体设计、规范编制或项目管理、监理、检测等服务\n"
                "的供应商,不得再参加该采购项目除整体设计、规范编制和项目管理、监理、检\n"
                "测等服务之外的其他采购活动。"
            ),
            "3.1.2 为采购项目提供整体设计、规范编制或项目管理、监理、检测等服务的供应商,不得再参加该采购项目除整体设计、规范编制和项目管理、监理、检测等服务之外的其他采购活动。",
        ),
        (
            20,
            "qualification",
            (
                "(2)联合体各方不得再单独参加或与其他供应商另外组成联合体参加同一\n"
                "合同项下的响应磋商。"
            ),
            "(2)联合体各方不得再单独参加或与其他供应商另外组成联合体参加同一合同项下的响应磋商。",
        ),
        (
            23,
            "rejection",
            (
                "12.2 供应商应当在磋商文件规定的提交响应文件截止时间前,将首次响应\n"
                "文件密封送达磋商文件规定的指定地点。在截止时间后送达的首次响应文件为无\n"
                "效文件,采购人、采购代理机构或者磋商小组将不予接收。"
            ),
            "在截止时间后送达的首次响应文件为无效文件,采购人、采购代理机构或者磋商小组将不予接收。",
        ),
    )
    for page, block, source, sentence in cases:
        result = extract_tender_blocks([_page(page, source)], filename="pub-gl-fzsc339.pdf")
        found = _blocks(result)
        matched = [item for item in found[block] if sentence in item["quote"]]

        assert len(matched) == 1
        assert matched[0]["page"] == page
        assert matched[0]["pages"] == [page]
        assert matched[0]["status"] == "NEEDS_REVIEW"
        assert result["product_pass"] is False
        assert result["audit_status"] == "pending_audit"
    designer = _blocks(
        extract_tender_blocks(
            [_page(19, cases[0][2])],
            filename="pub-gl-fzsc339.pdf",
        )
    )
    assert designer["rejection"] == []
    consortium = _blocks(
        extract_tender_blocks(
            [_page(20, cases[1][2])],
            filename="pub-gl-fzsc339.pdf",
        )
    )
    assert consortium["rejection"] == []


def test_participation_document_refusal_and_refund_timing_are_categories():
    pages = [
        _page(3, "为本项目编制规范的单位,不得再参加该项目的施工投标。"),
        _page(4, "联合体成员不得与其他投标人另行组成联合体。"),
        _page(5, "逾期递交的投标文件,招标人将拒收该投标文件。"),
        _page(6, "合同履行中,买方可以拒收不合格货物,并要求更换。"),
        _page(7, "未成交供应商的投标保证金,在中标通知书发出后5个工作日内退还。"),
        _page(8, "投标人须提交投标保证金凭证复印件。"),
        _page(9, "供应商提出质疑后,该投标文件仍按投标无效处理。"),
        _page(10, "投标人须提供近三年无重大投诉记录的书面声明并加盖公章。"),
    ]
    found = _blocks(extract_tender_blocks(pages, filename="categories.pdf"))

    assert any(item["page"] == 3 and "不得再参加" in item["quote"] for item in found["qualification"])
    assert all("施工投标" not in item["quote"] for item in found["rejection"])
    assert any(item["page"] == 4 and "组成联合体" in item["quote"] for item in found["qualification"])
    assert any(item["page"] == 5 and "拒收该投标文件" in item["quote"] for item in found["rejection"])
    assert all("不合格货物" not in item["quote"] for item in found["rejection"])
    assert all("工作日内退还" not in item["quote"] for item in found["materials"])
    assert any(item["page"] == 8 and "复印件" in item["quote"] for item in found["materials"])
    assert any(item["page"] == 9 and "投标无效" in item["quote"] for item in found["rejection"])
    assert any(item["page"] == 10 and "无重大投诉" in item["quote"] for item in found["materials"])
    assert all(item["status"] == "NEEDS_REVIEW" for group in found.values() for item in group)


def test_deposit_refund_timing_from_the_pdf_is_not_a_material():
    pages = [
        _page(
            22,
            "10.3.1 采购人或者采购代理机构将在采购活动结束后及时退还供应商的保证金,"
            "但因供应商自身原因导致无法及时退还的除外"
            "(比如:成交的供应商未向采购代理机构出具已签订合同证明材料)。"
            "未成交供应商的保证金将在成交通知书发出后5 个工作日内退还。",
        )
    ]
    found = _blocks(extract_tender_blocks(pages, filename="refund.pdf"))

    assert found["materials"] == []
    assert found["rejection"] == []
    assert all(item["status"] == "NEEDS_REVIEW" for group in found.values() for item in group)


def test_pdf_page_label_and_printed_offset_come_from_the_footer():
    pages = [
        _page(
            5,
            "二、申请人的资格要求：\n1.满足《中华人民共和国政府采购法》第二十二条的规定。\n第 2 页/共 8 页",
        ),
        _page(6, "有下列情形之一的，应予以废标：\n（1）符合专业条件的供应商不足3家的。"),
    ]
    result = extract_tender_blocks(pages, filename="offset.pdf")
    found = _blocks(result)
    qualification = found["qualification"][0]
    rejection = found["rejection"][0]

    assert qualification["page"] == 5
    assert qualification["locator"]["label"] == "PDF 第5页"
    assert qualification["printed_page"] == 2
    assert rejection["locator"]["label"] == "PDF 第6页"
    assert rejection["printed_page"] is None
    assert result["printed_page_offset"] == 3
    assert result["printed_page_total"] == 8
    assert result["product_pass"] is False
    stored = tender_blocks_for_run({"state": {"tender_blocks": result}})
    assert stored["printed_page_offset"] == 3
    assert stored["blocks"]["qualification"]["items"][0]["locator"]["label"] == "PDF 第5页"
    assert stored["blocks"]["rejection"]["items"][0]["printed_page"] is None

    conflicting = extract_tender_blocks(
        [
            _page(1, "投标人资格要求：具有市政公用工程施工总承包资质。\n第 1 页/共 4 页"),
            _page(2, "投标人资格要求：具有建筑工程施工总承包资质。\n第 9 页/共 4 页"),
        ],
        filename="conflict.pdf",
    )
    assert conflicting["printed_page_offset"] is None
    quoted = _blocks(conflicting)["qualification"]
    assert {item["printed_page"] for item in quoted} == {1, 9}


def test_slash_footer_is_stripped_from_the_clause():
    pages = [
        _page(8, "未按招标文件要求签字盖章的，投\n第 6 页 / 共 30 页\n标无效。"),
    ]
    rejection = _blocks(extract_tender_blocks(pages, filename="slash.pdf"))["rejection"]

    assert len(rejection) == 1
    assert rejection[0]["quote"] == "未按招标文件要求签字盖章的，投标无效。"
    assert "页" not in rejection[0]["quote"]
    assert rejection[0]["page"] == 8
    assert rejection[0]["printed_page"] == 6
    assert rejection[0]["locator"]["label"] == "PDF 第8页"


def test_scoring_needs_a_score_context_and_a_subject():
    pages = [
        _page(2, "开标时间为当日14点00分，请投标人准时出席。"),
        _page(3, "本项目分为两个分包，分部分项工程量清单另行提供。"),
        _page(4, "得3分。\n满分10分。\n扣5分。"),
        _page(5, "售后响应方案每缩短1小时得2分，满分10分。"),
    ]
    found = _blocks(extract_tender_blocks(pages, filename="scores.pdf"))
    quotes = _quotes(found["scoring"] + found["qualification"] + found["materials"] + found["rejection"])

    assert len(found["scoring"]) == 1
    assert found["scoring"][0]["page"] == 5
    assert "售后响应方案" in found["scoring"][0]["quote"]
    assert "14点00分" not in quotes
    assert "分包" not in quotes
    assert "分部分项" not in quotes
    assert "得3分" not in quotes
    fragments = {item["quote"] for group in found.values() for item in group}
    assert "满分10分。" not in fragments
    assert "扣5分。" not in fragments
    assert all(item["status"] == "NEEDS_REVIEW" for item in found["scoring"])


def test_definition_notes_and_non_response_invalidity_stay_out_of_rejection():
    pages = [
        _page(
            3,
            "有下列情形之一的，应予以废标：\n（1）投标人不足3家的。\n注：“有效”是指证书载明的有效期尚未届满。",
        ),
        _page(4, "采购人在其他渠道散发的非正式资料作无效处理。"),
        _page(5, "未经采购人网上发布或书面通知的内容，均作无效处理。"),
        _page(6, "因包装不当造成的后果，包括拒收、误放或遗漏，由投标人自行承担。"),
        _page(7, "逾期送达的投标文件，招标人将拒收该投标文件。"),
        _page(
            9,
            "",
            tables=[{"header": ["评审内容", "品牌要求"], "rows": [["设备", "指定品牌的投标无效这一说法不适用于本表"]]}],
        ),
    ]
    found = _blocks(extract_tender_blocks(pages, filename="keep-out.pdf"))
    quotes = _quotes(found["rejection"])

    assert "不足3家" in quotes
    assert any("将拒收该投标文件" in item["quote"] and item["page"] == 7 for item in found["rejection"])
    assert "有效期尚未届满" not in quotes
    assert "非正式资料" not in quotes
    assert "书面通知" not in quotes
    assert "自行承担" not in quotes
    assert "指定品牌" not in quotes
    assert all(item["status"] == "NEEDS_REVIEW" for item in found["rejection"])


def test_participation_limit_is_only_for_this_procurement():
    pages = [
        _page(2, "为本项目编制招标文件的单位，不得再参加本次采购的施工投标。"),
        _page(3, "合同履行期间，成交人不得参加与本项目无关的其他竞争性活动。"),
        _page(4, "中标后，中标人不得参加合同约定以外的分包。"),
    ]
    found = _blocks(extract_tender_blocks(pages, filename="who-may-bid.pdf"))

    assert any(item["page"] == 2 and "本次采购" in item["quote"] for item in found["qualification"])
    assert all("合同履行" not in item["quote"] for item in found["qualification"])
    assert all("中标后" not in item["quote"] for item in found["qualification"])
    assert all(item["page"] != 3 for item in found["rejection"])
    assert all(item["status"] == "NEEDS_REVIEW" for group in found.values() for item in group)


def test_a_bare_score_does_not_take_a_running_header_as_its_subject():
    header = "磋商文件示范文本页眉"
    pages = [
        _page(1, f"{header}\n第 1 页/共 3 页\n供应商须提交营业执照复印件。"),
        _page(2, f"{header}\n第 2 页/共 3 页\n(1)计划详细且针对本工程的,"),
        _page(3, f"{header}\n第 3 页/共 3 页\n得5 分;"),
    ]
    found = _blocks(extract_tender_blocks(pages, filename="banner.pdf"))
    quotes = _quotes(found["scoring"] + found["materials"] + found["qualification"] + found["rejection"])

    assert any("计划详细且针对本工程" in item["quote"] and "得5" in item["quote"] for item in found["scoring"])
    assert all(header not in item["quote"] for item in found["scoring"])
    assert "页眉" not in quotes
    assert all(item["status"] == "NEEDS_REVIEW" for item in found["scoring"])


def test_rejecting_the_quote_is_a_rejection_item():
    pages = [_page(11, "未响应实质性要求的，评审委员会将否决其报价。")]
    rejection = _blocks(extract_tender_blocks(pages, filename="quote.pdf"))["rejection"]

    assert len(rejection) == 1
    assert "否决其报价" in rejection[0]["quote"]
    assert rejection[0]["page"] == 11
    assert rejection[0]["locator"]["label"] == "PDF 第11页"
    assert rejection[0]["status"] == "NEEDS_REVIEW"
    assert rejection[0]["printed_page"] is None
