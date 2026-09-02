import hashlib
import asyncio
import csv
import html
import io
import json
import os
import secrets
import base64
import shutil
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import ALLOW_TRUSTED_HEADERS, BACKUP_ROOT, BOOTSTRAP_TOKEN, DB_PATH, ENVIRONMENT, JOB_STAGING_DIR, PROJECT_ROOT, UPLOAD_DIR
from .db import accuracy_metrics, add_accuracy_feedback, add_comment, cancel_scan_job, connect, consume_auth_action_token, count_users, create_auth_action_token, create_auth_session, create_project, create_remediation, create_scan_job, create_user, delete_auth_session, delete_run, ensure_default_project, ensure_workspace, find_duplicate_run_ids, get_workspace_settings, init_db, link_scan_job, list_audit_events, list_comments, list_expired_archived_run_ids, list_projects, list_recoverable_jobs, list_remediations, list_scan_jobs, list_workspace_members, list_workspace_remediations, load_auth_action_token, load_project, load_remediation, load_run, load_scan_job, load_session_user, load_user_by_id, load_user_by_username, record_audit_event, save_run, start_scan_job, update_project, update_remediation, update_scan_job, update_user_password, update_workspace_member, update_workspace_settings, workspace_usage
from .extraction import ExtractionError, extract_file
from .file_safety import scan_upload_safety
from .reporting import build_pdf_report
from .rules import extract_requirements, match_evidence
from .schemas import AccuracyFeedbackRequest, AuthActionCompleteRequest, AuthBootstrapRequest, BulkReportRequest, BulkRunRequest, CommentRequest, DecisionRequest, EvidenceMetadata, InvitationCreateRequest, LoginRequest, MemberCreateRequest, MemberUpdateRequest, PasswordChangeRequest, ProjectCreateRequest, ProjectUpdateRequest, RemediationCreateRequest, RemediationUpdateRequest, ReviewRequest, RunMetadataRequest, WorkspaceSettingsRequest
from .state import advance_state, initial_research_state, utc_now
from work.backup_restore import create_backup, list_backup_records, record_backup_verification


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [asyncio.create_task(_process_scan_job(job["job_id"])) for job in list_recoverable_jobs()]
    yield
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Bid Evidence Agent", version="0.3.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
init_db()

SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md"}
MUTATING_ROLES = {"OWNER", "ADMIN", "REVIEWER"}
MAX_UPLOAD_BYTES = int(os.environ.get("BIDPROOF_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
LOGIN_ATTEMPT_LIMIT = int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_LIMIT", "5"))
LOGIN_ATTEMPT_WINDOW_SECONDS = int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_WINDOW_SECONDS", "900"))
_login_attempts: dict[str, list[float]] = {}


def _principal(request: Request) -> dict[str, str]:
    if isinstance(request, SimpleNamespace):
        return _trusted_header_principal(request)
    token = request.cookies.get("bidproof_session")
    if token:
        user = load_session_user(_token_hash(token), utc_now())
        if user:
            return {"workspace_id": user["workspace_id"], "user_id": user["user_id"], "role": user["role"]}
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")
    has_explicit_trusted_identity = any(
        header in request.headers
        for header in ("X-Workspace-ID", "X-User-ID", "X-User-Role")
    )
    if ALLOW_TRUSTED_HEADERS and (has_explicit_trusted_identity or count_users() == 0):
        return _trusted_header_principal(request)
    raise HTTPException(status_code=401, detail="请先登录")


def _trusted_header_principal(request: Request | SimpleNamespace) -> dict[str, str]:
    workspace_id = request.headers.get("X-Workspace-ID", "local").strip() or "local"
    user_id = request.headers.get("X-User-ID", "local-owner").strip() or "local-owner"
    role = request.headers.get("X-User-Role", "OWNER").strip().upper() or "OWNER"
    ensure_workspace(workspace_id, user_id, role)
    return {"workspace_id": workspace_id, "user_id": user_id, "role": role}


def _password_hash(password: str, salt: bytes | None = None, iterations: int = 240_000) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = _password_hash(password, base64.urlsafe_b64decode(salt), int(iterations)).split("$", 3)[3]
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _bootstrap_locked() -> bool:
    return ENVIRONMENT == "production" and not BOOTSTRAP_TOKEN


def _login_attempt_key(request: Request, username: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{username.strip().casefold()}"


def _active_login_attempts(key: str, now: float) -> list[float]:
    attempts = [attempt for attempt in _login_attempts.get(key, []) if now - attempt < LOGIN_ATTEMPT_WINDOW_SECONDS]
    if attempts:
        _login_attempts[key] = attempts
    else:
        _login_attempts.pop(key, None)
    return attempts


def _raise_login_rate_limit(attempts: list[float], now: float) -> None:
    retry_after = max(1, int(LOGIN_ATTEMPT_WINDOW_SECONDS - (now - attempts[0])))
    raise HTTPException(
        status_code=429,
        detail="登录尝试过多，请稍后再试",
        headers={"Retry-After": str(retry_after)},
    )


def _enforce_login_rate_limit(key: str, now: float) -> None:
    attempts = _active_login_attempts(key, now)
    if len(attempts) >= LOGIN_ATTEMPT_LIMIT:
        _raise_login_rate_limit(attempts, now)


def _record_failed_login(key: str, now: float) -> None:
    attempts = _active_login_attempts(key, now)
    attempts.append(now)
    _login_attempts[key] = attempts
    if len(attempts) >= LOGIN_ATTEMPT_LIMIT:
        _raise_login_rate_limit(attempts, now)


def _active_auth_action(raw_token: str, purpose: str | None = None) -> dict:
    action = load_auth_action_token(_token_hash(raw_token))
    expired = not action or action.get("used_at") or action["expires_at"] <= utc_now()
    if expired or (purpose and action["purpose"] != purpose):
        raise HTTPException(status_code=410, detail="链接无效、已使用或已过期")
    return action


def _issue_session(response: Response, user_id: str, secure: bool) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    create_auth_session(_token_hash(token), user_id, expires.isoformat())
    response.set_cookie("bidproof_session", token, max_age=12 * 60 * 60, httponly=True, secure=secure, samesite="strict", path="/")


def _require_role(principal: dict[str, str], roles: set[str] = MUTATING_ROLES) -> None:
    if principal["role"] not in roles:
        raise HTTPException(status_code=403, detail="当前角色没有执行此操作的权限")


@app.get("/", include_in_schema=False)
def landing() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "static" / "landing.html")


@app.get("/app", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "static" / "index.html")


@app.get("/healthz")
def healthz(detail: bool = Query(default=False)) -> dict:
    response: dict = {"status": "ok", "service": "bid-evidence-agent"}
    if detail:
        try:
            with connect() as db:
                db.execute("SELECT 1").fetchone()
            response["database"] = "ok"
        except Exception:
            response["status"] = "degraded"
            response["database"] = "error"
        backups = list_backup_records(BACKUP_ROOT)
        verified = next((item for item in backups if item["valid"]), None)
        response["backup_status"] = "verified" if verified else ("unverified" if backups else "missing")
        response["last_backup_at"] = backups[0]["created_at"] if backups else None
        response["last_verified_backup_at"] = verified["verified_at"] if verified else None
        with connect() as db:
            job_rows = db.execute("SELECT status, COUNT(*) AS count FROM scan_jobs GROUP BY status").fetchall()
        response["job_counts"] = {row["status"]: int(row["count"]) for row in job_rows}
        response["failed_jobs"] = response["job_counts"].get("FAILED", 0)
        response["backup_age_hours"] = None
        if verified and verified.get("verified_at"):
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(verified["verified_at"])
                response["backup_age_hours"] = round(age.total_seconds() / 3600, 2)
            except ValueError:
                response["backup_age_hours"] = None
        reasons = []
        if not verified:
            reasons.append("NO_VERIFIED_BACKUP")
        if response["failed_jobs"]:
            reasons.append("FAILED_SCAN_JOBS")
        response["degraded_reasons"] = reasons
        if reasons:
            response["status"] = "degraded"
    return response


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict:
    users = count_users()
    if users == 0:
        return {
            "setup_required": True,
            "authenticated": False,
            "bootstrap_token_required": ENVIRONMENT == "production",
            "bootstrap_locked": _bootstrap_locked(),
        }
    token = request.cookies.get("bidproof_session")
    user = load_session_user(_token_hash(token), utc_now()) if token else None
    return {
        "setup_required": False,
        "authenticated": bool(user),
        "user": {"user_id": user["user_id"], "workspace_id": user["workspace_id"], "username": user["username"], "role": user["role"]} if user else None,
    }


@app.post("/api/auth/bootstrap")
def bootstrap_auth(request: Request, response: Response, payload: AuthBootstrapRequest) -> dict:
    if count_users() > 0:
        raise HTTPException(status_code=409, detail="管理员已经初始化")
    if _bootstrap_locked():
        raise HTTPException(status_code=503, detail="生产环境尚未配置初始化令牌，请联系运维人员")
    if ENVIRONMENT == "production" and not secrets.compare_digest(payload.bootstrap_token or "", BOOTSTRAP_TOKEN):
        raise HTTPException(status_code=403, detail="初始化令牌无效")
    workspace_id = uuid.uuid4().hex
    user = create_user(workspace_id, payload.username.strip(), _password_hash(payload.password), "OWNER")
    ensure_workspace(workspace_id, user["user_id"], "OWNER", payload.workspace_name.strip())
    _issue_session(response, user["user_id"], request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https")
    record_audit_event(workspace_id, user["user_id"], "AUTH_BOOTSTRAPPED", None, {"username": user["username"]})
    return {"user_id": user["user_id"], "workspace_id": workspace_id, "username": user["username"], "role": "OWNER"}


@app.post("/api/auth/login")
def login(request: Request, response: Response, payload: LoginRequest) -> dict:
    now = time.monotonic()
    attempt_key = _login_attempt_key(request, payload.username)
    _enforce_login_rate_limit(attempt_key, now)
    user = load_user_by_username(payload.username.strip())
    if not user or not bool(user.get("active", 1)) or not _verify_password(payload.password, user["password_hash"]):
        _record_failed_login(attempt_key, now)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    _login_attempts.pop(attempt_key, None)
    _issue_session(response, user["user_id"], request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https")
    record_audit_event(user["workspace_id"], user["user_id"], "AUTH_LOGIN")
    return {"user_id": user["user_id"], "workspace_id": user["workspace_id"], "username": user["username"], "role": user["role"]}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get("bidproof_session")
    if token:
        delete_auth_session(_token_hash(token))
    response.delete_cookie("bidproof_session", path="/")
    return {"logged_out": True}


@app.post("/api/auth/password")
def change_password(request: Request, payload: PasswordChangeRequest) -> dict:
    principal = _principal(request)
    user = load_user_by_id(principal["user_id"])
    if user is None or user.get("workspace_id") != principal["workspace_id"] or not bool(user.get("active", 1)):
        raise HTTPException(status_code=401, detail="当前账号无效")
    if not _verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="当前密码错误")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    if not update_user_password(user["user_id"], _password_hash(payload.new_password)):
        raise HTTPException(status_code=404, detail="账号不存在")
    record_audit_event(principal["workspace_id"], principal["user_id"], "AUTH_PASSWORD_CHANGED")
    return {"changed": True, "sessions_revoked": True}


@app.post("/api/auth/invitations", status_code=201)
def create_invitation(request: Request, payload: InvitationCreateRequest) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    if payload.role == "ADMIN" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以邀请管理员")
    username = payload.username.strip()
    if load_user_by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    raw_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
    create_auth_action_token(
        _token_hash(raw_token),
        principal["workspace_id"],
        "INVITE",
        expires_at,
        principal["user_id"],
        username=username,
        role=payload.role,
    )
    record_audit_event(
        principal["workspace_id"],
        principal["user_id"],
        "MEMBER_INVITATION_CREATED",
        None,
        {"username": username, "role": payload.role, "expires_at": expires_at},
    )
    return {
        "username": username,
        "role": payload.role,
        "expires_at": expires_at,
        "activation_path": f"/app?auth_action=activate&token={raw_token}",
    }


@app.get("/api/auth/action")
def inspect_auth_action(token: str = Query(min_length=20, max_length=500)) -> dict:
    action = _active_auth_action(token)
    username = action.get("username")
    if action["purpose"] == "RESET":
        user = load_user_by_id(action.get("user_id") or "")
        username = user["username"] if user else None
    if not username:
        raise HTTPException(status_code=410, detail="链接关联账号不存在")
    return {"action": action["purpose"], "username": username, "role": action.get("role")}


@app.post("/api/auth/activate")
def activate_invitation(request: Request, response: Response, payload: AuthActionCompleteRequest) -> dict:
    action = _active_auth_action(payload.token, "INVITE")
    if load_user_by_username(action["username"]):
        raise HTTPException(status_code=409, detail="用户名已存在，请直接登录")
    consumed_at = utc_now()
    if not consume_auth_action_token(_token_hash(payload.token), consumed_at):
        raise HTTPException(status_code=410, detail="链接无效、已使用或已过期")
    try:
        user = create_user(action["workspace_id"], action["username"], _password_hash(payload.password), action["role"])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在，请直接登录") from exc
    ensure_workspace(action["workspace_id"], user["user_id"], action["role"])
    _issue_session(response, user["user_id"], request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https")
    record_audit_event(action["workspace_id"], user["user_id"], "MEMBER_INVITATION_ACCEPTED", None, {"role": action["role"]})
    return {"user_id": user["user_id"], "workspace_id": action["workspace_id"], "username": user["username"], "role": user["role"]}


@app.post("/api/members/{user_id}/password-reset", status_code=201)
def issue_member_password_reset(request: Request, user_id: str) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    member = load_user_by_id(user_id)
    if member is None or member["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="成员不存在")
    if member["role"] == "OWNER" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以重置所有者密码")
    raw_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    create_auth_action_token(
        _token_hash(raw_token),
        principal["workspace_id"],
        "RESET",
        expires_at,
        principal["user_id"],
        user_id=user_id,
        role=member["role"],
    )
    record_audit_event(
        principal["workspace_id"],
        principal["user_id"],
        "MEMBER_PASSWORD_RESET_CREATED",
        None,
        {"member_id": user_id, "expires_at": expires_at},
    )
    return {"username": member["username"], "expires_at": expires_at, "reset_path": f"/app?auth_action=reset&token={raw_token}"}


@app.post("/api/auth/reset-password")
def complete_password_reset(request: Request, response: Response, payload: AuthActionCompleteRequest) -> dict:
    action = _active_auth_action(payload.token, "RESET")
    user = load_user_by_id(action.get("user_id") or "")
    if user is None or user["workspace_id"] != action["workspace_id"] or not bool(user.get("active", 1)):
        raise HTTPException(status_code=410, detail="链接关联账号不存在或已停用")
    consumed_at = utc_now()
    if not consume_auth_action_token(_token_hash(payload.token), consumed_at):
        raise HTTPException(status_code=410, detail="链接无效、已使用或已过期")
    update_user_password(user["user_id"], _password_hash(payload.password))
    _issue_session(response, user["user_id"], request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https")
    record_audit_event(action["workspace_id"], user["user_id"], "AUTH_PASSWORD_RESET_COMPLETED")
    return {"user_id": user["user_id"], "workspace_id": user["workspace_id"], "username": user["username"], "role": user["role"]}


@app.get("/api/members")
def get_members(request: Request) -> dict:
    principal = _principal(request)
    return {"workspace_id": principal["workspace_id"], "members": list_workspace_members(principal["workspace_id"])}


@app.post("/api/members", status_code=201)
def create_member(request: Request, payload: MemberCreateRequest) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    if payload.role == "ADMIN" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以创建管理员")
    try:
        user = create_user(principal["workspace_id"], payload.username.strip(), _password_hash(payload.password), payload.role)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    ensure_workspace(principal["workspace_id"], user["user_id"], payload.role)
    record_audit_event(principal["workspace_id"], principal["user_id"], "MEMBER_CREATED", None, {"member_id": user["user_id"], "username": user["username"], "role": payload.role})
    return {key: value for key, value in user.items() if key != "password_hash"} | {"active": True}


@app.patch("/api/members/{user_id}")
def update_member(request: Request, user_id: str, payload: MemberUpdateRequest) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    members = {item["user_id"]: item for item in list_workspace_members(principal["workspace_id"])}
    target = members.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    if target["role"] == "OWNER" and target["user_id"] != principal["user_id"]:
        raise HTTPException(status_code=403, detail="管理员不能修改所有者")
    if user_id == principal["user_id"] and payload.active is False:
        raise HTTPException(status_code=400, detail="不能停用当前账号")
    if payload.role == "ADMIN" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以授予管理员角色")
    updated = update_workspace_member(principal["workspace_id"], user_id, payload.role, payload.active)
    record_audit_event(principal["workspace_id"], principal["user_id"], "MEMBER_UPDATED", None, {"member_id": user_id, "role": updated["role"], "active": updated["active"]})
    return updated


@app.get("/api/projects")
def get_projects(request: Request, include_archived: bool = Query(default=False)) -> dict:
    principal = _principal(request)
    ensure_default_project(principal["workspace_id"])
    return {"workspace_id": principal["workspace_id"], "projects": list_projects(principal["workspace_id"], include_archived)}


@app.post("/api/projects", status_code=201)
def add_project(request: Request, payload: ProjectCreateRequest) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    code = (payload.code or f"PRJ-{uuid.uuid4().hex[:8]}").upper()
    try:
        project = create_project(principal["workspace_id"], payload.name.strip(), code)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="项目编码已存在") from exc
    record_audit_event(principal["workspace_id"], principal["user_id"], "PROJECT_CREATED", None, {"project_id": project["project_id"], "code": project["code"]})
    return project


@app.patch("/api/projects/{project_id}")
def patch_project(request: Request, project_id: str, payload: ProjectUpdateRequest) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    project = load_project(project_id)
    if project is None or project["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="项目不存在")
    updated = update_project(project_id, payload.name.strip() if payload.name else None, payload.archived)
    record_audit_event(principal["workspace_id"], principal["user_id"], "PROJECT_UPDATED", None, {"project_id": project_id, "archived": bool(updated["archived_at"])})
    return updated


@app.get("/api/backups")
def get_backups(request: Request) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    return {"backups": list_backup_records(BACKUP_ROOT), "restore_boundary": "恢复会替换运行中数据，仅允许离线运维命令执行。"}


@app.post("/api/backups", status_code=201)
def create_project_backup(request: Request) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    backup = create_backup(backup_root=BACKUP_ROOT)
    verification = record_backup_verification(backup)
    record_audit_event(principal["workspace_id"], principal["user_id"], "BACKUP_CREATED", None, {"backup_id": backup.name, "valid": verification["valid"]})
    return verification


@app.post("/api/backups/{backup_id}/verify")
def verify_project_backup(request: Request, backup_id: str) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    if Path(backup_id).name != backup_id:
        raise HTTPException(status_code=400, detail="备份编号无效")
    backup = BACKUP_ROOT / backup_id
    if not backup.is_dir():
        raise HTTPException(status_code=404, detail="备份不存在")
    verification = record_backup_verification(backup)
    record_audit_event(principal["workspace_id"], principal["user_id"], "BACKUP_VERIFIED", None, {"backup_id": backup_id, "valid": verification["valid"]})
    return verification


@app.post("/api/runs")
async def create_run(
    request: Request,
    tender: Annotated[UploadFile, File(...)],
    evidence: Annotated[list[UploadFile] | None, File()] = None,
    company_name: Annotated[str, Form()] = "未填写企业",
    evidence_metadata: Annotated[str | None, Form()] = None,
    project_id: Annotated[str | None, Form()] = None,
) -> dict:
    principal = _principal(request)
    _require_role(principal)
    project = ensure_default_project(principal["workspace_id"]) if not project_id else load_project(project_id)
    if project is None or project["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project["archived_at"]:
        raise HTTPException(status_code=409, detail="归档项目不能创建新扫描")
    if not tender.filename or Path(tender.filename).suffix.lower() not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="招标文件支持 PDF、DOCX、XLSX、PPTX、TXT、MD")
    metadata = _parse_evidence_metadata(evidence_metadata)
    run_id = uuid.uuid4().hex
    job_id = request.headers.get("X-BidProof-Job-ID") or uuid.uuid4().hex
    if request.headers.get("X-BidProof-Job-ID"):
        update_scan_job(job_id, "RUNNING")
    else:
        create_scan_job(job_id, principal["workspace_id"], run_id, "RUNNING")
    run_dir = UPLOAD_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    tender_path = run_dir / _safe_filename(tender.filename)
    try:
        tender_sha256 = await _save_upload(tender, tender_path)
        _validate_upload_content(tender_path)
    except HTTPException:
        _remove_tree(run_dir)
        update_scan_job(job_id, "FAILED", attempts=1, error="UPLOAD_REJECTED")
        raise
    duplicate_run_ids = find_duplicate_run_ids(principal["workspace_id"], tender_sha256)
    evidence_files: list[dict] = []
    evidence_assets: list[dict] = []
    evidence_pages: list[dict] = []

    for index, upload in enumerate(evidence or [], start=1):
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
            _remove_tree(run_dir)
            update_scan_job(job_id, "FAILED", attempts=1, error="UNSUPPORTED_EVIDENCE_FORMAT", progress_message="企业证据格式不受支持")
            raise HTTPException(status_code=400, detail="企业证据支持 PDF、DOCX、XLSX、PPTX、TXT、MD")
        target = run_dir / _safe_filename(upload.filename)
        try:
            sha256 = await _save_upload(upload, target)
            _validate_upload_content(target)
        except HTTPException:
            _remove_tree(run_dir)
            update_scan_job(job_id, "FAILED", attempts=1, error="UPLOAD_REJECTED")
            raise
        asset_id = f"EVD-{index:03d}"
        try:
            pages = extract_file(target)
        except ExtractionError as exc:
            _remove_tree(run_dir)
            update_scan_job(job_id, "FAILED", attempts=1, error="EVIDENCE_EXTRACTION_FAILED", progress_message="企业证据解析失败")
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        for page in pages:
            page["source_filename"] = upload.filename
            page["source_id"] = asset_id
            evidence_pages.append(page)
        file_meta = metadata.get(upload.filename, EvidenceMetadata())
        asset = {
            "asset_id": asset_id,
            "source_id": asset_id,
            "filename": upload.filename,
            "file_type": suffix.lstrip("."),
            "sha256": sha256,
            "category": file_meta.category,
            "valid_until": file_meta.valid_until,
            "pages": len(pages),
            "page_index": _page_index(pages),
            "indexed_at": utc_now(),
        }
        evidence_assets.append(asset)
        evidence_files.append({"filename": upload.filename, "path": str(target), **asset})

    try:
        tender_pages = extract_file(tender_path)
    except ExtractionError as exc:
        _remove_tree(run_dir)
        update_scan_job(job_id, "FAILED", attempts=1, error="TENDER_EXTRACTION_FAILED", progress_message="招标文件解析失败")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for page in tender_pages:
        page["source_id"] = "TENDER-001"

    requirements = extract_requirements(tender_pages)
    if evidence_pages and evidence_files:
        requirements = match_evidence(requirements, evidence_pages, evidence_files)

    source_documents = [
        {
            "source_id": "TENDER-001",
            "role": "tender",
            "filename": tender.filename,
            "file_type": Path(tender.filename).suffix.lower().lstrip("."),
            "sha256": tender_sha256,
            "pages": len(tender_pages),
            "page_index": _page_index(tender_pages),
            "parse_status": "PARSED",
        },
        *[
            {
                "source_id": asset["source_id"],
                "role": "enterprise_evidence",
                "filename": asset["filename"],
                "file_type": asset["file_type"],
                "sha256": asset["sha256"],
                "pages": asset["pages"],
                "page_index": asset["page_index"],
                "parse_status": "PARSED",
            }
            for asset in evidence_assets
        ],
    ]
    state = initial_research_state(run_id)
    state["research_brief"]["company_name"] = company_name
    state["source_registry"] = [
        {
            "source_id": item["source_id"],
            "filename": item["filename"],
            "pages": item["pages"],
            "source_type": item["role"],
        }
        for item in source_documents
    ]
    state["source_documents"] = source_documents
    state["evidence_assets"] = evidence_assets
    state["evidence_matrix"] = requirements
    quality = _scan_quality(tender_pages, evidence_pages)
    state["scan_quality"] = quality
    advance_state(state, "AUDIT")
    now = utc_now()
    run = {
        "run_id": run_id,
        "workspace_id": principal["workspace_id"],
        "owner_id": principal["user_id"],
        "parent_run_id": None,
        "version_number": 1,
        "job_id": job_id,
        "assignee_id": principal["user_id"],
        "reviewer_id": None,
        "tags": [],
        "favorite": False,
        "project_id": project["project_id"],
        "tender_sha256": tender_sha256,
        "duplicate_run_ids": duplicate_run_ids,
        "created_at": now,
        "updated_at": now,
        "archived_at": None,
        "status": state["status"],
        "tender_filename": tender.filename,
        "tender_path": str(tender_path),
        "evidence_files": evidence_files,
        "source_documents": source_documents,
        "evidence_assets": evidence_assets,
        "decision": {},
        "state": state,
        "requirements": requirements,
        "review": {"items": [], "updated_at": now},
    }
    save_run(run)
    link_scan_job(job_id, run_id)
    update_scan_job(job_id, "COMPLETED", attempts=1)
    record_audit_event(principal["workspace_id"], principal["user_id"], "RUN_CREATED", run_id, {"filename": tender.filename, "version_number": 1})
    return _public_run(run)


@app.get("/api/runs")
def list_runs(
    request: Request,
    include_archived: bool = Query(default=False),
    project_id: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    tag: str | None = Query(default=None, max_length=80),
    favorite: bool | None = Query(default=None),
    assignee_id: str | None = Query(default=None, max_length=120),
    reviewer_id: str | None = Query(default=None, max_length=120),
    sort: str = Query(default="updated_desc", pattern="^(updated_desc|filename)$"),
) -> list[dict]:
    from .db import list_runs as db_list_runs

    principal = _principal(request)
    scoped_runs = [
        run for run in db_list_runs()
        if run.get("workspace_id", "local") == principal["workspace_id"]
        and (include_archived or not run.get("archived_at"))
        and (not project_id or run.get("project_id") == project_id)
    ]
    normalized_search = search.strip().casefold() if search else ""
    if normalized_search:
        scoped_runs = [
            run for run in scoped_runs
            if normalized_search in " ".join([
                run.get("tender_filename", ""),
                run.get("run_id", ""),
                *run.get("tags", []),
            ]).casefold()
        ]
    if tag:
        scoped_runs = [run for run in scoped_runs if tag in run.get("tags", [])]
    if favorite is not None:
        scoped_runs = [run for run in scoped_runs if bool(run.get("favorite", False)) is favorite]
    if assignee_id is not None:
        scoped_runs = [run for run in scoped_runs if run.get("assignee_id") == assignee_id]
    if reviewer_id is not None:
        scoped_runs = [run for run in scoped_runs if run.get("reviewer_id") == reviewer_id]
    if sort == "filename":
        scoped_runs.sort(key=lambda run: (run.get("tender_filename", "").casefold(), run["run_id"]))
    else:
        scoped_runs.sort(key=lambda run: (run.get("updated_at", ""), run["run_id"]), reverse=True)
    return [_public_summary(run) for run in scoped_runs]


@app.post("/api/runs/bulk")
def bulk_manage_runs(request: Request, payload: BulkRunRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    updated = 0
    for run_id in dict.fromkeys(payload.run_ids):
        run = load_run(run_id)
        if run is None or run.get("workspace_id", "local") != principal["workspace_id"]:
            continue
        if payload.action == "DELETE":
            delete_run(run_id)
            _remove_tree(Path(run["tender_path"]).parent)
        else:
            run["archived_at"] = utc_now() if payload.action == "ARCHIVE" else None
            run["updated_at"] = utc_now()
            save_run(run)
        record_audit_event(principal["workspace_id"], principal["user_id"], f"RUN_{payload.action}", run_id)
        updated += 1
    return {"action": payload.action, "updated": updated}


@app.post("/api/runs/bulk/report.zip")
def bulk_report_zip(request: Request, payload: BulkReportRequest) -> Response:
    principal = _principal(request)
    archive_buffer = io.BytesIO()
    exported_run_ids: list[str] = []
    used_names: set[str] = set()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for run_id in dict.fromkeys(payload.run_ids):
            run = load_run(run_id)
            if run is None or run.get("workspace_id", "local") != principal["workspace_id"]:
                continue
            stem = _safe_filename(Path(run.get("tender_filename", "report")).stem) or "report"
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
    record_audit_event(
        principal["workspace_id"],
        principal["user_id"],
        "RUN_REPORTS_BULK_EXPORTED",
        None,
        {"format": payload.format, "run_ids": exported_run_ids, "count": len(exported_run_ids)},
    )
    return Response(
        content=archive_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="bidproof-reports.zip"'},
    )


@app.get("/api/runs/{run_id}")
def get_run(request: Request, run_id: str) -> dict:
    return _public_run(_require_scoped_run(run_id, _principal(request)))


@app.get("/api/runs/{run_id}/files/{source_id}")
def download_run_file(request: Request, run_id: str, source_id: str) -> FileResponse:
    run = _require_scoped_run(run_id, _principal(request))
    if Path(source_id).name != source_id:
        raise HTTPException(status_code=400, detail="文件编号无效")
    candidate_path: str | None = None
    filename: str | None = None
    if source_id == "TENDER-001":
        candidate_path = run.get("tender_path")
        filename = run.get("tender_filename")
    else:
        for asset in run.get("evidence_files", []):
            if asset.get("asset_id") == source_id or asset.get("source_id") == source_id:
                candidate_path = asset.get("path")
                filename = asset.get("filename")
                break
    if not candidate_path:
        raise HTTPException(status_code=404, detail="源文件不存在")
    path = Path(candidate_path).resolve()
    run_root = Path(run.get("tender_path", "")).resolve().parent
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="源文件不存在") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="源文件不存在")
    return FileResponse(path, filename=Path(filename or path.name).name, media_type="application/octet-stream")


@app.post("/api/runs/{run_id}/rescan")
async def rescan_run(
    request: Request,
    run_id: str,
    tender: Annotated[UploadFile, File(...)],
    evidence: Annotated[list[UploadFile] | None, File()] = None,
    company_name: Annotated[str, Form()] = "未填写企业",
    evidence_metadata: Annotated[str | None, Form()] = None,
    project_id: Annotated[str | None, Form()] = None,
) -> dict:
    principal = _principal(request)
    _require_role(principal)
    parent = _require_scoped_run(run_id, principal)
    created = await create_run(request, tender, evidence, company_name, evidence_metadata, project_id or parent.get("project_id"))
    child = _require_run(created["run_id"])
    child["parent_run_id"] = parent["run_id"]
    child["version_number"] = int(parent.get("version_number", 1)) + 1
    save_run(child)
    record_audit_event(principal["workspace_id"], principal["user_id"], "RUN_RESCANNED", child["run_id"], {"parent_run_id": parent["run_id"], "version_number": child["version_number"]})
    return _public_run(child)


@app.get("/api/runs/{run_id}/diff/{other_run_id}")
def diff_runs(request: Request, run_id: str, other_run_id: str) -> dict:
    principal = _principal(request)
    current = _require_scoped_run(run_id, principal)
    other = _require_scoped_run(other_run_id, principal)
    current_items = {_requirement_signature(item): item for item in current.get("requirements", [])}
    other_items = {_requirement_signature(item): item for item in other.get("requirements", [])}
    added = [current_items[key] for key in current_items.keys() - other_items.keys()]
    removed = [other_items[key] for key in other_items.keys() - current_items.keys()]
    changed = [
        {"before": other_items[key], "after": current_items[key]}
        for key in current_items.keys() & other_items.keys()
        if current_items[key].get("status") != other_items[key].get("status")
    ]
    return {"run_id": run_id, "compared_to": other_run_id, "added": added, "removed": removed, "changed": changed}


@app.get("/api/runs/{run_id}/audit")
def get_run_audit(request: Request, run_id: str) -> dict:
    principal = _principal(request)
    _require_scoped_run(run_id, principal)
    return {"run_id": run_id, "events": list_audit_events(principal["workspace_id"], run_id)}


@app.patch("/api/runs/{run_id}/metadata")
def update_run_metadata(request: Request, run_id: str, payload: RunMetadataRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    run = _require_scoped_run(run_id, principal)
    run["assignee_id"] = payload.assignee_id
    run["reviewer_id"] = payload.reviewer_id
    run["tags"] = list(dict.fromkeys(tag.strip() for tag in payload.tags if tag.strip()))
    run["favorite"] = payload.favorite
    run["updated_at"] = utc_now()
    save_run(run)
    record_audit_event(principal["workspace_id"], principal["user_id"], "RUN_METADATA_UPDATED", run_id, {"assignee_id": payload.assignee_id, "reviewer_id": payload.reviewer_id, "tags": run["tags"], "favorite": payload.favorite})
    return _public_run(run)


@app.post("/api/runs/{run_id}/comments")
def create_comment(request: Request, run_id: str, payload: CommentRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    _require_scoped_run(run_id, principal)
    comment = add_comment(principal["workspace_id"], run_id, principal["user_id"], payload.body.strip())
    record_audit_event(principal["workspace_id"], principal["user_id"], "COMMENT_ADDED", run_id, {"comment_id": comment["comment_id"]})
    return comment


@app.get("/api/runs/{run_id}/comments")
def get_comments(request: Request, run_id: str) -> dict:
    principal = _principal(request)
    _require_scoped_run(run_id, principal)
    return {"run_id": run_id, "comments": list_comments(principal["workspace_id"], run_id)}


@app.post("/api/runs/{run_id}/remediations", status_code=201)
def create_run_remediation(request: Request, run_id: str, payload: RemediationCreateRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    run = _require_scoped_run(run_id, principal)
    if payload.requirement_id and not any(item.get("requirement_id") == payload.requirement_id for item in run.get("requirements", [])):
        raise HTTPException(status_code=400, detail="要求项不存在")
    item = create_remediation(principal["workspace_id"], run_id, payload.model_dump())
    record_audit_event(principal["workspace_id"], principal["user_id"], "REMEDIATION_CREATED", run_id, {"remediation_id": item["remediation_id"]})
    return item


@app.get("/api/runs/{run_id}/remediations")
def get_run_remediations(request: Request, run_id: str) -> dict:
    principal = _principal(request)
    _require_scoped_run(run_id, principal)
    return {"remediations": list_remediations(principal["workspace_id"], run_id)}


@app.patch("/api/remediations/{remediation_id}")
def patch_remediation(request: Request, remediation_id: str, payload: RemediationUpdateRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    item = load_remediation(remediation_id)
    if item is None or item["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="整改项不存在")
    updated = update_remediation(remediation_id, payload.model_dump(exclude_unset=True))
    record_audit_event(principal["workspace_id"], principal["user_id"], "REMEDIATION_UPDATED", item["run_id"], {"remediation_id": remediation_id, "status": updated["status"]})
    return updated


@app.post("/api/runs/{run_id}/accuracy-feedback")
def create_accuracy_feedback(request: Request, run_id: str, payload: AccuracyFeedbackRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    run = _require_scoped_run(run_id, principal)
    if payload.predicted == "DETECTED" and not payload.requirement_id:
        raise HTTPException(status_code=422, detail="检测项反馈必须指定要求项")
    if payload.predicted == "MISSED" and (payload.actual != "RELEVANT" or not payload.locator_label or not payload.quote):
        raise HTTPException(status_code=422, detail="漏项反馈必须提供原文定位、原文引用并标记为相关")
    if payload.requirement_id and not any(item.get("requirement_id") == payload.requirement_id for item in run.get("requirements", [])):
        raise HTTPException(status_code=400, detail="要求项不存在")
    item = add_accuracy_feedback(principal["workspace_id"], run_id, principal["user_id"], payload.model_dump())
    record_audit_event(principal["workspace_id"], principal["user_id"], "ACCURACY_FEEDBACK_ADDED", run_id, {
        "feedback_id": item["feedback_id"],
        "category": item["category"],
        "dataset_scope": item["dataset_scope"],
        "review_complete": bool(item["review_complete"]),
    })
    return item


@app.get("/api/accuracy/metrics")
def get_accuracy_metrics(request: Request, include_test: bool = Query(default=False)) -> dict:
    principal = _principal(request)
    scopes = ("TEST", "PILOT", "ENTERPRISE") if include_test else ("PILOT", "ENTERPRISE")
    categories = accuracy_metrics(principal["workspace_id"], scopes=scopes)
    overall_counts = {
        key: sum(item[key] for item in categories)
        for key in ("tp", "fp", "fn", "tn", "sample_size", "detected_total", "labeled_detected")
    }
    precision_denominator = overall_counts["tp"] + overall_counts["fp"]
    recall_denominator = overall_counts["tp"] + overall_counts["fn"]
    false_positive_denominator = overall_counts["fp"] + overall_counts["tn"]
    overall_coverage = overall_counts["labeled_detected"] / overall_counts["detected_total"] if overall_counts["detected_total"] else None
    review_population_complete = bool(categories) and all(item["review_population_complete"] for item in categories)
    overall = {
        **overall_counts,
        "precision": round(overall_counts["tp"] / precision_denominator, 4) if precision_denominator else None,
        "recall": round(overall_counts["tp"] / recall_denominator, 4) if recall_denominator else None,
        "false_discovery_rate": round(overall_counts["fp"] / precision_denominator, 4) if precision_denominator else None,
        "false_positive_rate": round(overall_counts["fp"] / false_positive_denominator, 4) if false_positive_denominator else None,
        "miss_rate": round(overall_counts["fn"] / recall_denominator, 4) if recall_denominator else None,
        "coverage": round(overall_coverage, 4) if overall_coverage is not None else None,
        "review_population_complete": review_population_complete,
        "included_scopes": list(scopes),
        "measurement_status": "MEASURABLE" if overall_coverage == 1 and overall_counts["sample_size"] >= 20 and review_population_complete else "INSUFFICIENT",
    }
    return {
        "workspace_id": principal["workspace_id"],
        "overall": overall,
        "categories": categories,
        "boundary": "默认排除测试标签；检测项覆盖不足、样本少于 20 或漏项复核不完整时，指标状态保持 INSUFFICIENT，不能代表生产准确率。",
    }


@app.get("/api/jobs")
def get_scan_jobs(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    principal = _principal(request)
    jobs = list_scan_jobs(principal["workspace_id"], limit)
    return {"workspace_id": principal["workspace_id"], "jobs": [{key: value for key, value in job.items() if key != "payload"} for job in jobs]}


@app.get("/api/jobs/{job_id}")
def get_scan_job(request: Request, job_id: str) -> dict:
    principal = _principal(request)
    job = load_scan_job(job_id)
    if job is None or job["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="扫描作业不存在")
    return {key: value for key, value in job.items() if key != "payload"}


@app.get("/api/audit/export.csv")
def export_audit_csv(request: Request) -> Response:
    principal = _principal(request)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["event_id", "created_at", "event_type", "run_id", "user_id", "payload"])
    writer.writeheader()
    for event in list_audit_events(principal["workspace_id"]):
        writer.writerow({
            "event_id": event.get("event_id", ""),
            "created_at": event.get("created_at", ""),
            "event_type": event.get("event_type", ""),
            "run_id": event.get("run_id", "") or "",
            "user_id": event.get("user_id", ""),
            "payload": json.dumps(event.get("payload", {}), ensure_ascii=False),
        })
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bidproof-audit.csv"},
    )


@app.post("/api/jobs", status_code=202)
async def enqueue_scan_job(
    request: Request,
    background_tasks: BackgroundTasks,
    tender: Annotated[UploadFile, File(...)],
    evidence: Annotated[list[UploadFile] | None, File()] = None,
    company_name: Annotated[str, Form()] = "未填写企业",
    evidence_metadata: Annotated[str | None, Form()] = None,
    project_id: Annotated[str | None, Form()] = None,
) -> dict:
    principal = _principal(request)
    _require_role(principal)
    if not tender.filename or Path(tender.filename).suffix.lower() not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="招标文件格式不受支持")
    job_id = uuid.uuid4().hex
    staging = JOB_STAGING_DIR / job_id
    staging.mkdir(parents=True, exist_ok=False)
    tender_target = staging / f"tender-{_safe_filename(tender.filename)}"
    try:
        await _save_upload(tender, tender_target)
        _validate_upload_content(tender_target)
        evidence_records = []
        for index, upload in enumerate(evidence or [], 1):
            if not upload.filename:
                continue
            if Path(upload.filename).suffix.lower() not in SUPPORTED_UPLOAD_EXTENSIONS:
                raise HTTPException(status_code=400, detail="企业证据格式不受支持")
            target = staging / f"evidence-{index:03d}-{_safe_filename(upload.filename)}"
            await _save_upload(upload, target)
            _validate_upload_content(target)
            evidence_records.append({"path": str(target), "filename": upload.filename})
    except Exception:
        _remove_tree(staging)
        raise
    payload = {
        "tender_path": str(tender_target),
        "tender_filename": tender.filename,
        "evidence": evidence_records,
        "company_name": company_name,
        "evidence_metadata": evidence_metadata,
        "user_id": principal["user_id"],
        "role": principal["role"],
        "project_id": project_id,
    }
    create_scan_job(job_id, principal["workspace_id"], None, "PENDING", payload)
    update_scan_job(job_id, "PENDING", progress_total=max(2, len(evidence_records) + 2), progress_message="文件已接收，等待解析")
    record_audit_event(principal["workspace_id"], principal["user_id"], "SCAN_JOB_QUEUED", None, {"job_id": job_id, "filename": tender.filename})
    background_tasks.add_task(_process_scan_job, job_id)
    return {"job_id": job_id, "status": "PENDING"}


@app.post("/api/jobs/{job_id}/retry", status_code=202)
def retry_scan_job(request: Request, job_id: str, background_tasks: BackgroundTasks) -> dict:
    principal = _principal(request)
    _require_role(principal)
    job = load_scan_job(job_id)
    if job is None or job["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="扫描作业不存在")
    if job["status"] not in {"FAILED", "PENDING"}:
        raise HTTPException(status_code=409, detail="当前作业状态不可重试")
    update_scan_job(job_id, "PENDING", attempts=int(job.get("attempts", 0)), error=None, cancel_requested=False, progress_message="已重新排队")
    background_tasks.add_task(_process_scan_job, job_id)
    return {"job_id": job_id, "status": "PENDING"}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str) -> dict:
    principal = _principal(request)
    _require_role(principal)
    job = load_scan_job(job_id)
    if job is None or job["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="扫描作业不存在")
    if job["status"] not in {"PENDING", "RUNNING"}:
        raise HTTPException(status_code=409, detail="当前作业状态不可取消")
    cancelled = cancel_scan_job(job_id)
    record_audit_event(principal["workspace_id"], principal["user_id"], "SCAN_JOB_CANCELLED", job.get("run_id"), {"job_id": job_id})
    return {"job_id": job_id, "status": cancelled["status"] if cancelled else "CANCELLED"}


@app.get("/api/workspace/settings")
def workspace_settings(request: Request) -> dict:
    principal = _principal(request)
    return get_workspace_settings(principal["workspace_id"])


@app.patch("/api/workspace/settings")
def save_workspace_settings(request: Request, payload: WorkspaceSettingsRequest) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    settings = update_workspace_settings(principal["workspace_id"], payload.retention_days)
    record_audit_event(principal["workspace_id"], principal["user_id"], "WORKSPACE_SETTINGS_UPDATED", None, {"retention_days": payload.retention_days})
    return settings


@app.get("/api/workspace/usage")
def get_workspace_usage(request: Request) -> dict:
    principal = _principal(request)
    return {"workspace_id": principal["workspace_id"], **workspace_usage(principal["workspace_id"])}


@app.get("/api/workspace/privacy")
def get_workspace_privacy(request: Request) -> dict:
    principal = _principal(request)
    settings = get_workspace_settings(principal["workspace_id"]) or {"retention_days": 365}
    return {
        "workspace_id": principal["workspace_id"],
        "retention_days": settings["retention_days"],
        "uploaded_content_is_data": True,
        "boundary": "BidProof 不提供法律意见 (not legal advice)；上传内容按企业数据处理，权限和保留策略由企业管理员配置。",
        "deletion": "永久删除会移除任务、评论、反馈、作业和上传文件；备份副本需按运维策略单独处理。",
    }


@app.get("/api/notifications")
def get_notifications(request: Request) -> dict:
    principal = _principal(request)
    today = datetime.now(timezone.utc).date()
    notifications: list[dict] = []
    for item in list_workspace_remediations(principal["workspace_id"]):
        if item["status"] in {"DONE", "CANCELLED"} or not item.get("due_date"):
            continue
        try:
            due = datetime.fromisoformat(item["due_date"]).date()
        except ValueError:
            continue
        delta = (due - today).days
        if delta <= 3:
            notifications.append({
                "type": "REMEDIATION_OVERDUE" if delta < 0 else "REMEDIATION_DUE",
                "severity": "danger" if delta < 0 else "warning",
                "run_id": item["run_id"],
                "remediation_id": item["remediation_id"],
                "title": item["title"],
                "message": "已逾期" if delta < 0 else ("今天到期" if delta == 0 else f"{delta} 天后到期"),
            })
    for job in list_scan_jobs(principal["workspace_id"], limit=50):
        if job.get("status") == "FAILED":
            notifications.append({
                "type": "SCAN_JOB_FAILED",
                "severity": "danger",
                "job_id": job["job_id"],
                "run_id": job.get("run_id"),
                "title": "扫描作业失败",
                "message": job.get("progress_message") or job.get("error") or "可在作业页重试",
            })
    return {"workspace_id": principal["workspace_id"], "count": len(notifications), "notifications": notifications[:50]}


def _retention_candidates(workspace_id: str) -> tuple[str, list[str]]:
    settings = get_workspace_settings(workspace_id) or {"retention_days": 365}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(settings["retention_days"]))).isoformat()
    return cutoff, list_expired_archived_run_ids(workspace_id, cutoff)


@app.get("/api/retention/preview")
def retention_preview(request: Request) -> dict:
    principal = _principal(request)
    cutoff, run_ids = _retention_candidates(principal["workspace_id"])
    return {"workspace_id": principal["workspace_id"], "cutoff": cutoff, "count": len(run_ids), "run_ids": run_ids}


@app.post("/api/retention/purge")
def purge_retention(request: Request) -> dict:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    cutoff, run_ids = _retention_candidates(principal["workspace_id"])
    deleted = 0
    for run_id in run_ids:
        run = _require_scoped_run(run_id, principal)
        if delete_run(run_id):
            _remove_tree(Path(run["tender_path"]).parent)
            deleted += 1
    record_audit_event(principal["workspace_id"], principal["user_id"], "RETENTION_PURGE", None, {"cutoff": cutoff, "deleted": deleted})
    return {"cutoff": cutoff, "deleted": deleted, "run_ids": run_ids}


@app.get("/api/runs/{run_id}/requirements")
def list_requirements(
    request: Request,
    run_id: str,
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
) -> dict:
    run = _require_scoped_run(run_id, _principal(request))
    items = run["requirements"]
    if category:
        items = [item for item in items if item.get("category") == category.upper()]
    if status:
        items = [item for item in items if item.get("status") == status.upper()]
    if severity:
        items = [item for item in items if item.get("severity") == severity.upper()]
    return {"run_id": run_id, "count": len(items), "requirements": items}


@app.get("/api/runs/{run_id}/evidence")
def list_run_evidence(request: Request, run_id: str) -> dict:
    run = _require_scoped_run(run_id, _principal(request))
    return {"run_id": run_id, "assets": run.get("evidence_assets", [])}


@app.get("/api/runs/{run_id}/report.html", response_class=HTMLResponse)
def export_report_html(request: Request, run_id: str) -> HTMLResponse:
    run = _require_scoped_run(run_id, _principal(request))
    return HTMLResponse(
        content=_report_html(run),
        headers={"Content-Disposition": f'attachment; filename="bidproof-{run_id[:12]}.html"'},
    )


@app.get("/api/runs/{run_id}/report.csv")
def export_report_csv(request: Request, run_id: str) -> Response:
    run = _require_scoped_run(run_id, _principal(request))
    output = io.StringIO(newline="")
    fields = ["requirement_id", "category", "label", "status", "severity", "title", "tender_locator", "evidence_locators", "evidence_gap", "risk_impact", "next_action"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in run.get("requirements", []):
        writer.writerow({
            "requirement_id": item.get("requirement_id", ""),
            "category": item.get("category", ""),
            "label": item.get("label", ""),
            "status": item.get("status", ""),
            "severity": item.get("severity", ""),
            "title": item.get("title", ""),
            "tender_locator": _locator_label(item.get("source", {})),
            "evidence_locators": "; ".join(f'{entry.get("filename", "")} {_locator_label(entry)}' for entry in item.get("evidence", [])),
            "evidence_gap": _evidence_gap(item),
            "risk_impact": _risk_impact(item),
            "next_action": _next_action(item),
        })
    return Response(
        content=output.getvalue().lstrip("\ufeff"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bidproof-{run_id[:12]}.csv"'},
    )


@app.get("/api/runs/{run_id}/report.pdf")
def export_report_pdf(request: Request, run_id: str) -> Response:
    run = _require_scoped_run(run_id, _principal(request))
    try:
        payload = build_pdf_report(run)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="PDF 报告运行时不可用") from exc
    return Response(content=payload, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="bidproof-{run_id[:12]}.pdf"'})


@app.post("/api/runs/{run_id}/review")
async def review_run(request: Request, run_id: str, payload: ReviewRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    run = _require_scoped_run(run_id, principal)
    requirement = next(
        (item for item in run["requirements"] if item["requirement_id"] == payload.requirement_id),
        None,
    )
    if requirement is None:
        raise HTTPException(status_code=404, detail="要求项不存在")

    old_status = requirement["status"]
    new_status = _resolve_review_status(payload, old_status)
    if new_status == "PASS" and not _has_complete_citation(requirement):
        raise HTTPException(status_code=422, detail="PASS 必须同时具备招标和企业证据页码引用")
    requirement["status"] = new_status
    reviewed_at = utc_now()
    review_item = {
        "requirement_id": payload.requirement_id,
        "decision": payload.decision,
        "old_status": old_status,
        "new_status": new_status,
        "note": payload.note.strip(),
        "reviewed_at": reviewed_at,
    }
    run["review"]["items"].append(review_item)
    run["review"]["updated_at"] = reviewed_at
    run["state"]["review_events"].append(review_item)
    run["state"]["evidence_matrix"] = run["requirements"]
    run["state"] = advance_state(run["state"], "SYNTHESIZE")
    run["status"] = run["state"]["status"]
    run["updated_at"] = reviewed_at
    save_run(run)
    record_audit_event(principal["workspace_id"], principal["user_id"], "REQUIREMENT_REVIEWED", run_id, {"requirement_id": payload.requirement_id, "new_status": new_status})
    return _public_run(run)


@app.post("/api/runs/{run_id}/decision")
def save_decision(request: Request, run_id: str, payload: DecisionRequest) -> dict:
    principal = _principal(request)
    _require_role(principal)
    run = _require_scoped_run(run_id, principal)
    known_ids = {item["requirement_id"] for item in run["requirements"]}
    unknown_ids = sorted(set(payload.unresolved_requirement_ids) - known_ids)
    if unknown_ids:
        raise HTTPException(status_code=400, detail=f"未知要求项: {', '.join(unknown_ids)}")
    now = utc_now()
    decision = {
        "decision": payload.decision,
        "note": payload.note.strip(),
        "unresolved_requirement_ids": payload.unresolved_requirement_ids,
        "recorded_at": now,
    }
    run["decision"] = decision
    run["state"]["decision_record"] = decision
    run["state"]["action_plan"] = [
        {"action": payload.decision, "owner": "user", "created_at": now, "note": payload.note.strip()}
    ]
    run["updated_at"] = now
    save_run(run)
    record_audit_event(principal["workspace_id"], principal["user_id"], "RUN_DECISION_RECORDED", run_id, {"decision": payload.decision, "unresolved_count": len(payload.unresolved_requirement_ids)})
    return _public_run(run)


@app.get("/api/evidence")
def list_evidence(
    request: Request,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    valid_before: str | None = Query(default=None),
) -> dict:
    from .db import list_runs as db_list_runs

    principal = _principal(request)
    assets: list[dict] = []
    for run in db_list_runs():
        if run.get("workspace_id", "local") != principal["workspace_id"]:
            continue
        assets.extend({**asset, "run_id": run["run_id"]} for asset in run.get("evidence_assets", []))
    if category:
        assets = [asset for asset in assets if asset.get("category") == category.upper()]
    if q:
        needle = q.casefold()
        assets = [asset for asset in assets if needle in asset.get("filename", "").casefold()]
    if valid_before:
        assets = [asset for asset in assets if asset.get("valid_until") and asset["valid_until"] <= valid_before]
    return {"count": len(assets), "assets": assets}


@app.delete("/api/runs/{run_id}")
def remove_run(request: Request, run_id: str) -> dict[str, str]:
    principal = _principal(request)
    _require_role(principal, {"OWNER", "ADMIN"})
    run = _require_scoped_run(run_id, principal)
    removed = delete_run(run_id)
    _remove_tree(Path(run["tender_path"]).parent)
    record_audit_event(principal["workspace_id"], principal["user_id"], "RUN_DELETE", run_id)
    return {"run_id": run_id, "deleted": str(removed).lower()}


def _require_run(run_id: str) -> dict:
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return run


def _require_scoped_run(run_id: str, principal: dict[str, str]) -> dict:
    run = _require_run(run_id)
    if run.get("workspace_id", "local") != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return run


def _public_run(run: dict) -> dict:
    return {
        **_public_summary(run),
        "workspace_id": run.get("workspace_id", "local"),
        "owner_id": run.get("owner_id", "local-owner"),
        "parent_run_id": run.get("parent_run_id"),
        "version_number": run.get("version_number", 1),
        "job_id": run.get("job_id"),
        "assignee_id": run.get("assignee_id"),
        "reviewer_id": run.get("reviewer_id"),
        "tags": run.get("tags", []),
        "favorite": bool(run.get("favorite", False)),
        "project_id": run.get("project_id"),
        "tender_sha256": run.get("tender_sha256"),
        "duplicate_run_ids": run.get("duplicate_run_ids", []),
        "tender_filename": run["tender_filename"],
        "evidence_files": [
            {key: item[key] for key in ("asset_id", "filename", "file_type", "sha256", "category", "valid_until", "pages") if key in item}
            for item in run.get("evidence_assets", [])
        ],
        "source_documents": run.get("source_documents", []),
        "evidence_assets": run.get("evidence_assets", []),
        "requirements": run["requirements"],
        "review": run["review"],
        "decision": run.get("decision", {}),
        "archived_at": run.get("archived_at"),
        "scan_quality": _quality_for_run(run),
        "research_state": run["state"],
    }


def _public_summary(run: dict) -> dict:
    requirements = run.get("requirements", [])
    unresolved = [item for item in requirements if item.get("status") in {"UNKNOWN", "NEEDS_REVIEW"}]
    blockers = [
        item for item in requirements
        if item.get("category") in {"FATAL", "QUALIFICATION"}
        and item.get("status") in {"FAIL", "UNKNOWN", "NEEDS_REVIEW"}
    ]
    return {
        "run_id": run["run_id"],
        "workspace_id": run.get("workspace_id", "local"),
        "owner_id": run.get("owner_id", "local-owner"),
        "parent_run_id": run.get("parent_run_id"),
        "version_number": run.get("version_number", 1),
        "job_id": run.get("job_id"),
        "assignee_id": run.get("assignee_id"),
        "reviewer_id": run.get("reviewer_id"),
        "tags": run.get("tags", []),
        "favorite": bool(run.get("favorite", False)),
        "status": run["status"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "tender_filename": run["tender_filename"],
        "requirement_count": len(requirements),
        "unresolved_count": len(unresolved),
        "blocker_count": len(blockers),
        "fatal_risk_count": sum(1 for item in requirements if item.get("category") == "FATAL"),
        "decision": run.get("decision", {}),
        "archived_at": run.get("archived_at"),
        "scan_quality": _quality_for_run(run),
    }


def _resolve_review_status(payload: ReviewRequest, old_status: str) -> str:
    if payload.decision in {"PASS", "FAIL", "UNKNOWN", "NEEDS_REVIEW"}:
        return payload.decision
    if payload.decision == "CONFIRM":
        return payload.new_status or (old_status if old_status in {"PASS", "FAIL"} else "NEEDS_REVIEW")
    if payload.decision == "REJECT":
        return "NEEDS_REVIEW"
    return "UNKNOWN"


def _has_complete_citation(requirement: dict) -> bool:
    source = requirement.get("source", {})
    source_complete = bool(source.get("locator", {}).get("label") and source.get("quote"))
    return source_complete and any(item.get("locator", {}).get("label") and item.get("quote") for item in requirement.get("evidence", []))


def _parse_evidence_metadata(raw: str | None) -> dict[str, EvidenceMetadata]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="evidence_metadata 必须是 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="evidence_metadata 必须是对象")
    result: dict[str, EvidenceMetadata] = {}
    for filename, value in payload.items():
        if not isinstance(filename, str) or not isinstance(value, dict):
            raise HTTPException(status_code=400, detail="evidence_metadata 格式无效")
        result[filename] = EvidenceMetadata(**value)
    return result


def _page_index(pages: list[dict]) -> list[dict]:
    return [
        {
            "page": page.get("page"),
            "locator": page.get("locator", {"kind": "page", "label": f"第 {page.get('page', '?')} 页", "index": page.get("page")}),
            "char_count": page.get("char_count", len(page.get("text", ""))),
            "ocr_required": bool(page.get("ocr_required", False)),
            "low_text_confidence": bool(page.get("low_text_confidence", False)),
            "ocr_status": page.get("ocr_status", "NOT_REQUIRED"),
            "ocr_provider": page.get("ocr_provider"),
            "ocr_confidence": page.get("ocr_confidence"),
            "block_count": len(page.get("blocks", [])),
        }
        for page in pages
    ]


async def _save_upload(upload: UploadFile, target: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with target.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                handle.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"单个文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024) or MAX_UPLOAD_BYTES} MB")
            digest.update(chunk)
            handle.write(chunk)
    return digest.hexdigest()


def _validate_upload_content(path: Path) -> None:
    suffix = path.suffix.lower()
    header = path.read_bytes()[:8]
    if suffix == ".pdf" and not header.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="PDF 文件签名无效")
    if suffix in {".docx", ".xlsx", ".pptx"} and not header.startswith(b"PK"):
        raise HTTPException(status_code=422, detail="Office 文件签名无效")
    if suffix in {".txt", ".md"} and b"\x00" in path.read_bytes()[:4096]:
        raise HTTPException(status_code=422, detail="文本文件包含二进制内容")
    safety_issues = scan_upload_safety(path)
    if safety_issues:
        raise HTTPException(status_code=422, detail=safety_issues[0])


def _safe_filename(filename: str) -> str:
    return Path(filename).name.replace("..", "_")


def _remove_tree(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)


def _requirement_signature(item: dict) -> tuple[str, str]:
    return (str(item.get("category", "")), " ".join(str(item.get("title", "")).split()).casefold())


def _locator_label(item: dict) -> str:
    return str(item.get("locator", {}).get("label") or "定位缺失")


async def _process_scan_job(job_id: str) -> None:
    from contextlib import ExitStack

    job = load_scan_job(job_id)
    if job is None:
        return
    payload = job["payload"]
    if job.get("status") == "CANCELLED" or job.get("cancel_requested"):
        staged_tender = payload.get("tender_path")
        if staged_tender:
            _remove_tree(Path(staged_tender).parent)
        return
    attempts = int(job.get("attempts", 0)) + 1
    progress_total = max(2, len(payload.get("evidence", [])) + 2)
    if not start_scan_job(job_id, attempts=attempts, progress_total=progress_total, progress_message="准备解析文件"):
        return
    update_scan_job(job_id, "RUNNING", attempts=attempts, progress_current=0, progress_total=progress_total, progress_message="准备解析文件")
    headers = {
        "X-Workspace-ID": job["workspace_id"],
        "X-User-ID": payload.get("user_id", "local-owner"),
        "X-User-Role": payload.get("role", "OWNER"),
        "X-BidProof-Job-ID": job_id,
    }
    try:
        with ExitStack() as stack:
            tender_handle = stack.enter_context(Path(payload["tender_path"]).open("rb"))
            tender = UploadFile(filename=payload["tender_filename"], file=tender_handle)
            evidence_uploads = []
            for item in payload.get("evidence", []):
                handle = stack.enter_context(Path(item["path"]).open("rb"))
                evidence_uploads.append(UploadFile(filename=item["filename"], file=handle))
            update_scan_job(job_id, "RUNNING", progress_current=1, progress_total=progress_total, progress_message="解析招标文件与企业证据")
            if (load_scan_job(job_id) or {}).get("status") == "CANCELLED":
                _remove_tree(Path(payload["tender_path"]).parent)
                return
            result = await create_run(
                SimpleNamespace(headers=headers),
                tender,
                evidence_uploads,
                payload.get("company_name", "未填写企业"),
                payload.get("evidence_metadata"),
                payload.get("project_id"),
            )
        link_scan_job(job_id, result["run_id"])
        update_scan_job(job_id, "RUNNING", attempts=attempts, progress_current=max(1, progress_total - 1), progress_total=progress_total, progress_message="保存证据链结果")
        update_scan_job(job_id, "COMPLETED", attempts=attempts, progress_current=progress_total, progress_total=progress_total, progress_message="扫描完成")
        record_audit_event(job["workspace_id"], payload.get("user_id", "local-owner"), "SCAN_JOB_COMPLETED", result["run_id"], {"job_id": job_id, "attempts": attempts})
        _remove_tree(Path(payload["tender_path"]).parent)
    except Exception as exc:
        current_job = load_scan_job(job_id) or {}
        if current_job.get("status") == "CANCELLED" or current_job.get("cancel_requested"):
            return
        update_scan_job(
            job_id,
            "FAILED",
            attempts=attempts,
            error=current_job.get("error") or type(exc).__name__,
            progress_current=0,
            progress_total=progress_total,
            progress_message=current_job.get("progress_message") or "处理失败，可重试",
        )
        record_audit_event(job["workspace_id"], payload.get("user_id", "local-owner"), "SCAN_JOB_FAILED", None, {"job_id": job_id, "attempts": attempts, "error": type(exc).__name__})


def _scan_quality(tender_pages: list[dict], evidence_pages: list[dict]) -> dict:
    pages = [*tender_pages, *evidence_pages]
    return {
        "total_pages": len(pages),
        "text_pages": sum(bool(page.get("has_text")) for page in pages),
        "ocr_required_pages": sum(bool(page.get("ocr_required")) for page in pages),
        "ocr_failed_pages": sum(page.get("ocr_status") == "FAILED" for page in pages),
        "low_text_confidence_pages": sum(bool(page.get("low_text_confidence")) for page in pages),
        "interpretation": "规则初筛结果，必须结合原文定位和人工复核；OCR 抽取成功不等于语义判断准确。",
    }


def _quality_for_run(run: dict) -> dict:
    quality = run.get("state", {}).get("scan_quality", {})
    if quality.get("total_pages") is not None:
        return quality
    total_pages = sum(int(document.get("pages") or 0) for document in run.get("source_documents", []))
    return {
        "total_pages": total_pages,
        "text_pages": total_pages,
        "ocr_required_pages": 0,
        "ocr_failed_pages": 0,
        "low_text_confidence_pages": 0,
        "interpretation": "历史任务未保存逐定位单元的文本质量元数据；结果仍需结合原文定位和人工复核。",
    }


def _evidence_gap(item: dict) -> str:
    if item.get("status") == "PASS" and item.get("evidence"):
        return "已定位企业证据，仍需人工确认原件有效性"
    if item.get("category") in {"QUALIFICATION", "CREDENTIAL", "BOND", "SIGNATURE"}:
        return "未定位到可核验的企业证据"
    return "该项主要依赖招标原文，需人工确认适用条件"


def _risk_impact(item: dict) -> str:
    if item.get("category") == "FATAL":
        return "可能导致废标或资格失效"
    if item.get("category") == "QUALIFICATION":
        return "可能导致资格审查不通过"
    if item.get("category") == "DEADLINE":
        return "错过节点可能导致文件不被接收"
    return "可能影响合规性、评分或材料完整性"


def _next_action(item: dict) -> str:
    if item.get("status") in {"UNKNOWN", "NEEDS_REVIEW"}:
        return "补充证据并由人工复核"
    if item.get("status") == "FAIL":
        return "核对原文并制定风险处置方案"
    return "保留原文定位并确认原件有效"


def _report_html(run: dict) -> str:
    requirements = run.get("requirements", [])
    rows = []
    for item in requirements:
        source = item.get("source", {})
        evidence = item.get("evidence", [])
        evidence_locators = "; ".join(f'{entry.get("filename", "")} · {_locator_label(entry)}' for entry in evidence) or "未定位"
        rows.append(
            "<tr>"
            + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
                item.get("requirement_id", ""), item.get("category", ""), item.get("status", ""), item.get("title", ""),
                _locator_label(source), evidence_locators, _evidence_gap(item), _risk_impact(item), _next_action(item),
            ))
            + "</tr>"
        )
    quality = _quality_for_run(run)
    return f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>招标证据链报告 - {html.escape(run['tender_filename'])}</title>
<style>body{{font:14px/1.6 Arial,'Microsoft YaHei',sans-serif;color:#1f2937;margin:32px}}h1{{font-size:24px;margin:0 0 6px}}h2{{font-size:17px;margin:28px 0 8px}}.meta{{color:#667085;margin-bottom:20px}}.notice{{border:1px solid #fecdca;background:#fff6f5;padding:12px 14px;margin:16px 0}}.quality{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}.quality div{{border:1px solid #e4e7ec;padding:10px}}.quality b{{display:block;font-size:20px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #d0d5dd;padding:8px;vertical-align:top;text-align:left}}th{{background:#f2f4f7}}@media print{{body{{margin:12mm}}.notice{{break-inside:avoid}}}}</style>
<h1>招标证据链报告</h1><div class='meta'>文件：{html.escape(run['tender_filename'])} · 任务：{html.escape(run['run_id'][:12])} · 更新：{html.escape(run['updated_at'])}</div>
<div class='notice'><b>解读边界：</b>本报告是规则初筛和证据索引，不是自动投标结论。没有完整原文定位或存在 OCR 风险的项目必须人工复核。</div>
<h2>扫描质量</h2><div class='quality'><div><b>{quality.get('total_pages', 0)}</b>定位单元</div><div><b>{quality.get('text_pages', 0)}</b>有文本单元</div><div><b>{quality.get('ocr_required_pages', 0)}</b>需 OCR 单元</div><div><b>{quality.get('ocr_failed_pages', 0)}</b>OCR 失败单元</div><div><b>{quality.get('low_text_confidence_pages', 0)}</b>低文本质量单元</div></div>
<h2>逐项核验</h2><table><thead><tr><th>ID</th><th>类别</th><th>状态</th><th>要求与原文摘要</th><th>招标定位</th><th>企业证据定位</th><th>证据缺口</th><th>风险影响</th><th>建议动作</th></tr></thead><tbody>{''.join(rows)}</tbody></table></html>"""
