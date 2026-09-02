import hashlib
import json
from pathlib import Path

import pytest

from app.extraction import extract_pdf
from tests.conftest import requires_real_uploads


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "fixtures" / "real-upload" / "ground-truth-candidates.json"


@requires_real_uploads
def test_real_upload_fixture_manifest_has_traceable_candidates():
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(records) >= 5
    assert sum(len(record["candidates"]) for record in records) >= 25
    for record in records:
        source = ROOT / record["source_path"]
        assert source.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record["sha256"]
        assert record["source_status"] == "REAL_UPLOAD_UNVERIFIED_GROUND_TRUTH"
        for candidate in record["candidates"]:
            assert candidate["page"] >= 1
            assert candidate["quote"].strip()
            assert candidate["review_status"] == "PENDING_MANUAL_CONFIRMATION"


@requires_real_uploads
def test_real_upload_candidate_quotes_remain_page_locatable():
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for record in records:
        pages = extract_pdf(ROOT / record["source_path"])
        for candidate in record["candidates"]:
            page = pages[candidate["page"] - 1]
            anchor = "".join(candidate["quote"].split())[:24]
            assert anchor in "".join(page["text"].split())
