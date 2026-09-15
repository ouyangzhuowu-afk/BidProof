"""T1 privacy gate: classify sensitive pages and scrub images before any cloud OCR.

Escalation is allowed only when BIDPROOF_OCR_EGRESS_MODE is redacted_only or
vpc_private. Original page bytes are never sent; only scrubbed PNG tiles leave
the process. Credentials and raw payloads stay out of logs.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any


REDACTION_VERSION = "t1-redact-v1"

# Pages that must never escalate — seals / ID / license photocopies.
BLOCK_ESCALATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("seal", re.compile(r"公章|印章|鲜章|骑缝章")),
    ("id_card", re.compile(r"居民身份证|身份证号|身份证复印件")),
    ("license_scan", re.compile(r"营业执照副本|医疗器械(经营|生产)许可证|注册证复印件|许可证复印件")),
    ("bank_receipt", re.compile(r"开户许可证|银行回单|汇款凭证")),
    ("handwritten_signature", re.compile(r"亲笔签名|手写签名")),
    ("contact_sheet", re.compile(r"采购人信息|代理机构信息|联系方法|联系人\s*[:：]")),
]

# Heuristics that suggest a hard page worth cloud help (if not blocked).
ESCALATE_HINT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("toc", re.compile(r"目录|目\s*录")),
    ("dense_table", re.compile(r"开标一览表|报价明细|偏离表|评分表|技术参数表")),
]

PII_LINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"1[3-9]\d{9}"),
    re.compile(r"0\d{2,3}-?\d{7,8}"),
    re.compile(r"\d{17}[\dXx]"),
    re.compile(r"[\u4e00-\u9fff]{1,3}(?:女士|先生|主任|科长)"),
    re.compile(r"(?:联系人|电话|地址|邮箱|E-?mail)\s*[:：]"),
    re.compile(r"https?://|www\.", re.I),
]


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float | None = None
    bbox: tuple[float, float, float, float] | None = None  # image pixel x0,y0,x1,y1


@dataclass
class PageRisk:
    page_types: list[str] = field(default_factory=list)
    block_escalation: bool = False
    block_reasons: list[str] = field(default_factory=list)
    escalate_hints: list[str] = field(default_factory=list)


@dataclass
class RedactionResult:
    image_bytes: bytes
    clean: bool
    residual_findings: list[str]
    masked_line_count: int
    header_footer_masked: bool
    content_sha256: str
    version: str = REDACTION_VERSION


def egress_mode() -> str:
    mode = os.getenv("BIDPROOF_OCR_EGRESS_MODE", "never").strip().lower()
    if mode in {"redacted_only", "redacted", "t1"}:
        return "redacted_only"
    if mode in {"vpc_private", "vpc", "t2"}:
        return "vpc_private"
    return "never"


def egress_allowed_for_cloud() -> bool:
    """Master switch still required; mode selects how strictly we scrub."""
    flag = os.getenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0").strip().lower() in {"1", "true", "yes"}
    return flag and egress_mode() in {"redacted_only", "vpc_private"}


def escalate_min_confidence() -> float:
    try:
        return float(os.getenv("BID_OCR_ESCALATE_MIN_CONF", "0.55"))
    except ValueError:
        return 0.55


def classify_page_text(text: str) -> PageRisk:
    risk = PageRisk()
    blob = text or ""
    for name, pattern in BLOCK_ESCALATION_PATTERNS:
        if pattern.search(blob):
            risk.block_escalation = True
            risk.block_reasons.append(name)
            risk.page_types.append(name)
    for name, pattern in ESCALATE_HINT_PATTERNS:
        if pattern.search(blob):
            risk.escalate_hints.append(name)
            risk.page_types.append(name)
    if not risk.page_types:
        risk.page_types.append("body")
    return risk


def should_escalate_to_cloud(
    *,
    local_text: str,
    local_confidence: float | None,
    risk: PageRisk,
    page_height_pt: float = 842.0,
) -> tuple[bool, str]:
    if not egress_allowed_for_cloud():
        return False, "egress_disabled"
    if risk.block_escalation:
        return False, "blocked:" + ",".join(risk.block_reasons)
    reasons: list[str] = []
    if local_confidence is not None and local_confidence < escalate_min_confidence():
        reasons.append("low_confidence")
    if len((local_text or "").strip()) < 40:
        reasons.append("short_text")
    if page_height_pt >= 700 and len((local_text or "").strip()) < 500:
        reasons.append("possible_truncation")
    if risk.escalate_hints:
        reasons.append("hint:" + ",".join(risk.escalate_hints))
    if not reasons:
        return False, "local_ok"
    return True, ",".join(reasons)


def line_needs_mask(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    return any(pattern.search(value) for pattern in PII_LINE_PATTERNS)


def redact_png_bytes(
    image_bytes: bytes,
    lines: list[OCRLine] | tuple[OCRLine, ...] = (),
    *,
    header_ratio: float = 0.08,
    footer_ratio: float = 0.08,
) -> RedactionResult:
    """Black out header/footer bands and local-OCR line boxes that look like PII."""
    import fitz

    pixmap = fitz.Pixmap(image_bytes)
    if pixmap.alpha:
        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
    width, height = pixmap.width, pixmap.height
    # Paint via a 1-page PDF overlay then rasterize at 1:1 — keeps dependency set small.
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=image_bytes)
    header_h = height * header_ratio
    footer_h = height * footer_ratio
    page.draw_rect(fitz.Rect(0, 0, width, header_h), color=(0, 0, 0), fill=(0, 0, 0))
    page.draw_rect(fitz.Rect(0, height - footer_h, width, height), color=(0, 0, 0), fill=(0, 0, 0))

    masked = 0
    residuals: list[str] = []
    for line in lines:
        text = line.text or ""
        if not line_needs_mask(text):
            # Still check residual high-risk tokens that should block send.
            if re.search(r"身份证号|\d{17}[\dXx]|1[3-9]\d{9}", text):
                residuals.append("unmasked_pii_token")
            continue
        if line.bbox is None:
            residuals.append("pii_without_bbox")
            continue
        x0, y0, x1, y1 = line.bbox
        # Expand slightly so partial glyphs are covered.
        pad = 2.0
        rect = fitz.Rect(max(0, x0 - pad), max(0, y0 - pad), min(width, x1 + pad), min(height, y1 + pad))
        page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))
        masked += 1

    redacted = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png")
    doc.close()

    # Residual scan on line texts that were not maskable.
    for line in lines:
        if line_needs_mask(line.text) and line.bbox is None:
            continue
        if line.bbox is not None and line_needs_mask(line.text):
            continue
        if re.search(r"1[3-9]\d{9}|\d{17}[\dXx]", line.text or ""):
            residuals.append("pii_still_visible")

    # Unique residuals
    residual_findings = sorted(set(residuals))
    clean = "pii_still_visible" not in residual_findings and "unmasked_pii_token" not in residual_findings
    # pii_without_bbox is soft: header/footer already covered; allow escalate but mark unclean if many
    if residual_findings.count("pii_without_bbox") or "pii_without_bbox" in residual_findings:
        # If we only have pii_without_bbox, still escalate after header/footer mask — body phones
        # without boxes are rare when RapidOCR returns boxes. Treat as unclean to be safe.
        clean = False

    return RedactionResult(
        image_bytes=redacted,
        clean=clean,
        residual_findings=residual_findings,
        masked_line_count=masked,
        header_footer_masked=True,
        content_sha256=hashlib.sha256(redacted).hexdigest(),
    )


def rehydrate_placeholders(text: str, token_map: dict[str, str] | None = None) -> str:
    """Optional reverse map; T1 usually leaves placeholders as-is for review safety."""
    if not token_map:
        return text
    out = text
    for placeholder, original in token_map.items():
        out = out.replace(placeholder, original)
    return out


def merge_ocr_texts(local_text: str, cloud_text: str) -> str:
    """Prefer the longer substantive cloud recovery; never invent content."""
    local = (local_text or "").strip()
    cloud = (cloud_text or "").strip()
    if not cloud:
        return local
    if not local:
        return cloud
    if len(cloud) >= int(len(local) * 1.05):
        return cloud
    return local


def parse_lines_from_rapid_rows(rows: Any) -> list[OCRLine]:
    """Best-effort line+bbox parse for RapidOCR / Paddle-like row structures."""
    lines: list[OCRLine] = []
    if rows is None:
        return lines
    if hasattr(rows, "txts") and rows.txts is not None:
        boxes = getattr(rows, "boxes", None) or []
        scores = getattr(rows, "scores", None) or []
        for index, text in enumerate(rows.txts):
            bbox = None
            if index < len(boxes) and boxes[index] is not None:
                bbox = _quad_to_bbox(boxes[index])
            score = None
            if index < len(scores):
                try:
                    score = float(scores[index])
                except (TypeError, ValueError):
                    score = None
            if text and str(text).strip():
                lines.append(OCRLine(text=str(text).strip(), confidence=score, bbox=bbox))
        return lines
    for item in rows or []:
        if not item or len(item) < 2:
            continue
        box = item[0] if not isinstance(item[0], str) else None
        if len(item) >= 3:
            text, score = item[1], item[2]
        else:
            text, score = item[1], None
        if not text or not str(text).strip():
            continue
        conf = None
        try:
            conf = float(score) if score is not None else None
        except (TypeError, ValueError):
            conf = None
        lines.append(OCRLine(text=str(text).strip(), confidence=conf, bbox=_quad_to_bbox(box)))
    return lines


def _quad_to_bbox(box: Any) -> tuple[float, float, float, float] | None:
    if box is None:
        return None
    try:
        if len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
            x0, y0, x1, y1 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        return (min(xs), min(ys), max(xs), max(ys))
    except (TypeError, ValueError, IndexError):
        return None
