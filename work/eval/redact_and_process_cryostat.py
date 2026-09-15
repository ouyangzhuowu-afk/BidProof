"""Offline DOCX redaction for hospital / medical-device tenders.

No network calls. Writes only under work/eval/meddevice-redacted/ (safe to share)
and keeps the raw copy under work/uploads/_incoming-private/ (gitignored).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "work" / "uploads" / "_incoming-private"
OUT = ROOT / "work" / "eval" / "meddevice-redacted"

# Longer keys first so overlapping replacements stay stable.
REDACTION_MAP: list[tuple[str, str]] = [
    ("湖南晟美达工程管理咨询有限公司", "[代理机构A]"),
    ("到湖南晟美达工程管理咨询有限公司", "到[代理机构A]"),
    ("岳阳市中医医院病理科冷冻切片机采购项目", "[医院A]病理科冷冻切片机采购项目"),
    ("岳阳市中医医院", "[医院A]"),
    ("湖南省岳阳市岳阳楼区金鹗山街道万家坡社区原恒立公司办公楼三楼", "[代理地址A]"),
    ("岳阳楼区金鹗山街道万家坡社区原恒立公司办公楼三楼", "[代理地址A]"),
    ("岳阳市枫桥湖路269号", "[采购人地址A]"),
    ("枫桥湖路269号", "[采购人地址A]"),
    ("枫桥湖路", "[采购人地址A]"),
    ("枫桥湖", "[采购人地址A]"),
    # OOXML often splits runs: 「枫」+「桥湖路269号」
    ("桥湖路269号", "[采购人地址A]"),
    ("桥湖路", "[采购人地址A]"),
    ("SMD-CG-202549", "REDACTED-CG-0001"),
    ("http:/www.yyszyyy.com", "http://example.invalid/hospital-a"),
    ("www.yyszyyy.com", "example.invalid/hospital-a"),
    ("0730-8831781", "0000-0000000"),
    ("0730-8908399", "0000-0000001"),
    ("沈女士", "[联系人甲]"),
    ("陈先生", "[联系人乙]"),
    ("岳阳市", "[某市]"),
    ("湖南省", "[某省]"),
]


def _replace_all(text: str) -> str:
    out = text
    for src, dst in sorted(REDACTION_MAP, key=lambda pair: len(pair[0]), reverse=True):
        out = out.replace(src, dst)
    # Residual landline patterns that look local (0730-xxxxxxx) after known map.
    out = re.sub(r"0\d{2,3}-?\d{7,8}", "0000-0000000", out)
    return out


def redact_docx(src: Path, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    replaced_files = 0
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(info, data)
                    continue
                new_text = _replace_all(text)
                if new_text != text:
                    replaced_files += 1
                zout.writestr(info, new_text.encode("utf-8"))
            else:
                zout.writestr(info, data)
    return {
        "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "dest_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "xml_files_changed": replaced_files,
        "dest": str(dest.relative_to(ROOT)).replace("\\", "/"),
    }


def residual_scan(text: str) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    checks = {
        "phone": r"(?<!0000-)0\d{2,3}-?\d{7,8}|1[3-9]\d{9}",
        "hospital_leak": r"岳阳|晟美达|沈女士|陈先生|枫桥湖|桥湖路|金鹗山|yyszyyy|SMD-CG",
        "idcard": r"\d{17}[\dXx]",
    }
    for name, pat in checks.items():
        hits = sorted(set(re.findall(pat, text)))
        # Ignore intentional placeholders.
        hits = [h for h in hits if not h.startswith("0000-")]
        if hits:
            findings[name] = hits[:20]
    return findings


def main() -> None:
    raw = PRIVATE / "raw-cryostat-consult.docx"
    if not raw.exists():
        raise SystemExit(f"missing raw file: {raw}")

    OUT.mkdir(parents=True, exist_ok=True)
    redacted_docx = OUT / "consult-cryostat-redacted.docx"
    meta = redact_docx(raw, redacted_docx)

    # Local extract only — never enable cloud OCR for this corpus.
    from app.extraction import extract_ooxml
    from app.ocr import DisabledOCRAdapter, get_ocr_adapter
    from app.rules import extract_requirements

    assert isinstance(get_ocr_adapter(), DisabledOCRAdapter) or not get_ocr_adapter().enabled

    pages = extract_ooxml(redacted_docx)
    text = "\n".join(page["text"] for page in pages)
    (OUT / "consult-cryostat-redacted.txt").write_text(text, encoding="utf-8")
    residuals = residual_scan(text)
    requirements = extract_requirements(pages)
    categories: dict[str, int] = {}
    labels: dict[str, int] = {}
    for item in requirements:
        categories[item["category"]] = categories.get(item["category"], 0) + 1
        labels[item["label"]] = labels.get(item["label"], 0) + 1

    report = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "egress": "disabled",
        "ocr_provider": "disabled",
        "note": "Source was a hospital competitive-consultation tender for a cryostat (冷冻切片机), not a supplier bid-response. Processed offline after redaction.",
        "redaction": meta,
        "units": len(pages),
        "chars": len(text),
        "residual_findings": residuals,
        "requirement_count": len(requirements),
        "categories": categories,
        "labels": labels,
        "sample_requirements": [
            {
                "requirement_id": item["requirement_id"],
                "label": item["label"],
                "category": item["category"],
                "page": item["source"]["page"],
                "quote": item["source"]["quote"][:180],
            }
            for item in requirements[:12]
        ],
        "key_field_hits": {
            "device_license_clause": "医疗器械经营许可证" in text or "医疗器械注册证" in text,
            "budget_present": "万元" in text,
            "deadline_present": "截止" in text,
            "no_bond": "不缴纳" in text and "保证金" in text,
        },
    }
    (OUT / "process-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Redacted hospital cryostat consultation — offline process",
        "",
        f"- Generated: `{report['generated_at']}`",
        "- Egress / OCR: **disabled** (customer: no outbound)",
        f"- Redacted DOCX: `{meta['dest']}`",
        f"- Units / chars: {report['units']} / {report['chars']}",
        f"- Requirements extracted: **{report['requirement_count']}**",
        f"- Residual PII scan: `{residuals or 'clean'}`",
        "",
        "## Categories",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for key, value in sorted(categories.items()):
        md.append(f"| {key} | {value} |")
    md += [
        "",
        "## Labels",
        "",
        "| Label | Count |",
        "|---|---:|",
    ]
    for key, value in sorted(labels.items()):
        md.append(f"| {key} | {value} |")
    md += [
        "",
        "## Key field checks",
        "",
        "```json",
        json.dumps(report["key_field_hits"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Sample requirements (redacted quotes only)",
        "",
    ]
    for item in report["sample_requirements"]:
        md.append(
            f"- `{item['requirement_id']}` [{item['category']}/{item['label']}] "
            f"unit={item['page']}: {item['quote']}"
        )
    md += [
        "",
        "## Redaction map (placeholders)",
        "",
        "| Original class | Placeholder |",
        "|---|---|",
        "| Hospital name | `[医院A]` |",
        "| Agency | `[代理机构A]` |",
        "| Contacts | `[联系人甲/乙]` |",
        "| Phones / addresses | `0000-…` / `[采购人地址A]` / `[代理地址A]` |",
        "| Agency project id | `REDACTED-CG-0001` |",
        "",
        "Raw WeChat temp file and `work/uploads/_incoming-private/raw-*` must not be committed.",
        "",
    ]
    (OUT / "PROCESS_REPORT.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"ok": True, "requirements": len(requirements), "residuals": residuals, "out": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
