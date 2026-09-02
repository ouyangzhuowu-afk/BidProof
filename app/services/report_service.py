"""Report rendering for a single run and for bulk export."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from fastapi import HTTPException

from .. import presenters
from ..reporting import build_pdf_report
from ..repositories import audit, runs
from ..uploads import safe_filename


def html_report(run: dict) -> str:
    return presenters.report_html(run)


def csv_report(run: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=presenters.REPORT_COLUMNS)
    writer.writeheader()
    for item in run.get("requirements", []):
        writer.writerow(presenters.report_row(item))
    return output.getvalue().lstrip("\ufeff")


def pdf_report(run: dict) -> bytes:
    try:
        return build_pdf_report(run)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="PDF 报告运行时不可用") from exc


def bulk_pdf_archive(principal: dict[str, str], run_ids: list[str], report_format: str) -> bytes:
    archive_buffer = io.BytesIO()
    exported_run_ids: list[str] = []
    used_names: set[str] = set()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for run_id in dict.fromkeys(run_ids):
            run = runs.load(run_id)
            if run is None or run.get("workspace_id", "local") != principal["workspace_id"]:
                continue
            stem = safe_filename(Path(run.get("tender_filename", "report")).stem) or "report"
            name = f"{stem}-{run_id[:12]}.pdf"
            suffix = 2
            while name in used_names:
                name = f"{stem}-{run_id[:12]}-{suffix}.pdf"
                suffix += 1
            used_names.add(name)
            archive.writestr(name, build_pdf_report(run))
            exported_run_ids.append(run_id)
    if not exported_run_ids:
        raise HTTPException(status_code=404, detail="没有可导出的任务")
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "RUN_REPORTS_BULK_EXPORTED",
        None,
        {"format": report_format, "run_ids": exported_run_ids, "count": len(exported_run_ids)},
    )
    return archive_buffer.getvalue()


AUDIT_EXPORT_COLUMNS = ["event_id", "created_at", "event_type", "run_id", "user_id", "payload"]


def audit_csv(workspace_id: str) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=AUDIT_EXPORT_COLUMNS)
    writer.writeheader()
    for event in audit.events(workspace_id):
        writer.writerow({
            "event_id": event.get("event_id", ""),
            "created_at": event.get("created_at", ""),
            "event_type": event.get("event_type", ""),
            "run_id": event.get("run_id", "") or "",
            "user_id": event.get("user_id", ""),
            "payload": json.dumps(event.get("payload", {}), ensure_ascii=False),
        })
    return output.getvalue().encode("utf-8-sig")
