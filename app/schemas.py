from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


# Single source of truth for the account password policy. Applied wherever a password is set;
# on login it is enforced in the handler so an under-policy value still fails as a 401.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200
PASSWORD_POLICY_MESSAGE = "密码至少 8 位，且须同时包含字母和数字"


def password_meets_policy(password: str) -> bool:
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        return False
    # ASCII letter + ASCII digit — matches the product rule「同时包含数字和字母」.
    has_letter = any(ch.isascii() and ch.isalpha() for ch in password)
    has_digit = any(ch.isascii() and ch.isdigit() for ch in password)
    return has_letter and has_digit


def _enforce_password_policy(value: str) -> str:
    if not password_meets_policy(value):
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    return value


# Use for any field that *sets* a password. Login stays permissive (see LoginRequest).
AccountPassword = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH),
    AfterValidator(_enforce_password_policy),
]

ReviewDecision = Literal[
    "PASS",
    "FAIL",
    "UNKNOWN",
    "NEEDS_REVIEW",
    "CONFIRM",
    "REJECT",
    "REQUEST_EVIDENCE",
]


class ReviewRequest(BaseModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    decision: ReviewDecision
    note: str = Field(default="", max_length=2000)
    new_status: Literal["PASS", "FAIL", "UNKNOWN", "NEEDS_REVIEW"] | None = None
    revision: int | None = Field(default=None, ge=1)


class DecisionRequest(BaseModel):
    decision: Literal["CONTINUE", "HOLD", "STOP"]
    note: str = Field(default="", max_length=4000)
    unresolved_requirement_ids: list[str] = Field(default_factory=list, max_length=500)


class BulkRunRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal["ARCHIVE", "RESTORE", "DELETE"]


class BulkReportRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=100)
    format: Literal["pdf"] = "pdf"


class EvidenceMetadata(BaseModel):
    category: str = Field(default="UNCLASSIFIED", max_length=80)
    valid_until: str | None = Field(default=None, max_length=40)


class RunMetadataRequest(BaseModel):
    assignee_id: str | None = Field(default=None, max_length=120)
    reviewer_id: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    favorite: bool = False


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class RemediationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    requirement_id: str | None = Field(default=None, max_length=100)
    owner_id: str | None = Field(default=None, max_length=120)
    due_date: str | None = Field(default=None, max_length=40)
    note: str = Field(default="", max_length=2000)


class RemediationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    owner_id: str | None = Field(default=None, max_length=120)
    due_date: str | None = Field(default=None, max_length=40)
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"] | None = None
    note: str | None = Field(default=None, max_length=2000)


class AccuracyFeedbackRequest(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    predicted: Literal["DETECTED", "MISSED"]
    actual: Literal["RELEVANT", "NOT_RELEVANT"]
    requirement_id: str | None = Field(default=None, max_length=100)
    locator_label: str | None = Field(default=None, max_length=200)
    quote: str | None = Field(default=None, max_length=2000)
    note: str = Field(default="", max_length=2000)
    dataset_scope: Literal["TEST", "PILOT", "ENTERPRISE"] = "PILOT"
    review_complete: bool = False


class AuthBootstrapRequest(BaseModel):
    workspace_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=3, max_length=80)
    password: AccountPassword
    bootstrap_token: str | None = Field(default=None, max_length=500)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    # Deliberately permissive: a credential that fails policy must fail as a normal 401 in the
    # login handler, not as a 422, so response codes cannot be used to probe password policy.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    workspace_id: str | None = Field(default=None, max_length=64)


class TrialJoinRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: AccountPassword
    join_code: str = Field(min_length=4, max_length=120)


class PersonalRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: AccountPassword
    display_name: str | None = Field(default=None, max_length=120)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: AccountPassword


class InvitationCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    role: Literal["ADMIN", "REVIEWER", "VIEWER"]


class AuthActionCompleteRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    password: AccountPassword


class MemberCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: AccountPassword
    role: Literal["ADMIN", "REVIEWER", "VIEWER"]


class MemberUpdateRequest(BaseModel):
    role: Literal["ADMIN", "REVIEWER", "VIEWER"] | None = None
    active: bool | None = None


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    mfa_token: str | None = Field(default=None, max_length=200)


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    expires_days: int | None = Field(default=None, ge=1, le=3650)
    permissions: list[str] = Field(default_factory=list, max_length=40)


class WorkspaceSettingsRequest(BaseModel):
    retention_days: int = Field(ge=1, le=3650)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None
