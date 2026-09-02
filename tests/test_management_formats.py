import csv
import io
import zipfile

from fastapi.testclient import TestClient

from app import main
from app.services import scan_service
from app.extraction import ExtractionError, extract_file


def _pdf_bytes(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buffer.getvalue()


def _docx_with_extra_entry(name: str, payload: bytes = b"blocked") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="urn:test"><w:p><w:r><w:t>资格要求</w:t></w:r></w:p></w:document>')
        archive.writestr(name, payload)
    return buffer.getvalue()


def test_office_documents_are_extractable_as_page_like_sources(tmp_path):
    docx = tmp_path / "evidence.docx"
    docx.write_bytes(_zip_bytes({
        "word/document.xml": '<document xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><body><p><t>营业执照有效</t></p></body></document>',
    }))
    xlsx = tmp_path / "evidence.xlsx"
    xlsx.write_bytes(_zip_bytes({
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>项目经验</t></is></c></row></sheetData></worksheet>',
    }))
    pptx = tmp_path / "evidence.pptx"
    pptx.write_bytes(_zip_bytes({
        "ppt/slides/slide1.xml": '<sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>团队证书</a:t></sld>',
    }))

    assert "营业执照有效" in extract_file(docx)[0]["text"]
    assert "项目经验" in extract_file(xlsx)[0]["text"]
    assert "团队证书" in extract_file(pptx)[0]["text"]
    assert extract_file(docx)[0]["locator"]["kind"] == "paragraph"
    assert extract_file(xlsx)[0]["locator"]["kind"] == "sheet"
    assert extract_file(pptx)[0]["locator"] == {"kind": "slide", "label": "幻灯片 1", "index": 1}


def test_legacy_office_extensions_fail_with_conversion_guidance(tmp_path):
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"not an OOXML document")

    try:
        extract_file(path)
    except ExtractionError as exc:
        assert "docx" in str(exc).lower()
    else:
        raise AssertionError("legacy office file should require conversion")


def test_bulk_archive_restore_and_report_exports(monkeypatch):
    client = TestClient(main.app)

    def fake_extract(_path):
        return [{"page": 1, "text": "资格要求：提供营业执照。", "has_text": True, "char_count": 12, "blocks": []}]

    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    created = []
    for name in ("one.pdf", "two.pdf"):
        response = client.post("/api/runs", files={"tender": (name, _pdf_bytes("资格要求"), "application/pdf")})
        assert response.status_code == 200
        created.append(response.json()["run_id"])

    bulk = client.post("/api/runs/bulk", json={"run_ids": created, "action": "ARCHIVE"})
    assert bulk.status_code == 200
    assert bulk.json()["updated"] == 2
    active_ids = {item["run_id"] for item in client.get("/api/runs").json()}
    assert not active_ids.intersection(created)
    assert len(client.get("/api/runs?include_archived=true").json()) >= 2

    report = client.get(f"/api/runs/{created[0]}/report.html")
    assert report.status_code == 200
    assert "招标证据链报告" in report.text
    assert "资格要求" in report.text
    assert "attachment" in report.headers.get("content-disposition", "")

    csv_response = client.get(f"/api/runs/{created[0]}/report.csv")
    assert csv_response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert rows and rows[0]["requirement_id"].startswith("REQ-")

    restored = client.post("/api/runs/bulk", json={"run_ids": created, "action": "RESTORE"})
    assert restored.status_code == 200
    assert len(client.get("/api/runs").json()) >= 2

    for run_id in created:
        assert client.delete(f"/api/runs/{run_id}").status_code == 200


def test_active_or_unsafe_document_content_is_rejected(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])

    macro = client.post(
        "/api/runs",
        files={"tender": ("macro.docx", _docx_with_extra_entry("word/vbaProject.bin"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert macro.status_code == 422
    assert "宏" in macro.json()["detail"]

    traversal = client.post(
        "/api/runs",
        files={"tender": ("traversal.docx", _docx_with_extra_entry("../outside.txt"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert traversal.status_code == 422

    active_pdf = client.post("/api/runs", files={"tender": ("active.pdf", _pdf_bytes("资格要求") + b"\n/JavaScript /OpenAction", "application/pdf")})
    assert active_pdf.status_code == 422
    assert "活动内容" in active_pdf.json()["detail"]


def test_bulk_pdf_report_zip_is_workspace_scoped(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    owner = {"X-Workspace-ID": "report-ws", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    foreign = {"X-Workspace-ID": "foreign-ws", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    first = client.post("/api/runs", headers=owner, files={"tender": ("Alpha.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    second = client.post("/api/runs", headers=owner, files={"tender": ("Beta.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    outside = client.post("/api/runs", headers=foreign, files={"tender": ("Secret.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()

    response = client.post(
        "/api/runs/bulk/report.zip",
        headers=owner,
        json={"run_ids": [first["run_id"], second["run_id"], outside["run_id"]], "format": "pdf"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        assert len(names) == 2
        assert all(name.endswith(".pdf") for name in names)
        assert all(archive.read(name).startswith(b"%PDF") for name in names)
        assert not any("Secret" in name for name in names)
