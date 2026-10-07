from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserRole(StrEnum):
    employee = "employee"
    support_engineer = "support_engineer"
    admin = "admin"


class TicketStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    waiting_on_requester = "waiting_on_requester"
    resolved = "resolved"
    closed = "closed"


class TicketPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class TicketCategory(StrEnum):
    account_access = "account_access"
    hardware = "hardware"
    network = "network"
    software = "software"
    email = "email"
    security = "security"
    other = "other"


class RegisterInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    department: str = Field(min_length=2, max_length=120)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1 or "." not in email.rsplit("@", 1)[1]:
            raise ValueError("Enter a valid email address.")
        return email


class LoginInput(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    role: UserRole


class UserRead(UserSummary):
    email: str
    department: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class TicketInput(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    description: str = Field(min_length=10, max_length=12000)
    category: TicketCategory
    priority: TicketPriority = TicketPriority.normal
    department: str = Field(min_length=2, max_length=120)


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=180)
    description: str | None = Field(default=None, min_length=10, max_length=12000)
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    status: TicketStatus | None = None
    department: str | None = Field(default=None, min_length=2, max_length=120)
    assigned_engineer_id: UUID | None = None
    resolution: str | None = Field(default=None, max_length=12000)

    @model_validator(mode="before")
    @classmethod
    def reject_null_non_nullable_fields(cls, value: object) -> object:
        if isinstance(value, dict):
            nullable = {"assigned_engineer_id", "resolution"}
            invalid = [key for key, field_value in value.items() if field_value is None and key not in nullable]
            if invalid:
                raise ValueError(f"These fields cannot be null: {', '.join(sorted(invalid))}.")
        return value


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    department: str
    requester: UserSummary
    assigned_engineer: UserSummary | None
    resolution: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class TicketPage(BaseModel):
    items: list[TicketRead]
    page: int
    page_size: int
    total: int


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class TicketCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID
    author: UserSummary
    body: str
    created_at: datetime


class CountByLabel(BaseModel):
    label: str
    count: int


class EngineerWorkload(BaseModel):
    engineer: UserSummary
    open_tickets: int


class DashboardSummary(BaseModel):
    open_tickets: int
    resolved_tickets: int
    closed_tickets: int
    urgent_tickets: int
    by_category: list[CountByLabel]
    by_department: list[CountByLabel]
    engineer_workload: list[EngineerWorkload]


class ActivityRead(BaseModel):
    id: UUID
    ticket_id: UUID
    ticket_number: str
    actor: UserSummary
    action: str
    detail: str
    created_at: datetime


class KnowledgeUploadInput(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0, le=15 * 1024 * 1024)


class KnowledgeUploadResponse(BaseModel):
    document_id: UUID
    object_path: str
    upload_url: str


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    chunk_count: int
    error_message: str | None
    created_at: datetime


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


class CitationRead(BaseModel):
    document_id: UUID
    title: str
    filename: str
    excerpt: str
    chunk_index: int
    relevance: float


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[CitationRead]
    needs_human_support: bool


class TicketAttachmentUploadInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0, le=10 * 1024 * 1024)


class TicketAttachmentUploadResponse(BaseModel):
    attachment_id: UUID
    object_path: str
    upload_url: str


class TicketAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    created_at: datetime
    uploaded_by: UserSummary


class TicketAttachmentDownload(BaseModel):
    download_url: str


class AssistantMessageInput(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class AssistantResolveInput(BaseModel):
    solved: bool


class AssistantMessageRead(BaseModel):
    role: str
    content: str
    created_at: str
    kind: str = "message"


class AssistantAnalysisRead(BaseModel):
    problem_summary: str
    issue_type: str
    category: TicketCategory
    department: str
    priority: TicketPriority
    priority_reason: str
    symptoms: list[str]
    timeline: str
    device: str
    operating_system: str
    error_message: str
    affected_users: str
    business_impact: str
    troubleshooting_attempted: list[str]
    likely_area: str
    confidence: float
    escalation_reason: str
    recommended_action: str


class RelatedTicketRead(BaseModel):
    id: UUID
    number: str
    title: str
    status: TicketStatus
    resolution: str | None
    relevance: float


class AssistantSessionRead(BaseModel):
    id: UUID
    status: str
    messages: list[AssistantMessageRead]
    analysis: AssistantAnalysisRead | None
    answer: GroundedAnswer | None
    related_tickets: list[RelatedTicketRead]
    ticket_id: UUID | None
    ticket_number: str | None
    assigned_engineer: UserSummary | None
    created_at: datetime
    updated_at: datetime


class KnowledgeGapRead(BaseModel):
    id: UUID
    session_id: UUID
    ticket_id: UUID | None
    ticket_number: str | None
    query_text: str
    department: str
    category: TicketCategory
    priority: TicketPriority
    reason: str
    status: str
    created_at: datetime


class KnowledgeResolutionDraftRead(BaseModel):
    ticket_id: UUID
    ticket_number: str
    title: str
    filename: str
    content_type: str
    markdown: str
