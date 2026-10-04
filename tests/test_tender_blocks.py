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
    assert rejection[0]["locator"]["label"] == "第 3-4 页"


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
