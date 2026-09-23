#!/usr/bin/env python3
"""Exercise a deployed API with disposable synthetic PDFs and a dedicated test account.

Example:
  BIDPROOF_SMOKE_USERNAME=smoke BIDPROOF_SMOKE_PASSWORD='...' \
    python scripts/production-smoke.py --url http://127.0.0.1:8768

Non-loopback URLs require --allow-remote and HTTPS. Creates and deletes only its own scan;
never writes pilot/ICP ledgers. Reports engineering checks, not business acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import ipaddress
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class SmokeFailure(RuntimeError):
    """A safe diagnostic that contains neither credentials nor server response bodies."""


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SmokeFailure(f"Unexpected HTTP redirect ({code}); use the final service origin")


@dataclass
class Reply:
    status: int
    body: bytes
    headers: dict[str, str]

    def object(self) -> dict:
        try:
            value = json.loads(self.body)
        except (ValueError, UnicodeError) as exc:
            raise SmokeFailure("Expected a valid JSON response") from exc
        if not isinstance(value, dict):
            raise SmokeFailure("Expected a JSON object response")
        return value


def validated_origin(value: str, allow_remote: bool) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise SmokeFailure("Invalid service URL") from exc
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise SmokeFailure("Use an http(s) origin without credentials, path, query or fragment")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.lower() == "localhost"
    if not loopback and not allow_remote:
        raise SmokeFailure("Remote target requires explicit --allow-remote")
    if not loopback and parsed.scheme != "https":
        raise SmokeFailure("Remote checks require HTTPS")
    return f"{parsed.scheme}://{parsed.netloc}"


class Client:
    def __init__(self, origin: str):
        self.origin = origin
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirects())

    def request(self, method: str, path: str, *, payload=None, body: bytes | None = None,
                content_type: str | None = None, csrf: bool = True, expected=(200,)) -> Reply:
        if not path.startswith("/") or path.startswith("//"):
            raise SmokeFailure("Invalid relative API path")
        headers = {"Accept": "application/json", "Origin": self.origin}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        if csrf and method not in {"GET", "HEAD"}:
            token = next((cookie.value for cookie in self.jar if cookie.name == "bidproof_csrf"), None)
            if token:
                headers["X-CSRF-Token"] = token
        request = urllib.request.Request(self.origin + path, data=body, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SmokeFailure(f"Network failure during {method} {path.split('?')[0]}") from exc
        with response:
            result = Reply(response.status, response.read(10_000_001), dict(response.headers.items()))
        if len(result.body) > 10_000_000:
            raise SmokeFailure("Synthetic response exceeded 10 MB safety bound")
        if result.status not in expected:
            raise SmokeFailure(f"{method} {path.split('?')[0]} returned {result.status}; expected {expected}")
        return result


def identifier(value, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise SmokeFailure(f"Missing or invalid {label}")
    return value


def synthetic_pdf(title: str, body: str) -> bytes:
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise SmokeFailure("Install requirements-production.lock to generate synthetic PDFs") from exc
    with fitz.open() as document:
        page = document.new_page(width=595, height=842)
        page.insert_text((48, 42), "BIDPROOF SYNTHETIC API SMOKE - NOT BUSINESS EVIDENCE", fontsize=10)
        page.insert_textbox(fitz.Rect(48, 85, 545, 155), title, fontname="china-s", fontsize=18)
        page.insert_textbox(fitz.Rect(48, 180, 545, 690), body, fontname="china-s", fontsize=13, lineheight=1.6)
        return document.tobytes()


def multipart(company: str, tender: bytes, evidence: bytes) -> tuple[bytes, str]:
    boundary = "bidproof-smoke-" + secrets.token_hex(16)
    parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"company_name\"\r\n\r\n{company}\r\n".encode()]
    for name, filename, content in [("tender", "synthetic-tender.pdf", tender), ("evidence", "synthetic-evidence.pdf", evidence)]:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n".encode())
        parts.extend([content, b"\r\n"])
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def ensure(value: bool, message: str) -> None:
    if not value:
        raise SmokeFailure(message)


def check(name: str) -> None:
    print(json.dumps({"check": name, "status": "passed"}, ensure_ascii=False), flush=True)


def execute(arguments: argparse.Namespace) -> None:
    origin = validated_origin(arguments.url, arguments.allow_remote)
    if not arguments.username or not arguments.password:
        raise SmokeFailure("Provide a dedicated test account via --username/--password or BIDPROOF_SMOKE_USERNAME/PASSWORD")
    client = Client(origin)
    run_id = None
    job_id = None
    logged_in = False
    main_error = None
    cleanup_errors = []
    try:
        ensure(client.request("GET", "/healthz").object().get("status") == "ok", "Liveness status is not ok")
        ensure(client.request("GET", "/readyz").object().get("status") == "ready", "Readiness status is not ready")
        client.request("GET", "/api/runs", expected=(401,))
        check("health_readiness_and_anonymous_access_denied")
        login_payload = {"username": arguments.username, "password": arguments.password}
        if arguments.workspace_id:
            login_payload["workspace_id"] = arguments.workspace_id
        login = client.request("POST", "/api/auth/login", payload=login_payload).object()
        ensure(not login.get("mfa_required"), "Use a dedicated smoke account without interactive MFA")
        logged_in = True
        auth = client.request("GET", "/api/auth/status").object()
        ensure(auth.get("authenticated") is True, "Login did not create an authenticated session")
        ensure(any(cookie.name == "bidproof_csrf" for cookie in client.jar), "CSRF cookie is missing")
        client.request("POST", "/api/auth/logout", payload={}, csrf=False, expected=(403,))
        ensure(client.request("GET", "/api/auth/status").object().get("authenticated") is True,
               "A request missing CSRF changed session state")
        check("cookie_auth_and_csrf_rejection")
        marker = "SYNTHETIC-SMOKE-" + secrets.token_hex(6)
        tender = synthetic_pdf("合成招标文件 · 工程检查专用", "投标人须提供有效营业执照。\n投标文件未按要求签字并加盖公章的，否决投标。\n交付期限为合同签订后30日。\n本文件仅用于工程检查，不代表真实采购。")
        evidence = synthetic_pdf("合成企业材料 · 工程检查专用", f"本公司具有独立承担民事责任的能力，提供有效营业执照。\n公司名称：{marker}。\n投标文件已签字并加盖公章。\n本文件仅用于工程检查，不代表真实企业资质。")
        body, content_type = multipart(marker, tender, evidence)
        job_id = identifier(client.request("POST", "/api/jobs", body=body, content_type=content_type, expected=(202,)).object().get("job_id"), "job id")
        deadline = time.monotonic() + arguments.timeout
        poll_delay = 0.25
        while time.monotonic() < deadline:
            job = client.request("GET", f"/api/jobs/{job_id}").object()
            status = job.get("status")
            if status == "COMPLETED":
                run_id = identifier(job.get("run_id"), "run id")
                break
            ensure(status in {"PENDING", "RUNNING"}, "Synthetic scan entered a failed or unexpected state")
            time.sleep(poll_delay)
            poll_delay = min(2.0, poll_delay * 1.6)
        ensure(run_id is not None, "Queue timeout; verify an independent worker is running")
        check("queue_upload_and_completion")
        run = client.request("GET", f"/api/runs/{run_id}").object()
        ensure(run.get("run_id") == run_id, "Returned task identity differs from created task")
        requirements = run.get("requirements")
        ensure(isinstance(requirements, list) and bool(requirements), "Synthetic tender generated no requirement items")
        sources = run.get("source_documents")
        ensure(isinstance(sources, list) and len(sources) == 2, "Expected tender and evidence source documents")
        assets = client.request("GET", f"/api/runs/{run_id}/evidence").object().get("assets")
        ensure(isinstance(assets, list) and bool(assets), "Evidence index is empty")
        tender_download = client.request("GET", f"/api/runs/{run_id}/files/TENDER-001").body
        ensure(hashlib.sha256(tender_download).digest() == hashlib.sha256(tender).digest(), "Original tender download differs from uploaded bytes")
        evidence_source = next((source for source in sources if source.get("source_id") != "TENDER-001"), None)
        ensure(evidence_source is not None, "Evidence source not found")
        source_id = identifier(evidence_source.get("source_id"), "evidence source id")
        evidence_download = client.request("GET", f"/api/runs/{run_id}/files/{source_id}").body
        ensure(evidence_download == evidence, "Original evidence download differs from uploaded bytes")
        for source in ("TENDER-001", source_id):
            preview = client.request("GET", f"/api/runs/{run_id}/files/{source}/pages/1")
            ensure(preview.body.startswith(b"\x89PNG\r\n\x1a\n"), "Source preview is not a PNG")
        check("evidence_index_original_bytes_and_page_previews")
        revision = run.get("revision")
        ensure(isinstance(revision, int) and revision >= 1, "Task revision is missing")
        requirement_id = identifier(requirements[0].get("requirement_id"), "requirement id")
        review = client.request("POST", f"/api/runs/{run_id}/review", payload={
            "requirement_id": requirement_id, "decision": "NEEDS_REVIEW",
            "note": "Synthetic manual review; keep unresolved pending human inspection.", "revision": revision,
        }).object()
        ensure(review.get("revision", 0) > revision, "Manual review did not advance task revision")
        ensure(any(item.get("requirement_id") == requirement_id and item.get("status") == "NEEDS_REVIEW"
                   for item in review.get("requirements", [])), "Manual review was not retained")
        revision = review["revision"]
        check("manual_review_with_revision")
        payload = {"decision": "HOLD", "note": "Synthetic engineering smoke only; not a business decision.",
                   "unresolved_requirement_ids": [requirement_id], "revision": revision}
        decision = client.request("POST", f"/api/runs/{run_id}/decision", payload=payload).object()
        ensure(decision.get("decision", {}).get("decision") == "HOLD", "Decision was not saved")
        ensure(decision.get("revision", 0) > revision, "Decision did not advance task revision")
        client.request("POST", f"/api/runs/{run_id}/decision", payload={**payload, "decision": "STOP"}, expected=(409,))
        latest = client.request("GET", f"/api/runs/{run_id}").object()
        ensure(latest.get("decision", {}).get("decision") == "HOLD", "Stale decision overwrote current state")
        check("decision_revision_and_stale_write_rejection")
        report = client.request("GET", f"/api/runs/{run_id}/report.pdf")
        ensure(report.body.startswith(b"%PDF-"), "Report export is not a PDF")
        csv_report = client.request("GET", f"/api/runs/{run_id}/report.csv")
        ensure(len(csv_report.body) > 20, "CSV report export is empty")
        check("pdf_and_csv_exports")
        deleted = client.request("DELETE", f"/api/runs/{run_id}").object()
        ensure(deleted.get("deleted") == "true", "Synthetic task was not deleted")
        client.request("GET", f"/api/runs/{run_id}", expected=(404,))
        run_id = None
        check("delete_and_verify_absence")
    except Exception as exc:  # noqa: BLE001 — preserve failure while completing scoped cleanup
        main_error = exc
    finally:
        # Resolve only the job this process created; never enumerate or delete other tasks.
        if job_id and logged_in:
            try:
                job_reply = client.request("GET", f"/api/jobs/{job_id}", expected=(200, 404))
                job = job_reply.object() if job_reply.status == 200 else {}
                if job.get("status") in {"PENDING", "RUNNING"}:
                    client.request("POST", f"/api/jobs/{job_id}/cancel", payload={}, expected=(200, 409))
                    job = client.request("GET", f"/api/jobs/{job_id}").object()
                if run_id is None and job.get("run_id"):
                    candidate = identifier(job["run_id"], "cleanup run id")
                    existing = client.request("GET", f"/api/runs/{candidate}", expected=(200, 404))
                    if existing.status == 200:
                        run_id = candidate
            except Exception:  # noqa: BLE001 — redact response contents and report cleanup failure
                cleanup_errors.append("synthetic_job_cleanup")
        if run_id and logged_in:
            try:
                client.request("DELETE", f"/api/runs/{run_id}", expected=(200, 404))
                client.request("GET", f"/api/runs/{run_id}", expected=(404,))
            except Exception:  # noqa: BLE001 — redact response contents and report cleanup failure
                cleanup_errors.append("synthetic_run_cleanup")
        if logged_in:
            try:
                client.request("POST", "/api/auth/logout", payload={})
                ensure(client.request("GET", "/api/auth/status").object().get("authenticated") is False,
                       "Logout left an authenticated session")
                check("logout")
            except Exception:  # noqa: BLE001 — redact response contents and report cleanup failure
                cleanup_errors.append("logout")
    if cleanup_errors:
        raise SmokeFailure("Cleanup incomplete: " + ", ".join(cleanup_errors)) from main_error
    if main_error:
        if isinstance(main_error, SmokeFailure):
            raise main_error
        raise SmokeFailure("Unexpected smoke failure; inspect service logs with the test time window") from main_error
    print(json.dumps({"status": "passed", "scope": "synthetic_engineering_only", "business_acceptance": False}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Explicit target origin; defaults are intentionally not inferred")
    parser.add_argument("--username", default=os.environ.get("BIDPROOF_SMOKE_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("BIDPROOF_SMOKE_PASSWORD", ""), help="Prefer BIDPROOF_SMOKE_PASSWORD to avoid shell history")
    parser.add_argument("--workspace-id", default=os.environ.get("BIDPROOF_SMOKE_WORKSPACE_ID", ""))
    parser.add_argument("--allow-remote", action="store_true", help="Explicitly authorize synthetic create/delete against a remote HTTPS origin")
    parser.add_argument("--timeout", type=int, default=120, help="Queue wait in seconds (5-600)")
    arguments = parser.parse_args()
    if not 5 <= arguments.timeout <= 600:
        parser.error("--timeout must be between 5 and 600 seconds")
    try:
        execute(arguments)
    except SmokeFailure as exc:
        print(json.dumps({"status": "failed", "reason": str(exc), "business_acceptance": False}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
