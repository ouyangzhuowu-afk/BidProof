from app.rules import extract_requirements, match_evidence


def test_extracts_page_cited_fatal_and_deadline_requirements():
    pages = [{"page": 3, "text": "投标人资格要求：具有软件企业资质。出现以下情形的，否决投标。投标截止时间：2026年9月1日。"}]
    requirements = extract_requirements(pages)
    assert any(item["category"] == "QUALIFICATION" and item["source"]["page"] == 3 for item in requirements)
    assert any(item["category"] == "FATAL" for item in requirements)
    assert any(item["category"] == "DEADLINE" for item in requirements)
    assert all(item["status"] == "NEEDS_REVIEW" for item in requirements)


def test_matched_evidence_stays_reviewable_and_keeps_page_citation():
    tender = [{"page": 2, "text": "投标保证金须提供保函。"}]
    requirements = extract_requirements(tender)
    matched = match_evidence(requirements, [{"page": 1, "text": "本公司已提供银行保函，金额符合要求。"}], "evidence.txt")
    bond = next(item for item in matched if item["category"] == "BOND")
    assert bond["status"] == "NEEDS_REVIEW"
    assert bond["suggested_status"] == "PASS"
    assert bond["source"]["page"] == 2
    assert bond["evidence"][0]["page"] == 1


def test_missing_evidence_fails_closed():
    requirements = extract_requirements([{ "page": 1, "text": "资格要求：提供营业执照。" }])
    matched = match_evidence(requirements, [{"page": 1, "text": "项目团队简介。"}], "evidence.txt")
    assert matched[0]["status"] == "UNKNOWN"


def test_non_evidence_requirements_remain_for_human_review():
    requirements = extract_requirements([{ "page": 1, "text": "投标截止时间：2026年9月1日。出现无效投标情形的，否决投标。" }])
    matched = match_evidence(requirements, [{"page": 1, "text": "本公司材料中提到投标截止和否决。"}], "evidence.txt")
    assert all(item["status"] == "NEEDS_REVIEW" for item in matched)


def test_match_uses_the_page_source_filename_for_multiple_evidence_files():
    requirements = extract_requirements([{ "page": 1, "text": "资格要求：提供软件企业资质证书。" }])
    matched = match_evidence(
        requirements,
        [
            {"page": 1, "text": "项目简介。", "source_filename": "profile.txt"},
            {"page": 2, "text": "软件企业资质证书编号 ABC。", "source_filename": "certificates.pdf"},
        ],
        [{"filename": "profile.txt"}, {"filename": "certificates.pdf"}],
    )
    assert matched[0]["status"] == "NEEDS_REVIEW"
    assert matched[0]["suggested_status"] == "PASS"
    assert matched[0]["evidence"][0]["filename"] == "certificates.pdf"


def test_failed_ocr_page_cannot_create_pass():
    requirements = extract_requirements([{"page": 1, "text": "资格要求：提供软件企业资质证书。"}])

    matched = match_evidence(
        requirements,
        [{"page": 2, "text": "软件企业资质证书编号 ABC。", "ocr_status": "FAILED"}],
        "failed-ocr.pdf",
    )

    assert matched[0]["status"] == "UNKNOWN"
    assert matched[0]["evidence"] == []
