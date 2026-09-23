"""Upload intake: size limits, signature checks and filesystem placement."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .file_safety import scan_upload_safety

SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md"}
MAX_UPLOAD_BYTES = int(os.environ.get("BIDPROOF_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
MAX_EVIDENCE_FILES = int(os.environ.get("BIDPROOF_MAX_EVIDENCE_FILES", "20"))
MAX_PDF_PAGES = int(os.environ.get("BIDPROOF_MAX_PDF_PAGES", "500"))
CHUNK_BYTES = 1024 * 1024


def is_supported(filename: str | None) -> bool:
    return bool(filename) and Path(filename).suffix.lower() in SUPPORTED_UPLOAD_EXTENSIONS


def validate_intake(tender: UploadFile, evidence: list[UploadFile] | None,
                    company_name: str, evidence_metadata: str | None) -> None:
    if len(evidence or []) > MAX_EVIDENCE_FILES:
        raise HTTPException(413, f"企业证据最多 {MAX_EVIDENCE_FILES} 份，请分批处理")
    if len(company_name) > 200 or len(evidence_metadata or "") > 32768:
        raise HTTPException(422, "企业名称或证据说明过长")
    for upload in [tender, *(evidence or [])]:
        filename = upload.filename or ""
        if not filename or len(filename.encode("utf-8")) > 240 or any(ord(c) < 32 for c in filename):
            raise HTTPException(422, "文件名为空、过长或包含控制字符")


def safe_filename(filename: str) -> str:
    return Path(filename).name.replace("..", "_")


def remove_tree(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)


async def save_upload(upload: UploadFile, target: Path) -> str:
    """Stream an upload to disk under the size cap and return its SHA-256."""
    digest = hashlib.sha256()
    total = 0
    with target.open("wb") as handle:
        while chunk := await upload.read(CHUNK_BYTES):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                handle.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"单个文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024) or MAX_UPLOAD_BYTES} MB")
            digest.update(chunk)
            handle.write(chunk)
    return digest.hexdigest()


def validate_upload_content(path: Path, *, inspect_pdf: bool = True) -> None:
    """Reject files whose bytes contradict their extension, or that carry active content."""
    suffix = path.suffix.lower()
    with path.open("rb") as handle:
        header = handle.read(8)
        text_prefix = header + handle.read(4096 - len(header)) if suffix in {".txt", ".md"} else header
    if suffix == ".pdf" and not header.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="PDF 文件签名无效")
    if suffix == ".pdf" and inspect_pdf:
        import pymupdf
        try:
            with pymupdf.open(path) as document:
                if document.page_count > MAX_PDF_PAGES:
                    raise HTTPException(413, f"单份 PDF 最多 {MAX_PDF_PAGES} 页，请拆分后处理")
        except pymupdf.FileDataError:
            # Malformed PDF diagnostics remain the extraction layer's responsibility.
            pass
    if suffix in {".docx", ".xlsx", ".pptx"} and not header.startswith(b"PK"):
        raise HTTPException(status_code=422, detail="Office 文件签名无效")
    if suffix in {".txt", ".md"} and b"\x00" in text_prefix:
        raise HTTPException(status_code=422, detail="文本文件包含二进制内容")
    safety_issues = scan_upload_safety(path)
    if safety_issues:
        raise HTTPException(status_code=422, detail=safety_issues[0])
