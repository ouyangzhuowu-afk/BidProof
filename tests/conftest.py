import os
import tempfile

import pytest


_TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="bidproof-pytest-")
os.environ["BIDPROOF_DATA_ROOT"] = _TEST_RUNTIME.name
os.environ["BIDPROOF_ENV"] = "test"
os.environ["BIDPROOF_ALLOW_TRUSTED_HEADERS"] = "1"

REAL_UPLOAD_MARKER = "real_upload"

TEST_AUTH_HEADERS = {
    "X-Workspace-ID": "pytest-default",
    "X-User-ID": "pytest-owner",
    "X-User-Role": "OWNER",
}


def real_upload_sources_available() -> bool:
    from pathlib import Path

    manifest = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "real-upload"
        / "ground-truth-candidates.json"
    )
    if not manifest.is_file():
        return False
    import json

    records = json.loads(manifest.read_text(encoding="utf-8"))
    root = manifest.parents[2]
    return all((root / record["source_path"]).is_file() for record in records)


requires_real_uploads = pytest.mark.skipif(
    not real_upload_sources_available(),
    reason="work/uploads fixture PDFs are not present in this checkout",
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{REAL_UPLOAD_MARKER}: tests that require local real-upload PDF fixtures",
    )
