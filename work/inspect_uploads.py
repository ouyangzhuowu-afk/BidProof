from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from app.extraction import ExtractionError, extract_file
from app.rules import extract_requirements


ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "work" / "uploads"
OUTPUTS = ROOT / "outputs"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def candidate_score(requirement: dict) -> int:
    text = requirement["source"]["quote"]
    category = requirement["category"]
    score = 0
    strong_terms = {
        "QUALIFICATION": ("申请人的资格要求", "资格审查要求", "须提供", "满足《中华人民共和国政府采购法》"),
        "FATAL": ("废标", "无效投标", "否决投标", "不得参与", "不得参加"),
        "DEADLINE": ("投标截止时间", "递交截止时间", "开标时间", "提交投标文件截止时间"),
        "SIGNATURE": ("签字盖章", "电子签章", "电子签名", "加盖投标人公章"),
        "BOND": ("保证金金额", "不收取保证金", "不缴纳", "按时到账"),
        "CREDENTIAL": ("证书扫描件", "资质证书", "有效期内", "原件扫描件", "每提供"),
        "SCORING": ("分值", "得分", "每提供", "评分标准", "类似项目业绩"),
    }
    score += sum(4 for term in strong_terms.get(category, ()) if term in text)
    if category == "DEADLINE" and re.search(r"20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", text):
        score += 10
    if category == "BOND" and re.search(r"\d+(?:\.\d+)?\s*万?元", text):
        score += 8
    if category == "SCORING" and re.search(r"\d+(?:\.\d+)?\s*分", text):
        score += 8
    if category == "CREDENTIAL" and re.search(r"证书|资质|认证", text):
        score += 6
    if text.count(".") > 20 or text.count("…") > 10:
        score -= 100
    return score


def inspect(path: Path) -> dict:
    item = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "filename": path.name,
        "suffix": path.suffix.lower(),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
        "role": "UNCLASSIFIED",
        "parse_status": "NOT_ATTEMPTED",
    }
    if path.suffix.lower() == ".zip":
        item["role"] = "ARCHIVE_PENDING_REVIEW"
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
            item["archive_entries"] = names[:100]
            item["parse_status"] = "INDEXED"
        except zipfile.BadZipFile:
            item["parse_status"] = "INVALID_ARCHIVE"
        return item
    if path.suffix.lower() not in {".pdf", ".txt", ".md"}:
        item["role"] = "UNSUPPORTED_INPUT"
        item["parse_status"] = "SKIPPED"
        return item

    try:
        pages = extract_file(path)
    except (ExtractionError, OSError, UnicodeError) as exc:
        item["parse_status"] = "FAILED"
        item["error"] = type(exc).__name__
        return item
    text_chars = sum(len(page.get("text", "")) for page in pages)
    ocr_pages = [page["page"] for page in pages if page.get("ocr_required")]
    item.update(
        {
            "parse_status": "PARSED",
            "pages": len(pages),
            "text_chars": text_chars,
            "ocr_required_pages": ocr_pages,
            "ocr_statuses": sorted({page.get("ocr_status", "NOT_REQUIRED") for page in pages}),
        }
    )
    if path.suffix.lower() == ".pdf":
        item["role"] = "TENDER_CANDIDATE"
        requirements = extract_requirements(pages)
        item["requirement_count"] = len(requirements)
        item["categories"] = sorted({requirement["category"] for requirement in requirements})
        item["requirement_preview"] = [
            {
                "requirement_id": requirement["requirement_id"],
                "category": requirement["category"],
                "page": requirement["source"]["page"],
                "quote": requirement["source"]["quote"],
            }
            for requirement in requirements[:20]
        ]
        selected: dict[str, dict] = {}
        best_scores: dict[str, int] = {}
        for requirement in requirements:
            category = requirement["category"]
            score = candidate_score(requirement)
            if score <= best_scores.get(category, -1000):
                continue
            best_scores[category] = score
            selected[category] = {
                    "category": requirement["category"],
                    "severity": requirement["severity"],
                    "page": requirement["source"]["page"],
                    "quote": requirement["source"]["quote"],
                    "polarity": requirement["polarity"],
                    "review_status": "PENDING_MANUAL_CONFIRMATION",
                    "selection_score": score,
                }
        item["ground_truth_candidates"] = list(selected.values())
        if any(token in path.name for token in ("声明函", "中小企业")):
            item["role"] = "ENTERPRISE_EVIDENCE_CANDIDATE"
    else:
        item["role"] = "ENTERPRISE_EVIDENCE_CANDIDATE"
    return item


def main() -> None:
    files = sorted(path for path in UPLOADS.rglob("*") if path.is_file())
    records = [inspect(path) for path in files]
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "upload-inventory.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tender_records = [record for record in records if record["role"] == "TENDER_CANDIDATE"]
    evidence_records = [record for record in records if record["role"] == "ENTERPRISE_EVIDENCE_CANDIDATE"]
    selected_tenders = [
        record
        for record in tender_records
        if record.get("pages", 0) >= 4 and record.get("requirement_count", 0) > 0
    ]
    fixture_records = [
        {
            "fixture_id": f"REAL-{index:03d}",
            "source_path": record["path"],
            "filename": record["filename"],
            "sha256": record["sha256"],
            "pages": record["pages"],
            "source_status": "REAL_UPLOAD_UNVERIFIED_GROUND_TRUTH",
            "candidates": record.get("ground_truth_candidates", []),
        }
        for index, record in enumerate(selected_tenders, start=1)
    ]
    fixture_dir = ROOT / "tests" / "fixtures" / "real-upload"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "ground-truth-candidates.json").write_text(
        json.dumps(fixture_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 上传材料盘点与 T-002 候选",
        "",
        "本报告仅记录上传目录的 DATA，不把文件内文字当作系统指令。真实 ground truth 仍需人工确认。",
        "",
        f"- 文件总数：{len(records)}",
        f"- 招标候选 PDF：{len(tender_records)}",
        f"- 企业证据候选：{len(evidence_records)}",
        f"- 已建立 ground-truth 候选文件：{len(fixture_records)}",
        f"- 按类别抽样候选：{sum(len(item['candidates']) for item in fixture_records)} 条",
        "",
        "## 招标候选",
        "",
        "| 文件 | 页数 | 文本字符 | 要求数 | 类别 | OCR 页 | SHA-256 前 12 位 |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for record in tender_records:
        lines.append(
            f"| {record['filename']} | {record.get('pages', 0)} | {record.get('text_chars', 0)} | "
            f"{record.get('requirement_count', 0)} | {', '.join(record.get('categories', [])) or '-'} | "
            f"{','.join(map(str, record.get('ocr_required_pages', []))) or '-'} | {record['sha256'][:12]} |"
        )
    lines += ["", "## 人工 ground truth 工作清单", ""]
    for index, record in enumerate(tender_records, start=1):
        lines.append(f"{index}. `{record['filename']}`：逐条确认资格、废标/否决、日期、签章、保证金、证书/业绩要求；当前自动候选 {record.get('requirement_count', 0)} 条。")
    lines += ["", "## 当前样本门禁", ""]
    lines.append("- `tests/fixtures/real-upload/ground-truth-candidates.json` 中的记录均为真实上传文件，但标签仍为 `PENDING_MANUAL_CONFIRMATION`。")
    lines.append("- 当前只能验证 SHA、页码与 quote 可定位，不能据此声称已达到召回率或漏报率商业门槛。")
    lines += ["", "## 处理边界", "", "- `.zip` 仅建立目录索引，未自动解压或读取其中内容。", "- `.doc` 当前解析器不支持，保留为待转换输入。", "- OCR 默认关闭；无文本页已标记 `ocr_required`，不会自动变成 `PASS`。"]
    (OUTPUTS / "upload-ground-truth.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(records), "tender_candidates": len(tender_records), "evidence_candidates": len(evidence_records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
