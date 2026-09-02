import re
from typing import Any


REQUIREMENT_PATTERNS: list[tuple[str, str, str]] = [
    ("资格条件", "QUALIFICATION", r"资格条件|资格要求|投标人资格|供应商资格"),
    ("废标/否决", "FATAL", r"废标|否决投标|无效投标|不得参与|一票否决"),
    ("评分项", "SCORING", r"评分标准|评分办法|评审因素|技术评分|商务评分"),
    ("关键日期", "DEADLINE", r"投标截止|开标时间|递交截止|提交截止|响应文件递交"),
    ("签章要求", "SIGNATURE", r"签字盖章|签章|电子签章|法定代表人"),
    ("保证金", "BOND", r"投标保证金|履约保证金|保函"),
    ("证书/业绩", "CREDENTIAL", r"资质证书|认证证书|类似业绩|项目经验|人员证书"),
]

EVIDENCE_CATEGORIES = {"QUALIFICATION", "SIGNATURE", "BOND", "CREDENTIAL"}


def _snippet(text: str, start: int, end: int, radius: int = 110) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].split())


def extract_requirements(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    counter = 1
    for page in pages:
        text = page["text"]
        if not text.strip():
            continue
        for label, category, pattern in REQUIREMENT_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                snippet = _snippet(text, match.start(), match.end())
                locator = dict(page.get("locator", {"kind": "page", "label": f"第 {page['page']} 页", "index": page["page"]}))
                block_hit = next((
                    block for block in page.get("blocks", [])
                    if block.get("locator") and block.get("text")
                    and match.group(0) in block["text"]
                ), None)
                if block_hit:
                    locator = block_hit["locator"]
                requirements.append(
                    {
                        "requirement_id": f"REQ-{counter:04d}",
                        "label": label,
                        "category": category,
                        "title": snippet[:160],
                        "source": {
                            "source_id": page.get("source_id", "TENDER-001"),
                            "page": page["page"],
                            "locator": locator,
                            "quote": snippet,
                        },
                        "evidence": [],
                        "status": "NEEDS_REVIEW",
                        "severity": "HIGH" if category in {"FATAL", "QUALIFICATION"} else "MEDIUM",
                        "criticality": "HARD" if category in {"QUALIFICATION", "FATAL", "DEADLINE", "SIGNATURE", "BOND", "CREDENTIAL"} else "SOFT",
                        "detection_method": "deterministic_keyword",
                        "polarity": _polarity(snippet),
                        "confidence": None,
                        "rule_score": 1,
                        "rule_score_kind": "HEURISTIC_MATCH_COUNT",
                        "confidence_kind": "UN_CALIBRATED_HEURISTIC",
                    }
                )
                counter += 1
    return _deduplicate(requirements)


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, int]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (item["category"], item["source"]["quote"], item["source"]["page"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def match_evidence(
    requirements: list[dict[str, Any]],
    evidence_pages: list[dict[str, Any]],
    evidence_name: str | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    eligible_pages = [page for page in evidence_pages if page.get("ocr_status") != "FAILED"]
    all_text = "\n".join(page["text"] for page in eligible_pages)
    compact = re.sub(r"\s+", "", all_text).lower()
    for requirement in requirements:
        if requirement["category"] not in EVIDENCE_CATEGORIES:
            continue
        terms = _terms_for(requirement)
        hits = [term for term in terms if term in compact]
        if not hits:
            requirement["status"] = "UNKNOWN"
            continue
        page_hit = next((p for p in eligible_pages if any(term in re.sub(r"\s+", "", p["text"]).lower() for term in terms)), None)
        if page_hit is None:
            requirement["status"] = "UNKNOWN"
            continue
        block_hit = next((
            block for block in page_hit.get("blocks", [])
            if block.get("text") and any(term in re.sub(r"\s+", "", block["text"]).lower() for term in terms)
        ), None)
        filename = page_hit.get("source_filename")
        if not filename:
            filename = evidence_name if isinstance(evidence_name, str) else evidence_name[0].get("filename", "evidence")
        requirement["evidence"].append(
            {
                "filename": filename,
                "page": page_hit["page"],
                "locator": (block_hit or {}).get("locator") or page_hit.get("locator", {"kind": "page", "label": f"第 {page_hit['page']} 页", "index": page_hit["page"]}),
                "quote": " ".join(((block_hit or {}).get("text") or page_hit["text"]).split())[:240],
                "matched_terms": hits,
                "match_method": "normalized_keyword",
            }
        )
        requirement["status"] = "NEEDS_REVIEW"
        requirement["suggested_status"] = "PASS"
        requirement["match_review_status"] = "PENDING"
        requirement["confidence"] = None
        requirement["rule_score"] = len(hits)
        requirement["rule_score_kind"] = "HEURISTIC_MATCH_COUNT"
        requirement["confidence_kind"] = "UN_CALIBRATED_HEURISTIC"
    return requirements


def _terms_for(requirement: dict[str, Any]) -> list[str]:
    text = requirement["title"]
    terms = [t.lower() for t in re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z]{3,}", text)]
    category_terms = {
        "QUALIFICATION": ["营业执照", "资格", "供应商"],
        "FATAL": ["废标", "否决", "无效"],
        "SCORING": ["评分", "业绩"],
        "DEADLINE": ["截止", "开标", "递交"],
        "SIGNATURE": ["签章", "盖章", "法定代表人"],
        "BOND": ["保证金", "保函"],
        "CREDENTIAL": ["证书", "资质", "业绩"],
    }
    return list(dict.fromkeys(terms + [x.lower() for x in category_terms.get(requirement["category"], [])]))


def _polarity(text: str) -> str:
    if re.search(r"不得|禁止|无效|否决|不符合|未提供|缺少", text):
        return "NEGATIVE_OR_EXCLUSION"
    if re.search(r"必须|须|应当|要求|提供", text):
        return "OBLIGATION"
    return "NEUTRAL"
