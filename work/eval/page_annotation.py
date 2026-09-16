"""S-A-01: page-level JSONL annotation schema and fail-closed validator.

Sandbox / engineering labels only. Never writes pilot or ICP ledgers.
Unknown schema versions and illegal samples are rejected; weak v0.1 labels stay
loadable so older incomplete annotations remain compatible.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = "1.0"
WEAK_SCHEMA_VERSION = "0.1"
COMPATIBLE_SCHEMA_VERSIONS = frozenset({WEAK_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION})
PAGE_TYPES = frozenset({"cover", "toc", "body", "table", "seal"})
REQUIRED_V1 = (
    "schema_version",
    "doc_id",
    "page",
    "page_type",
    "text_gt",
    "fields",
    "table_html",
    "has_seal",
    "has_hw",
)
REQUIRED_WEAK = ("doc_id", "page", "text_gt")


class AnnotationError(ValueError):
    """Raised when a JSONL file cannot be trusted (fail-closed)."""


@dataclass
class ValidationIssue:
    line_no: int
    code: str
    message: str


@dataclass
class RecordValidation:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    normalized: dict[str, Any] | None = None


@dataclass
class JsonlValidation:
    ok: bool
    records: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)


def _issue(code: str, message: str, line_no: int = 0) -> ValidationIssue:
    return ValidationIssue(line_no=line_no, code=code, message=message)


def _as_schema_version(value: Any) -> str:
    if value is None or value == "":
        return WEAK_SCHEMA_VERSION
    return str(value).strip()


def _validate_fields(fields: Any, line_no: int) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(fields, list):
        return [_issue("invalid_fields", "fields must be a list of {name, value} objects", line_no)]
    for index, item in enumerate(fields):
        if not isinstance(item, dict):
            issues.append(_issue("invalid_fields", f"fields[{index}] must be an object", line_no))
            continue
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not name.strip():
            issues.append(_issue("invalid_fields", f"fields[{index}].name must be a non-empty string", line_no))
        if "value" not in item or not isinstance(value, str):
            issues.append(_issue("invalid_fields", f"fields[{index}].value must be a string", line_no))
    return issues


def validate_record(record: Any, line_no: int = 0) -> RecordValidation:
    if not isinstance(record, dict):
        return RecordValidation(
            ok=False,
            issues=[_issue("not_object", "each JSONL line must be a JSON object", line_no)],
        )

    issues: list[ValidationIssue] = []
    version = _as_schema_version(record.get("schema_version"))
    if version not in COMPATIBLE_SCHEMA_VERSIONS:
        issues.append(
            _issue(
                "unsupported_schema_version",
                f"schema_version {version!r} is not compatible; supported: "
                f"{sorted(COMPATIBLE_SCHEMA_VERSIONS)}",
                line_no,
            )
        )

    required = REQUIRED_V1 if version == CURRENT_SCHEMA_VERSION else REQUIRED_WEAK
    if version == CURRENT_SCHEMA_VERSION:
        missing = [key for key in required if key not in record]
        if missing:
            issues.append(
                _issue("missing_required", f"schema 1.0 missing required keys: {', '.join(missing)}", line_no)
            )
    else:
        missing = [key for key in required if key not in record]
        if missing:
            issues.append(
                _issue("missing_required", f"weak label missing required keys: {', '.join(missing)}", line_no)
            )

    doc_id = record.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        issues.append(_issue("invalid_doc_id", "doc_id must be a non-empty string", line_no))

    page = record.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        issues.append(_issue("invalid_page", "page must be a positive integer", line_no))

    page_type = record.get("page_type", "body")
    if "page_type" in record or version == CURRENT_SCHEMA_VERSION:
        if page_type not in PAGE_TYPES:
            issues.append(
                _issue(
                    "invalid_page_type",
                    f"page_type must be one of {sorted(PAGE_TYPES)}",
                    line_no,
                )
            )

    text_gt = record.get("text_gt")
    if not isinstance(text_gt, str):
        issues.append(_issue("invalid_text_gt", "text_gt must be a string", line_no))

    if "fields" in record or version == CURRENT_SCHEMA_VERSION:
        issues.extend(_validate_fields(record.get("fields"), line_no))

    if "table_html" in record or version == CURRENT_SCHEMA_VERSION:
        table_html = record.get("table_html", None)
        if table_html is not None and not isinstance(table_html, str):
            issues.append(_issue("invalid_table_html", "table_html must be a string or null", line_no))

    if "has_seal" in record or version == CURRENT_SCHEMA_VERSION:
        if not isinstance(record.get("has_seal", False), bool):
            issues.append(_issue("invalid_has_seal", "has_seal must be a boolean", line_no))

    if "has_hw" in record or version == CURRENT_SCHEMA_VERSION:
        if not isinstance(record.get("has_hw", False), bool):
            issues.append(_issue("invalid_has_hw", "has_hw must be a boolean", line_no))

    if issues:
        return RecordValidation(ok=False, issues=issues)

    normalized = {
        "schema_version": version,
        "doc_id": str(doc_id).strip(),
        "page": int(page),
        "page_type": page_type if page_type in PAGE_TYPES else "body",
        "text_gt": text_gt,
        "fields": list(record.get("fields") or []),
        "table_html": record.get("table_html", None),
        "has_seal": bool(record.get("has_seal", False)),
        "has_hw": bool(record.get("has_hw", False)),
    }
    return RecordValidation(ok=True, issues=[], normalized=normalized)


def validate_jsonl_text(text: str) -> JsonlValidation:
    records: list[dict[str, Any]] = []
    issues: list[ValidationIssue] = []
    seen: set[tuple[str, int]] = set()
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(_issue("invalid_json", f"line is not JSON: {exc.msg}", line_no))
            continue
        result = validate_record(parsed, line_no=line_no)
        if not result.ok:
            issues.extend(result.issues)
            continue
        assert result.normalized is not None
        key = (result.normalized["doc_id"], result.normalized["page"])
        if key in seen:
            issues.append(
                _issue(
                    "duplicate_page",
                    f"duplicate sample {(key[0], key[1])}",
                    line_no,
                )
            )
            continue
        seen.add(key)
        records.append(result.normalized)
    return JsonlValidation(ok=not issues, records=records, issues=issues)


def validate_jsonl_path(path: Path) -> JsonlValidation:
    return validate_jsonl_text(path.read_text(encoding="utf-8"))


def load_annotations(path: Path) -> list[dict[str, Any]]:
    result = validate_jsonl_path(path)
    if not result.ok:
        details = "; ".join(f"L{i.line_no}:{i.code}:{i.message}" for i in result.issues)
        raise AnnotationError(f"fail-closed: illegal annotation samples in {path}: {details}")
    return result.records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate page-level OCR annotation JSONL (S-A-01).")
    parser.add_argument("path", type=Path, help="JSONL file to validate")
    args = parser.parse_args(argv)
    result = validate_jsonl_path(args.path)
    payload = {
        "ok": result.ok,
        "records": len(result.records),
        "issues": [{"line": i.line_no, "code": i.code, "message": i.message} for i in result.issues],
        "schema_versions_supported": sorted(COMPATIBLE_SCHEMA_VERSIONS),
        "claim_scope": "engineering labels only; not a product or business PASS",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
