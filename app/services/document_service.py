"""Read-only, bounded source-page previews for the evidence workbench."""

from __future__ import annotations

import math

import pymupdf as fitz
from fastapi import HTTPException

from .run_service import source_file

# A page uses at most ~12 MB of RGB pixel data. Callers cannot request an
# arbitrary resolution; a larger document page is scaled down before rendering.
MAX_PREVIEW_EDGE = 2000
PREVIEW_SCALE = 1.5


def source_page_png(run: dict, source_id: str, page_number: int) -> bytes:
    """Render the requested 1-based PDF page after the download path guard."""
    path, _filename = source_file(run, source_id)
    if path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="此格式暂不支持原页预览，请下载源文件核验")
    if page_number < 1:
        raise HTTPException(status_code=422, detail="页码必须从 1 开始")
    try:
        with fitz.open(path) as document:
            if not document.is_pdf:
                raise HTTPException(status_code=415, detail="源文件不是可预览的 PDF")
            if document.needs_pass:
                raise HTTPException(status_code=422, detail="PDF 已加密，暂时无法预览原页")
            if page_number > document.page_count:
                raise HTTPException(status_code=404, detail="源文件中不存在此页")
            page = document.load_page(page_number - 1)
            width, height = page.rect.width, page.rect.height
            if any(not math.isfinite(value) or value <= 0 for value in (width, height)):
                raise HTTPException(status_code=422, detail="PDF 页面尺寸无效")
            scale = min(PREVIEW_SCALE, MAX_PREVIEW_EDGE / max(width, height))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
            return pixmap.tobytes("png")
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="原页暂时无法读取，请下载源文件核验") from exc
